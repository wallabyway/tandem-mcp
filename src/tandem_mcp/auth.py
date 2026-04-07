"""2-legged OAuth (client_credentials) for Autodesk Platform Services, with file-based token caching."""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx

AUTH_URL = "https://developer.api.autodesk.com/authentication/v2/token"
TOKEN_CACHE = Path(__file__).resolve().parent.parent.parent / ".token"


async def get_token(client_id: str, client_secret: str, scopes: list[str] | None = None) -> str:
    """Return a valid access token, refreshing via 2LO if the cached one is expired."""
    cached = _read_cache()
    if cached:
        return cached

    token, expires_at = await _request_token(client_id, client_secret, scopes or ["data:read", "data:write"])
    _write_cache(token, expires_at)
    return token


async def _request_token(client_id: str, client_secret: str, scopes: list[str]) -> tuple[str, float]:
    """Perform the client_credentials grant and return (access_token, expires_at_epoch)."""
    async with httpx.AsyncClient() as http:
        r = await http.post(
            AUTH_URL,
            params={"grant_type": "client_credentials", "scope": " ".join(scopes)},
            auth=(client_id, client_secret),
            timeout=15,
        )
        if not r.is_success:
            raise RuntimeError(f"Auth error: {r.status_code} — {r.text}")
        data = r.json()
    expires_in = data.get("expires_in", 3600)
    expires_at = time.time() + expires_in - 60  # 60s safety margin
    return data["access_token"], expires_at


def _read_cache() -> str | None:
    """Read cached token if it exists and hasn't expired."""
    if not TOKEN_CACHE.exists():
        return None
    try:
        blob = json.loads(TOKEN_CACHE.read_text())
        if blob.get("expires_at", 0) > time.time():
            return blob["access_token"]
    except (json.JSONDecodeError, KeyError):
        pass
    return None


def _write_cache(token: str, expires_at: float) -> None:
    """Write token + expiry to the cache file."""
    TOKEN_CACHE.write_text(json.dumps({"access_token": token, "expires_at": expires_at}))
