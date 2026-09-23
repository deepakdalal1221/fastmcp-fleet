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

_BASE = "https://api.pulumi.com/api"
_TIMEOUT = 30.0


def _token() -> str:
    v = os.environ.get("PULUMI_ACCESS_TOKEN")
    if not v:
        raise ConfigError("PULUMI_ACCESS_TOKEN is not set")
    return v


def _headers() -> dict[str, str]:
    return {"Authorization": f"token {_token()}", "Accept": "application/vnd.pulumi+8"}


def _raise_for(r: httpx.Response) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"pulumi auth failed: HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("pulumi resource not found")
    if r.status_code == 429:
        raise RateLimitError("pulumi rate limited")
    if r.status_code >= 400:
        raise UpstreamError(f"pulumi HTTP {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_stacks(
        organization: Annotated[str, Field(min_length=1, description="Pulumi organization")],
    ) -> dict:
        """List Pulumi stacks for an organization."""
        async with make_client("pulumi", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/user/stacks?organization={organization}", headers=_headers())
            _raise_for(r)
            data = r.json()
        stacks = data.get("stacks") or data if isinstance(data, list) else data.get("stacks", [])
        return {
            "stacks": [
                {
                    "project": p.get("projectName"),
                    "stack": p.get("stackName"),
                    "organization": p.get("orgName"),
                }
                for p in stacks
            ]
        }

    @mcp.tool
    async def get_stack(
        organization: Annotated[str, Field(min_length=1)],
        project: Annotated[str, Field(min_length=1)],
        stack: Annotated[str, Field(min_length=1)],
    ) -> dict:
        """Get details of a single Pulumi stack."""
        async with make_client("pulumi", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/stacks/{organization}/{project}/{stack}", headers=_headers())
            _raise_for(r)
            p = r.json()
        return {
            "project": p.get("projectName"),
            "stack": p.get("stackName"),
            "organization": p.get("orgName"),
            "last_update": p.get("lastUpdate"),
            "resource_count": p.get("resourceCount"),
            "version": p.get("version"),
        }

    @mcp.tool
    async def list_organizations() -> dict:
        """List Pulumi organizations for the authenticated user."""
        async with make_client("pulumi", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/user", headers=_headers())
            _raise_for(r)
            u = r.json()
        return {
            "user": u.get("githubLogin") or u.get("name"),
            "organizations": [{"name": o.get("name")} for o in u.get("organizations", [])],
        }
