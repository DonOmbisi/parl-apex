import os
import shutil
import tempfile
from unittest.mock import AsyncMock

import pytest
import yaml
from httpx import ASGITransport, AsyncClient

from agents.research_graph_agent import (
    ResearchGraphEntity,
    ResearchGraphExtraction,
    ResearchGraphRelationship,
    tag_external_research_evidence,
)
from app.main import app


def test_external_research_evidence_tag_is_explicit():
    tagged = tag_external_research_evidence(
        "Report names Jane Doe as CEO.",
        "Consult Ralph",
    )

    assert "SOURCE=EXTERNAL_RESEARCH" in tagged
    assert "ORIGIN=Consult Ralph" in tagged
    assert "INTERNAL_CONFIRMATION=false" in tagged
    assert "Jane Doe" in tagged


@pytest.fixture()
def temp_client_config():
    temp_dir = tempfile.mkdtemp()
    old_cwd = os.getcwd()
    os.chdir(temp_dir)
    os.makedirs("clients/acme_org", exist_ok=True)
    os.makedirs("data/graphs", exist_ok=True)

    with open("clients/acme_org/config.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(
            {
                "name": "Acme Org",
                "sector": "Manufacturing",
                "connectors": [],
                "agents": [],
                "graph_path": "data/graphs/acme_org.db",
            },
            f,
        )

    yield temp_dir

    os.chdir(old_cwd)
    try:
        from graph import close_all_graphs

        close_all_graphs()
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.mark.anyio
async def test_research_ingest_endpoint_writes_external_research_graph(monkeypatch, temp_client_config):
    extraction = ResearchGraphExtraction(
        entities=[
            ResearchGraphEntity(name="Acme Org", type="Organization"),
            ResearchGraphEntity(name="Jane Doe", type="Person"),
            ResearchGraphEntity(name="IFC", type="Funder"),
        ],
        relationships=[
            ResearchGraphRelationship(
                source_name="Acme Org",
                source_type="Organization",
                target_name="Jane Doe",
                target_type="Person",
                relationship_type="HAS_LEADER",
                evidence="The report names Jane Doe as CEO.",
            ),
            ResearchGraphRelationship(
                source_name="IFC",
                source_type="Funder",
                target_name="Acme Org",
                target_type="Organization",
                relationship_type="FUNDS",
                evidence="The report describes IFC funding.",
            ),
        ],
        summary="Extracted leadership and funder relationships.",
    )

    mock_result = AsyncMock()
    mock_result.output = extraction
    mock_run = AsyncMock(return_value=mock_result)
    monkeypatch.setattr("app.routers.research.research_graph_agent.run", mock_run)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post(
            "/research/ingest",
            json={
                "client_identifier": "acme_org",
                "report": "Acme Org public research report.",
                "named_entities": {
                    "leadership": ["Jane Doe"],
                    "funders": ["IFC"],
                },
                "strategic_priorities": ["Regional expansion"],
                "financial_figures": ["Revenue: KES 120M"],
                "source_label": "Consult Ralph report 2026-06-29",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["client_identifier"] == "Acme Org"
    assert data["entities_written"] == 3
    assert data["relationships_written"] == 2

    from graph import get_client_graph

    graph = get_client_graph("Acme Org", "data/graphs/acme_org.db")
    rows = graph.execute_query(
        """
        MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity)
        RETURN a.name AS source_name, r.type AS relationship_type, b.name AS target_name, r.evidence AS evidence
        """
    )

    assert {row["relationship_type"] for row in rows} == {"HAS_LEADER", "FUNDS"}
    assert all("SOURCE=EXTERNAL_RESEARCH" in row["evidence"] for row in rows)
    assert all("INTERNAL_CONFIRMATION=false" in row["evidence"] for row in rows)
    assert all("Consult Ralph report 2026-06-29" in row["evidence"] for row in rows)
