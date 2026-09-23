from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from pydantic import Field

from mcp_common.errors import AuthError, ConfigError, NotFoundError, RateLimitError, UpstreamError
from mcp_common.http import is_offline, make_client
from mcp_common import local_store

_BASE = "https://circleci.com/api/v2"
_TIMEOUT = 30.0


def _token() -> str:
    v = os.environ.get("CIRCLECI_TOKEN")
    if not v:
        raise ConfigError("CIRCLECI_TOKEN is not set")
    return v


def _headers() -> dict[str, str]:
    return {"Circle-Token": _token(), "Accept": "application/json"}


def _raise_for(r: httpx.Response) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"circleci auth failed: HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("circleci resource not found")
    if r.status_code == 429:
        raise RateLimitError("circleci rate limited")
    if r.status_code >= 400:
        raise UpstreamError(f"circleci HTTP {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_pipelines(
        project_slug: Annotated[str, Field(min_length=1, description="e.g. gh/org/repo")],
        limit: Annotated[int, Field(ge=1, le=100)] = 20,
    ) -> dict:
        """List recent CircleCI pipelines for a project."""
        async with make_client("circleci", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/project/{project_slug}/pipeline", headers=_headers(), params={"page-token": None})
            _raise_for(r)
            data = r.json()
        items = data.get("items", [])[:limit]
        return {"pipelines": [{"id": p.get("id"), "number": p.get("number"), "state": p.get("state"), "created_at": p.get("created_at"), "vcs_revision": (p.get("vcs") or {}).get("revision")} for p in items]}

    @mcp.tool
    async def get_pipeline(
        pipeline_id: Annotated[str, Field(min_length=1, description="CircleCI pipeline id (UUID)")],
    ) -> dict:
        """Get a CircleCI pipeline by id."""
        async with make_client("circleci", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/pipeline/{pipeline_id}", headers=_headers())
            _raise_for(r)
            p = r.json()
        return {"id": p.get("id"), "number": p.get("number"), "state": p.get("state"), "trigger": (p.get("trigger") or {}).get("type"), "created_at": p.get("created_at")}

    @mcp.tool
    async def list_workflows(
        pipeline_id: Annotated[str, Field(min_length=1, description="CircleCI pipeline id")],
    ) -> dict:
        """List workflows for a CircleCI pipeline."""
        async with make_client("circleci", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/pipeline/{pipeline_id}/workflow", headers=_headers())
            _raise_for(r)
            data = r.json()
        return {"workflows": [{"id": w.get("id"), "name": w.get("name"), "status": w.get("status"), "created_at": w.get("created_at")} for w in data.get("items", [])]}
