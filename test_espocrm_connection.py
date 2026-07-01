# test_espocrm_connection.py
#
# Run directly:
#     python test_espocrm_connection.py
#
# This script:
#   1. Verifies authentication.
#   2. Detects whether the entity is Finding or CFinding.
#   3. Checks Account access.
#   4. Creates a test Finding.
#   5. Prints detailed diagnostics for every request.

import json
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

ESPOCRM_BASE_URL = os.environ["ESPOCRM_BASE_URL"].rstrip("/")
API_KEY = os.environ["ESPOCRM_FINDING_API_KEY"]

headers = {
    "X-Api-Key": API_KEY,
    "Content-Type": "application/json",
}


def print_response(title: str, response: httpx.Response):
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)
    print("URL:", response.request.url)
    print("Status:", response.status_code)
    print("Content-Type:", response.headers.get("Content-Type"))

    try:
        print(json.dumps(response.json(), indent=2))
    except Exception:
        print(response.text)


# ---------------------------------------------------------------------
# STEP 1: Detect the correct Finding endpoint
# ---------------------------------------------------------------------

entity_name = None

for candidate in ["Finding", "CFinding"]:
    resp = httpx.get(
        f"{ESPOCRM_BASE_URL}/api/v1/{candidate}",
        headers=headers,
        timeout=30,
    )

    print_response(f"READ {candidate}", resp)

    if resp.status_code == 200:
        entity_name = candidate
        break

if entity_name is None:
    print("\n❌ Could not locate the Finding entity.")
    raise SystemExit(1)

print(f"\n✅ Using entity endpoint: {entity_name}")

# ---------------------------------------------------------------------
# STEP 2: Check Account permissions
# ---------------------------------------------------------------------

account_resp = httpx.get(
    f"{ESPOCRM_BASE_URL}/api/v1/Account",
    headers=headers,
    timeout=30,
)

print_response("READ Account", account_resp)

# ---------------------------------------------------------------------
# STEP 3: Create a test Finding
# ---------------------------------------------------------------------

account_id = "6a3906607657e279f"

payload = {
    "name": "Connection Test Finding - DELETE ME",
    "agentSource": "SPOT",
    "description": "Manual API connectivity test.",
    "evidence": "Created from test_espocrm_connection.py",
    "recommendedAction": "Delete this record after verification.",
    "severity": "Informational",
    "status": "New",
    "accountId": account_id,
}

print("\nPayload:")
print(json.dumps(payload, indent=2))

create_resp = httpx.post(
    f"{ESPOCRM_BASE_URL}/api/v1/{entity_name}",
    headers=headers,
    json=payload,
    timeout=30,
)

print_response("CREATE Finding", create_resp)

# ---------------------------------------------------------------------
# STEP 4: Retry with alternate relationship field if needed
# ---------------------------------------------------------------------

if create_resp.status_code >= 400:
    print("\nRetrying using 'account' instead of 'accountId'...")

    payload.pop("accountId", None)
    payload["account"] = account_id

    print("\nRetry Payload:")
    print(json.dumps(payload, indent=2))

    retry_resp = httpx.post(
        f"{ESPOCRM_BASE_URL}/api/v1/{entity_name}",
        headers=headers,
        json=payload,
        timeout=30,
    )

    print_response("CREATE Finding (Retry)", retry_resp)

print("\nDone.")