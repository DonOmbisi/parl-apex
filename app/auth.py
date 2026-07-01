import os

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: str | None = Security(API_KEY_HEADER)) -> str:
    expected = os.getenv("APP_API_KEY")
    if not expected:
        return "no-auth"
    if api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return api_key
