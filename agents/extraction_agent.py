import logging
import os
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.groq import GroqModel

logger = logging.getLogger("parl_apex.agents")

class StructuredFindings(BaseModel):
    sector: str | None = Field(
        description="The sector of the organization, if identifiable from the research (e.g. Healthcare, Agriculture, Non-Profit, Retail)."
    )
    description: str = Field(description="A brief description of what the organization does.")
    funding_sources: list[str] = Field(description="Entities, donors, or revenue sources that fund the organization.")
    technologies: list[str] = Field(description="Systems, software, or technology platforms mentioned in the research.")
    challenges: list[str] = Field(description="Challenges, pain points, or operational bottlenecks identified.")
    strategic_priorities: list[str] = Field(description="Strategic priorities, future goals, or vision areas.")

EXTRACTION_SYSTEM_PROMPT = """You are an expert data extraction agent at Predictive Analytical Resources Limited (PARL).
Your job is to analyze the provided raw company research report and extract key structured findings.

Strict Rules:
1. Extract ONLY facts that are present in the report. Do not invent any names, technologies, funding sources, or challenges.
2. Keep the extracted items concise and descriptive (e.g. "Oracle ERP" for technology, or "High staff turnover in logistics" for challenge).
3. If a field like 'funding_sources' or 'technologies' is not mentioned in the report, return an empty list. Do not hallucinate.
"""

# Prevent import-time errors if GROQ_API_KEY is not set
if not os.getenv("GROQ_API_KEY"):
    os.environ["GROQ_API_KEY"] = "mock-groq-api-key-placeholder"

try:
    model = GroqModel("llama-3.3-70b-versatile")
    extraction_agent = Agent(
        model,
        output_type=StructuredFindings,
        system_prompt=EXTRACTION_SYSTEM_PROMPT,
    )
    logger.info("Initialized Extraction Agent with Groq llama-3.3-70b-versatile.")
except Exception as e:
    logger.error(f"Failed to initialize Groq model for Extraction Agent: {e}")
    extraction_agent = Agent(
        "groq:llama-3.3-70b-versatile",
        output_type=StructuredFindings,
        system_prompt=EXTRACTION_SYSTEM_PROMPT,
    )
