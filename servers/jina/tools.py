from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import AuthError, ConfigError, NotFoundError, RateLimitError, UpstreamError
from mcp_common.http import is_offline, make_client
from pydantic import Field

_SID = "jina"
_TIMEOUT = 30.0
_BASE = "https://api.jina.ai/v1"


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
    async def read_url(url: str) -> dict:
        """Read url on jina (offline stub)."""
        if is_offline():
            rec = await local_store.get(_SID, "reads", str(url))
            if rec is None:
                raise NotFoundError(f"read_url: not found: {url}")
            return rec
        raise ConfigError(f"read_url live mode not implemented for {_SID}; run offline")

    @mcp.tool
    async def search(query: str) -> dict:
        """Search on jina (offline stub)."""
        if is_offline():
            items = await local_store.list_all(_SID, "searches")
            return {"items": items, "count": len(items)}
        raise ConfigError(f"search live mode not implemented for {_SID}; run offline")
