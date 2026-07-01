import pytest

from agents.erpnext_extraction_agent import extract_from_connector_result
from connectors.erpnext_connector import ERPNextConnectorResult, RawInvoice


def test_erpnext_extraction_maps_invoices_to_graph_relationships():
    result = ERPNextConnectorResult(
        client_name="Nairobi Retail",
        credentials_ref="NAIROBI_RETAIL_ERPNEXT",
        fetched_at="2026-06-26T12:00:00+00:00",
        invoices=[
            RawInvoice(
                name="SINV-0001",
                customer="Acme Buyer",
                posting_date="2026-06-01",
                due_date="2026-06-15",
                grand_total=120000,
                outstanding_amount=75000,
                currency="KES",
                status="Overdue",
            ),
            RawInvoice(
                name="SINV-0002",
                customer="Beta Buyer",
                posting_date="2026-06-20",
                due_date="2026-07-05",
                grand_total=30000,
                outstanding_amount=30000,
                currency="KES",
                status="Unpaid",
            ),
        ],
    )

    output = extract_from_connector_result(result)

    relationships = {
        (rel.source_name, rel.target_name): rel.relationship_type
        for rel in output.relationships
    }

    assert output.client_name == "Nairobi Retail"
    assert len(output.relationships) == 4
    assert relationships[("Nairobi Retail", "SINV-0001")] == "HAS_INVOICE"
    assert relationships[("Acme Buyer", "SINV-0001")] == "OWES_OVERDUE_INVOICE"
    assert relationships[("Nairobi Retail", "SINV-0002")] == "HAS_INVOICE"
    assert relationships[("Beta Buyer", "SINV-0002")] == "OWES_INVOICE"
    assert "2 invoice(s)" in output.summary


def test_start_scheduler_passes_credentials_ref_and_graph_path(monkeypatch):
    from apscheduler.triggers.cron import CronTrigger
    from core.config import ClientConfig, ConnectorConfig
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
                credentials_ref="NAIROBI_RETAIL_ERPNEXT",
                schedule="0 9 * * *",
            )
        ],
        agents=[],
        graph_path="data/graphs/nairobi_retail.db",
    )

    monkeypatch.setattr(scheduler_module, "scheduler", FakeScheduler())
    monkeypatch.setattr(scheduler_module, "load_client_configs", lambda clients_dir: [fake_config])

    scheduler_module.start_scheduler("clients")

    add_job_call = next(call for call in calls if len(call) == 5)
    _, trigger, args, job_id, replace_existing = add_job_call

    assert isinstance(trigger, CronTrigger)
    assert args == [
        "Nairobi Retail",
        "erpnext",
        "NAIROBI_RETAIL_ERPNEXT",
        "data/graphs/nairobi_retail.db",
    ]
    assert job_id == "Nairobi Retail_erpnext"
    assert replace_existing is True


@pytest.mark.anyio
async def test_connector_job_writes_extracted_relationships(monkeypatch):
    import core.scheduler as scheduler_module
    import connectors

    class FakeConnector:
        def __init__(self, client_name, credentials_ref):
            assert client_name == "Nairobi Retail"
            assert credentials_ref == "NAIROBI_RETAIL_ERPNEXT"

        async def fetch(self):
            return ERPNextConnectorResult(
                client_name="Nairobi Retail",
                credentials_ref="NAIROBI_RETAIL_ERPNEXT",
                fetched_at="2026-06-26T12:00:00+00:00",
                invoices=[
                    RawInvoice(
                        name="SINV-0001",
                        customer="Acme Buyer",
                        posting_date="2026-06-01",
                        due_date="2026-06-15",
                        grand_total=120000,
                        outstanding_amount=75000,
                        currency="KES",
                        status="Overdue",
                    )
                ],
            )

    class FakeGraph:
        def __init__(self):
            self.relationships = []

        def add_relationship(self, **kwargs):
            self.relationships.append(kwargs)

    fake_graph = FakeGraph()

    monkeypatch.setitem(connectors.CONNECTOR_REGISTRY, "erpnext_test", FakeConnector)
    monkeypatch.setattr(
        "graph.get_client_graph",
        lambda client_name, graph_path: fake_graph,
    )

    await scheduler_module.run_connector_job(
        client_name="Nairobi Retail",
        connector_type="erpnext_test",
        credentials_ref="NAIROBI_RETAIL_ERPNEXT",
        graph_path="data/graphs/nairobi_retail.db",
    )

    assert len(fake_graph.relationships) == 2
    assert fake_graph.relationships[0]["relationship_type"] == "HAS_INVOICE"
    assert fake_graph.relationships[1]["relationship_type"] == "OWES_OVERDUE_INVOICE"
