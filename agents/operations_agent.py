import json
import logging
import os
from collections import defaultdict
from datetime import datetime, time, timezone

import pandas as pd
import pm4py
from pydantic_ai import Agent
from pydantic_ai.models.groq import GroqModel

from agents.operations_schemas import (
    EventLogRecord,
    OperationsAgentOutput,
    ProcessBottleneckMetric,
)
from connectors.erpnext_connector import ERPNextConnectorResult

logger = logging.getLogger("parl_apex.agents.operations")

if not os.getenv("GROQ_API_KEY"):
    os.environ["GROQ_API_KEY"] = "mock-groq-api-key-placeholder"

OPERATIONS_SYSTEM_PROMPT = """You are PARL's Operations Agent.
PM4Py has already performed the process mining analysis. Your only job is to translate the quantitative bottleneck metrics into plain-language findings for a non-technical executive or operations lead.

Strict rules:
1. Do not invent bottlenecks, steps, case counts, costs, or delays not present in the PM4Py metrics.
2. Each finding must name the specific bottleneck step and include the average and worst-case delay observed.
3. Include estimated delay cost only when a cost figure is present in the metrics.
4. Recommend a practical intervention that directly addresses the measured bottleneck.
5. If event-log data is sparse or incomplete, say so in missing_or_uncertain_data.
"""

try:
    model = GroqModel("llama-3.3-70b-versatile")
    operations_agent = Agent(
        model,
        output_type=OperationsAgentOutput,
        system_prompt=OPERATIONS_SYSTEM_PROMPT,
    )
    logger.info("Initialized Operations Agent with Groq llama-3.3-70b-versatile.")
except Exception as e:
    logger.error(f"Failed to initialize Groq model for Operations Agent: {e}")
    operations_agent = Agent(
        "groq:llama-3.3-70b-versatile",
        output_type=OperationsAgentOutput,
        system_prompt=OPERATIONS_SYSTEM_PROMPT,
    )


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _parse_date_as_utc(value: str) -> datetime:
    return datetime.combine(datetime.fromisoformat(value).date(), time.min, tzinfo=timezone.utc)


def erpnext_result_to_event_log(result: ERPNextConnectorResult) -> list[EventLogRecord]:
    events: list[EventLogRecord] = []
    fetched_at = _parse_datetime(result.fetched_at)

    for invoice in result.invoices:
        if invoice.posting_date:
            events.append(
                EventLogRecord(
                    case_id=invoice.name,
                    activity="invoice_posted",
                    timestamp=_parse_date_as_utc(invoice.posting_date),
                    cost=invoice.outstanding_amount,
                    currency=invoice.currency,
                    evidence=f"ERPNext: {invoice.name} posting_date={invoice.posting_date}",
                )
            )

        if invoice.due_date:
            events.append(
                EventLogRecord(
                    case_id=invoice.name,
                    activity="payment_due",
                    timestamp=_parse_date_as_utc(invoice.due_date),
                    cost=invoice.outstanding_amount,
                    currency=invoice.currency,
                    evidence=f"ERPNext: {invoice.name} due_date={invoice.due_date}",
                )
            )

        status_activity = (
            "still_overdue_at_status_check"
            if invoice.status.upper() == "OVERDUE"
            else "still_unpaid_at_status_check"
        )
        events.append(
            EventLogRecord(
                case_id=invoice.name,
                activity=status_activity,
                timestamp=fetched_at,
                cost=invoice.outstanding_amount,
                currency=invoice.currency,
                evidence=(
                    f"ERPNext: {invoice.name} status={invoice.status} "
                    f"outstanding={invoice.currency} {invoice.outstanding_amount:.2f}"
                ),
            )
        )

    return sorted(events, key=lambda event: (event.case_id, event.timestamp))


