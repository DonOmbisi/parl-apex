"""process_tenders.py — one-off script: fetch a completed Valyu task,
normalise the output, filter out unusable tenders, and write good ones
to EspoCRM.

Usage:
    uv run python process_tenders.py <deepresearch_id>

If no argument is given it falls back to the last known task ID.
"""

import json
import os
import sys
from datetime import date, datetime

from dotenv import load_dotenv

load_dotenv()

from valyu import Valyu

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

TASK_ID = sys.argv[1] if len(sys.argv) > 1 else "de2474f0-0036-43cd-8995-3d2910b4e735"
ESPOCRM_BASE_URL = os.environ.get("ESPOCRM_BASE_URL", "http://100.81.131.67")
ESPOCRM_API_KEY = os.environ.get("ESPOCRM_TENDER_API_KEY", "")

# ---------------------------------------------------------------------------
# Fetch result from Valyu
# ---------------------------------------------------------------------------

valyu = Valyu(os.environ["VALYU_API_KEY"])
result = valyu.deepresearch.status(TASK_ID)

print("Status  :", result.status)
print("Progress:", getattr(result, "progress", "N/A"))

raw_output = result.output
print("\nOutput type:", type(raw_output))
print("Raw output preview (first 1000 chars):")
print(str(raw_output)[:1000])

# ---------------------------------------------------------------------------
# Normalise: both list and dict shapes are supported
# ---------------------------------------------------------------------------

if isinstance(raw_output, list):
    tenders: list = raw_output
elif isinstance(raw_output, dict):
    # The model may have placed the array under "tenders", "items", or the root
    tenders = (
        raw_output.get("tenders")
        or raw_output.get("items")
        or raw_output.get("results")
        or []
    )
    # Some outputs embed the schema + data under a top-level key; try first value
    if not tenders:
        for v in raw_output.values():
            if isinstance(v, list):
                tenders = v
                break
else:
    tenders = []

print(f"\nTotal tenders before filtering: {len(tenders)}")

# Save full raw output for inspection
with open("tender_result.json", "w", encoding="utf-8") as f:
    json.dump(raw_output, f, indent=2, ensure_ascii=False)
print("Full output saved to tender_result.json")

# ---------------------------------------------------------------------------
# Filter: remove tenders with no usable deadline or a past deadline
# ---------------------------------------------------------------------------

TODAY = date.today()
SKIP_DEADLINES = {"unknown", "n/a", "closed", "none", "", "soon"}


def _deadline_is_valid(deadline_str: str) -> bool:
    """Return True if the deadline is a future date we can parse."""
    if not deadline_str:
        return False
    dl = deadline_str.strip().lower()
    if dl in SKIP_DEADLINES:
        return False
    # Try to parse as a date
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            parsed = datetime.strptime(deadline_str.strip(), fmt).date()
            return parsed >= TODAY
        except ValueError:
            continue
    # If we can't parse it but it's not in the skip list, keep it with a warning
    print(f"  ⚠  Could not parse deadline '{deadline_str}' — keeping anyway")
    return True


usable: list = []
skipped: list = []

for t in tenders:
    if not isinstance(t, dict):
        skipped.append(t)
        continue
    dl = t.get("deadline", "")
    if _deadline_is_valid(dl):
        usable.append(t)
    else:
        skipped.append(t)
        print(f"  ✗  Skipped (deadline='{dl}'): {t.get('title', 'NO TITLE')[:80]}")

print(f"\nUsable tenders (valid future deadline): {len(usable)}")
print(f"Skipped tenders:                        {len(skipped)}")

# ---------------------------------------------------------------------------
# Preview usable tenders
# ---------------------------------------------------------------------------

for i, t in enumerate(usable, 1):
    print(
        f"\n  [{i}] {t.get('title', 'NO TITLE')[:80]}\n"
        f"       Ref: {t.get('reference_number', '—')} | "
        f"Entity: {t.get('issuing_entity', '—')[:50]}\n"
        f"       Deadline: {t.get('deadline', '—')} | "
        f"Category: {t.get('category', '—')}"
    )

# ---------------------------------------------------------------------------
# Write to EspoCRM
# ---------------------------------------------------------------------------

if not usable:
    print("\nNo usable tenders to write — done.")
    sys.exit(0)

if not ESPOCRM_API_KEY:
    print("\n⚠  ESPOCRM_TENDER_API_KEY not set — skipping CRM write.")
    sys.exit(0)

import httpx

ESPOCRM_HEADERS = {
    "X-Api-Key": ESPOCRM_API_KEY,
    "Content-Type": "application/json",
}

written = 0
failed = 0

for t in usable:
    payload = {
        "name": t.get("title", "Untitled Tender"),
        "cReferenceNumber": t.get("reference_number") or "",
        "cIssuingEntity": t.get("issuing_entity") or "",
        "cCategory": t.get("category") or "",
        "cDeadline": t.get("deadline") or "",
        "cEstimatedValue": t.get("estimated_value"),
        "cEstimatedValueCurrency": t.get("estimated_value_currency") or "",
        "cBidSecurityAmount": t.get("bid_security_amount"),
        "cStatus": t.get("status") or "Active",
        "description": t.get("description") or "",
        "cSourceUrl": t.get("source_url") or "",
        "cSourceConfidenceTier": t.get("source_confidence_tier") or "",
    }
    # Remove None values — EspoCRM doesn't accept null for numeric fields
    payload = {k: v for k, v in payload.items() if v is not None}

    try:
        resp = httpx.post(
            f"{ESPOCRM_BASE_URL}/api/v1/CTender",
            headers=ESPOCRM_HEADERS,
            json=payload,
            timeout=15.0,
        )
        if resp.status_code in (200, 201):
            written += 1
            print(f"  ✓ Written: {payload['name'][:70]}")
        else:
            failed += 1
            print(f"  ✗ Failed ({resp.status_code}): {payload['name'][:70]}")
            print(f"    Response: {resp.text[:200]}")
    except Exception as exc:
        failed += 1
        print(f"  ✗ Error writing '{payload['name'][:70]}': {exc}")

print(f"\n{'='*60}")
print(f"Written: {written}  |  Failed: {failed}  |  Skipped: {len(skipped)}")