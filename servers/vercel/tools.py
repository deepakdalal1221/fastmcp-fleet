from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from pydantic import Field

from mcp_common.errors import (
    AuthError,
    ConfigError,
    NotFoundError,
    RateLimitError,
    UpstreamError,
)

_BASE = "https://api.vercel.com"
_TIMEOUT = 30.0


def _token() -> str:
    v = os.environ.get("VERCEL_TOKEN")
    if not v:
        raise ConfigError("VERCEL_TOKEN is not set")
    return v


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_token()}", "Accept": "application/json"}


def _team_params() -> dict[str, str]:
    tid = os.environ.get("VERCEL_TEAM_ID")
    return {"teamId": tid} if tid else {}


def _raise_for(r: httpx.Response) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"vercel auth failed: HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("vercel resource not found")
    if r.status_code == 429:
        raise RateLimitError("vercel rate limited")
    if r.status_code >= 400:
        raise UpstreamError(f"vercel HTTP {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_projects(
        limit: Annotated[int, Field(ge=1, le=100)] = 20,
    ) -> dict:
        """List Vercel projects for the authenticated user or team."""
        params = {"limit": limit, **_team_params()}
        async with make_client("vercel", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/v9/projects", headers=_headers(), params=params)
            _raise_for(r)
            data = r.json()
        return {
            "projects": [
                {
                    "id": p["id"],
                    "name": p["name"],
                    "framework": p.get("framework"),
                    "latest_deploy": (p.get("latestDeployments") or [{}])[0].get("url"),
                }
                for p in data.get("projects", [])
            ]
        }

    @mcp.tool
    async def list_deployments(
        project_id: Annotated[str | None, Field(description="filter by project id")] = None,
        limit: Annotated[int, Field(ge=1, le=100)] = 20,
    ) -> dict:
        """List Vercel deployments, optionally filtered by project."""
        params = {"limit": limit, **_team_params()}
        if project_id:
            params["projectId"] = project_id
        async with make_client("vercel", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/v6/deployments", headers=_headers(), params=params)
            _raise_for(r)
            data = r.json()
        return {
            "deployments": [
                {
                    "uid": d["uid"],
                    "url": d.get("url"),
                    "state": d.get("state"),
                    "created": d.get("created"),
                    "target": d.get("target"),
                }
                for d in data.get("deployments", [])
            ]
        }

    @mcp.tool
    async def get_deployment(
        deployment_id: Annotated[str, Field(min_length=1, description="Vercel deployment id (uid)")],
    ) -> dict:
        """Get a single Vercel deployment by id."""
        params = _team_params()
        async with make_client("vercel", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/v13/deployments/{deployment_id}", headers=_headers(), params=params)
            _raise_for(r)
            d = r.json()
        return {
            "uid": d.get("uid") or d.get("id"),
            "name": d.get("name"),
            "url": d.get("url"),
            "state": d.get("readyState") or d.get("state"),
            "created": d.get("createdAt") or d.get("created"),
            "target": d.get("target"),
        }