def analyze_event_log_with_pm4py(events: list[EventLogRecord]) -> list[ProcessBottleneckMetric]:
    if len(events) < 2:
        return []

    rows = [
        {
            "case_id": event.case_id,
            "activity": event.activity,
            "timestamp": event.timestamp,
            "cost": event.cost,
            "currency": event.currency,
            "evidence": event.evidence,
        }
        for event in events
    ]
    dataframe = pd.DataFrame(rows)
    dataframe = pm4py.format_dataframe(
        dataframe,
        case_id="case_id",
        activity_key="activity",
        timestamp_key="timestamp",
    )

    performance_dfg, _, _ = pm4py.discover_performance_dfg(dataframe)
    frequency_dfg, _, _ = pm4py.discover_dfg(dataframe)

    transition_observations: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for _, group in dataframe.sort_values("time:timestamp").groupby("case:concept:name"):
        ordered = list(group.to_dict("records"))
        for current, following in zip(ordered, ordered[1:]):
            transition = (current["concept:name"], following["concept:name"])
            delay_hours = (
                following["time:timestamp"] - current["time:timestamp"]
            ).total_seconds() / 3600
            transition_observations[transition].append(
                {
                    "delay_hours": delay_hours,
                    "cost": following.get("cost"),
                    "currency": following.get("currency"),
                    "evidence": following.get("evidence"),
                }
            )

    bottlenecks: list[ProcessBottleneckMetric] = []
    for transition, average_delay_seconds in performance_dfg.items():
        observations = transition_observations.get(transition, [])
        if not observations:
            continue

        costs = [obs["cost"] for obs in observations if obs.get("cost") is not None]
        currencies = [obs["currency"] for obs in observations if obs.get("currency")]
        evidence = [obs["evidence"] for obs in observations if obs.get("evidence")]

        bottlenecks.append(
            ProcessBottleneckMetric(
                source_activity=transition[0],
                target_activity=transition[1],
                average_delay_hours=round(float(average_delay_seconds) / 3600, 2),
                worst_case_delay_hours=round(
                    max(obs["delay_hours"] for obs in observations),
                    2,
                ),
                case_count=int(frequency_dfg.get(transition, len(observations))),
                estimated_delay_cost=round(float(sum(costs)), 2) if costs else None,
                currency=currencies[0] if currencies else None,
                evidence=evidence[:5],
            )
        )

    return sorted(
        bottlenecks,
        key=lambda item: (item.average_delay_hours, item.worst_case_delay_hours, item.case_count),
        reverse=True,
    )


def build_operations_prompt(client_name: str, bottlenecks: list[ProcessBottleneckMetric]) -> str:
    context = json.dumps(
        [bottleneck.model_dump() for bottleneck in bottlenecks],
        ensure_ascii=True,
        indent=2,
    )
    return (
        f"Translate these PM4Py process-mining bottleneck metrics for {client_name} "
        "into typed operations findings. Do not add any bottlenecks or costs beyond these metrics.\n\n"
        f"PM4Py bottleneck metrics:\n{context}"
    )


async def run_operations_agent_for_events(
    client_name: str,
    events: list[EventLogRecord],
) -> OperationsAgentOutput:
    bottlenecks = analyze_event_log_with_pm4py(events)
    prompt = build_operations_prompt(client_name, bottlenecks)
    result = await operations_agent.run(prompt)
    return result.output


async def run_operations_agent_for_erpnext_result(
    result: ERPNextConnectorResult,
) -> OperationsAgentOutput:
    events = erpnext_result_to_event_log(result)
    return await run_operations_agent_for_events(result.client_name, events)


def write_operations_output_to_graph(graph, client_name: str, output: OperationsAgentOutput) -> int:
    written = 0
    timestamp = datetime.now(timezone.utc).isoformat()

    for index, finding in enumerate(output.findings, start=1):
        finding_name = f"Operations Finding - {client_name} - {timestamp} - {index}"
        evidence = (
            f"OperationsAgent {timestamp} | severity={finding.severity} | "
            f"bottleneck={finding.bottleneck_step} | average_delay={finding.average_delay_observed} | "
            f"worst_case_delay={finding.worst_case_delay_observed} | "
            f"estimated_cost={finding.estimated_cost_of_delay} | "
            f"recommended_intervention={finding.recommended_intervention} | "
            f"pm4py_evidence={json.dumps(finding.evidence, ensure_ascii=True)}"
        )
        graph.add_relationship(
            source_name=client_name,
            source_type="Organization",
            target_name=finding_name,
            target_type="OperationsFinding",
            relationship_type="HAS_OPERATIONS_FINDING",
            evidence=evidence,
        )
        written += 1

    summary_name = f"Operations Summary - {client_name} - {timestamp}"
    graph.add_relationship(
        source_name=client_name,
        source_type="Organization",
        target_name=summary_name,
        target_type="OperationsSummary",
        relationship_type="HAS_OPERATIONS_SUMMARY",
        evidence=(
            f"OperationsAgent {timestamp} | summary={output.process_summary} | "
            f"missing_or_uncertain_data={output.missing_or_uncertain_data}"
        ),
    )
    written += 1

    return written
