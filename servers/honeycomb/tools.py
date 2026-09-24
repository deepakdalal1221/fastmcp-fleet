from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import AuthError, ConfigError, NotFoundError, RateLimitError, UpstreamError
from mcp_common.http import is_offline, make_client
from pydantic import Field

_SID = "honeycomb"
_TIMEOUT = 30.0
_BASE = "https://api.honeycomb.io/1"


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
    async def query_dataset(dataset: str, query: dict | None = None) -> dict:
        """Query dataset on honeycomb (offline stub)."""
        if is_offline():
            items = await local_store.list_all(_SID, "results")
            return {"items": items, "count": len(items)}
        raise ConfigError(f"query_dataset live mode not implemented for {_SID}; run offline")

    @mcp.tool
    async def list_boards() -> dict:
        """List boards on honeycomb (offline stub)."""
        if is_offline():
            items = await local_store.list_all(_SID, "boards")
            return {"items": items, "count": len(items)}
        raise ConfigError(f"list_boards live mode not implemented for {_SID}; run offline")
