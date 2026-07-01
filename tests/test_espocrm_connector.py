from datetime import date

import pytest

from connectors import espocrm_connector


class FakeResponse:
    def __init__(self, data=None, status_code=200):
        self._data = data if data is not None else {}
        self.status_code = status_code

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise espocrm_connector.httpx.HTTPStatusError(
                "EspoCRM error",
                request=espocrm_connector.httpx.Request("POST", "https://crm.example.test"),
                response=espocrm_connector.httpx.Response(self.status_code),
            )
        return None


class FakeEspoClient:
    responses = []
    calls = []

    def __init__(self, *args, **kwargs):
        self.init_args = args
        self.init_kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, url, params=None):
        self.calls.append(("get", url, params))
        return FakeResponse(self.responses.pop(0))

    async def post(self, url, json=None):
        self.calls.append(("post", url, json))
        response = self.responses.pop(0) if self.responses else {"id": "new-id"}
        if isinstance(response, tuple):
            data, status_code = response
            return FakeResponse(data, status_code=status_code)
        return FakeResponse(response)

    async def patch(self, url, json=None):
        self.calls.append(("patch", url, json))
        return FakeResponse({"id": url.rsplit("/", 1)[-1]})


@pytest.fixture(autouse=True)
def fake_espocrm(monkeypatch):
    monkeypatch.setenv("ESPOCRM_BASE_URL", "https://crm.example.test")
    monkeypatch.setenv("ESPOCRM_TENDER_API_KEY", "test-key")
    monkeypatch.setenv("ESPOCRM_FINDING_API_KEY", "finding-key")
    monkeypatch.setattr(espocrm_connector.httpx, "AsyncClient", FakeEspoClient)
    FakeEspoClient.responses = []
    FakeEspoClient.calls = []


def sample_tender(**overrides):
    tender = {
        "title": "Cybersecurity platform tender",
        "reference_number": "REF-001",
        "issuing_entity": "Example University",
        "category": "Cybersecurity",
        "deadline": "2026-08-15",
        "estimated_value": 120000,
        "estimated_value_currency": "USD",
        "description": "Procure endpoint protection and security monitoring.",
        "source_url": "https://example.test/tenders/ref-001",
        "source_confidence_tier": "high",
        "win_likelihood_score": 82,
        "win_likelihood_reasoning": "Strong category and sector fit.",
    }
    tender.update(overrides)
    return tender


@pytest.mark.anyio
async def test_upsert_tender_record_creates_new_record():
    FakeEspoClient.responses = [{"list": []}]

    outcome = await espocrm_connector.upsert_tender_record(sample_tender())

    assert outcome == "created"
    method, url, payload = FakeEspoClient.calls[-1]
    assert method == "post"
    assert url == "https://crm.example.test/api/v1/Tender"
    assert payload["status"] == "New"
    assert payload["referenceNumber"] == "REF-001"
    assert payload["winLikelihoodScore"] == 82
    assert payload["winLikelihoodReasoning"] == "Strong category and sector fit."


@pytest.mark.anyio
async def test_upsert_tender_record_patches_scores_when_description_changes():
    FakeEspoClient.responses = [
        {"list": [{"id": "existing-id", "description": "Old description", "status": "Pursuing"}]}
    ]

    outcome = await espocrm_connector.upsert_tender_record(sample_tender())

    assert outcome == "updated"
    method, url, payload = FakeEspoClient.calls[-1]
    assert method == "patch"
    assert url == "https://crm.example.test/api/v1/Tender/existing-id"
    assert payload["description"] == "Procure endpoint protection and security monitoring."
    assert payload["winLikelihoodScore"] == 82
    assert payload["winLikelihoodReasoning"] == "Strong category and sector fit."
    assert "status" not in payload
    assert "assignedUserId" not in payload


@pytest.mark.anyio
async def test_upsert_tender_record_only_patches_volatile_fields_when_unchanged():
    FakeEspoClient.responses = [
        {
            "list": [
                {
                    "id": "existing-id",
                    "description": "Procure endpoint protection and security monitoring.",
                }
            ]
        }
    ]

    outcome = await espocrm_connector.upsert_tender_record(sample_tender())

    assert outcome == "unchanged"
    method, _, payload = FakeEspoClient.calls[-1]
    assert method == "patch"
    assert payload == {
        "deadline": "2026-08-15",
        "estimatedValue": 120000,
        "estimatedValueCurrency": "USD",
    }


