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

_TIMEOUT = 30.0


def _base() -> str:
    v = os.environ.get("TOWER_URL")
    if not v:
        raise ConfigError("TOWER_URL is not set")
    return v.rstrip("/")


def _token() -> str:
    v = os.environ.get("TOWER_TOKEN")
    if not v:
        raise ConfigError("TOWER_TOKEN is not set")
    return v


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_token()}", "Accept": "application/json"}


def _raise_for(r: httpx.Response) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"ansible auth failed: HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("ansible resource not found")
    if r.status_code == 429:
        raise RateLimitError("ansible rate limited")
    if r.status_code >= 400:
        raise UpstreamError(f"ansible HTTP {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_inventories() -> dict:
        """List Ansible AWX/Automation Platform inventories."""
        async with make_client("ansible", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_base()}/api/v2/inventories/", headers=_headers())
            _raise_for(r)
            data = r.json()
        return {
            "inventories": [
                {
                    "id": p["id"],
                    "name": p["name"],
                    "kind": p.get("kind"),
                    "total_hosts": p.get("total_hosts"),
                }
                for p in data.get("results", [])
            ]
        }

    @mcp.tool
    async def list_projects() -> dict:
        """List Ansible projects."""
        async with make_client("ansible", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_base()}/api/v2/projects/", headers=_headers())
            _raise_for(r)
            data = r.json()
        return {
            "projects": [
                {
                    "id": p["id"],
                    "name": p["name"],
                    "scm_type": p.get("scm_type"),
                    "scm_url": p.get("scm_url"),
                    "status": p.get("status"),
                }
                for p in data.get("results", [])
            ]
        }

    @mcp.tool
    async def list_job_templates() -> dict:
        """List Ansible job templates."""
        async with make_client("ansible", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_base()}/api/v2/job_templates/", headers=_headers())
            _raise_for(r)
            data = r.json()
        return {
            "job_templates": [
                {
                    "id": p["id"],
                    "name": p["name"],
                    "job_type": p.get("job_type"),
                    "playbook": p.get("playbook"),
                }
                for p in data.get("results", [])
            ]
        }
