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

_BASE = "https://api.heroku.com"
_TIMEOUT = 30.0


def _token() -> str:
    v = os.environ.get("HEROKU_API_KEY")
    if not v:
        raise ConfigError("HEROKU_API_KEY is not set")
    return v


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_token()}",
        "Accept": "application/vnd.heroku+json; version=3",
    }


def _raise_for(r: httpx.Response) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"heroku auth failed: HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("heroku resource not found")
    if r.status_code == 429:
        raise RateLimitError("heroku rate limited")
    if r.status_code >= 400:
        raise UpstreamError(f"heroku HTTP {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_apps() -> dict:
        """List Heroku apps for the authenticated user."""
        async with make_client("heroku", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/apps", headers=_headers())
            _raise_for(r)
            data = r.json()
        return {
            "apps": [
                {
                    "id": p["id"],
                    "name": p.get("name"),
                    "region": (p.get("region") or {}).get("name"),
                    "stack": (p.get("stack") or {}).get("name"),
                    "web_url": p.get("web_url"),
                }
                for p in data
            ]
        }

    @mcp.tool
    async def get_app(
        app: Annotated[str, Field(min_length=1, description="Heroku app id or name")],
    ) -> dict:
        """Get a Heroku app by id or name."""
        async with make_client("heroku", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/apps/{app}", headers=_headers())
            _raise_for(r)
            p = r.json()
        return {
            "id": p.get("id"),
            "name": p.get("name"),
            "region": (p.get("region") or {}).get("name"),
            "stack": (p.get("stack") or {}).get("name"),
            "created_at": p.get("created_at"),
            "released_at": p.get("released_at"),
            "web_url": p.get("web_url"),
        }

    @mcp.tool
    async def list_dynos(
        app: Annotated[str, Field(min_length=1, description="Heroku app id or name")],
    ) -> dict:
        """List dynos of a Heroku app."""
        async with make_client("heroku", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/apps/{app}/dynos", headers=_headers())
            _raise_for(r)
            data = r.json()
        return {
            "dynos": [
                {
                    "id": p.get("id"),
                    "name": p.get("name"),
                    "type": p.get("type"),
                    "state": p.get("state"),
                    "size": p.get("size"),
                    "updated_at": p.get("updated_at"),
                }
                for p in data
            ]
        }
