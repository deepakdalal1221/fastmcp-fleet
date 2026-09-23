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

_BASE = "https://api.hetzner.cloud/v1"
_TIMEOUT = 30.0


def _token() -> str:
    v = os.environ.get("HETZNER_TOKEN")
    if not v:
        raise ConfigError("HETZNER_TOKEN is not set")
    return v


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_token()}", "Accept": "application/json"}


def _raise_for(r: httpx.Response) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"hetzner auth failed: HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("hetzner resource not found")
    if r.status_code == 429:
        raise RateLimitError("hetzner rate limited")
    if r.status_code >= 400:
        raise UpstreamError(f"hetzner HTTP {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_servers(per_page: Annotated[int, Field(ge=1, le=50)] = 25) -> dict:
        """List Hetzner Cloud servers."""
        async with make_client("hetzner", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/servers", headers=_headers(), params={"per_page": per_page})
            _raise_for(r)
            data = r.json()
        return {
            "servers": [
                {
                    "id": p["id"],
                    "name": p.get("name"),
                    "status": p.get("status"),
                    "server_type": (p.get("server_type") or {}).get("name"),
                    "datacenter": (p.get("datacenter") or {}).get("name"),
                }
                for p in data.get("servers", [])
            ]
        }

    @mcp.tool
    async def list_images(
        type_: Annotated[str, Field(description="system | snapshot | backup | app")] = "system",
    ) -> dict:
        """List Hetzner Cloud images."""
        async with make_client("hetzner", timeout=_TIMEOUT) as c:
            r = await c.get(
                f"{_BASE}/images", headers=_headers(), params={"type": type_, "per_page": 50}
            )
            _raise_for(r)
            data = r.json()
        return {
            "images": [
                {
                    "id": p["id"],
                    "name": p.get("name"),
                    "os_flavor": p.get("os_flavor"),
                    "os_version": p.get("os_version"),
                }
                for p in data.get("images", [])
            ]
        }

    @mcp.tool
    async def list_ssh_keys() -> dict:
        """List Hetzner Cloud SSH keys."""
        async with make_client("hetzner", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/ssh_keys", headers=_headers())
            _raise_for(r)
            data = r.json()
        return {
            "ssh_keys": [
                {"id": p["id"], "name": p.get("name"), "fingerprint": p.get("fingerprint")}
                for p in data.get("ssh_keys", [])
            ]
        }
