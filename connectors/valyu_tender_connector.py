import os

import httpx


async def create_tender_research_task(webhook_url: str) -> str:
    api_key = os.getenv("VALYU_API_KEY")
    if not api_key:
        raise EnvironmentError("VALYU_API_KEY is required")

    payload = {
        "query": (
            "Find current public tenders in East and Central Africa relevant to "
            "statistical and qualitative research tools, CRM/ERP systems, cybersecurity, "
            "biometric identity verification, and AI-content-detection software. Return "
            "structured tender records."
        ),
        "mode": "fast",
        "webhook_url": webhook_url,
        "structured_output": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
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
                },
            },
        },
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            "https://api.valyu.ai/v1/deepresearch/tasks",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("deepresearch_id") or data.get("task_id") or ""
