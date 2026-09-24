from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import AuthError, ConfigError, NotFoundError, UpstreamError
from mcp_common.http import is_offline, make_client
from pydantic import Field

_BASE = "https://graph.microsoft.com/v1.0/me/onenote"
_TIMEOUT = 30.0


def _token():
    v = os.environ.get("MSGRAPH_TOKEN")
    if not v:
        raise ConfigError("MSGRAPH_TOKEN is not set")
    return v


def _headers():
    return {"Authorization": f"Bearer {_token()}", "Accept": "application/json"}


def _raise_for(r):
    if r.status_code in (401, 403):
        raise AuthError(f"onenote HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("onenote not found")
    if r.status_code >= 400:
        raise UpstreamError(f"onenote HTTP {r.status_code}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_notebooks() -> dict:
        """List OneNote notebooks."""
        async with make_client("onenote", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/notebooks", headers=_headers())
            _raise_for(r)
        d = r.json()
        return {
            "notebooks": [
                {"id": n["id"], "displayName": n.get("displayName")} for n in d.get("value", [])
            ]
        }

    @mcp.tool
    async def list_pages(top: Annotated[int, Field(ge=1, le=100)] = 20) -> dict:
        """List OneNote pages."""
        async with make_client("onenote", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/pages", headers=_headers(), params={"$top": top})
            _raise_for(r)
        d = r.json()
        return {
            "pages": [
                {
                    "id": p["id"],
                    "title": p.get("title"),
                    "createdDateTime": p.get("createdDateTime"),
                }
                for p in d.get("value", [])
            ]
        }

    @mcp.tool
    async def get_page(page_id: Annotated[str, Field(min_length=1)]) -> dict:
        """Get a OneNote page's metadata."""
        async with make_client("onenote", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/pages/{page_id}", headers=_headers())
            _raise_for(r)
        return r.json()
