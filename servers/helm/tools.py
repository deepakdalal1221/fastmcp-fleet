from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import AuthError, ConfigError, NotFoundError, RateLimitError, UpstreamError
from mcp_common.http import is_offline, make_client
from pydantic import Field

_SID = "helm"
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
    async def list_releases(namespace: str | None = None) -> dict:
        """List releases on helm (offline stub)."""
        if is_offline():
            items = await local_store.list_all(_SID, "releases")
            return {"items": items, "count": len(items)}
        raise ConfigError(f"list_releases live mode not implemented for {_SID}; run offline")

    @mcp.tool
    async def get_release(name: str) -> dict:
        """Get release on helm (offline stub)."""
        if is_offline():
            rec = await local_store.get(_SID, "releases", str(name))
            if rec is None:
                raise NotFoundError(f"get_release: not found: {name}")
            return rec
        raise ConfigError(f"get_release live mode not implemented for {_SID}; run offline")

    @mcp.tool
    async def install(name: str, chart: str, namespace: str = "default") -> dict:
        """Install on helm (offline stub)."""
        if is_offline():
            n = local_store.next_id(_SID, "releases")
            record = {"id": n, "name": name, "chart": chart, "namespace": namespace}
            await local_store.put(_SID, "releases", str(n), record)
            return {"created": record}
        raise ConfigError(f"install live mode not implemented for {_SID}; run offline")

    @mcp.tool
    async def upgrade(name: str, chart: str) -> dict:
        """Upgrade on helm (offline stub)."""
        if is_offline():
            n = local_store.next_id(_SID, "upgrades")
            record = {"id": n, "name": name, "chart": chart}
            await local_store.put(_SID, "upgrades", str(n), record)
            return {"created": record}
        raise ConfigError(f"upgrade live mode not implemented for {_SID}; run offline")
