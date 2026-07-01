from datetime import date
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger("parl_apex.connectors.espocrm")

ESPOCRM_TENDER_ENTITY = "Tender"
ESPOCRM_FINDING_ENTITY = "CFinding"
ESPOCRM_ACCOUNT_ENTITY = "Account"
HUMAN_OWNED_FIELDS = {"status", "assignedUserId"}


def _base_url() -> str:
    base_url = os.getenv("ESPOCRM_BASE_URL", "").rstrip("/")
    if not base_url:
        raise EnvironmentError("ESPOCRM_BASE_URL is required")
    return base_url


def _headers() -> dict[str, str]:
    api_key = os.getenv("ESPOCRM_TENDER_API_KEY")
    if not api_key:
        raise EnvironmentError("ESPOCRM_TENDER_API_KEY is required")
    return {"X-Api-Key": api_key, "Content-Type": "application/json"}


def _finding_headers() -> dict[str, str]:
    api_key = os.getenv("ESPOCRM_FINDING_API_KEY")
    if not api_key:
        raise EnvironmentError("ESPOCRM_FINDING_API_KEY is required")
    return {"X-Api-Key": api_key, "Content-Type": "application/json"}


def _entity_url(entity: str = ESPOCRM_TENDER_ENTITY) -> str:
    return f"{_base_url()}/api/v1/{entity}"


def _record_url(record_id: str) -> str:
    return f"{_entity_url()}/{record_id}"


def _entity_record_url(entity: str, record_id: str) -> str:
    return f"{_entity_url(entity)}/{record_id}"


def _espocrm_list(data: Any) -> list[dict]:
    if isinstance(data, dict):
        if isinstance(data.get("list"), list):
            return data["list"]
        if isinstance(data.get("records"), list):
            return data["records"]
    if isinstance(data, list):
        return data
    return []


def _tender_payload(tender: dict, include_score: bool = True, status: str | None = None) -> dict:
    payload = {
        "name": tender.get("title") or tender.get("reference_number") or tender.get("source_url"),
        "title": tender.get("title"),
        "referenceNumber": tender.get("reference_number"),
        "issuingEntity": tender.get("issuing_entity"),
        "category": tender.get("category"),
        "deadline": tender.get("deadline"),
        "estimatedValue": tender.get("estimated_value"),
        "estimatedValueCurrency": tender.get("estimated_value_currency"),
        "bidSecurityAmount": tender.get("bid_security_amount"),
        "description": tender.get("description"),
        "sourceURL": tender.get("source_url"),
        "sourceSite": tender.get("source_site", "valyu-deep-research"),
        "sourceConfidenceTier": tender.get("source_confidence_tier"),
    }
    if status is not None:
        payload["status"] = status
    if include_score:
        payload["winLikelihoodScore"] = tender.get("win_likelihood_score")
        payload["winLikelihoodReasoning"] = tender.get("win_likelihood_reasoning")
    return {key: value for key, value in payload.items() if value is not None}


async def _find_existing_tender(client: httpx.AsyncClient, tender: dict) -> dict | None:
    reference_number = (tender.get("reference_number") or "").strip()
    source_url = (tender.get("source_url") or "").strip()

    if reference_number:
        where = [{"type": "equals", "attribute": "referenceNumber", "value": reference_number}]
    elif source_url:
        where = [{"type": "equals", "attribute": "sourceURL", "value": source_url}]
    else:
        return None

    response = await client.get(_entity_url(), params={"where": where, "maxSize": 1})
    response.raise_for_status()
    records = _espocrm_list(response.json())
    return records[0] if records else None


def _use_case_value(use_case: Any, field: str, default: Any = None) -> Any:
    if isinstance(use_case, dict):
        return use_case.get(field, default)
    return getattr(use_case, field, default)


def _finding_severity(use_case: Any) -> str:
    confidence = str(_use_case_value(use_case, "confidence", "") or "").strip().lower()
    if confidence == "high":
        return "High"
    if confidence == "medium":
        return "Medium"
    return "Low"


def _finding_evidence(use_case: Any) -> str:
    confidence_reasoning = _use_case_value(use_case, "confidence_reasoning", None)
    key_assumptions = _use_case_value(use_case, "key_assumptions", []) or []
    evidence_parts = []
    if confidence_reasoning:
        evidence_parts.append(f"Confidence reasoning: {confidence_reasoning}")
    if key_assumptions:
        evidence_parts.append("Key assumptions: " + "; ".join(str(item) for item in key_assumptions))
    return "\n".join(evidence_parts)


