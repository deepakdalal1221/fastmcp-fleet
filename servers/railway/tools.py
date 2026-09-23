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

_BASE = "https://backboard.railway.app/graphql/v2"
_TIMEOUT = 30.0


def _token() -> str:
    v = os.environ.get("RAILWAY_TOKEN")
    if not v:
        raise ConfigError("RAILWAY_TOKEN is not set")
    return v


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_token()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _raise_for(r: httpx.Response) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"railway auth failed: HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("railway resource not found")
    if r.status_code == 429:
        raise RateLimitError("railway rate limited")
    if r.status_code >= 400:
        raise UpstreamError(f"railway HTTP {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_projects() -> dict:
        """List Railway projects for the authenticated user."""
        gql = {"query": "query{me{projects{edges{node{id,name,description,createdAt}}}}}"}
        async with make_client("railway", timeout=_TIMEOUT) as c:
            r = await c.post(_BASE, headers=_headers(), json=gql)
            _raise_for(r)
            data = r.json()
        edges = (((data.get("data") or {}).get("me") or {}).get("projects") or {}).get(
            "edges"
        ) or []
        return {
            "projects": [
                {
                    "id": (e.get("node") or {}).get("id"),
                    "name": (e.get("node") or {}).get("name"),
                    "description": (e.get("node") or {}).get("description"),
                    "createdAt": (e.get("node") or {}).get("createdAt"),
                }
                for e in edges
            ]
        }

    @mcp.tool
    async def list_services(
        project_id: Annotated[str, Field(min_length=1, description="Railway project id")],
    ) -> dict:
        """List services within a Railway project."""
        gql = {
            "query": "query($p:String!){project(id:$p){services{edges{node{id,name}}}}}",
            "variables": {"p": project_id},
        }
        async with make_client("railway", timeout=_TIMEOUT) as c:
            r = await c.post(_BASE, headers=_headers(), json=gql)
            _raise_for(r)
            data = r.json()
        edges = (((data.get("data") or {}).get("project") or {}).get("services") or {}).get(
            "edges"
        ) or []
        return {
            "services": [
                {"id": (e.get("node") or {}).get("id"), "name": (e.get("node") or {}).get("name")}
                for e in edges
            ]
        }
