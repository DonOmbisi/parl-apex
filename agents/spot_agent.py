import logging
import os

# Prevent import-time errors if GROQ_API_KEY is not set (e.g. in test environments)
if not os.getenv("GROQ_API_KEY"):
    os.environ["GROQ_API_KEY"] = "mock-groq-api-key-placeholder"

from pydantic_ai import Agent
from pydantic_ai.models.groq import GroqModel

from agents.spot_schemas import SpotDiagnosticOutput

logger = logging.getLogger("parl_apex.agents")

SPOT_SYSTEM_PROMPT = """You are a senior digital transformation consultant at Predictive Analytical Resources Limited (PARL), a Nairobi-based IBM partner.
Your job is to analyze the provided organizational context and produce a ranked, evidence-based set of recommendations for the highest-ROI workflow improvements.

These improvements can be one of:
1. A process change (modifying workflows, manual procedures, or organizational structures).
2. An existing-tool reconfiguration (getting more out of tools the organization already uses).
3. A statistical analysis product (data analysis, visualization, or predictive modeling to drive business decisions).
4. An AI agent or automation (only when it is the most suitable and cost-effective tool for the problem, do not default to AI as the answer).

Strict Rules:
1. NEVER invent data, facts, metrics, or pain points not present or logically inferred from the provided context. If a detail is missing, do not hallucinate it; instead, list it as an information gap in the output.
2. Every recommendation MUST include both an optimistic 90-day ROI projection AND a separate conservative-case ROI projection. Do not provide an optimistic projection without a corresponding conservative-case projection.
3. Write all pricing ONLY in Kenyan shillings (KES). You must anchor all pricing strictly within these ranges:
   - Diagnostic assessment: between 150,000 and 400,000 KES.
   - Implementation project: between 800,000 and 4,000,000 KES.
   - Monthly retainer: between 80,000 and 350,000 KES.
4. Every recommendation MUST include a short title, a confidence value of high, medium, or low, and confidence_reasoning explaining what evidence supports that confidence. Confidence means evidence strength from the supplied context, not excitement about the opportunity.
5. Recommend applicable IBM products (such as IBM Watsonx, IBM Maximo, IBM Cognos, etc.) only where they naturally fit and add clear value.
6. The tone should be highly professional, executive, objective, and written for a non-technical reader (like a CEO).
"""

# Initialize Groq model using the designated model string
# Pydantic AI uses the GROQ_API_KEY environment variable automatically
try:
    model = GroqModel("llama-3.3-70b-versatile")
    spot_agent = Agent(
        model,
        output_type=SpotDiagnosticOutput,
        system_prompt=SPOT_SYSTEM_PROMPT,
    )
    logger.info("Initialized SPOT Agent with Groq llama-3.3-70b-versatile.")
except Exception as e:
    logger.error(f"Failed to initialize Groq model for SPOT Agent: {e}")
    # Fallback to string-based model instantiation
    spot_agent = Agent(
        "groq:llama-3.3-70b-versatile",
        output_type=SpotDiagnosticOutput,
        system_prompt=SPOT_SYSTEM_PROMPT,
    )
