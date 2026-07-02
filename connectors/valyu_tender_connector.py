"""Valyu deep-research connector for tender discovery.

Uses the official Valyu Python SDK (``pip install valyu``) which
authenticates via the ``x-api-key`` header — the same mechanism used by
the ``valyu-js`` SDK in Consult Ralph.

The previous raw-httpx implementation sent ``Authorization: Bearer …``
which the Valyu API does not recognise, resulting in 401 errors.
"""

import asyncio
import os
from functools import lru_cache

from valyu import Valyu

# ---------------------------------------------------------------------------
# Constants — unchanged from the original implementation
# ---------------------------------------------------------------------------

TENDER_RESEARCH_QUERY = (
    "Find current open government and NGO tenders in Kenya, Uganda, Tanzania, Rwanda, and Ethiopia "
    "issued in the last 30 days, specifically for: statistical software (SPSS, Stata, NVivo, MAXQDA), "
    "data analytics platforms, cybersecurity solutions, CRM/ERP implementation, and biometric identity "
    "verification. For each tender include the official reference number, issuing organization, exact "
    "submission deadline, estimated contract value, and direct URL to the official tender notice on "
    "government procurement portals (tenders.go.ke, icta.go.ke, treasury.go.ke, egpkenya.go.ke, "
    "PPDA Uganda) or international donor portals (UNDP, World Bank, USAID). "
    "Exclude tenders whose deadlines have already passed."
)

TENDER_SCHEMA = {
    "title": {"type": "string"},
    "reference_number": {"type": "string"},
    "issuing_entity": {"type": "string"},
    "category": {"type": "string"},
    "deadline": {"type": "string"},
    "estimated_value": {"type": "number"},
    "estimated_value_currency": {"type": "string"},
    "bid_security_amount": {"type": "number"},
    "status": {"type": "string"},
    "description": {"type": "string"},
    "source_url": {"type": "string"},
    "source_confidence_tier": {"type": "string"},
}


# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _get_valyu_client() -> Valyu:
    """Return a singleton Valyu client, mirroring Consult Ralph's
    ``new Valyu(getValyuApiKey())`` pattern.

    The SDK reads ``VALYU_API_KEY`` from the environment automatically if
    no ``api_key`` argument is passed, but we pass it explicitly for
    clarity and to produce a better error message when it is missing.
    """
    api_key = os.getenv("VALYU_API_KEY")
    if not api_key:
        raise EnvironmentError("VALYU_API_KEY is required")
    return Valyu(api_key=api_key)


# ---------------------------------------------------------------------------
# Public API — signature unchanged so callers (run_tender_test.py etc.)
# continue to work without modification.
# ---------------------------------------------------------------------------

async def create_tender_research_task(webhook_url: str) -> str:
    """Create a Valyu deep-research task for tender discovery.

    Mirrors Consult Ralph's self-hosted path::

        const valyu = new Valyu(getValyuApiKey());
        return valyu.deepresearch.create(options);

    The SDK is synchronous (``requests``-based), so we run it in an
    executor to keep the FastAPI event-loop unblocked.
    """
    client = _get_valyu_client()

    def _call() -> str:
        response = client.deepresearch.create(
            query=TENDER_RESEARCH_QUERY,
            mode="standard",
            webhook_url=webhook_url,
            output_formats=[{
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": TENDER_SCHEMA,
                },
            }],
        )

        if not response.success:
            raise RuntimeError(
                f"Valyu deepresearch.create failed: {response.error}"
            )

        # The response object exposes deepresearch_id as an attribute
        task_id = getattr(response, "deepresearch_id", None) or ""
        return task_id

    # Run the synchronous SDK call in a thread so we don't block the
    # async event-loop.
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _call)
