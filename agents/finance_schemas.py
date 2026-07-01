from typing import Literal

from pydantic import BaseModel, Field


FinancialHealth = Literal["critical", "at risk", "stable", "healthy"]
FindingSeverity = Literal["critical", "high", "medium", "low"]


class FinanceFinding(BaseModel):
    severity: FindingSeverity = Field(
        description="Severity of this finance finding: critical, high, medium, or low."
    )
    description: str = Field(
        description="Plain-language description of the specific finance issue or observation."
    )
    evidence: list[str] = Field(
        description="Specific evidence from the knowledge graph supporting this finding."
    )
    recommended_action: str = Field(
        description="Concrete recommended action for the organization."
    )
    time_sensitivity: str = Field(
        description="How urgent this finding is and why."
    )


class FinanceAgentOutput(BaseModel):
    organization_name: str = Field(description="The organization being analyzed.")
    overall_financial_health: FinancialHealth = Field(
        description="Overall financial health: critical, at risk, stable, or healthy."
    )
    health_reasoning: str = Field(
        description="One-sentence reasoning for the overall financial health rating."
    )
    findings: list[FinanceFinding] = Field(
        description="Specific findings about cash risk, budget variance, receivables/payables, and funding compliance where supported by graph evidence."
    )
    top_priority: str = Field(
        description="A single explicit top priority for the organization."
    )
    missing_or_uncertain_data: str = Field(
        description="Honest note about what finance data is still missing or uncertain."
    )
