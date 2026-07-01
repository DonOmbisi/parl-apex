import json
import logging
import os

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.groq import GroqModel

logger = logging.getLogger("parl_apex.agents.tender_scoring")

PARL_BUSINESS_CONTEXT = """\
PARL vendor and product portfolio:
- Statistical and qualitative research tools.
- CRM and ERP systems.
- Cybersecurity products.
- Biometric identity verification.
- AI-content-detection software.

PARL sector focus:
- NGOs.
- Universities.
- Financial institutions.
- Government agencies.
- East and Central Africa.

Historical tender win/loss data:
- None is currently available. Scores are not calibrated against past PARL outcomes.
"""

TENDER_SCORING_SYSTEM_PROMPT = f"""You are PARL's tender fit scoring agent.
Use PARL's business context to judge whether a tender fits PARL's portfolio and target sectors.

{PARL_BUSINESS_CONTEXT}

Rules:
1. Return a win_likelihood_score from 0 to 100.
2. Explain the score in plain language.
3. Because no historical win/loss data is available, the reasoning must explicitly say the score is based on category and sector fit only, not calibrated against past outcomes.
4. If the tender requests a product category PARL has no partnership or capability for, score it low and name the specific missing capability.
5. Do not invent PARL capabilities or past performance.
6. Do not fake confidence; explain uncertainty plainly when tender details are incomplete.
"""


class TenderScore(BaseModel):
    win_likelihood_score: int = Field(ge=0, le=100)
    win_likelihood_reasoning: str


if not os.getenv("GROQ_API_KEY"):
    os.environ["GROQ_API_KEY"] = "mock-groq-api-key-placeholder"

try:
    model = GroqModel("llama-3.3-70b-versatile")
    tender_scoring_agent = Agent(
        model,
        output_type=TenderScore,
        system_prompt=TENDER_SCORING_SYSTEM_PROMPT,
    )
except Exception as e:
    logger.error("Failed to initialize tender scoring Groq model: %s", e)
    tender_scoring_agent = Agent(
        "groq:llama-3.3-70b-versatile",
        output_type=TenderScore,
        system_prompt=TENDER_SCORING_SYSTEM_PROMPT,
    )


async def score_tender(tender: dict) -> TenderScore:
    prompt = (
        "Score this tender for PARL. Use only the provided tender fields and PARL context.\n\n"
        f"{json.dumps(tender, ensure_ascii=True, indent=2)}"
    )
    result = await tender_scoring_agent.run(prompt)
    return result.output
