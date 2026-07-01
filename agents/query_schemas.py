from typing import Literal

from pydantic import BaseModel, Field


AnswerConfidence = Literal["high", "medium", "low", "insufficient"]


class QueryEvidence(BaseModel):
    source_name: str
    source_type: str
    relationship_type: str
    target_name: str
    target_type: str
    evidence: str
    timestamp: str | None = None


class QueryAgentOutput(BaseModel):
    client_identifier: str
    question: str
    answer: str = Field(
        description="Direct answer to the user's question. Say clearly if the graph is insufficient."
    )
    confidence: AnswerConfidence
    supporting_evidence: list[QueryEvidence] = Field(
        description="Specific graph entries that support the answer."
    )
    missing_information: str = Field(
        description="What information is missing or uncertain, especially when confidence is low or insufficient."
    )
