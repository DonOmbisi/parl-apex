from unittest.mock import AsyncMock

import pytest
from apscheduler.triggers.cron import CronTrigger

from core.config import AgentConfig, ClientConfig, ConnectorConfig
from synthesis.correlation_engine import (
    build_correlation_prompt,
    extract_specialist_outputs,
    has_at_least_two_sources,
    write_correlation_output_to_graph,
)
from synthesis.correlation_schemas import CorrelationEngineOutput, CorrelationFinding


def test_extract_specialist_outputs_requires_two_sources():
    recent_entries = [
        {
            "target_name": "Finance Finding - A",
            "target_type": "FinanceFinding",
            "relationship_type": "HAS_FINANCE_FINDING",
            "evidence": "FinanceAgent evidence",
            "timestamp": "2026-06-26T08:00:00+00:00",
        },
        {
            "target_name": "Operations Finding - A",
            "target_type": "OperationsFinding",
            "relationship_type": "HAS_OPERATIONS_FINDING",
            "evidence": "OperationsAgent evidence",
            "timestamp": "2026-06-26T08:05:00+00:00",
        },
        {
            "target_name": "SINV-0001",
            "target_type": "Invoice",
            "relationship_type": "HAS_INVOICE",
            "evidence": "ERPNext invoice evidence",
            "timestamp": "2026-06-26T08:10:00+00:00",
        },
    ]

    outputs = extract_specialist_outputs(recent_entries)

    assert [output["source"] for output in outputs] == [
        "FinanceAgent",
        "OperationsAgent",
    ]
    assert has_at_least_two_sources(outputs) is True
    assert has_at_least_two_sources(outputs[:1]) is False


def test_correlation_prompt_instructs_cross_source_urgency_ranking():
    prompt = build_correlation_prompt(
        "Nairobi Retail",
        [
            {"source": "FinanceAgent", "evidence": "Overdue receivable"},
            {"source": "OperationsAgent", "evidence": "Payment step delay"},
        ],
        [],
    )

    assert "Nairobi Retail" in prompt
    assert "at least two different sources" in prompt
    assert "Rank by urgency" in prompt
    assert "FinanceAgent" in prompt
    assert "OperationsAgent" in prompt


def test_correlation_writeback_skips_single_source_correlations():
    class FakeGraph:
        def __init__(self):
            self.relationships = []

        def add_relationship(self, **kwargs):
            self.relationships.append(kwargs)

    graph = FakeGraph()
    output = CorrelationEngineOutput(
        organization_name="Nairobi Retail",
        correlations=[
            CorrelationFinding(
                contributing_sources=["FinanceAgent"],
                visible_symptom="Receivables are overdue.",
                hidden_root_cause="Only finance evidence was present.",
                evidence_by_source={"FinanceAgent": ["Finance evidence"]},
                time_to_serious_problem="Already serious.",
                recommended_intervention="Finance follow-up.",
                urgency_rank=1,
            ),
            CorrelationFinding(
                contributing_sources=["FinanceAgent", "OperationsAgent"],
                visible_symptom="Cash collection is slow while invoice processing is delayed.",
                hidden_root_cause="Approval and collection timing are reinforcing each other.",
                evidence_by_source={
                    "FinanceAgent": ["Overdue receivable"],
                    "OperationsAgent": ["Long payment_due to status_check delay"],
                },
                time_to_serious_problem="Within 30 days.",
                recommended_intervention="Create a joint finance-operations escalation lane.",
                urgency_rank=2,
            ),
        ],
        synthesis_summary="One valid cross-source correlation was found.",
        insufficient_evidence_note="Single-source finance-only issue was excluded.",
    )

    written = write_correlation_output_to_graph(graph, "Nairobi Retail", output)

    assert written == 2
    relationship_types = [rel["relationship_type"] for rel in graph.relationships]
    assert relationship_types == ["HAS_CORRELATION", "HAS_CORRELATION_SUMMARY"]
    assert "FinanceAgent" in graph.relationships[0]["evidence"]
    assert "OperationsAgent" in graph.relationships[0]["evidence"]


def test_start_scheduler_skips_correlation_with_fewer_than_two_connector_types(monkeypatch):
    import core.scheduler as scheduler_module

    calls = []

    class FakeScheduler:
        running = False

        def remove_all_jobs(self):
            calls.append(("remove_all_jobs",))

        def add_job(self, func, trigger, args, id, replace_existing):
            calls.append((func, trigger, args, id, replace_existing))

        def start(self):
            self.running = True
            calls.append(("start",))

    fake_config = ClientConfig(
        name="Nairobi Retail",
        sector="Retail",
        connectors=[
            ConnectorConfig(
                type="erpnext",
                credentials_ref="NAIROBI_ERPNEXT",
                schedule="0 9 * * *",
            )
        ],
        agents=[
            AgentConfig(
                name="correlation",
                schedule="0 18 * * *",
                recent_days=7,
            )
        ],
        graph_path="data/graphs/nairobi_retail.db",
    )

    monkeypatch.setattr(scheduler_module, "scheduler", FakeScheduler())
    monkeypatch.setattr(scheduler_module, "load_client_configs", lambda clients_dir: [fake_config])

    scheduler_module.start_scheduler("clients")

    added_agent_jobs = [
        call for call in calls if len(call) == 5 and call[0] == scheduler_module.run_agent_job
    ]
    assert added_agent_jobs == []


