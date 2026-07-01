from unittest.mock import AsyncMock

import pytest
from apscheduler.triggers.cron import CronTrigger

from agents.finance_agent import build_finance_prompt, write_finance_output_to_graph
from agents.finance_schemas import FinanceAgentOutput, FinanceFinding
from core.config import AgentConfig, ClientConfig


def test_finance_prompt_includes_graph_entries_and_no_invention_instruction():
    prompt = build_finance_prompt(
        "Nairobi Retail",
        [
            {
                "source_name": "Acme Buyer",
                "relationship_type": "OWES_OVERDUE_INVOICE",
                "target_name": "SINV-0001",
                "evidence": "ERPNext: SINV-0001 | KES 75000 outstanding",
            }
        ],
    )

    assert "Nairobi Retail" in prompt
    assert "OWES_OVERDUE_INVOICE" in prompt
    assert "SINV-0001" in prompt
    assert "inventing" in prompt


def test_finance_output_writeback_creates_assessment_findings_and_priority():
    class FakeGraph:
        def __init__(self):
            self.relationships = []

        def add_relationship(self, **kwargs):
            self.relationships.append(kwargs)

    graph = FakeGraph()
    output = FinanceAgentOutput(
        organization_name="Nairobi Retail",
        overall_financial_health="at risk",
        health_reasoning="Overdue receivables are visible in the graph.",
        findings=[
            FinanceFinding(
                severity="high",
                description="A customer has an overdue receivable.",
                evidence=["ERPNext: SINV-0001 | KES 75000 outstanding"],
                recommended_action="Call the customer and agree a dated payment plan.",
                time_sensitivity="This week, because the invoice is overdue.",
            )
        ],
        top_priority="Recover the overdue receivable linked to SINV-0001.",
        missing_or_uncertain_data="No payroll, bank balance, budget, or donor compliance data was present.",
    )

    written = write_finance_output_to_graph(graph, "Nairobi Retail", output)

    assert written == 3
    relationship_types = [rel["relationship_type"] for rel in graph.relationships]
    target_types = [rel["target_type"] for rel in graph.relationships]
    assert relationship_types == [
        "HAS_FINANCE_ASSESSMENT",
        "HAS_FINANCE_FINDING",
        "HAS_FINANCE_TOP_PRIORITY",
    ]
    assert target_types == [
        "FinanceAssessment",
        "FinanceFinding",
        "FinanceTopPriority",
    ]
    assert "at risk" in graph.relationships[0]["evidence"]
    assert "SINV-0001" in graph.relationships[1]["evidence"]


def test_client_config_accepts_legacy_and_scheduled_agent_entries():
    config = ClientConfig(
        name="Nairobi Retail",
        sector="Retail",
        connectors=[],
        agents=[
            "retail_analyzer",
            {
                "name": "finance",
                "schedule": "0 8 * * 1-5",
                "recent_days": 14,
            },
        ],
        graph_path="data/graphs/nairobi_retail.db",
    )

    assert config.agents[0] == "retail_analyzer"
    assert isinstance(config.agents[1], AgentConfig)
    assert config.agents[1].name == "finance"
    assert config.agents[1].recent_days == 14


def test_start_scheduler_registers_scheduled_finance_agent(monkeypatch):
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
        connectors=[],
        agents=[
            AgentConfig(
                name="finance",
                schedule="0 8 * * 1-5",
                recent_days=14,
            )
        ],
        graph_path="data/graphs/nairobi_retail.db",
    )

    monkeypatch.setattr(scheduler_module, "scheduler", FakeScheduler())
    monkeypatch.setattr(scheduler_module, "load_client_configs", lambda clients_dir: [fake_config])

    scheduler_module.start_scheduler("clients")

    add_job_call = next(call for call in calls if len(call) == 5)
    func, trigger, args, job_id, replace_existing = add_job_call

    assert func == scheduler_module.run_agent_job
    assert isinstance(trigger, CronTrigger)
    assert args == [
        "Nairobi Retail",
        "finance",
        "data/graphs/nairobi_retail.db",
        14,
    ]
    assert job_id == "Nairobi Retail_finance"
    assert replace_existing is True


@pytest.mark.anyio
async def test_run_agent_job_writes_finance_output(monkeypatch):
    import core.scheduler as scheduler_module

    class FakeGraph:
        def __init__(self):
            self.relationships = []

        def add_relationship(self, **kwargs):
            self.relationships.append(kwargs)

    fake_graph = FakeGraph()
    output = FinanceAgentOutput(
        organization_name="Nairobi Retail",
        overall_financial_health="at risk",
        health_reasoning="Overdue receivables are visible in the graph.",
        findings=[
            FinanceFinding(
                severity="high",
                description="A customer has an overdue receivable.",
                evidence=["ERPNext: SINV-0001"],
                recommended_action="Follow up with the customer.",
                time_sensitivity="This week.",
            )
        ],
        top_priority="Recover overdue receivables.",
        missing_or_uncertain_data="No bank balance data was present.",
    )

    mock_runner = AsyncMock(return_value=output)

    monkeypatch.setattr("agents.finance_agent.run_finance_agent_for_client", mock_runner)
    monkeypatch.setattr(
        "graph.get_client_graph",
        lambda client_name, graph_path: fake_graph,
    )

    await scheduler_module.run_agent_job(
        client_name="Nairobi Retail",
        agent_name="finance",
        graph_path="data/graphs/nairobi_retail.db",
        recent_days=14,
    )

    mock_runner.assert_awaited_once_with(
        client_name="Nairobi Retail",
        graph_path="data/graphs/nairobi_retail.db",
        recent_days=14,
    )
    assert len(fake_graph.relationships) == 3
    assert fake_graph.relationships[1]["relationship_type"] == "HAS_FINANCE_FINDING"
