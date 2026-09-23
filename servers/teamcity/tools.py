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
    v = os.environ.get("TEAMCITY_URL")
    if not v:
        raise ConfigError("TEAMCITY_URL is not set")
    return v.rstrip("/")


def _token() -> str:
    v = os.environ.get("TEAMCITY_TOKEN")
    if not v:
        raise ConfigError("TEAMCITY_TOKEN is not set")
    return v


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_token()}", "Accept": "application/json"}


def _raise_for(r: httpx.Response) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"teamcity auth failed: HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("teamcity resource not found")
    if r.status_code == 429:
        raise RateLimitError("teamcity rate limited")
    if r.status_code >= 400:
        raise UpstreamError(f"teamcity HTTP {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_projects() -> dict:
        """List TeamCity projects."""
        async with make_client("teamcity", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_base()}/app/rest/projects", headers=_headers())
            _raise_for(r)
            data = r.json()
        return {
            "projects": [
                {
                    "id": p["id"],
                    "name": p["name"],
                    "parent": (p.get("parentProject") or {}).get("id"),
                    "href": p.get("href"),
                }
                for p in data.get("project", [])
            ]
        }

    @mcp.tool
    async def list_builds(
        build_type_id: Annotated[str, Field(description="build configuration id (locator)")] = "",
        count: Annotated[int, Field(ge=1, le=200)] = 20,
    ) -> dict:
        """List TeamCity builds, optionally filtered by buildType id."""
        locator = f"buildType:{build_type_id},count:{count}" if build_type_id else f"count:{count}"
        async with make_client("teamcity", timeout=_TIMEOUT) as c:
            r = await c.get(
                f"{_base()}/app/rest/builds", headers=_headers(), params={"locator": locator}
            )
            _raise_for(r)
            data = r.json()
        return {
            "builds": [
                {
                    "id": p["id"],
                    "number": p.get("number"),
                    "status": p.get("status"),
                    "state": p.get("state"),
                    "buildTypeId": p.get("buildTypeId"),
                }
                for p in data.get("build", [])
            ]
        }

    @mcp.tool
    async def get_build(
        build_id: Annotated[int, Field(ge=1)],
    ) -> dict:
        """Get a single TeamCity build."""
        async with make_client("teamcity", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_base()}/app/rest/builds/id:{build_id}", headers=_headers())
            _raise_for(r)
            p = r.json()
        return {
            "id": p.get("id"),
            "number": p.get("number"),
            "status": p.get("status"),
            "state": p.get("state"),
            "buildTypeId": p.get("buildTypeId"),
            "webUrl": p.get("webUrl"),
            "queuedDate": p.get("queuedDate"),
            "startDate": p.get("startDate"),
            "finishDate": p.get("finishDate"),
        }
