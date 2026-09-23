from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import AuthError, ConfigError, NotFoundError, RateLimitError, UpstreamError
from mcp_common.http import is_offline, make_client
from pydantic import Field

_BASE = "https://app.terraform.io/api/v2"
_TIMEOUT = 30.0


def _token() -> str:
    v = os.environ.get("TFC_TOKEN")
    if not v:
        raise ConfigError("TFC_TOKEN is not set")
    return v


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_token()}",
        "Accept": "application/vnd.api+json",
        "Content-Type": "application/vnd.api+json",
    }


def _raise_for(r: httpx.Response) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"terraform auth failed: HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("terraform resource not found")
    if r.status_code == 429:
        raise RateLimitError("terraform rate limited")
    if r.status_code >= 400:
        raise UpstreamError(f"terraform HTTP {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_workspaces(
        organization: Annotated[str, Field(min_length=1, description="Terraform Cloud org name")],
        page_size: Annotated[int, Field(ge=1, le=100)] = 20,
    ) -> dict:
        """List Terraform Cloud workspaces in an organization."""
        async with make_client("terraform", timeout=_TIMEOUT) as c:
            r = await c.get(
                f"{_BASE}/organizations/{organization}/workspaces",
                headers=_headers(),
                params={"page[size]": page_size},
            )
            _raise_for(r)
            data = r.json()
        return {
            "workspaces": [
                {
                    "id": w["id"],
                    "name": w["attributes"].get("name"),
                    "terraform_version": w["attributes"].get("terraform-version"),
                    "environment": w["attributes"].get("environment"),
                }
                for w in data.get("data", [])
            ]
        }

    @mcp.tool
    async def get_workspace(
        workspace_id: Annotated[
            str, Field(min_length=1, description="Terraform workspace id (ws-...)")
        ],
    ) -> dict:
        """Get a single Terraform Cloud workspace."""
        async with make_client("terraform", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/workspaces/{workspace_id}", headers=_headers())
            _raise_for(r)
            w = r.json().get("data", {})
        a = w.get("attributes") or {}
        return {
            "id": w.get("id"),
            "name": a.get("name"),
            "terraform_version": a.get("terraform-version"),
            "auto_apply": a.get("auto-apply"),
            "locked": a.get("locked"),
        }

    @mcp.tool
    async def list_runs(
        workspace_id: Annotated[str, Field(min_length=1, description="Terraform workspace id")],
        page_size: Annotated[int, Field(ge=1, le=100)] = 20,
    ) -> dict:
        """List runs for a Terraform Cloud workspace."""
        async with make_client("terraform", timeout=_TIMEOUT) as c:
            r = await c.get(
                f"{_BASE}/workspaces/{workspace_id}/runs",
                headers=_headers(),
                params={"page[size]": page_size},
            )
            _raise_for(r)
            data = r.json()
        return {
            "runs": [
                {
                    "id": run["id"],
                    "status": run["attributes"].get("status"),
                    "created": run["attributes"].get("created-at"),
                    "message": run["attributes"].get("message"),
                }
                for run in data.get("data", [])
            ]
        }
