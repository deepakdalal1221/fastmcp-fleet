from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from mcp_common.errors import (
    AuthError,
    ConfigError,
    NotFoundError,
    RateLimitError,
    UpstreamError,
)
from mcp_common.http import make_client
from pydantic import Field

_BASE = "https://api.netlify.com/api/v1"
_TIMEOUT = 30.0


def _token() -> str:
    v = os.environ.get("NETLIFY_TOKEN")
    if not v:
        raise ConfigError("NETLIFY_TOKEN is not set")
    return v


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_token()}", "Accept": "application/json"}


def _raise_for(r: httpx.Response) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"netlify auth failed: HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("netlify resource not found")
    if r.status_code == 429:
        raise RateLimitError("netlify rate limited")
    if r.status_code >= 400:
        raise UpstreamError(f"netlify HTTP {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_sites(
        per_page: Annotated[int, Field(ge=1, le=100)] = 20,
    ) -> dict:
        """List Netlify sites for the authenticated user."""
        async with make_client("netlify", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/sites", headers=_headers(), params={"per_page": per_page})
            _raise_for(r)
            data = r.json()
        return {
            "sites": [
                {
                    "id": s["id"],
                    "name": s["name"],
                    "url": s.get("url"),
                    "state": s.get("state"),
                    "custom_domain": s.get("custom_domain"),
                }
                for s in data
            ]
        }

    @mcp.tool
    async def list_deploys(
        site_id: Annotated[str, Field(min_length=1, description="Netlify site id")],
        per_page: Annotated[int, Field(ge=1, le=100)] = 20,
    ) -> dict:
        """List deploys for a Netlify site."""
        async with make_client("netlify", timeout=_TIMEOUT) as c:
            r = await c.get(
                f"{_BASE}/sites/{site_id}/deploys",
                headers=_headers(),
                params={"per_page": per_page},
            )
            _raise_for(r)
            data = r.json()
        return {
            "deploys": [
                {
                    "id": d["id"],
                    "state": d.get("state"),
                    "url": d.get("deploy_url") or d.get("url"),
                    "commit_ref": d.get("commit_ref"),
                    "created": d.get("created_at"),
                }
                for d in data
            ]
        }

    @mcp.tool
    async def get_site(
        site_id: Annotated[str, Field(min_length=1, description="Netlify site id")],
    ) -> dict:
        """Get a single Netlify site by id."""
        async with make_client("netlify", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/sites/{site_id}", headers=_headers())
            _raise_for(r)
            s = r.json()
        return {
            "id": s.get("id"),
            "name": s.get("name"),
            "url": s.get("url"),
            "state": s.get("state"),
            "custom_domain": s.get("custom_domain"),
            "published_deploy_id": (s.get("published_deploy") or {}).get("id"),
            "created": s.get("created_at"),
        }
