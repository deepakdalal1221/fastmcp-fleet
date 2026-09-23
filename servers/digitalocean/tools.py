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

_BASE = "https://api.digitalocean.com/v2"
_TIMEOUT = 30.0


def _token() -> str:
    v = os.environ.get("DIGITALOCEAN_TOKEN")
    if not v:
        raise ConfigError("DIGITALOCEAN_TOKEN is not set")
    return v


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_token()}", "Accept": "application/json"}


def _raise_for(r: httpx.Response) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"digitalocean auth failed: HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("digitalocean resource not found")
    if r.status_code == 429:
        raise RateLimitError("digitalocean rate limited")
    if r.status_code >= 400:
        raise UpstreamError(f"digitalocean HTTP {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_droplets(
        per_page: Annotated[int, Field(ge=1, le=200)] = 20,
    ) -> dict:
        """List DigitalOcean Droplets."""
        async with make_client("digitalocean", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/droplets", headers=_headers(), params={"per_page": per_page})
            _raise_for(r)
            data = r.json()
        return {
            "droplets": [
                {
                    "id": d["id"],
                    "name": d["name"],
                    "status": d.get("status"),
                    "region": (d.get("region") or {}).get("slug"),
                    "size": (d.get("size") or {}).get("slug"),
                    "public_ip": next(
                        (n["ip_address"] for n in (d.get("networks", {}) or {}).get("v4", []) if n.get("type") == "public"),
                        None,
                    ),
                }
                for d in data.get("droplets", [])
            ]
        }

    @mcp.tool
    async def list_apps(
        per_page: Annotated[int, Field(ge=1, le=200)] = 20,
    ) -> dict:
        """List DigitalOcean App Platform apps."""
        async with make_client("digitalocean", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/apps", headers=_headers(), params={"per_page": per_page})
            _raise_for(r)
            data = r.json()
        return {
            "apps": [
                {
                    "id": a["id"],
                    "spec_name": (a.get("spec") or {}).get("name"),
                    "region": (a.get("region") or {}).get("slug"),
                    "live_url": a.get("live_url"),
                    "phase": (a.get("last_deployment_active_at") and "active") or a.get("phase"),
                    "created": a.get("created_at"),
                }
                for a in data.get("apps", [])
            ]
        }

    @mcp.tool
    async def list_databases(
        per_page: Annotated[int, Field(ge=1, le=200)] = 20,
    ) -> dict:
        """List DigitalOcean managed database clusters."""
        async with make_client("digitalocean", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/databases", headers=_headers(), params={"per_page": per_page})
            _raise_for(r)
            data = r.json()
        return {
            "databases": [
                {
                    "id": d["id"],
                    "name": d["name"],
                    "engine": d.get("engine"),
                    "version": d.get("version"),
                    "region": d.get("region"),
                    "status": d.get("status"),
                    "num_nodes": d.get("num_nodes"),
                }
                for d in data.get("databases", [])
            ]
        }
