from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import AuthError, ConfigError, NotFoundError, RateLimitError, UpstreamError
from mcp_common.http import is_offline, make_client
from pydantic import Field

_SID = "jaeger"
_TIMEOUT = 30.0


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
    async def list_services() -> dict:
        """List services on jaeger (offline stub)."""
        if is_offline():
            items = await local_store.list_all(_SID, "services")
            return {"items": items, "count": len(items)}
        raise ConfigError(f"list_services live mode not implemented for {_SID}; run offline")

    @mcp.tool
    async def get_trace(trace_id: str) -> dict:
        """Get trace on jaeger (offline stub)."""
        if is_offline():
            rec = await local_store.get(_SID, "traces", str(trace_id))
            if rec is None:
                raise NotFoundError(f"get_trace: not found: {trace_id}")
            return rec
        raise ConfigError(f"get_trace live mode not implemented for {_SID}; run offline")

    @mcp.tool
    async def search_traces(service: str, limit: int = 20) -> dict:
        """Search traces on jaeger (offline stub)."""
        if is_offline():
            items = await local_store.list_all(_SID, "traces")
            return {"items": items, "count": len(items)}
        raise ConfigError(f"search_traces live mode not implemented for {_SID}; run offline")
