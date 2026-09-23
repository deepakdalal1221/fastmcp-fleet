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

_BASE = "https://api.render.com/v1"
_TIMEOUT = 30.0


def _token() -> str:
    v = os.environ.get("RENDER_API_KEY")
    if not v:
        raise ConfigError("RENDER_API_KEY is not set")
    return v


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_token()}", "Accept": "application/json"}


def _raise_for(r: httpx.Response) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"render auth failed: HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("render resource not found")
    if r.status_code == 429:
        raise RateLimitError("render rate limited")
    if r.status_code >= 400:
        raise UpstreamError(f"render HTTP {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_services(
        limit: Annotated[int, Field(ge=1, le=100)] = 20,
    ) -> dict:
        """List Render services owned by the caller."""
        async with make_client("render", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/services", headers=_headers(), params={"limit": limit})
            _raise_for(r)
            data = r.json()
        items = data if isinstance(data, list) else data.get("services", [])
        return {
            "services": [
                {
                    "id": (i.get("service") or i).get("id"),
                    "name": (i.get("service") or i).get("name"),
                    "type": (i.get("service") or i).get("type"),
                    "suspended": (i.get("service") or i).get("suspended"),
                    "url": (i.get("service") or i).get("serviceDetails", {}).get("url"),
                    "created": (i.get("service") or i).get("createdAt"),
                }
                for i in items
            ]
        }

    @mcp.tool
    async def get_service(
        service_id: Annotated[str, Field(min_length=1, description="Render service id (starts with 'srv-')")],
    ) -> dict:
        """Get a single Render service by id."""
        async with make_client("render", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/services/{service_id}", headers=_headers())
            _raise_for(r)
            s = r.json()
        return {
            "id": s.get("id"),
            "name": s.get("name"),
            "type": s.get("type"),
            "repo": s.get("repo"),
            "branch": s.get("branch"),
            "suspended": s.get("suspended"),
            "created": s.get("createdAt"),
            "url": (s.get("serviceDetails") or {}).get("url"),
        }

    @mcp.tool
    async def list_deploys(
        service_id: Annotated[str, Field(min_length=1, description="Render service id")],
        limit: Annotated[int, Field(ge=1, le=100)] = 20,
    ) -> dict:
        """List deploys for a Render service."""
        async with make_client("render", timeout=_TIMEOUT) as c:
            r = await c.get(
                f"{_BASE}/services/{service_id}/deploys",
                headers=_headers(),
                params={"limit": limit},
            )
            _raise_for(r)
            data = r.json()
        items = data if isinstance(data, list) else data.get("deploys", [])
        return {
            "deploys": [
                {
                    "id": (i.get("deploy") or i).get("id"),
                    "status": (i.get("deploy") or i).get("status"),
                    "commit_id": ((i.get("deploy") or i).get("commit") or {}).get("id"),
                    "created": (i.get("deploy") or i).get("createdAt"),
                    "finished": (i.get("deploy") or i).get("finishedAt"),
                }
                for i in items
            ]
        }
