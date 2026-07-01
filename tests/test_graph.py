import os
import shutil
import tempfile
from datetime import datetime, timezone
import pytest

from graph.client_graph import ClientKnowledgeGraph

def test_client_knowledge_graph_persistence():
    # Create a temporary directory for the Kuzu database
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_graph.db")
    
    try:
        # 1. Initialize graph
        graph = ClientKnowledgeGraph(db_path)
        
        # 2. Add sample relationships
        # Relationship 1: Alice -> Bob
        graph.add_relationship(
            source_name="Alice",
            source_type="Person",
            target_name="Bob",
            target_type="Person",
            relationship_type="COLLEAGUE",
            evidence="Met at Nairobi HQ in 2025"
        )
        
        # Relationship 2: Bob -> AcmeCorp
        graph.add_relationship(
            source_name="Bob",
            source_type="Person",
            target_name="AcmeCorp",
            target_type="Organization",
            relationship_type="EMPLOYEE_OF",
            evidence="HR database record #9923"
        )
        
        # Relationship 3: Alice -> AcmeCorp
        graph.add_relationship(
            source_name="Alice",
            source_type="Person",
            target_name="AcmeCorp",
            target_type="Organization",
            relationship_type="CONSULTANT_FOR",
            evidence="Signed contract dated 2026-01-10"
        )
        
        # 3. Verify relationships can be read back using arbitrary queries
        query = """
        MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity)
        WHERE a.name = $name
        RETURN b.name AS target, r.type AS rel_type
        """
        results = graph.execute_query(query, {"name": "Alice"})
        
        # Format results for easy checking
        alice_rels = {row["target"]: row["rel_type"] for row in results}
        
        assert "Bob" in alice_rels
        assert alice_rels["Bob"] == "COLLEAGUE"
        assert "AcmeCorp" in alice_rels
        assert alice_rels["AcmeCorp"] == "CONSULTANT_FOR"
        
        # 4. Verify get_recent_elements works
        recent = graph.get_recent_elements(days=1)
        assert len(recent) == 3
        
        # Extract and verify evidence
        evidences = [row["evidence"] for row in recent]
        assert "Met at Nairobi HQ in 2025" in evidences
        assert "HR database record #9923" in evidences
        assert "Signed contract dated 2026-01-10" in evidences
        
        # Close graph to release file locks
        graph.close()
        
        # 5. Reopen the graph and verify data persistence
        reopened_graph = ClientKnowledgeGraph(db_path)
        persisted_results = reopened_graph.execute_query(query, {"name": "Alice"})
        reopened_alice_rels = {row["target"]: row["rel_type"] for row in persisted_results}
        
        assert "Bob" in reopened_alice_rels
        assert reopened_alice_rels["Bob"] == "COLLEAGUE"
        
        reopened_graph.close()
        
    finally:
        # Clean up temporary database files
        try:
            shutil.rmtree(temp_dir)
        except Exception as e:
            print(f"Failed to clean up temp directory {temp_dir}: {e}")
