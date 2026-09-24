from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import AuthError, ConfigError, NotFoundError, RateLimitError, UpstreamError
from mcp_common.http import is_offline, make_client
from pydantic import Field

_SID = "git-local"
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
    async def status() -> dict:
        """Status on git-local (offline stub)."""
        if is_offline():
            items = await local_store.list_all(_SID, "statuses")
            return {"items": items, "count": len(items)}
        raise ConfigError(f"status live mode not implemented for {_SID}; run offline")

    @mcp.tool
    async def log(limit: int = 10) -> dict:
        """Log on git-local (offline stub)."""
        if is_offline():
            items = await local_store.list_all(_SID, "log_entries")
            return {"items": items, "count": len(items)}
        raise ConfigError(f"log live mode not implemented for {_SID}; run offline")

    @mcp.tool
    async def diff(path: str | None = None) -> dict:
        """Diff on git-local (offline stub)."""
        if is_offline():
            items = await local_store.list_all(_SID, "diffs")
            return {"items": items, "count": len(items)}
        raise ConfigError(f"diff live mode not implemented for {_SID}; run offline")

    @mcp.tool
    async def blame(path: str) -> dict:
        """Blame on git-local (offline stub)."""
        if is_offline():
            items = await local_store.list_all(_SID, "blames")
            return {"items": items, "count": len(items)}
        raise ConfigError(f"blame live mode not implemented for {_SID}; run offline")

    @mcp.tool
    async def show(ref: str) -> dict:
        """Show on git-local (offline stub)."""
        if is_offline():
            rec = await local_store.get(_SID, "shows", str(ref))
            if rec is None:
                raise NotFoundError(f"show: not found: {ref}")
            return rec
        raise ConfigError(f"show live mode not implemented for {_SID}; run offline")

    @mcp.tool
    async def branches() -> dict:
        """Branches on git-local (offline stub)."""
        if is_offline():
            items = await local_store.list_all(_SID, "branches")
            return {"items": items, "count": len(items)}
        raise ConfigError(f"branches live mode not implemented for {_SID}; run offline")
