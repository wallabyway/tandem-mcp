"""Lightweight TTL-based in-memory cache for Tandem API responses.

Caches read-only data that rarely changes (schemas, model IDs, levels, rooms)
to avoid redundant API round-trips within a session.
"""

from __future__ import annotations

import time
from typing import Any

DEFAULT_TTL = 300  # 5 minutes — safe for schema / structural data


class TTLCache:
    """Simple async-friendly TTL cache backed by a plain dict."""

    def __init__(self, ttl: float = DEFAULT_TTL) -> None:
        self._ttl = ttl
        self._store: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() > expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        self._store[key] = (time.monotonic() + (ttl or self._ttl), value)

    def invalidate(self, key: str) -> None:
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()

    @property
    def size(self) -> int:
        return len(self._store)


schema_cache = TTLCache(ttl=600)
model_ids_cache = TTLCache(ttl=300)
levels_cache = TTLCache(ttl=300)
rooms_cache = TTLCache(ttl=300)
scan_cache = TTLCache(ttl=30)