def test_start_scheduler_registers_correlation_with_two_connector_types(monkeypatch):
    import core.scheduler as scheduler_module

    calls = []

    class FakeScheduler:
        running = False

        def remove_all_jobs(self):
            calls.append(("remove_all_jobs",))

        def add_job(self, func, trigger, args, id, replace_existing):
            calls.append((func, trigger, args, id, replace_existing))

        def start(self):
            self.running = True
            calls.append(("start",))

    fake_config = ClientConfig(
        name="Nairobi Retail",
        sector="Retail",
        connectors=[
            ConnectorConfig(
                type="erpnext",
                credentials_ref="NAIROBI_ERPNEXT",
                schedule="0 9 * * *",
            ),
            ConnectorConfig(
                type="kobo",
                credentials_ref="NAIROBI_KOBO",
                schedule="0 10 * * *",
            ),
        ],
        agents=[
            AgentConfig(
                name="correlation",
                schedule="0 18 * * *",
                recent_days=7,
            )
        ],
        graph_path="data/graphs/nairobi_retail.db",
    )

    monkeypatch.setattr(scheduler_module, "scheduler", FakeScheduler())
    monkeypatch.setattr(scheduler_module, "load_client_configs", lambda clients_dir: [fake_config])

    scheduler_module.start_scheduler("clients")

    agent_job = [
        call for call in calls if len(call) == 5 and call[0] == scheduler_module.run_agent_job
    ][0]

    func, trigger, args, job_id, replace_existing = agent_job
    assert func == scheduler_module.run_agent_job
    assert isinstance(trigger, CronTrigger)
    assert args == [
        "Nairobi Retail",
        "correlation",
        "data/graphs/nairobi_retail.db",
        7,
    ]
    assert job_id == "Nairobi Retail_correlation"
    assert replace_existing is True


@pytest.mark.anyio
async def test_run_agent_job_writes_correlation_output(monkeypatch):
    import core.scheduler as scheduler_module

    class FakeGraph:
        def __init__(self):
            self.relationships = []

        def get_recent_elements(self, days):
            return [
                {
                    "target_name": "Finance Finding - A",
                    "target_type": "FinanceFinding",
                    "relationship_type": "HAS_FINANCE_FINDING",
                    "evidence": "Finance evidence",
                },
                {
                    "target_name": "Operations Finding - A",
                    "target_type": "OperationsFinding",
                    "relationship_type": "HAS_OPERATIONS_FINDING",
                    "evidence": "Operations evidence",
                },
            ]

        def add_relationship(self, **kwargs):
            self.relationships.append(kwargs)

    fake_graph = FakeGraph()
    output = CorrelationEngineOutput(
        organization_name="Nairobi Retail",
        correlations=[
            CorrelationFinding(
                contributing_sources=["FinanceAgent", "OperationsAgent"],
                visible_symptom="Overdue cash collection and payment workflow delay appear together.",
                hidden_root_cause="Invoice follow-up depends on delayed operational status checks.",
                evidence_by_source={
                    "FinanceAgent": ["Finance evidence"],
                    "OperationsAgent": ["Operations evidence"],
                },
                time_to_serious_problem="Within 30 days.",
                recommended_intervention="Run a joint finance-operations receivables review.",
                urgency_rank=1,
            )
        ],
        synthesis_summary="One urgent correlation found.",
        insufficient_evidence_note="None.",
    )

    mock_runner = AsyncMock(return_value=output)
    monkeypatch.setattr("graph.get_client_graph", lambda client_name, graph_path: fake_graph)
    monkeypatch.setattr(
        "synthesis.correlation_engine.run_correlation_engine_for_client",
        mock_runner,
    )

    await scheduler_module.run_agent_job(
        client_name="Nairobi Retail",
        agent_name="correlation",
        graph_path="data/graphs/nairobi_retail.db",
        recent_days=7,
    )

    mock_runner.assert_awaited_once_with(
        client_name="Nairobi Retail",
        graph_path="data/graphs/nairobi_retail.db",
        recent_days=7,
    )
    assert len(fake_graph.relationships) == 2
    assert fake_graph.relationships[0]["relationship_type"] == "HAS_CORRELATION"
