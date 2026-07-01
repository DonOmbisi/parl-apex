import json
import logging
import os
from datetime import datetime, timezone

from pydantic_ai import Agent
from pydantic_ai.models.groq import GroqModel

from agents.finance_schemas import FinanceAgentOutput

logger = logging.getLogger("parl_apex.agents.finance")

if not os.getenv("GROQ_API_KEY"):
    os.environ["GROQ_API_KEY"] = "mock-groq-api-key-placeholder"

FINANCE_SYSTEM_PROMPT = """You are PARL's Finance Agent for East African organizations.
You read recent knowledge graph entries and produce finance findings only when they are directly supported by the graph evidence.

You must assess cash risk, budget variance, overdue receivables and payables, and donor or funding compliance risk where relevant.

Strict rules:
1. Never invent a finding, metric, funder, payment, invoice, payroll risk, budget variance, or compliance issue not directly supported by the graph entries provided.
2. Every finding must cite the graph evidence that supports it.
3. If evidence is thin or missing, say so in missing_or_uncertain_data instead of filling gaps.
4. Understand East African organizational finance context, including donor grant cycles, multi-currency exposure, and cash gaps appearing just before payroll.
5. Any payroll-related risk appearing in the graph must be treated as the highest severity and most time-sensitive finding.
6. Keep recommendations practical and written for a finance lead or CEO.
"""

try:
    model = GroqModel("llama-3.3-70b-versatile")
    finance_agent = Agent(
        model,
        output_type=FinanceAgentOutput,
        system_prompt=FINANCE_SYSTEM_PROMPT,
    )
    logger.info("Initialized Finance Agent with Groq llama-3.3-70b-versatile.")
except Exception as e:
    logger.error(f"Failed to initialize Groq model for Finance Agent: {e}")
    finance_agent = Agent(
        "groq:llama-3.3-70b-versatile",
        output_type=FinanceAgentOutput,
        system_prompt=FINANCE_SYSTEM_PROMPT,
    )


def build_finance_prompt(client_name: str, recent_entries: list[dict]) -> str:
    graph_context = json.dumps(recent_entries, default=str, ensure_ascii=True, indent=2)
    return (
        f"Analyze recent finance-relevant knowledge graph entries for {client_name}.\n\n"
        "Return only findings supported by the graph entries below. If the graph has no "
        "finance evidence for a category, mention that uncertainty instead of inventing it.\n\n"
        f"Knowledge graph entries:\n{graph_context}"
    )


async def run_finance_agent_for_client(
    client_name: str,
    graph_path: str,
    recent_days: int = 7,
) -> FinanceAgentOutput:
    from graph import get_client_graph

    graph = get_client_graph(client_name, graph_path)
    recent_entries = graph.get_recent_elements(days=recent_days)
    prompt = build_finance_prompt(client_name, recent_entries)
    result = await finance_agent.run(prompt)
    return result.output


def write_finance_output_to_graph(graph, client_name: str, output: FinanceAgentOutput) -> int:
    written = 0
    timestamp = datetime.now(timezone.utc).isoformat()
    assessment_name = f"Finance Assessment - {client_name} - {timestamp}"
    assessment_evidence = (
        f"FinanceAgent {timestamp} | health={output.overall_financial_health} | "
        f"reasoning={output.health_reasoning}"
    )

    graph.add_relationship(
        source_name=client_name,
        source_type="Organization",
        target_name=assessment_name,
        target_type="FinanceAssessment",
        relationship_type="HAS_FINANCE_ASSESSMENT",
        evidence=assessment_evidence,
    )
    written += 1

    for index, finding in enumerate(output.findings, start=1):
        finding_name = f"Finance Finding - {client_name} - {timestamp} - {index}"
        evidence = (
            f"FinanceAgent {timestamp} | severity={finding.severity} | "
            f"description={finding.description} | graph_evidence={json.dumps(finding.evidence, ensure_ascii=True)} | "
            f"recommended_action={finding.recommended_action} | time_sensitivity={finding.time_sensitivity}"
        )
        graph.add_relationship(
            source_name=client_name,
            source_type="Organization",
            target_name=finding_name,
            target_type="FinanceFinding",
            relationship_type="HAS_FINANCE_FINDING",
            evidence=evidence,
        )
        written += 1

    priority_name = f"Finance Top Priority - {client_name} - {timestamp}"
    graph.add_relationship(
        source_name=client_name,
        source_type="Organization",
        target_name=priority_name,
        target_type="FinanceTopPriority",
        relationship_type="HAS_FINANCE_TOP_PRIORITY",
        evidence=f"FinanceAgent {timestamp} | top_priority={output.top_priority}",
    )
    written += 1

    return written
