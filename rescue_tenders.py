"""rescue_tenders.py — A one-off script to fix Valyu's formatting issue.

Valyu has been stuffing all the tender details into the `title` field instead of 
properly filling out the JSON schema (leaving `deadline` blank). 

This script uses the project's existing Pydantic AI Groq integration to 
parse the messy `tender_result.json` back into the correct schema, and then 
writes the clean tenders directly to EspoCRM.

Usage:
    uv run python rescue_tenders.py
"""

import json
import os
import sys
import httpx
from datetime import date
from dotenv import load_dotenv
from pydantic import BaseModel
from pydantic_ai import Agent

load_dotenv()

ESPOCRM_BASE_URL = os.environ.get("ESPOCRM_BASE_URL", "http://100.81.131.67")
ESPOCRM_API_KEY = os.environ.get("ESPOCRM_TENDER_API_KEY", "")

# ---------------------------------------------------------------------------
# LLM Extraction setup
# ---------------------------------------------------------------------------

class ExtractedTender(BaseModel):
    title: str | None = None
    reference_number: str | None = None
    issuing_entity: str | None = None
    category: str | None = None
    deadline: str | None = None
    estimated_value: float | None = None
    estimated_value_currency: str | None = None
    bid_security_amount: float | None = None
    status: str | None = None
    description: str | None = None
    source_url: str | None = None
    source_confidence_tier: str | None = None

class RescueResponse(BaseModel):
    tenders: list[ExtractedTender]

agent = Agent(
    "groq:llama-3.3-70b-versatile",
    output_type=RescueResponse,
    system_prompt=(
        "You are a structured data extractor. "
        "The user will provide messy JSON where all the tender details are stuffed into the `title` field. "
        "Extract the real title, deadline, reference number, issuing entity, category, status, "
        "and source URL into the proper fields. Format the deadline clearly (e.g. YYYY-MM-DD or Unknown). "
        "If a field is not present in the text, leave it null."
    )
)

# ---------------------------------------------------------------------------
# Rescue and Write
# ---------------------------------------------------------------------------

async def main():
    if not os.path.exists("tender_result.json"):
        print("Could not find tender_result.json. Please run process_tenders.py first.")
        sys.exit(1)

    print("Loading messy Valyu output...")
    with open("tender_result.json", "r", encoding="utf-8") as f:
        messy_data = json.load(f)

    # Some outputs have it at root, some under 'tenders'
    if isinstance(messy_data, dict):
        raw_list = messy_data.get("tenders", []) or list(messy_data.values())[0]
    else:
        raw_list = messy_data

    print(f"Found {len(raw_list)} messy tenders. Asking LLaMA-3.3 to restructure them...")
    
    # We pass the raw list to the LLM to structure
    result = await agent.run(json.dumps(raw_list))
    clean_tenders = result.output.tenders

    print(f"\nSuccessfully cleaned {len(clean_tenders)} tenders. Preview:")
    for t in clean_tenders:
        print(f"  ✓ {t.title[:60]}... | Deadline: {t.deadline} | Ref: {t.reference_number}")

    if not ESPOCRM_API_KEY:
        print("\n[!] ESPOCRM_TENDER_API_KEY not set — skipping CRM write.")
        sys.exit(0)

    print("\nWriting to EspoCRM...")
    headers = {"X-Api-Key": ESPOCRM_API_KEY, "Content-Type": "application/json"}
    
    written = 0
    failed = 0

    # Since we are using an async script, we can just use httpx synchronously for simplicity 
    # or just use AsyncClient.
    async with httpx.AsyncClient() as client:
        for t in clean_tenders:
            payload = {
                "name": t.title or "Untitled Tender",
                "cReferenceNumber": t.reference_number or "",
                "cIssuingEntity": t.issuing_entity or "",
                "cCategory": t.category or "",
                "cDeadline": t.deadline or "",
                "cEstimatedValue": t.estimated_value,
                "cEstimatedValueCurrency": t.estimated_value_currency or "",
                "cBidSecurityAmount": t.bid_security_amount,
                "cStatus": t.status or "Active",
                "description": t.description or "",
                "cSourceUrl": t.source_url or "",
                "cSourceConfidenceTier": t.source_confidence_tier or "Tier 4",
            }
            # Remove nulls
            payload = {k: v for k, v in payload.items() if v is not None}
            
            try:
                resp = await client.post(
                    f"{ESPOCRM_BASE_URL}/api/v1/CTender",
                    headers=headers,
                    json=payload,
                    timeout=15.0,
                )
                if resp.status_code in (200, 201):
                    written += 1
                    print(f"  [v] Written: {payload['name'][:70]}")
                else:
                    failed += 1
                    print(f"  [x] Failed ({resp.status_code}): {payload['name'][:70]}")
                    print(f"    Response: {resp.text[:200]}")
            except Exception as exc:
                failed += 1
                print(f"  [x] Error writing '{payload['name'][:70]}': {exc}")

    print(f"\nDone! Written: {written} | Failed: {failed}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
