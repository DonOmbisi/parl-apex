from pydantic import BaseModel, Field


class CorrelationFinding(BaseModel):
    contributing_sources: list[str] = Field(
        description="At least two departments, connectors, or specialist-agent sources contributing evidence."
    )
    visible_symptom: str = Field(
        description="Plain-language symptom visible across the contributing sources."
    )
    hidden_root_cause: str = Field(
        description="Plain-language root cause that plausibly connects the different sources."
    )
    evidence_by_source: dict[str, list[str]] = Field(
        description="Specific evidence drawn from each contributing source."
    )
    time_to_serious_problem: str = Field(
        description="Estimated time until this becomes serious if unaddressed."
    )
    recommended_intervention: str = Field(
        description="Recommended cross-functional intervention."
    )
    urgency_rank: int = Field(
        ge=1,
        description="Rank by urgency, with 1 being most urgent.",
    )


class CorrelationEngineOutput(BaseModel):
    organization_name: str
    correlations: list[CorrelationFinding]
    synthesis_summary: str = Field(
        description="Brief summary of what was correlated and what was not."
    )
    insufficient_evidence_note: str = Field(
        description="Honest note about missing sources or why some patterns were not treated as correlations."
    )
