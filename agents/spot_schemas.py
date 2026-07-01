from typing import Literal

from pydantic import BaseModel, Field

class UseCaseRecommendation(BaseModel):
    title: str = Field(description="A concise title for the recommendation, suitable for a CRM Finding record.")
    department: str = Field(description="The department or business unit this recommendation applies to.")
    pain_point: str = Field(description="The description of the pain point identified in the input.")
    proposed_solution: str = Field(description="The proposed solution (process change, tool reconfiguration, statistical analysis, or AI agent).")
    estimated_cost_kes: int = Field(
        description="Estimated cost in Kenyan Shillings (KES). Anchors: diagnostic: 150,000 to 400,000 KES, implementation: 800,000 to 4,000,000 KES, monthly retainer: 80,000 to 350,000 KES."
    )
    optimistic_90_day_roi: str = Field(description="Optimistic 90-day ROI projection (e.g. percentage or monetary value with explanation).")
    conservative_90_day_roi: str = Field(description="Conservative 90-day ROI projection (must always accompany the optimistic ROI).")
    confidence: Literal["high", "medium", "low"] = Field(description="Confidence level based only on the evidence provided in the context.")
    confidence_reasoning: str = Field(description="Plain-language explanation of why this recommendation has the stated confidence level.")
    key_assumptions: list[str] = Field(description="Key assumptions behind both the optimistic and conservative projections.")
    identified_risks: list[str] = Field(description="Key risks identified for this recommendation.")
    applicable_ibm_products: list[str] = Field(description="IBM products that apply to this recommendation, if any.")

class SpotDiagnosticOutput(BaseModel):
    organization_name: str = Field(description="The name of the organization.")
    sector: str = Field(description="The sector of the organization.")
    executive_summary: str = Field(description="A concise executive summary written for a non-technical reader (e.g. CEO).")
    use_cases: list[UseCaseRecommendation] = Field(description="Ranked, evidence-based set of recommendations for high-ROI workflow improvements.")
    organizational_readiness_assessment: str = Field(description="An overall assessment of the organization's readiness for these changes.")
    information_gaps: list[str] = Field(description="Explicit list of information gaps that must be filled before implementation begins.")
