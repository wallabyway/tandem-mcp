"""Structured logging and performance instrumentation for the Tandem MCP server."""

from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from functools import wraps
from typing import Any, AsyncIterator, Callable

LOG_LEVEL = os.environ.get("TANDEM_LOG_LEVEL", "INFO").upper()

logger = logging.getLogger("tandem_mcp")

_configured = False


def configure_logging() -> None:
    global _configured
    if _configured:
        return
    _configured = True
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("[%(asctime)s] %(levelname)-5s %(name)s | %(message)s", datefmt="%H:%M:%S")
    )
    logger.addHandler(handler)
    logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
    logger.propagate = False


@asynccontextmanager
async def timed(label: str, **extra: Any) -> AsyncIterator[dict]:
    """Async context manager that logs elapsed time for a block."""
    ctx: dict[str, Any] = {}
    start = time.perf_counter()
    detail = " ".join(f"{k}={v}" for k, v in extra.items()) if extra else ""
    logger.debug("START %s %s", label, detail)
    try:
        yield ctx
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000
        ctx["elapsed_ms"] = elapsed_ms
        hit = ctx.get("cache_hit")
        cache_tag = f" [CACHE HIT]" if hit else ""
        logger.info("DONE  %s %s — %.0fms%s", label, detail, elapsed_ms, cache_tag)


def log_tool(fn: Callable) -> Callable:
    """Decorator that logs tool invocations with timing."""
    @wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        params = ", ".join(f"{k}={v!r}" for k, v in kwargs.items())
        async with timed(f"tool.{fn.__name__}", params=params):
            return await fn(*args, **kwargs)
    return wrapper
