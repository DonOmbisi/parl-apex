import os
import shutil
import tempfile

import yaml


def test_loader_initializes_client_graph_and_graph_persists_relationships():
    from core.scheduler import load_client_configs
    from graph import close_all_graphs, get_client_graph
    from graph.client_graph import ClientKnowledgeGraph

    temp_dir = tempfile.mkdtemp()
    old_cwd = os.getcwd()

    try:
        os.chdir(temp_dir)
        os.makedirs("clients/sample_client", exist_ok=True)
        graph_path = "data/graphs/sample_client.db"

        with open("clients/sample_client/config.yaml", "w", encoding="utf-8") as f:
            yaml.safe_dump(
                {
                    "name": "Sample Client",
                    "sector": "Health",
                    "connectors": [],
                    "agents": ["finance"],
                    "graph_path": graph_path,
                },
                f,
            )

        configs = load_client_configs("clients")
        assert len(configs) == 1
        assert configs[0].graph_path == graph_path

        graph = get_client_graph("Sample Client")
        graph.add_relationship(
            source_name="Sample Client",
            source_type="Organization",
            target_name="KoboToolbox",
            target_type="Technology",
            relationship_type="HAS_SYSTEM",
            evidence="Temporary test config",
        )
        graph.add_relationship(
            source_name="Sample Client",
            source_type="Organization",
            target_name="Manual reconciliation",
            target_type="Challenge",
            relationship_type="HAS_CHALLENGE",
            evidence="Temporary test config",
        )

        recent = graph.get_recent_elements(days=1)
        assert len(recent) == 2

        close_all_graphs()

        reopened_graph = ClientKnowledgeGraph(graph_path)
        rows = reopened_graph.execute_query(
            """
            MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity)
            WHERE a.name = $name
            RETURN b.name AS target_name, b.type AS target_type, r.type AS relationship_type
            """,
            {"name": "Sample Client"},
        )
        relationships = {row["target_name"]: row["relationship_type"] for row in rows}

        assert relationships["KoboToolbox"] == "HAS_SYSTEM"
        assert relationships["Manual reconciliation"] == "HAS_CHALLENGE"

        reopened_graph.close()
    finally:
        os.chdir(old_cwd)
        close_all_graphs()
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_execute_query_rejects_write_queries(tmp_path):
    from graph.client_graph import ClientKnowledgeGraph

    graph = ClientKnowledgeGraph(str(tmp_path / "readonly_check.db"))

    try:
        try:
            graph.execute_query("CREATE (:Entity {name: 'Bad', type: 'Test'})")
        except ValueError as exc:
            assert "read-only" in str(exc)
        else:
            raise AssertionError("Expected write query to be rejected")
    finally:
        graph.close()