async def _find_account_by_name(client: httpx.AsyncClient, organization_name: str) -> dict | None:
    exact_params = {
        "where[0][type]": "equals",
        "where[0][attribute]": "name",
        "where[0][value]": organization_name,
        "maxSize": 1,
    }
    response = await client.get(
        _entity_url(ESPOCRM_ACCOUNT_ENTITY),
        params=exact_params,
    )
    response.raise_for_status()
    records = _espocrm_list(response.json())
    if records:
        return records[0]

    contains_params = {
        "where[0][type]": "contains",
        "where[0][attribute]": "name",
        "where[0][value]": organization_name,
        "maxSize": 1,
    }
    response = await client.get(
        _entity_url(ESPOCRM_ACCOUNT_ENTITY),
        params=contains_params,
    )
    response.raise_for_status()
    records = _espocrm_list(response.json())
    return records[0] if records else None


async def create_finding_record(use_case: Any, organization_name: str) -> str:
    title = (
        _use_case_value(use_case, "title")
        or _use_case_value(use_case, "ai_solution")
        or _use_case_value(use_case, "proposed_solution")
        or "SPOT Finding"
    )
    pain_point = _use_case_value(use_case, "pain_point", "") or ""
    ai_solution = (
        _use_case_value(use_case, "ai_solution")
        or _use_case_value(use_case, "proposed_solution")
        or ""
    )
    description = f"Pain point: {pain_point} Proposed solution: {ai_solution}".strip()

    payload = {
        "name": title,
        "agentSource": "SPOT",
        "description": description,
        "evidence": _finding_evidence(use_case),
        "recommendedAction": ai_solution,
        "severity": _finding_severity(use_case),
        "status": "New",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0, headers=_finding_headers()) as client:
            account = await _find_account_by_name(client, organization_name)
            if account and account.get("id"):
                payload["accountId"] = account["id"]

            response = await client.post(
                _entity_url(ESPOCRM_FINDING_ENTITY),
                json={key: value for key, value in payload.items() if value not in (None, "")},
            )
            response.raise_for_status()
            data = response.json()
            return data.get("id", "")
    except Exception as e:
        logger.error(
            "Failed to create EspoCRM Finding for use_case=%s organization=%s: %s",
            title,
            organization_name,
            e,
            exc_info=True,
        )
        return ""


async def upsert_tender_record(tender: dict) -> str:
    async with httpx.AsyncClient(timeout=30.0, headers=_headers()) as client:
        existing = await _find_existing_tender(client, tender)

        if not existing:
            response = await client.post(
                _entity_url(),
                json=_tender_payload(tender, include_score=True, status="New"),
            )
            response.raise_for_status()
            return "created"

        existing_description = existing.get("description") or ""
        new_description = tender.get("description") or ""
        record_id = existing.get("id")
        if not record_id:
            raise ValueError("Existing EspoCRM tender record did not include an id")

        if existing_description == new_description:
            response = await client.patch(
                _record_url(record_id),
                json={
                    "deadline": tender.get("deadline"),
                    "estimatedValue": tender.get("estimated_value"),
                    "estimatedValueCurrency": tender.get("estimated_value_currency"),
                },
            )
            response.raise_for_status()
            return "unchanged"

        response = await client.patch(
            _record_url(record_id),
            json={
                "deadline": tender.get("deadline"),
                "estimatedValue": tender.get("estimated_value"),
                "estimatedValueCurrency": tender.get("estimated_value_currency"),
                "description": new_description,
                "winLikelihoodScore": tender.get("win_likelihood_score"),
                "winLikelihoodReasoning": tender.get("win_likelihood_reasoning"),
            },
        )
        response.raise_for_status()
        return "updated"


async def flag_disappeared_tenders(seen_reference_numbers: list[str], source_site: str) -> list[str]:
    seen = {value for value in seen_reference_numbers if value}
    today = date.today().isoformat()
    flagged: list[str] = []
    where = [
        {"type": "equals", "attribute": "sourceSite", "value": source_site},
        {
            "type": "notIn",
            "attribute": "status",
            "value": ["Won", "Lost", "Not Pursuing"],
        },
    ]

    async with httpx.AsyncClient(timeout=30.0, headers=_headers()) as client:
        response = await client.get(_entity_url(), params={"where": where, "maxSize": 200})
        response.raise_for_status()

        for record in _espocrm_list(response.json()):
            reference_number = record.get("referenceNumber") or record.get("sourceURL")
            if not reference_number or reference_number in seen:
                continue

            record_id = record.get("id")
            if not record_id:
                continue

            status = record.get("status") or ""
            description = record.get("description") or ""

            if status in {"New", "Under Review"}:
                note = f"[Auto-flagged {today}: listing no longer found on source site]"
                payload = {
                    "status": "Not Pursuing",
                    "description": f"{description}\n\n{note}".strip(),
                }
            elif status in {"Pursuing", "Submitted"}:
                note = (
                    f"[Auto-note {today}: listing no longer found on source site - "
                    "tender may have closed; status left unchanged for review]"
                )
                payload = {"description": f"{description}\n\n{note}".strip()}
            else:
                continue

            patch_response = await client.patch(_record_url(record_id), json=payload)
            patch_response.raise_for_status()
            flagged.append(reference_number)

    return flagged
