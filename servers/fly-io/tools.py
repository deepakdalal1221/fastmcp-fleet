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

_BASE = "https://api.machines.dev/v1"
_TIMEOUT = 30.0


def _token() -> str:
    v = os.environ.get("FLY_API_TOKEN")
    if not v:
        raise ConfigError("FLY_API_TOKEN is not set")
    return v


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_token()}", "Accept": "application/json"}


def _raise_for(r: httpx.Response) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"fly-io auth failed: HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("fly-io resource not found")
    if r.status_code == 429:
        raise RateLimitError("fly-io rate limited")
    if r.status_code >= 400:
        raise UpstreamError(f"fly-io HTTP {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_apps(
        org_slug: Annotated[
            str, Field(description="Fly.io org slug (e.g. 'personal')")
        ] = "personal",
    ) -> dict:
        """List Fly.io apps for an organization."""
        async with make_client("fly-io", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/apps", headers=_headers(), params={"org_slug": org_slug})
            _raise_for(r)
            data = r.json()
        return {
            "apps": [
                {
                    "id": a.get("id"),
                    "name": a.get("name"),
                    "organization": (a.get("organization") or {}).get("slug"),
                    "status": a.get("status"),
                }
                for a in data.get("apps", [])
            ]
        }

    @mcp.tool
    async def list_machines(
        app_name: Annotated[str, Field(min_length=1, description="Fly.io app name")],
    ) -> dict:
        """List Machines for a Fly.io app."""
        async with make_client("fly-io", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/apps/{app_name}/machines", headers=_headers())
            _raise_for(r)
            data = r.json()
        items = data if isinstance(data, list) else data.get("machines", [])
        return {
            "machines": [
                {
                    "id": m.get("id"),
                    "name": m.get("name"),
                    "state": m.get("state"),
                    "region": m.get("region"),
                    "image": ((m.get("config") or {}).get("image")),
                    "private_ip": m.get("private_ip"),
                }
                for m in items
            ]
        }

    @mcp.tool
    async def get_machine(
        app_name: Annotated[str, Field(min_length=1, description="Fly.io app name")],
        machine_id: Annotated[str, Field(min_length=1, description="Fly Machine id")],
    ) -> dict:
        """Get a single Fly.io Machine by id."""
        async with make_client("fly-io", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/apps/{app_name}/machines/{machine_id}", headers=_headers())
            _raise_for(r)
            m = r.json()
        return {
            "id": m.get("id"),
            "name": m.get("name"),
            "state": m.get("state"),
            "region": m.get("region"),
            "image": ((m.get("config") or {}).get("image")),
            "private_ip": m.get("private_ip"),
            "instance_id": m.get("instance_id"),
            "created": m.get("created_at"),
        }
