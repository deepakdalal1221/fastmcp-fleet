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


def _token():
    v = os.environ.get("ROAM_TOKEN")
    if not v:
        raise ConfigError("ROAM_TOKEN is not set")
    return v


def _graph():
    v = os.environ.get("ROAM_GRAPH")
    if not v:
        raise ConfigError("ROAM_GRAPH is not set")
    return v


def _headers():
    return {
        "Authorization": f"Bearer {_token()}",
        "X-Authorization": f"Bearer {_token()}",
        "Content-Type": "application/json",
    }


def _raise_for(r):
    if r.status_code in (401, 403):
        raise AuthError(f"roam HTTP {r.status_code}")
    if r.status_code >= 400:
        raise UpstreamError(f"roam HTTP {r.status_code}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def query(
        datalog: Annotated[str, Field(min_length=1, description="Datalog query")],
    ) -> dict:
        """Query the Roam graph with Datalog."""
        body = {"query": datalog}
        async with make_client("roam", timeout=_TIMEOUT) as c:
            r = await c.post(
                f"https://api.roamresearch.com/api/graph/{_graph()}/q",
                headers=_headers(),
                json=body,
            )
            _raise_for(r)
        return r.json()

    @mcp.tool
    async def list_pages() -> dict:
        """List Roam pages (via Datalog)."""
        return await query.fn("[:find ?title :where [?e :node/title ?title]]")
