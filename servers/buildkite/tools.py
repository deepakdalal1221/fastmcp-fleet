from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from pydantic import Field

from mcp_common.errors import AuthError, ConfigError, NotFoundError, RateLimitError, UpstreamError
from mcp_common.http import is_offline, make_client
from mcp_common import local_store

_BASE = "https://api.buildkite.com/v2"
_TIMEOUT = 30.0


def _token() -> str:
    v = os.environ.get("BUILDKITE_TOKEN")
    if not v:
        raise ConfigError("BUILDKITE_TOKEN is not set")
    return v


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_token()}", "Accept": "application/json"}


def _raise_for(r: httpx.Response) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"buildkite auth failed: HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("buildkite resource not found")
    if r.status_code == 429:
        raise RateLimitError("buildkite rate limited")
    if r.status_code >= 400:
        raise UpstreamError(f"buildkite HTTP {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_pipelines(
        organization: Annotated[str, Field(min_length=1, description="Buildkite organization slug")],
        per_page: Annotated[int, Field(ge=1, le=100)] = 20,
    ) -> dict:
        """List Buildkite pipelines in an organization."""
        async with make_client("buildkite", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/organizations/{organization}/pipelines", headers=_headers(), params={"per_page": per_page})
            _raise_for(r)
            data = r.json()
        return {"pipelines": [{"slug": p["slug"], "name": p["name"], "repository": p.get("repository"), "default_branch": p.get("default_branch"), "builds_url": p.get("builds_url")} for p in data]}

    @mcp.tool
    async def list_builds(
        organization: Annotated[str, Field(min_length=1)],
        pipeline: Annotated[str, Field(min_length=1, description="pipeline slug")],
        per_page: Annotated[int, Field(ge=1, le=100)] = 20,
    ) -> dict:
        """List builds for a Buildkite pipeline."""
        async with make_client("buildkite", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/organizations/{organization}/pipelines/{pipeline}/builds", headers=_headers(), params={"per_page": per_page})
            _raise_for(r)
            data = r.json()
        return {"builds": [{"number": p["number"], "state": p.get("state"), "commit": (p.get("commit") or "")[:8], "branch": p.get("branch"), "web_url": p.get("web_url")} for p in data]}

    @mcp.tool
    async def get_build(
        organization: Annotated[str, Field(min_length=1)],
        pipeline: Annotated[str, Field(min_length=1)],
        build_number: Annotated[int, Field(ge=1)],
    ) -> dict:
        """Get a single Buildkite build by number."""
        async with make_client("buildkite", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/organizations/{organization}/pipelines/{pipeline}/builds/{build_number}", headers=_headers())
            _raise_for(r)
            p = r.json()
        return {"number": p.get("number"), "state": p.get("state"), "commit": p.get("commit", "")[:8], "branch": p.get("branch"), "duration_s": (int((p.get("finished_at") or 0)) - int((p.get("started_at") or 0))) if p.get("finished_at") and p.get("started_at") else None, "web_url": p.get("web_url")}
