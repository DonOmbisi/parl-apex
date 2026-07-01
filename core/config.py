from pydantic import BaseModel, Field

class ConnectorConfig(BaseModel):
    type: str
    credentials_ref: str
    schedule: str  # Cron string, e.g. "0 9 * * *"

class AgentConfig(BaseModel):
    name: str
    schedule: str
    recent_days: int = 7

class ClientConfig(BaseModel):
    name: str
    sector: str
    connectors: list[ConnectorConfig] = Field(default_factory=list)
    agents: list[str | AgentConfig] = Field(default_factory=list)
    graph_path: str | None = None
