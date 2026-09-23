from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import AuthError, ConfigError, NotFoundError, RateLimitError, UpstreamError
from mcp_common.http import is_offline, make_client
from pydantic import Field

_BASE = "https://api.codecov.io/api/v2"
_TIMEOUT = 30.0


def _token() -> str:
    v = os.environ.get("CODECOV_TOKEN")
    if not v:
        raise ConfigError("CODECOV_TOKEN is not set")
    return v


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_token()}", "Accept": "application/json"}


def _raise_for(r: httpx.Response) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"codecov auth failed: HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("codecov resource not found")
    if r.status_code == 429:
        raise RateLimitError("codecov rate limited")
    if r.status_code >= 400:
        raise UpstreamError(f"codecov HTTP {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_repos(
        service: Annotated[
            str, Field(description="git service: github | gitlab | bitbucket")
        ] = "github",
        owner: Annotated[str, Field(min_length=1, description="account owner (user or org)")] = "",
    ) -> dict:
        """List Codecov repositories for an owner."""
        async with make_client("codecov", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/{service}/{owner}/repos", headers=_headers())
            _raise_for(r)
            data = r.json()
        return {
            "repos": [
                {
                    "name": p["name"],
                    "active": p.get("active"),
                    "coverage": p.get("coverage"),
                    "language": p.get("language"),
                }
                for p in data.get("results", [])
            ]
        }

    @mcp.tool
    async def get_repo_coverage(
        service: Annotated[str, Field(description="git service")] = "github",
        owner: Annotated[str, Field(min_length=1)] = "",
        repo: Annotated[str, Field(min_length=1, description="repo name")] = "",
    ) -> dict:
        """Get latest coverage for a Codecov repo."""
        async with make_client("codecov", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/{service}/{owner}/repos/{repo}", headers=_headers())
            _raise_for(r)
            p = r.json()
        return {
            "name": p.get("name"),
            "active": p.get("active"),
            "coverage": p.get("coverage"),
            "branch": p.get("branch"),
            "updatestamp": p.get("updatestamp"),
        }

    @mcp.tool
    async def list_reports(
        service: Annotated[str, Field(description="git service")] = "github",
        owner: Annotated[str, Field(min_length=1)] = "",
        repo: Annotated[str, Field(min_length=1)] = "",
    ) -> dict:
        """List coverage reports for a Codecov repo."""
        async with make_client("codecov", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/{service}/{owner}/repos/{repo}/reports", headers=_headers())
            _raise_for(r)
            data = r.json()
        return {
            "reports": [
                {
                    "commit": p.get("commitid", "")[:8],
                    "totals_coverage": (p.get("totals") or {}).get("coverage"),
                    "updatestamp": p.get("updatestamp"),
                }
                for p in data.get("results", [])
            ]
        }
