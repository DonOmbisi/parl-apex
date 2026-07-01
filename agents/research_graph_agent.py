import json
import logging
import os

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.groq import GroqModel

logger = logging.getLogger("parl_apex.agents.research_graph")

if not os.getenv("GROQ_API_KEY"):
    os.environ["GROQ_API_KEY"] = "mock-groq-api-key-placeholder"


class ResearchGraphEntity(BaseModel):
    name: str = Field(description="Entity name exactly as supported by the research.")
    type: str = Field(
        description="Entity type, such as Organization, Person, Funder, Partner, Competitor, Priority, or FinancialFigure."
    )


class ResearchGraphRelationship(BaseModel):
    source_name: str
    source_type: str
    target_name: str
    target_type: str
    relationship_type: str = Field(
        description="Relationship type, such as HAS_LEADER, FUNDED_BY, PARTNERS_WITH, COMPETES_WITH, HAS_PRIORITY, or HAS_FINANCIAL_FIGURE."
    )
    evidence: str = Field(
        description="Short evidence note from the research report supporting this relationship."
    )


class ResearchGraphExtraction(BaseModel):
    entities: list[ResearchGraphEntity] = Field(default_factory=list)
    relationships: list[ResearchGraphRelationship] = Field(default_factory=list)
    summary: str = Field(description="Brief summary of what was extracted.")


RESEARCH_GRAPH_SYSTEM_PROMPT = """You are PARL's external research graph extraction agent.
You convert completed Consult Ralph research into graph-ready entities and relationships.

Strict rules:
1. Extract only facts present in the supplied research. Do not invent leaders, funders, partners, competitors, priorities, or financial figures.
2. Preserve public-research uncertainty. If a fact is public but not internally confirmed, keep the evidence wording cautious.
3. Use concise entity names and stable entity types.
4. Return relationships that can be written into a graph with Entity nodes and RELATES_TO edges.
5. Prefer these relationship types where appropriate: HAS_LEADER, FUNDED_BY, PARTNERS_WITH, COMPETES_WITH, HAS_PRIORITY, HAS_FINANCIAL_FIGURE.
6. Evidence must cite the public research source text or field that supports the relationship.
"""

try:
    model = GroqModel("llama-3.3-70b-versatile")
    research_graph_agent = Agent(
        model,
        output_type=ResearchGraphExtraction,
        system_prompt=RESEARCH_GRAPH_SYSTEM_PROMPT,
    )
    logger.info("Initialized Research Graph Agent with Groq llama-3.3-70b-versatile.")
except Exception as e:
    logger.error("Failed to initialize Groq model for Research Graph Agent: %s", e)
    research_graph_agent = Agent(
        "groq:llama-3.3-70b-versatile",
        output_type=ResearchGraphExtraction,
        system_prompt=RESEARCH_GRAPH_SYSTEM_PROMPT,
    )


def build_research_graph_prompt(
    client_name: str,
    report: str,
    named_entities: dict[str, list[str]],
    strategic_priorities: list[str],
    financial_figures: list[str],
) -> str:
    payload = {
        "client_name": client_name,
        "completed_consult_ralph_report": report,
        "named_entities": named_entities,
        "strategic_priorities": strategic_priorities,
        "financial_figures": financial_figures,
    }
    return (
        "Convert this completed Consult Ralph external research package into graph-ready "
        "entities and relationships for the client knowledge graph.\n\n"
        f"{json.dumps(payload, ensure_ascii=True, indent=2)}"
    )


def tag_external_research_evidence(evidence: str, source_label: str) -> str:
    clean_evidence = evidence.strip() if evidence else "Consult Ralph research report"
    return (
        f"SOURCE=EXTERNAL_RESEARCH | ORIGIN={source_label} | "
        f"INTERNAL_CONFIRMATION=false | {clean_evidence}"
    )
