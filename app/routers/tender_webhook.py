import logging
import os
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request

from agents.tender_scoring_agent import score_tender
from connectors.espocrm_connector import flag_disappeared_tenders, upsert_tender_record

logger = logging.getLogger("parl_apex.routers.tender_webhook")

router = APIRouter(prefix="/webhooks/valyu", tags=["webhooks"])


def _extract_tenders(payload: dict[str, Any]) -> list[dict]:
    for key in ("tenders", "results", "structured_output", "output"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict) and isinstance(value.get("tenders"), list):
            return [item for item in value["tenders"] if isinstance(item, dict)]
    return []


@router.post("/tender-research")
async def tender_research_webhook(
    request: Request,
    x_valyu_webhook_secret: str | None = Header(default=None),
):
    expected_secret = os.getenv("VALYU_WEBHOOK_SECRET")
    if expected_secret and x_valyu_webhook_secret != expected_secret:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    payload = await request.json()
    tenders = _extract_tenders(payload)
    results = []
    seen_reference_numbers: list[str] = []

    for tender in tenders:
        if tender.get("reference_number"):
            seen_reference_numbers.append(tender["reference_number"])

        score = await score_tender(tender)
        scored_tender = {
            **tender,
            "win_likelihood_score": score.win_likelihood_score,
            "win_likelihood_reasoning": score.win_likelihood_reasoning,
            "source_site": "valyu-deep-research",
        }
        outcome = await upsert_tender_record(scored_tender)
        results.append(
            {
                "reference_number": tender.get("reference_number"),
                "source_url": tender.get("source_url"),
                "outcome": outcome,
                "win_likelihood_score": score.win_likelihood_score,
            }
        )

    try:
        disappeared = await flag_disappeared_tenders(
            seen_reference_numbers=seen_reference_numbers,
            source_site="valyu-deep-research",
        )
        logger.info("Tender disappearance handling flagged/noted: %s", disappeared)
    except Exception as e:
        disappeared = []
        logger.error("Tender disappearance handling failed: %s", e, exc_info=True)

    return {
        "status": "success",
        "processed": len(results),
        "results": results,
        "disappeared_flagged_or_noted": disappeared,
    }
