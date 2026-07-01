import logging
from pathlib import Path

import yaml
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from pydantic import ValidationError

from core.config import AgentConfig, ClientConfig

logger = logging.getLogger("parl_apex.scheduler")

scheduler = AsyncIOScheduler()


def load_client_configs(clients_dir: str) -> list[ClientConfig]:
    """
    Scan the clients folder, read each client/config.yaml file, and return
    validated client configuration models.
    """
    configs: list[ClientConfig] = []
    clients_path = Path(clients_dir)

    if not clients_path.exists():
        logger.warning("Clients directory %s does not exist.", clients_dir)
        return configs

    for config_file in sorted(clients_path.glob("*/config.yaml")):
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if not data:
                logger.warning("Skipping empty client configuration: %s", config_file)
                continue

            config = ClientConfig(**data)

            if config.graph_path:
                from graph import get_client_graph
                get_client_graph(config.name, config.graph_path)

            configs.append(config)
            logger.info(
                "Loaded client configuration and initialized graph: %s from %s",
                config.name,
                config_file,
            )
        except yaml.YAMLError as e:
            logger.error("Failed to parse YAML in %s: %s", config_file, e)
        except ValidationError as e:
            logger.error("Configuration validation failed for %s: %s", config_file, e)
        except Exception as e:
            logger.error("Unexpected error loading %s: %s", config_file, e)

    return configs


async def run_connector_job(
    client_name: str,
    connector_type: str,
    credentials_ref: str,
    graph_path: str | None = None,
) -> None:
    """
    Stage Two placeholder job.

    Later stages replace this placeholder with real connector execution. For
    now, the job proves that client connector schedules can be registered and
    triggered from config files without hardcoded client-specific logic.
    """
    if connector_type == "valyu_tender_research":
        from connectors.valyu_tender_connector import create_tender_research_task
        import os

        webhook_base_url = os.getenv("PARL_APEX_WEBHOOK_BASE_URL", "").rstrip("/")
        if not webhook_base_url:
            logger.error(
                "[CONNECTOR FAILED] client=%s connector=%s missing PARL_APEX_WEBHOOK_BASE_URL",
                client_name,
                connector_type,
            )
            return

        webhook_url = f"{webhook_base_url}/webhooks/valyu/tender-research"
        task_id = await create_tender_research_task(webhook_url=webhook_url)
        logger.info(
            "[CONNECTOR TRIGGERED] client=%s connector=%s valyu_task_id=%s",
            client_name,
            connector_type,
            task_id,
        )
        return

    import connectors
    from agents.erpnext_extraction_agent import extract_from_connector_result
    from graph import get_client_graph

    connector_cls = connectors.CONNECTOR_REGISTRY.get(connector_type)
    if connector_cls and graph_path:
        connector = connector_cls(client_name, credentials_ref)
        result = await connector.fetch()
        extraction = extract_from_connector_result(result)
        graph = get_client_graph(client_name, graph_path)

        for relationship in extraction.relationships:
            graph.add_relationship(
                source_name=relationship.source_name,
                source_type=relationship.source_type,
                target_name=relationship.target_name,
                target_type=relationship.target_type,
                relationship_type=relationship.relationship_type,
                evidence=relationship.evidence,
            )

        logger.info(
            "[CONNECTOR TRIGGERED] client=%s connector=%s relationships_written=%s",
            client_name,
            connector_type,
            len(extraction.relationships),
        )
        return

    logger.info(
        "[CONNECTOR TRIGGERED] client=%s connector=%s credentials_ref=%s graph_path=%s",
        client_name,
        connector_type,
        credentials_ref,
        graph_path,
    )


