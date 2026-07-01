import json
import logging
import os
from datetime import datetime, timezone

from pydantic_ai import Agent
from pydantic_ai.models.groq import GroqModel

from synthesis.correlation_schemas import CorrelationEngineOutput

logger = logging.getLogger("parl_apex.synthesis.correlation")

if not os.getenv("GROQ_API_KEY"):
    os.environ["GROQ_API_KEY"] = "mock-groq-api-key-placeholder"

CORRELATION_SYSTEM_PROMPT = """You are PARL's Correlation Engine.
Your job is to reason across recent specialist-agent findings and knowledge graph entries for one client.

Strict rules:
1. Only surface a correlation if it draws on evidence from at least two different sources, such as FinanceAgent plus OperationsAgent, or two different connectors/departments.
2. A finding visible from one source alone is not a correlation. Leave it to that source's specialist agent.
3. Every correlation must include specific evidence from each contributing source.
4. Do not invent facts, departments, timelines, costs, connectors, or root causes not supported by the provided evidence.
5. Rank correlations by urgency, not by novelty or how interesting they are.
6. Write plainly for an executive reader who needs to act across departments.
"""

SPECIALIST_TARGET_TYPES = {
    "FinanceAssessment": "FinanceAgent",
    "FinanceFinding": "FinanceAgent",
    "FinanceTopPriority": "FinanceAgent",
    "OperationsFinding": "OperationsAgent",
    "OperationsSummary": "OperationsAgent",
}

try:
    model = GroqModel("llama-3.3-70b-versatile")
    correlation_agent = Agent(
        model,
        output_type=CorrelationEngineOutput,
        system_prompt=CORRELATION_SYSTEM_PROMPT,
    )
    logger.info("Initialized Correlation Engine with Groq llama-3.3-70b-versatile.")
except Exception as e:
    logger.error(f"Failed to initialize Groq model for Correlation Engine: {e}")
    correlation_agent = Agent(
        "groq:llama-3.3-70b-versatile",
        output_type=CorrelationEngineOutput,
        system_prompt=CORRELATION_SYSTEM_PROMPT,
    )


def extract_specialist_outputs(recent_entries: list[dict]) -> list[dict]:
    outputs = []
    for entry in recent_entries:
        target_type = entry.get("target_type")
        source = SPECIALIST_TARGET_TYPES.get(target_type)
        if not source:
            continue

        outputs.append(
            {
                "source": source,
                "target_name": entry.get("target_name"),
                "target_type": target_type,
                "relationship_type": entry.get("relationship_type"),
                "evidence": entry.get("evidence"),
                "timestamp": entry.get("timestamp"),
            }
        )
    return outputs


def has_at_least_two_sources(specialist_outputs: list[dict]) -> bool:
    return len({output["source"] for output in specialist_outputs}) >= 2


def build_correlation_prompt(
    client_name: str,
    specialist_outputs: list[dict],
    graph_entries: list[dict],
) -> str:
    payload = {
        "client_name": client_name,
        "specialist_outputs": specialist_outputs,
        "recent_graph_entries": graph_entries,
    }
    context = json.dumps(payload, default=str, ensure_ascii=True, indent=2)
    return (
        f"Find urgent cross-source correlations for {client_name}.\n\n"
        "Only return correlations that use evidence from at least two different sources. "
        "Rank by urgency. If there are not two sources, return no correlations and explain "
        "the insufficiency.\n\n"
        f"Evidence package:\n{context}"
    )


async def run_correlation_engine_for_client(
    client_name: str,
    graph_path: str,
    recent_days: int = 7,
) -> CorrelationEngineOutput:
    from graph import get_client_graph

    graph = get_client_graph(client_name, graph_path)
    recent_entries = graph.get_recent_elements(days=recent_days)
    specialist_outputs = extract_specialist_outputs(recent_entries)
    prompt = build_correlation_prompt(client_name, specialist_outputs, recent_entries)
    result = await correlation_agent.run(prompt)
    return result.output


def write_correlation_output_to_graph(
    graph,
    client_name: str,
    output: CorrelationEngineOutput,
) -> int:
    written = 0
    timestamp = datetime.now(timezone.utc).isoformat()

    for correlation in output.correlations:
        if len(set(correlation.contributing_sources)) < 2:
            logger.warning(
                "Skipping correlation with fewer than two contributing sources: %s",
                correlation.visible_symptom,
            )
            continue

        correlation_name = (
            f"Correlation - {client_name} - rank {correlation.urgency_rank} - {timestamp}"
        )
        evidence = (
            f"CorrelationEngine {timestamp} | sources={json.dumps(correlation.contributing_sources, ensure_ascii=True)} | "
            f"visible_symptom={correlation.visible_symptom} | "
            f"hidden_root_cause={correlation.hidden_root_cause} | "
            f"time_to_serious_problem={correlation.time_to_serious_problem} | "
            f"recommended_intervention={correlation.recommended_intervention} | "
            f"evidence_by_source={json.dumps(correlation.evidence_by_source, ensure_ascii=True)}"
        )
        graph.add_relationship(
            source_name=client_name,
            source_type="Organization",
            target_name=correlation_name,
            target_type="CorrelationFinding",
            relationship_type="HAS_CORRELATION",
            evidence=evidence,
        )
        written += 1

    summary_name = f"Correlation Summary - {client_name} - {timestamp}"
    graph.add_relationship(
        source_name=client_name,
        source_type="Organization",
        target_name=summary_name,
        target_type="CorrelationSummary",
        relationship_type="HAS_CORRELATION_SUMMARY",
        evidence=(
            f"CorrelationEngine {timestamp} | summary={output.synthesis_summary} | "
            f"insufficient_evidence_note={output.insufficient_evidence_note}"
        ),
    )
    written += 1

    return written
