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

_BASE = "https://api.linode.com/v4"
_TIMEOUT = 30.0


def _token() -> str:
    v = os.environ.get("LINODE_TOKEN")
    if not v:
        raise ConfigError("LINODE_TOKEN is not set")
    return v


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_token()}", "Accept": "application/json"}


def _raise_for(r: httpx.Response) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"linode auth failed: HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("linode resource not found")
    if r.status_code == 429:
        raise RateLimitError("linode rate limited")
    if r.status_code >= 400:
        raise UpstreamError(f"linode HTTP {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_instances(page_size: Annotated[int, Field(ge=1, le=200)] = 20) -> dict:
        """List Linode compute instances."""
        async with make_client("linode", timeout=_TIMEOUT) as c:
            r = await c.get(
                f"{_BASE}/linode/instances", headers=_headers(), params={"page_size": page_size}
            )
            _raise_for(r)
            data = r.json()
        return {
            "instances": [
                {
                    "id": p["id"],
                    "label": p.get("label"),
                    "region": p.get("region"),
                    "type": p.get("type"),
                    "status": p.get("status"),
                    "ipv4": p.get("ipv4"),
                }
                for p in data.get("data", [])
            ]
        }

    @mcp.tool
    async def list_domains(page_size: Annotated[int, Field(ge=1, le=200)] = 20) -> dict:
        """List Linode DNS domains."""
        async with make_client("linode", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/domains", headers=_headers(), params={"page_size": page_size})
            _raise_for(r)
            data = r.json()
        return {
            "domains": [
                {
                    "id": p["id"],
                    "domain": p.get("domain"),
                    "type": p.get("type"),
                    "status": p.get("status"),
                }
                for p in data.get("data", [])
            ]
        }

    @mcp.tool
    async def list_volumes(page_size: Annotated[int, Field(ge=1, le=200)] = 20) -> dict:
        """List Linode block storage volumes."""
        async with make_client("linode", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/volumes", headers=_headers(), params={"page_size": page_size})
            _raise_for(r)
            data = r.json()
        return {
            "volumes": [
                {
                    "id": p["id"],
                    "label": p.get("label"),
                    "size_gb": p.get("size"),
                    "region": p.get("region"),
                    "status": p.get("status"),
                }
                for p in data.get("data", [])
            ]
        }
