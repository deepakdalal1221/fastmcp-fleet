from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import (
    AuthError,
    ConfigError,
    NotFoundError,
    RateLimitError,
    UpstreamError,
)
from mcp_common.http import is_offline, make_client
from pydantic import Field

_SID = "chrome-devtools"
_TIMEOUT = 30.0
_BASE = None


def _env(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        raise ConfigError(f"{name} is not set")
    return v


def _raise_for(r: httpx.Response) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"auth failed: HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("not found")
    if r.status_code == 429:
        raise RateLimitError("rate limited by upstream")
    if r.status_code >= 400:
        raise UpstreamError(f"HTTP {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def navigate(url: str) -> dict:
        """Navigate (send)."""
        if is_offline():
            n = local_store.next_id(_SID, "navigations")
            record = {"id": n, "url": url, "sent": True}
            await local_store.put(_SID, "navigations", str(n), record)
            return record
        raise ConfigError("live mode not implemented; run offline")

    @mcp.tool
    async def evaluate(expression: str) -> dict:
        """Evaluate (send)."""
        if is_offline():
            n = local_store.next_id(_SID, "evaluations")
            record = {"id": n, "expression": expression, "sent": True}
            await local_store.put(_SID, "evaluations", str(n), record)
            return record
        raise ConfigError("live mode not implemented; run offline")

    @mcp.tool
    async def screenshot(path: str | None = None) -> dict:
        """Screenshot (send)."""
        if is_offline():
            n = local_store.next_id(_SID, "screenshots")
            record = {"id": n, "path": path, "sent": True}
            await local_store.put(_SID, "screenshots", str(n), record)
            return record
        raise ConfigError("live mode not implemented; run offline")
