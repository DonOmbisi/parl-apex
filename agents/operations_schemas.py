from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


OperationSeverity = Literal["critical", "high", "medium", "low"]


class EventLogRecord(BaseModel):
    case_id: str = Field(description="Identifier for one process instance, such as a single invoice or purchase order.")
    activity: str = Field(description="Name of the process activity that happened.")
    timestamp: datetime = Field(description="When the activity happened.")
    cost: float | None = Field(default=None, description="Optional cost associated with this case or delay.")
    currency: str | None = Field(default=None, description="Optional currency for the cost field.")
    evidence: str | None = Field(default=None, description="Source record evidence for traceability.")


class ProcessBottleneckMetric(BaseModel):
    source_activity: str
    target_activity: str
    average_delay_hours: float
    worst_case_delay_hours: float
    case_count: int
    estimated_delay_cost: float | None = None
    currency: str | None = None
    evidence: list[str] = Field(default_factory=list)


class OperationsFinding(BaseModel):
    severity: OperationSeverity
    bottleneck_step: str = Field(description="The specific transition or step where delay is concentrated.")
    average_delay_observed: str = Field(description="Plain-language average delay observed.")
    worst_case_delay_observed: str = Field(description="Plain-language worst-case delay observed.")
    estimated_cost_of_delay: str | None = Field(default=None, description="Estimated cost if a cost figure is available.")
    recommended_intervention: str = Field(description="Concrete recommended process intervention.")
    evidence: list[str] = Field(description="Quantitative PM4Py evidence supporting the finding.")


class OperationsAgentOutput(BaseModel):
    organization_name: str
    findings: list[OperationsFinding]
    process_summary: str
    missing_or_uncertain_data: str
