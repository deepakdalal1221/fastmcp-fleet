from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import AuthError, ConfigError, NotFoundError, UpstreamError
from mcp_common.http import is_offline, make_client
from pydantic import Field

_BASE = "https://api.planetscale.com/v1"
_TIMEOUT = 30.0


def _token():
    v = os.environ.get("PLANETSCALE_TOKEN")
    if not v:
        raise ConfigError("PLANETSCALE_TOKEN is not set")
    return v


def _org():
    v = os.environ.get("PLANETSCALE_ORG")
    if not v:
        raise ConfigError("PLANETSCALE_ORG is not set")
    return v


def _headers():
    return {"Authorization": _token(), "Accept": "application/json"}


def _raise_for(r):
    if r.status_code in (401, 403):
        raise AuthError(f"planetscale HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("planetscale not found")
    if r.status_code >= 400:
        raise UpstreamError(f"planetscale HTTP {r.status_code}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_databases() -> dict:
        """List PlanetScale databases in the organization."""
        async with make_client("planetscale", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/organizations/{_org()}/databases", headers=_headers())
            _raise_for(r)
        return {
            "databases": [
                {
                    "id": d["id"],
                    "name": d["name"],
                    "region": (d.get("region") or {}).get("slug"),
                    "plan": d.get("plan"),
                }
                for d in r.json().get("data", [])
            ]
        }

    @mcp.tool
    async def get_database(name: Annotated[str, Field(min_length=1)]) -> dict:
        """Get a PlanetScale database."""
        async with make_client("planetscale", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/organizations/{_org()}/databases/{name}", headers=_headers())
            _raise_for(r)
        return r.json()

    @mcp.tool
    async def list_branches(database: Annotated[str, Field(min_length=1)]) -> dict:
        """List branches of a PlanetScale database."""
        async with make_client("planetscale", timeout=_TIMEOUT) as c:
            r = await c.get(
                f"{_BASE}/organizations/{_org()}/databases/{database}/branches", headers=_headers()
            )
            _raise_for(r)
        return {
            "branches": [
                {
                    "id": b["id"],
                    "name": b["name"],
                    "production": b.get("production"),
                    "region": (b.get("region") or {}).get("slug"),
                }
                for b in r.json().get("data", [])
            ]
        }
