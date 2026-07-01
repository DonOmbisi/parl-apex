import logging
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agents.query_agent import run_query_agent_for_client, write_query_audit_to_graph
from agents.query_schemas import QueryAgentOutput
from app.routers.clients import slugify
from graph import get_client_graph

logger = logging.getLogger("parl_apex.routers.query")

router = APIRouter(prefix="/query", tags=["query"])


class QueryRequest(BaseModel):
    client_identifier: str = Field(
        description="Client slug or organization name, e.g. kenya_red_cross or Kenya Red Cross."
    )
    question: str = Field(description="Free-form question to ask against the client's graph.")
    recent_days: int = Field(default=90, ge=1, le=3650)


def resolve_client_graph(client_identifier: str) -> tuple[str, str]:
    cleaned = client_identifier.strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="client_identifier is required")

    clients_dir = Path("clients")
    direct_slug = slugify(cleaned)
    direct_config = clients_dir / direct_slug / "config.yaml"

    if direct_config.exists():
        with open(direct_config, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        return config.get("name", cleaned), config.get("graph_path", f"graphs/{direct_slug}.db")

    if clients_dir.exists():
        for config_path in clients_dir.glob("*/config.yaml"):
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
            name = config.get("name")
            if name and slugify(name) == direct_slug:
                return name, config.get("graph_path", f"graphs/{slugify(name)}.db")

    raise HTTPException(
        status_code=404,
        detail=f"No client configuration found for '{client_identifier}'. Run research seeding first.",
    )


@router.post("/ask", response_model=QueryAgentOutput)
async def ask_query(body: QueryRequest):
    client_name, graph_path = resolve_client_graph(body.client_identifier)
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is required")

    logger.info("Received graph query for client '%s': %s", client_name, question)

    try:
        output = await run_query_agent_for_client(
            client_identifier=client_name,
            graph_path=graph_path,
            question=question,
            recent_days=body.recent_days,
        )
        graph = get_client_graph(client_name, graph_path)
        write_query_audit_to_graph(graph, client_name, question, output)
        return output
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to answer graph query: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error running query agent: {str(e)}",
        )
