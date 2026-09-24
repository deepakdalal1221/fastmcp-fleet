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

_SID = "snowflake"
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
    async def query(sql: str) -> dict:
        """Query (list)."""
        if is_offline():
            items = await local_store.list_all(_SID, "rows")
            return {"items": items, "count": len(items)}
        raise ConfigError("live mode not implemented; run offline")

    @mcp.tool
    async def list_databases() -> dict:
        """List databases (list)."""
        if is_offline():
            items = await local_store.list_all(_SID, "databases")
            return {"items": items, "count": len(items)}
        raise ConfigError("live mode not implemented; run offline")

    @mcp.tool
    async def list_warehouses() -> dict:
        """List warehouses (list)."""
        if is_offline():
            items = await local_store.list_all(_SID, "warehouses")
            return {"items": items, "count": len(items)}
        raise ConfigError("live mode not implemented; run offline")
