import logging
import os

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agents.research_graph_agent import (
    ResearchGraphExtraction,
    build_research_graph_prompt,
    research_graph_agent,
    tag_external_research_evidence,
)
from app.routers.query import resolve_client_graph
from graph import get_client_graph

logger = logging.getLogger("parl_apex.routers.research")

router = APIRouter(prefix="/research", tags=["research"])


class ResearchIngestRequest(BaseModel):
    client_identifier: str = Field(
        description="Client slug or organization name already configured in clients/*/config.yaml."
    )
    report: str = Field(description="Completed Consult Ralph research report text.")
    named_entities: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Named entities surfaced by Consult Ralph, grouped by category such as leadership, funders, partners, and competitors.",
    )
    strategic_priorities: list[str] = Field(default_factory=list)
    financial_figures: list[str] = Field(default_factory=list)
    source_label: str = Field(default="Consult Ralph external research")


class ResearchIngestResponse(BaseModel):
    client_identifier: str
    entities_written: int
    relationships_written: int
    status: str
    summary: str
    espocrm_status: str | None = None


async def mirror_research_to_espocrm(
    client_name: str,
    sector: str | None,
    summary: str,
    source_label: str,
) -> str:
    base_url = os.getenv("ESPOCRM_BASE_URL", "").rstrip("/")
    api_key = os.getenv("ESPOCRM_API_KEY") or os.getenv("ESPOCRM_TENDER_API_KEY")
    if not base_url or not api_key:
        return "skipped: ESPOCRM_BASE_URL or ESPOCRM_API_KEY not configured"

    headers = {"X-Api-Key": api_key, "Content-Type": "application/json"}
    account_url = f"{base_url}/api/v1/Account"
    where = [{"type": "equals", "attribute": "name", "value": client_name}]
    description = (
        f"Consult Ralph promotion\n"
        f"Source: {source_label}\n"
        f"Sector: {sector or 'Unknown'}\n"
        f"Summary: {summary}"
    )

    try:
        async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
            lookup = await client.get(account_url, params={"where": where, "maxSize": 1})
            lookup.raise_for_status()
            data = lookup.json()
            records = data.get("list") or data.get("records") or []

            payload = {
                "name": client_name,
                "industry": sector,
                "description": description,
            }
            payload = {key: value for key, value in payload.items() if value is not None}

            if records:
                record_id = records[0].get("id")
                if not record_id:
                    return "skipped: existing EspoCRM account did not include an id"
                response = await client.patch(f"{account_url}/{record_id}", json=payload)
                response.raise_for_status()
                return "updated"

            response = await client.post(account_url, json=payload)
            response.raise_for_status()
            return "created"
    except Exception as e:
        logger.error("Failed to mirror research promotion to EspoCRM for %s: %s", client_name, e, exc_info=True)
        return f"failed: {str(e)}"


@router.post("/ingest", response_model=ResearchIngestResponse)
async def ingest_external_research(body: ResearchIngestRequest):
    client_name, graph_path = resolve_client_graph(body.client_identifier)
    if not body.report.strip():
        raise HTTPException(status_code=400, detail="report is required")

    prompt = build_research_graph_prompt(
        client_name=client_name,
        report=body.report,
        named_entities=body.named_entities,
        strategic_priorities=body.strategic_priorities,
        financial_figures=body.financial_figures,
    )

    try:
        result = await research_graph_agent.run(prompt)
        extraction: ResearchGraphExtraction = result.output
        graph = get_client_graph(client_name, graph_path)

        unique_entities = {
            (entity.name.strip(), entity.type.strip())
            for entity in extraction.entities
            if entity.name.strip() and entity.type.strip()
        }
        relationships_written = 0

        for relationship in extraction.relationships:
            if not relationship.source_name.strip() or not relationship.target_name.strip():
                continue

            graph.add_relationship(
                source_name=relationship.source_name.strip(),
                source_type=relationship.source_type.strip() or "Entity",
                target_name=relationship.target_name.strip(),
                target_type=relationship.target_type.strip() or "Entity",
                relationship_type=relationship.relationship_type.strip(),
                evidence=tag_external_research_evidence(
                    relationship.evidence,
                    body.source_label,
                ),
            )
            unique_entities.add((relationship.source_name.strip(), relationship.source_type.strip() or "Entity"))
            unique_entities.add((relationship.target_name.strip(), relationship.target_type.strip() or "Entity"))
            relationships_written += 1

        logger.info(
            "[EXTERNAL RESEARCH INGEST] client=%s entities=%s relationships=%s source=%s",
            client_name,
            len(unique_entities),
            relationships_written,
            body.source_label,
        )

        espocrm_status = await mirror_research_to_espocrm(
            client_name=client_name,
            sector=None,
            summary=extraction.summary,
            source_label=body.source_label,
        )

        return ResearchIngestResponse(
            client_identifier=client_name,
            entities_written=len(unique_entities),
            relationships_written=relationships_written,
            status="success",
            summary=extraction.summary,
            espocrm_status=espocrm_status,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to ingest external research for %s: %s", client_name, e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error ingesting external research: {str(e)}",
        )