async def run_agent_job(
    client_name: str,
    agent_name: str,
    graph_path: str,
    recent_days: int,
) -> None:
    if agent_name == "finance":
        from agents.finance_agent import (
            run_finance_agent_for_client,
            write_finance_output_to_graph,
        )
        from graph import get_client_graph

        output = await run_finance_agent_for_client(
            client_name=client_name,
            graph_path=graph_path,
            recent_days=recent_days,
        )
        graph = get_client_graph(client_name, graph_path)
        written = write_finance_output_to_graph(graph, client_name, output)
        logger.info(
            "[AGENT TRIGGERED] client=%s agent=%s findings_written=%s",
            client_name,
            agent_name,
            written,
        )
        return

    if agent_name == "correlation":
        from graph import get_client_graph
        from synthesis.correlation_engine import (
            run_correlation_engine_for_client,
            write_correlation_output_to_graph,
        )

        output = await run_correlation_engine_for_client(
            client_name=client_name,
            graph_path=graph_path,
            recent_days=recent_days,
        )
        graph = get_client_graph(client_name, graph_path)
        written = write_correlation_output_to_graph(graph, client_name, output)
        logger.info(
            "[AGENT TRIGGERED] client=%s agent=%s correlations_written=%s",
            client_name,
            agent_name,
            written,
        )
        return

    logger.info(
        "[AGENT TRIGGERED] client=%s agent=%s graph_path=%s recent_days=%s",
        client_name,
        agent_name,
        graph_path,
        recent_days,
    )


def start_scheduler(clients_dir: str = "clients") -> AsyncIOScheduler:
    """
    Load client configs, register one APScheduler job per connector, and start
    the in-process scheduler.
    """
    configs = load_client_configs(clients_dir)
    scheduler.remove_all_jobs()

    job_count = 0
    for config in configs:
        for connector in config.connectors:
            try:
                trigger = CronTrigger.from_crontab(connector.schedule)
                job_id = f"{config.name}_{connector.type}"

                scheduler.add_job(
                    run_connector_job,
                    trigger=trigger,
                    args=[
                        config.name,
                        connector.type,
                        connector.credentials_ref,
                        config.graph_path,
                    ],
                    id=job_id,
                    replace_existing=True,
                )
                job_count += 1
                logger.info(
                    "Registered connector job for client '%s', connector '%s', schedule '%s'",
                    config.name,
                    connector.type,
                    connector.schedule,
                )
            except Exception as e:
                logger.error(
                    "Failed to register connector job for client '%s', connector '%s', schedule '%s': %s",
                    config.name,
                    connector.type,
                    connector.schedule,
                    e,
                )

        for agent in config.agents:
            if not isinstance(agent, AgentConfig):
                continue
            if not config.graph_path:
                logger.warning(
                    "Skipping agent job for client '%s', agent '%s': missing graph_path",
                    config.name,
                    agent.name,
                )
                continue
            if agent.name == "correlation":
                connector_types = {connector.type for connector in config.connectors}
                if len(connector_types) < 2:
                    logger.info(
                        "Skipping correlation agent for client '%s': fewer than two connector types",
                        config.name,
                    )
                    continue

            try:
                trigger = CronTrigger.from_crontab(agent.schedule)
                job_id = f"{config.name}_{agent.name}"

                scheduler.add_job(
                    run_agent_job,
                    trigger=trigger,
                    args=[
                        config.name,
                        agent.name,
                        config.graph_path,
                        agent.recent_days,
                    ],
                    id=job_id,
                    replace_existing=True,
                )
                job_count += 1
                logger.info(
                    "Registered agent job for client '%s', agent '%s', schedule '%s'",
                    config.name,
                    agent.name,
                    agent.schedule,
                )
            except Exception as e:
                logger.error(
                    "Failed to register agent job for client '%s', agent '%s', schedule '%s': %s",
                    config.name,
                    agent.name,
                    agent.schedule,
                    e,
                )

    logger.info("Total connector jobs registered: %s", job_count)

    if not scheduler.running:
        scheduler.start()
        logger.info("APScheduler started successfully.")

    return scheduler


def shutdown_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown()
        logger.info("APScheduler shut down successfully.")
