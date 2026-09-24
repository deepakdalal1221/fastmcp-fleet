from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import AuthError, ConfigError, NotFoundError, UpstreamError
from mcp_common.http import is_offline, make_client
from pydantic import Field

_BASE = "https://api.dropboxapi.com/2"
_TIMEOUT = 30.0


def _token():
    v = os.environ.get("DROPBOX_TOKEN")
    if not v:
        raise ConfigError("DROPBOX_TOKEN is not set")
    return v


def _headers():
    return {"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"}


def _raise_for(r):
    if r.status_code in (401, 403):
        raise AuthError(f"dropbox-paper HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("dropbox-paper not found")
    if r.status_code >= 400:
        raise UpstreamError(f"dropbox-paper HTTP {r.status_code}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_docs(limit: Annotated[int, Field(ge=1, le=1000)] = 50) -> dict:
        """List Dropbox Paper docs (legacy API)."""
        async with make_client("dropbox-paper", timeout=_TIMEOUT) as c:
            r = await c.post(f"{_BASE}/paper/docs/list", headers=_headers(), json={"limit": limit})
            _raise_for(r)
        return r.json()

    @mcp.tool
    async def get_doc(doc_id: Annotated[str, Field(min_length=1)]) -> dict:
        """Fetch metadata for a Dropbox Paper doc."""
        async with make_client("dropbox-paper", timeout=_TIMEOUT) as c:
            r = await c.post(
                f"{_BASE}/paper/docs/get_metadata", headers=_headers(), json={"doc_id": doc_id}
            )
            _raise_for(r)
        return r.json()
