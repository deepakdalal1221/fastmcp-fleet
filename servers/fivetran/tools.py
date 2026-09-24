from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import AuthError, ConfigError, NotFoundError, RateLimitError, UpstreamError
from mcp_common.http import is_offline, make_client
from pydantic import Field

_SID = "fivetran"
_TIMEOUT = 30.0
_BASE = "https://api.fivetran.com/v1"


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
    async def list_connectors() -> dict:
        """List connectors on fivetran (offline stub)."""
        if is_offline():
            items = await local_store.list_all(_SID, "connectors")
            return {"items": items, "count": len(items)}
        raise ConfigError(f"list_connectors live mode not implemented for {_SID}; run offline")

    @mcp.tool
    async def sync_connector(connector_id: str) -> dict:
        """Sync connector on fivetran (offline stub)."""
        if is_offline():
            n = local_store.next_id(_SID, "syncs")
            record = {"id": n, "connector_id": connector_id}
            await local_store.put(_SID, "syncs", str(n), record)
            return {"created": record}
        raise ConfigError(f"sync_connector live mode not implemented for {_SID}; run offline")
