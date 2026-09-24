from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import AuthError, ConfigError, NotFoundError, UpstreamError
from mcp_common.http import is_offline, make_client
from pydantic import Field

_TIMEOUT = 30.0


def _base():
    v = os.environ.get("LOGSEQ_URL")
    if not v:
        raise ConfigError("LOGSEQ_URL is not set (http://localhost:12315)")
    return v.rstrip("/")


def _token():
    v = os.environ.get("LOGSEQ_TOKEN")
    if not v:
        raise ConfigError("LOGSEQ_TOKEN is not set")
    return v


def _headers():
    return {"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"}


def _raise_for(r):
    if r.status_code in (401, 403):
        raise AuthError(f"logseq HTTP {r.status_code}")
    if r.status_code >= 400:
        raise UpstreamError(f"logseq HTTP {r.status_code}")


async def _call(method, args=None):
    body = {"method": method, "args": args or []}
    async with make_client("logseq", timeout=_TIMEOUT) as c:
        r = await c.post(f"{_base()}/api", headers=_headers(), json=body)
        _raise_for(r)
    return r.json()


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def query(
        q: Annotated[str, Field(min_length=1, description="Datascript/Logseq query")],
    ) -> dict:
        """Run a Logseq DB query."""
        return {"result": await _call("logseq.db.datascriptQuery", [q])}

    @mcp.tool
    async def list_pages() -> dict:
        """List Logseq pages."""
        return {"pages": await _call("logseq.editor.getAllPages")}

    @mcp.tool
    async def create_page(name: Annotated[str, Field(min_length=1)]) -> dict:
        """Create a Logseq page."""
        return {"page": await _call("logseq.editor.createPage", [name])}
