import os
import shutil
import tempfile

import pytest
import yaml
from apscheduler.triggers.cron import CronTrigger

from core.config import ClientConfig


@pytest.fixture()
def temp_clients_dir():
    temp_dir = tempfile.mkdtemp()
    clients_dir = os.path.join(temp_dir, "clients")
    os.makedirs(os.path.join(clients_dir, "alpha_org"))
    os.makedirs(os.path.join(clients_dir, "beta_org"))

    with open(os.path.join(clients_dir, "alpha_org", "config.yaml"), "w", encoding="utf-8") as f:
        yaml.safe_dump(
            {
                "name": "Alpha Org",
                "sector": "Retail",
                "connectors": [
                    {
                        "type": "erpnext",
                        "credentials_ref": "ALPHA_ERPNEXT",
                        "schedule": "0 9 * * *",
                    }
                ],
                "agents": ["finance"],
                "graph_path": "data/graphs/alpha_org.db",
            },
            f,
        )

    with open(os.path.join(clients_dir, "beta_org", "config.yaml"), "w", encoding="utf-8") as f:
        yaml.safe_dump(
            {
                "name": "Beta Org",
                "sector": "Logistics",
                "connectors": [
                    {
                        "type": "email",
                        "credentials_ref": "BETA_EMAIL",
                        "schedule": "30 8 * * 1-5",
                    },
                    {
                        "type": "local_files",
                        "credentials_ref": "BETA_LOCAL_PATH",
                        "schedule": "*/15 * * * *",
                    },
                ],
                "agents": ["operations", "finance"],
                "graph_path": "data/graphs/beta_org.db",
            },
            f,
        )

    yield clients_dir

    shutil.rmtree(temp_dir, ignore_errors=True)


def test_load_client_configs_reads_plain_yaml_files(temp_clients_dir):
    from core.scheduler import load_client_configs

    configs = load_client_configs(temp_clients_dir)

    assert len(configs) == 2
    assert all(isinstance(config, ClientConfig) for config in configs)
    assert {config.name for config in configs} == {"Alpha Org", "Beta Org"}
    assert configs[0].connectors
    assert all(isinstance(agent, str) for config in configs for agent in config.agents)


def test_start_scheduler_registers_one_placeholder_job_per_connector(monkeypatch, temp_clients_dir):
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

    monkeypatch.setattr(scheduler_module, "scheduler", FakeScheduler())

    scheduler_module.start_scheduler(temp_clients_dir)

    add_job_calls = [call for call in calls if len(call) == 5]

    assert len(add_job_calls) == 3
    for func, trigger, args, job_id, replace_existing in add_job_calls:
        assert func == scheduler_module.run_connector_job
        assert isinstance(trigger, CronTrigger)
        assert len(args) in {3, 4}
        assert job_id == f"{args[0]}_{args[1]}"
        assert replace_existing is True


@pytest.mark.anyio
async def test_placeholder_connector_job_only_logs(caplog):
    from core.scheduler import run_connector_job

    caplog.set_level("INFO")

    await run_connector_job(
        client_name="Alpha Org",
        connector_type="erpnext",
        credentials_ref="ALPHA_ERPNEXT",
    )

    assert "CONNECTOR TRIGGERED" in caplog.text
    assert "Alpha Org" in caplog.text
    assert "erpnext" in caplog.text
