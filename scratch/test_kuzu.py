import kuzu
import shutil
import os
import tempfile

# Use a temporary directory for testing
temp_dir = tempfile.mkdtemp()
db_path = os.path.join(temp_dir, "test_kuzu_db")

print(f"Initializing test database at {db_path}...")
db = kuzu.Database(db_path)
conn = kuzu.Connection(db)

# Create schema
conn.execute("CREATE NODE TABLE Entity(name STRING, type STRING, PRIMARY KEY(name))")
conn.execute("CREATE REL TABLE RELATES_TO(FROM Entity TO Entity, type STRING, evidence STRING, timestamp TIMESTAMP)")
print("Schema created successfully.")

# Test MERGE
conn.execute(
    "MERGE (a:Entity {name: $name}) ON CREATE SET a.type = $type",
    {"name": "Alice", "type": "Person"}
)
conn.execute(
    "MERGE (a:Entity {name: $name}) ON CREATE SET a.type = $type",
    {"name": "Bob", "type": "Person"}
)
print("Entities merged successfully.")

# Test creating relationship
# Kuzu supports TIMESTAMP, so let's pass a timestamp value
# Kuzu timestamp can be created from datetime, or we can use an integer representing microseconds, or use date/timestamp function
# Let's test passing a timestamp. In Kuzu, we can insert it or set it.
# Let's see if we can use a timestamp.
# Let's pass a timestamp in milliseconds or microseconds, or string representation?
# Kuzu's TIMESTAMP is usually represented as a datetime object in python, or int. Let's try passing a datetime.
import datetime
now = datetime.datetime.now()

conn.execute(
    "MATCH (a:Entity {name: $src}), (b:Entity {name: $dst}) "
    "MERGE (a)-[r:RELATES_TO]->(b) "
    "ON CREATE SET r.type = $rel_type, r.evidence = $evidence, r.timestamp = $timestamp",
    {"src": "Alice", "dst": "Bob", "rel_type": "KNOWS", "evidence": "Met at a conference", "timestamp": now}
)
print("Relationship merged successfully.")

# Query back
result = conn.execute("MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity) RETURN a.name, r.type, b.name, r.evidence, r.timestamp")
while result.has_next():
    print("Row:", result.get_next())

# Clean up
del conn
del db
try:
    shutil.rmtree(temp_dir)
    print("Cleaned up temporary database.")
except Exception as e:
    print(f"Failed to clean up: {e}")
