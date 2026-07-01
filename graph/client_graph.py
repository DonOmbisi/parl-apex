import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
import kuzu

from core.paths import resolve_data_path

logger = logging.getLogger("parl_apex.graph")

class ClientKnowledgeGraph:
    """
    Wraps a Kuzu embedded property graph database connection for a single client.
    Manages the schema and provides methods for adding relationships, querying,
    and retrieving recent elements.
    """
    def __init__(self, db_path: str):
        self.db_path = resolve_data_path(db_path)
        
        # Ensure parent directory exists
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Connecting to Kuzu database at: {self.db_path}")
        self.db = kuzu.Database(self.db_path)
        self.conn = kuzu.Connection(self.db)
        
        self._initialize_schema()

    def _initialize_schema(self):
        """
        Initializes the node and relationship tables if they do not exist.
        """
        # Create Entity node table
        try:
            self.conn.execute(
                "CREATE NODE TABLE Entity(name STRING, type STRING, PRIMARY KEY(name))"
            )
            logger.info("Created node table 'Entity'.")
        except Exception as e:
            # Table already exists, or other error
            if "Table" in str(e) and "already exists" in str(e):
                logger.debug("Node table 'Entity' already exists.")
            else:
                logger.warning(f"Note on creating Entity table: {e}")

        # Create RELATES_TO relationship table
        try:
            self.conn.execute(
                "CREATE REL TABLE RELATES_TO(FROM Entity TO Entity, type STRING, evidence STRING, timestamp TIMESTAMP)"
            )
            logger.info("Created relationship table 'RELATES_TO'.")
        except Exception as e:
            if "Table" in str(e) and "already exists" in str(e):
                logger.debug("Relationship table 'RELATES_TO' already exists.")
            else:
                logger.warning(f"Note on creating RELATES_TO table: {e}")

    def add_relationship(
        self,
        source_name: str,
        source_type: str,
        target_name: str,
        target_type: str,
        relationship_type: str,
        evidence: str
    ):
        """
        Upserts two entities and creates/merges a relationship between them.
        """
        # 1. Upsert source entity
        self.conn.execute(
            "MERGE (a:Entity {name: $name}) ON CREATE SET a.type = $type",
            {"name": source_name, "type": source_type}
        )
        
        # 2. Upsert target entity
        self.conn.execute(
            "MERGE (b:Entity {name: $name}) ON CREATE SET b.type = $type",
            {"name": target_name, "type": target_type}
        )
        
        # 3. Create relationship with timestamp
        now = datetime.now(timezone.utc)
        self.conn.execute(
            "MATCH (a:Entity {name: $src}), (b:Entity {name: $dst}) "
            "MERGE (a)-[r:RELATES_TO]->(b) "
            "ON CREATE SET r.type = $rel_type, r.evidence = $evidence, r.timestamp = $timestamp "
            "ON MATCH SET r.type = $rel_type, r.evidence = $evidence, r.timestamp = $timestamp",
            {
                "src": source_name,
                "dst": target_name,
                "rel_type": relationship_type,
                "evidence": evidence,
                "timestamp": now
            }
        )
        logger.info(
            f"Added relationship: ({source_name}:{source_type})-[{relationship_type}]->({target_name}:{target_type})"
        )

    def execute_query(self, query: str, params: dict = None) -> list[dict]:
        """
        Executes a read-only Cypher query on the graph and returns the result as
        a list of dicts.
        """
        forbidden_keywords = (
            "CREATE",
            "DELETE",
            "DETACH",
            "DROP",
            "MERGE",
            "REMOVE",
            "SET",
        )
        normalized_query = query.upper()
        if any(keyword in normalized_query for keyword in forbidden_keywords):
            raise ValueError("execute_query only accepts read-only graph queries.")

        result = self.conn.execute(query, params or {})
        cols = result.get_column_names()
        rows = []
        while result.has_next():
            row_values = result.get_next()
            rows.append(dict(zip(cols, row_values)))
        return rows

    def get_recent_elements(self, days: int) -> list[dict]:
        """
        Returns all relationships added within the past given number of days.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        query = """
        MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity)
        WHERE r.timestamp >= $cutoff
        RETURN a.name AS source_name, a.type AS source_type, 
               r.type AS relationship_type, r.evidence AS evidence, r.timestamp AS timestamp,
               b.name AS target_name, b.type AS target_type
        """
        return self.execute_query(query, {"cutoff": cutoff})

    def close(self):
        """
        Closes the connection and database.
        """
        # Deleting connection and database handles releases the file lock in Kuzu
        if hasattr(self, 'conn'):
            del self.conn
        if hasattr(self, 'db'):
            del self.db
        logger.info(f"Released lock on Kuzu database at: {self.db_path}")
