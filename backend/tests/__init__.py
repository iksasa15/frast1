import os

os.environ.setdefault("INGEST_TOKEN", "test-only-ingest-token")
os.environ.setdefault("LAB_AGENT_TOKEN", "test-only-agent-token")
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("TOPOLOGY_PATH", "../configs/topology.json")
