from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from pydantic import Field

from mcp_common.errors import AuthError, ConfigError, NotFoundError, RateLimitError, UpstreamError

_BASE = "https://api.snyk.io/v1"
_TIMEOUT = 30.0


def _token() -> str:
    v = os.environ.get("SNYK_TOKEN")
    if not v:
        raise ConfigError("SNYK_TOKEN is not set")
    return v


def _org() -> str:
    v = os.environ.get("SNYK_ORG")
    if not v:
        raise ConfigError("SNYK_ORG is not set")
    return v


def _headers() -> dict[str, str]:
    return {"Authorization": f"token {_token()}", "Content-Type": "application/json"}


def _raise_for(r: httpx.Response) -> None:
    if r.status_code < 400:
        return
    if r.status_code in (401, 403):
        raise AuthError(f"snyk auth failed: {r.text[:200]}")
    if r.status_code == 404:
        raise NotFoundError(f"snyk not found: {r.text[:200]}")
    if r.status_code == 429:
        raise RateLimitError(f"snyk rate-limited: {r.text[:200]}")
    raise UpstreamError(f"snyk {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_projects() -> dict:
        """List Snyk projects for the configured organization."""
        async with make_client("snyk", timeout=_TIMEOUT) as client:
            r = await client.get(f"{_BASE}/org/{_org()}/projects", headers=_headers())
        _raise_for(r)
        data = r.json()
        return {
            "projects": [
                {
                    "id": p.get("id"),
                    "name": p.get("name"),
                    "type": p.get("type"),
                    "origin": p.get("origin"),
                    "created": p.get("created"),
                }
                for p in data.get("projects", [])
            ]
        }

    @mcp.tool
    async def list_issues(
        project_id: Annotated[str, Field(description="Snyk project id")],
    ) -> dict:
        """List aggregated vulnerability issues for a Snyk project."""
        payload = {
            "filters": {
                "severities": ["critical", "high", "medium", "low"],
                "types": ["vuln"],
            }
        }
        async with make_client("snyk", timeout=_TIMEOUT) as client:
            r = await client.post(
                f"{_BASE}/org/{_org()}/project/{project_id}/aggregated-issues",
                headers=_headers(),
                json=payload,
            )
        _raise_for(r)
        data = r.json()
        return {
            "issues": [
                {
                    "id": i.get("id"),
                    "title": i.get("issueData", {}).get("title"),
                    "severity": i.get("issueData", {}).get("severity"),
                    "pkgName": i.get("pkgName"),
                }
                for i in data.get("issues", [])
            ]
        }
