import json
import logging
import os
import re
from datetime import datetime, timezone

from pydantic_ai import Agent
from pydantic_ai.models.groq import GroqModel

from agents.query_schemas import QueryAgentOutput, QueryEvidence

logger = logging.getLogger("parl_apex.agents.query")

if not os.getenv("GROQ_API_KEY"):
    os.environ["GROQ_API_KEY"] = "mock-groq-api-key-placeholder"

QUERY_SYSTEM_PROMPT = """You are PARL's Query Agent.
You answer free-form questions about one client using only the supplied Kuzu knowledge graph entries.

Strict rules:
1. Answer directly and plainly.
2. Cite the specific graph entries that support your answer in supporting_evidence.
3. Do not invent facts, systems, funders, financial risks, processes, dates, or recommendations not present in the graph entries.
4. If the graph does not contain enough information to answer confidently, say so directly and set confidence to "insufficient".
5. If evidence partially answers the question, answer the supported part and list what is missing.
"""

try:
    model = GroqModel("llama-3.3-70b-versatile")
    query_agent = Agent(
        model,
        output_type=QueryAgentOutput,
        system_prompt=QUERY_SYSTEM_PROMPT,
    )
    logger.info("Initialized Query Agent with Groq llama-3.3-70b-versatile.")
except Exception as e:
    logger.error(f"Failed to initialize Groq model for Query Agent: {e}")
    query_agent = Agent(
        "groq:llama-3.3-70b-versatile",
        output_type=QueryAgentOutput,
        system_prompt=QUERY_SYSTEM_PROMPT,
    )


STOPWORDS = {
    "about",
    "after",
    "again",
    "against",
    "client",
    "could",
    "does",
    "from",
    "have",
    "into",
    "show",
    "that",
    "their",
    "there",
    "these",
    "thing",
    "this",
    "what",
    "when",
    "where",
    "which",
    "with",
    "would",
}


def _question_terms(question: str) -> set[str]:
    words = re.findall(r"[A-Za-z0-9_]{3,}", question.lower())
    terms = {word for word in words if word not in STOPWORDS}
    singulars = {word[:-1] for word in terms if word.endswith("s") and len(word) > 3}
    return terms | singulars


def _entry_text(entry: dict) -> str:
    return " ".join(
        str(entry.get(key, ""))
        for key in (
            "source_name",
            "source_type",
            "relationship_type",
            "target_name",
            "target_type",
            "evidence",
        )
    ).lower()


def rank_relevant_entries(question: str, entries: list[dict], limit: int = 12) -> list[dict]:
    terms = _question_terms(question)
    if not terms:
        return entries[:limit]

    scored = []
    for entry in entries:
        text = _entry_text(entry)
        score = sum(1 for term in terms if term in text)
        if score:
            scored.append((score, entry))

    if not scored:
        return []

    scored.sort(key=lambda item: item[0], reverse=True)
    return [entry for _, entry in scored[:limit]]


def build_query_prompt(
    client_identifier: str,
    question: str,
    relevant_entries: list[dict],
) -> str:
    context = json.dumps(relevant_entries, default=str, ensure_ascii=True, indent=2)
    return (
        f"Client identifier: {client_identifier}\n"
        f"Question: {question}\n\n"
        "Use only these Kuzu graph entries as evidence. If they do not answer the "
        "question, say the graph does not contain enough information.\n\n"
        f"Relevant graph entries:\n{context}"
    )


def insufficient_answer(
    client_identifier: str,
    question: str,
    missing_information: str,
) -> QueryAgentOutput:
    return QueryAgentOutput(
        client_identifier=client_identifier,
        question=question,
        answer="The knowledge graph does not contain enough information to answer that confidently.",
        confidence="insufficient",
        supporting_evidence=[],
        missing_information=missing_information,
    )


async def run_query_agent_for_client(
    client_identifier: str,
    graph_path: str,
    question: str,
    recent_days: int = 90,
) -> QueryAgentOutput:
    from graph import get_client_graph

    graph = get_client_graph(client_identifier, graph_path)
    recent_entries = graph.get_recent_elements(days=recent_days)
    relevant_entries = rank_relevant_entries(question, recent_entries)

    if not relevant_entries:
        return insufficient_answer(
            client_identifier=client_identifier,
            question=question,
            missing_information=(
                "No recent graph relationships matched the question terms. "
                "More client data may need to be seeded or synced first."
            ),
        )

    prompt = build_query_prompt(client_identifier, question, relevant_entries)
    result = await query_agent.run(prompt)
    return result.output


def evidence_from_entries(entries: list[dict]) -> list[QueryEvidence]:
    return [
        QueryEvidence(
            source_name=str(entry.get("source_name", "")),
            source_type=str(entry.get("source_type", "")),
            relationship_type=str(entry.get("relationship_type", "")),
            target_name=str(entry.get("target_name", "")),
            target_type=str(entry.get("target_type", "")),
            evidence=str(entry.get("evidence", "")),
            timestamp=str(entry.get("timestamp")) if entry.get("timestamp") is not None else None,
        )
        for entry in entries
    ]


def write_query_audit_to_graph(
    graph,
    client_identifier: str,
    question: str,
    output: QueryAgentOutput,
) -> int:
    timestamp = datetime.now(timezone.utc).isoformat()
    graph.add_relationship(
        source_name=client_identifier,
        source_type="Organization",
        target_name=f"Query Answer - {client_identifier} - {timestamp}",
        target_type="QueryAnswer",
        relationship_type="HAS_QUERY_ANSWER",
        evidence=(
            f"QueryAgent {timestamp} | question={question} | "
            f"confidence={output.confidence} | answer={output.answer} | "
            f"supporting_evidence={json.dumps([item.model_dump() for item in output.supporting_evidence], ensure_ascii=True)} | "
            f"missing_information={output.missing_information}"
        ),
    )
    return 1
