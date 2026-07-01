import os
import shutil
import tempfile
from unittest.mock import AsyncMock

import pytest
import yaml
from httpx import ASGITransport, AsyncClient

from agents.query_agent import insufficient_answer, rank_relevant_entries
from agents.query_schemas import QueryAgentOutput, QueryEvidence
from app.main import app


def test_rank_relevant_entries_matches_question_terms():
    entries = [
        {
            "source_name": "Kenya Red Cross",
            "source_type": "Organization",
            "relationship_type": "HAS_SYSTEM",
            "target_name": "KoboToolbox",
            "target_type": "Technology",
            "evidence": "Consult Ralph Research Output",
        },
        {
            "source_name": "IFRC",
            "source_type": "Funder",
            "relationship_type": "FUNDS",
            "target_name": "Kenya Red Cross",
            "target_type": "Organization",
            "evidence": "Consult Ralph Research Output",
        },
    ]

    ranked = rank_relevant_entries("Which systems does the client use?", entries)

    assert len(ranked) == 1
    assert ranked[0]["target_name"] == "KoboToolbox"


def test_insufficient_answer_is_explicit():
    output = insufficient_answer(
        client_identifier="Kenya Red Cross",
        question="What is payroll risk?",
        missing_information="No payroll entries were found.",
    )

    assert output.confidence == "insufficient"
    assert output.supporting_evidence == []
    assert "does not contain enough information" in output.answer


@pytest.fixture()
def temp_clients_dir():
    temp_dir = tempfile.mkdtemp()
    old_cwd = os.getcwd()
    os.chdir(temp_dir)
    os.makedirs("clients/kenya_red_cross", exist_ok=True)
    os.makedirs("data/graphs", exist_ok=True)
    with open("clients/kenya_red_cross/config.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(
            {
                "name": "Kenya Red Cross",
                "sector": "Non-Profit",
                "connectors": [],
                "agents": [],
                "graph_path": "data/graphs/kenya_red_cross.db",
            },
            f,
        )

    yield temp_dir

    os.chdir(old_cwd)
    try:
        shutil.rmtree(temp_dir)
    except Exception:
        pass


@pytest.mark.anyio
async def test_query_endpoint_returns_typed_answer(monkeypatch, temp_clients_dir):
    output = QueryAgentOutput(
        client_identifier="Kenya Red Cross",
        question="What systems does the client use?",
        answer="The graph indicates Kenya Red Cross uses KoboToolbox.",
        confidence="high",
        supporting_evidence=[
            QueryEvidence(
                source_name="Kenya Red Cross",
                source_type="Organization",
                relationship_type="HAS_SYSTEM",
                target_name="KoboToolbox",
                target_type="Technology",
                evidence="Consult Ralph Research Output",
            )
        ],
        missing_information="No ERP details were present.",
    )
    mock_runner = AsyncMock(return_value=output)

    class FakeGraph:
        def __init__(self):
            self.relationships = []

        def add_relationship(self, **kwargs):
            self.relationships.append(kwargs)

    fake_graph = FakeGraph()

    monkeypatch.setattr("app.routers.query.run_query_agent_for_client", mock_runner)
    monkeypatch.setattr("app.routers.query.get_client_graph", lambda client_name, graph_path: fake_graph)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post(
            "/query/ask",
            json={
                "client_identifier": "kenya_red_cross",
                "question": "What systems does the client use?",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["answer"] == "The graph indicates Kenya Red Cross uses KoboToolbox."
    assert data["confidence"] == "high"
    assert data["supporting_evidence"][0]["target_name"] == "KoboToolbox"
    assert len(fake_graph.relationships) == 1
    mock_runner.assert_awaited_once_with(
        client_identifier="Kenya Red Cross",
        graph_path="data/graphs/kenya_red_cross.db",
        question="What systems does the client use?",
        recent_days=90,
    )
