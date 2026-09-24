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
    v = os.environ.get("GERRIT_URL")
    if not v:
        raise ConfigError("GERRIT_URL is not set")
    return v.rstrip("/") + "/a"


def _auth():
    u, p = os.environ.get("GERRIT_USER"), os.environ.get("GERRIT_PASSWORD")
    if not u or not p:
        raise ConfigError("GERRIT_USER and GERRIT_PASSWORD must be set")
    return httpx.BasicAuth(u, p)


def _raise_for(r):
    if r.status_code in (401, 403):
        raise AuthError(f"gerrit HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("gerrit not found")
    if r.status_code >= 400:
        raise UpstreamError(f"gerrit HTTP {r.status_code}")


def _strip(text):
    return text.split("\n", 1)[1] if text.startswith(")]}'") else text


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_projects(limit: Annotated[int, Field(ge=1, le=100)] = 20) -> dict:
        """List Gerrit projects."""
        async with make_client("gerrit", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_base()}/projects/", auth=_auth(), params={"n": limit})
            _raise_for(r)
            import json

            data = json.loads(_strip(r.text))
        return {"projects": [{"name": k, "state": v.get("state")} for k, v in data.items()]}

    @mcp.tool
    async def list_changes(
        query: Annotated[
            str, Field(description="Gerrit query, e.g. 'status:open'")
        ] = "status:open",
        limit: Annotated[int, Field(ge=1, le=100)] = 25,
    ) -> dict:
        """Query Gerrit changes."""
        async with make_client("gerrit", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_base()}/changes/", auth=_auth(), params={"q": query, "n": limit})
            _raise_for(r)
            import json

            data = json.loads(_strip(r.text))
        return {
            "changes": [
                {
                    "id": c.get("_number"),
                    "subject": c.get("subject"),
                    "status": c.get("status"),
                    "project": c.get("project"),
                }
                for c in data
            ]
        }

    @mcp.tool
    async def get_change(change_id: Annotated[str, Field(min_length=1)]) -> dict:
        """Get a Gerrit change."""
        async with make_client("gerrit", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_base()}/changes/{change_id}", auth=_auth())
            _raise_for(r)
            import json

            c_data = json.loads(_strip(r.text))
        return {
            "id": c_data.get("_number"),
            "subject": c_data.get("subject"),
            "status": c_data.get("status"),
            "project": c_data.get("project"),
            "branch": c_data.get("branch"),
        }