@pytest.mark.anyio
async def test_flag_disappeared_tenders_flags_new_and_notes_active_records():
    FakeEspoClient.responses = [
        {
            "list": [
                {
                    "id": "new-id",
                    "referenceNumber": "REF-NEW",
                    "status": "New",
                    "description": "New tender",
                },
                {
                    "id": "pursuing-id",
                    "referenceNumber": "REF-PURSUING",
                    "status": "Pursuing",
                    "description": "Active tender",
                },
                {
                    "id": "seen-id",
                    "referenceNumber": "REF-SEEN",
                    "status": "Under Review",
                    "description": "Still present",
                },
            ]
        }
    ]

    result = await espocrm_connector.flag_disappeared_tenders(
        seen_reference_numbers=["REF-SEEN"],
        source_site="valyu-deep-research",
    )

    assert result == ["REF-NEW", "REF-PURSUING"]
    patch_calls = [call for call in FakeEspoClient.calls if call[0] == "patch"]
    assert len(patch_calls) == 2

    today = date.today().isoformat()
    new_payload = patch_calls[0][2]
    pursuing_payload = patch_calls[1][2]
    assert new_payload["status"] == "Not Pursuing"
    assert f"[Auto-flagged {today}: listing no longer found on source site]" in new_payload["description"]
    assert "status" not in pursuing_payload
    assert f"[Auto-note {today}: listing no longer found on source site" in pursuing_payload["description"]


@pytest.mark.anyio
async def test_create_finding_record_maps_spot_use_case_to_finding_with_related_account():
    FakeEspoClient.responses = [{"list": [{"id": "account-id", "name": "Acme Org"}]}]
    use_case = {
        "title": "Automate invoice follow-up",
        "department": "Finance",
        "pain_point": "Invoice follow-up is manual and delayed.",
        "ai_solution": "Deploy an automated receivables reminder workflow.",
        "risks": ["Customer contact data may be incomplete."],
        "confidence": "high",
        "confidence_reasoning": "The pain point is directly supported by the SPOT context.",
        "key_assumptions": ["Finance owns receivables follow-up.", "Customer email addresses exist."],
        "estimated_cost_kes": 1_200_000,
    }

    finding_id = await espocrm_connector.create_finding_record(use_case, "Acme Org")

    assert finding_id == "new-id"
    get_call, post_call = FakeEspoClient.calls
    assert get_call[0] == "get"
    assert get_call[1] == "https://crm.example.test/api/v1/Account"
    assert get_call[2] == {
        "where[0][type]": "equals",
        "where[0][attribute]": "name",
        "where[0][value]": "Acme Org",
        "maxSize": 1,
    }

    method, url, payload = post_call
    assert method == "post"
    assert url == "https://crm.example.test/api/v1/CFinding"
    assert payload["name"] == "Automate invoice follow-up"
    assert payload["agentSource"] == "SPOT"
    assert payload["description"] == (
        "Pain point: Invoice follow-up is manual and delayed. "
        "Proposed solution: Deploy an automated receivables reminder workflow."
    )
    assert "The pain point is directly supported" in payload["evidence"]
    assert "Finance owns receivables follow-up." in payload["evidence"]
    assert payload["recommendedAction"] == "Deploy an automated receivables reminder workflow."
    assert payload["severity"] == "High"
    assert payload["status"] == "New"
    assert payload["accountId"] == "account-id"


@pytest.mark.anyio
async def test_create_finding_record_leaves_related_organization_empty_when_account_missing():
    FakeEspoClient.responses = [{"list": []}, {"list": []}]
    use_case = {
        "title": "Reconfigure CRM pipeline",
        "ai_solution": "Reconfigure the existing CRM pipeline.",
        "pain_point": "Pipeline stages are inconsistent.",
        "identified_risks": [],
        "confidence": "medium",
        "key_assumptions": ["CRM users can adopt the new stages."],
        "estimated_cost_kes": 250_000,
    }

    await espocrm_connector.create_finding_record(use_case, "Missing Org")

    assert len([call for call in FakeEspoClient.calls if call[0] == "get"]) == 2
    _, _, payload = FakeEspoClient.calls[-1]
    assert payload["name"] == "Reconfigure CRM pipeline"
    assert payload["severity"] == "Medium"
    assert "accountId" not in payload


@pytest.mark.anyio
async def test_create_finding_record_gracefully_handles_non_200_response(caplog):
    caplog.set_level("ERROR")
    FakeEspoClient.responses = [
        {"list": [{"id": "account-id", "name": "Acme Org"}]},
        ({"message": "bad field"}, 400),
    ]
    use_case = {
        "title": "Broken CRM field test",
        "department": "Operations",
        "pain_point": "A finding payload is rejected.",
        "ai_solution": "Review the EspoCRM field mapping.",
        "risks": ["Field mismatch."],
        "confidence": "low",
        "confidence_reasoning": "This is a failure-path test.",
        "key_assumptions": ["EspoCRM returns a 400."],
        "estimated_cost_kes": 100000,
    }

    finding_id = await espocrm_connector.create_finding_record(use_case, "Acme Org")

    assert finding_id == ""
    assert "Failed to create EspoCRM Finding" in caplog.text
    assert "Broken CRM field test" in caplog.text
