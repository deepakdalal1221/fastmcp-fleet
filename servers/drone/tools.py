from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import (
    AuthError,
    ConfigError,
    NotFoundError,
    RateLimitError,
    UpstreamError,
)
from mcp_common.http import is_offline, make_client
from pydantic import Field

_TIMEOUT = 30.0


def _base() -> str:
    v = os.environ.get("DRONE_URL")
    if not v:
        raise ConfigError("DRONE_URL is not set")
    return v.rstrip("/")


def _token() -> str:
    v = os.environ.get("DRONE_TOKEN")
    if not v:
        raise ConfigError("DRONE_TOKEN is not set")
    return v


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_token()}", "Accept": "application/json"}


def _raise_for(r: httpx.Response) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"drone auth failed: HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("drone resource not found")
    if r.status_code == 429:
        raise RateLimitError("drone rate limited")
    if r.status_code >= 400:
        raise UpstreamError(f"drone HTTP {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_repos() -> dict:
        """List Drone CI repositories for the authenticated user."""
        async with make_client("drone", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_base()}/api/user/repos", headers=_headers())
            _raise_for(r)
            data = r.json()
        return {
            "repos": [
                {
                    "id": p["id"],
                    "slug": p.get("slug"),
                    "active": p.get("active"),
                    "visibility": p.get("visibility"),
                }
                for p in data
            ]
        }

    @mcp.tool
    async def list_builds(
        owner: Annotated[str, Field(min_length=1)],
        name: Annotated[str, Field(min_length=1, description="repo name")],
    ) -> dict:
        """List builds for a Drone repository."""
        async with make_client("drone", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_base()}/api/repos/{owner}/{name}/builds", headers=_headers())
            _raise_for(r)
            data = r.json()
        return {
            "builds": [
                {
                    "number": p["number"],
                    "status": p.get("status"),
                    "event": p.get("event"),
                    "branch": p.get("target"),
                    "commit": (p.get("after") or "")[:8],
                }
                for p in data
            ]
        }

    @mcp.tool
    async def get_build(
        owner: Annotated[str, Field(min_length=1)],
        name: Annotated[str, Field(min_length=1)],
        number: Annotated[int, Field(ge=1)],
    ) -> dict:
        """Get a single Drone build."""
        async with make_client("drone", timeout=_TIMEOUT) as c:
            r = await c.get(
                f"{_base()}/api/repos/{owner}/{name}/builds/{number}", headers=_headers()
            )
            _raise_for(r)
            p = r.json()
        return {
            "number": p.get("number"),
            "status": p.get("status"),
            "event": p.get("event"),
            "branch": p.get("target"),
            "commit": p.get("after"),
            "message": p.get("message"),
            "started": p.get("started"),
            "finished": p.get("finished"),
        }
