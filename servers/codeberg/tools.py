from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import AuthError, ConfigError, NotFoundError, UpstreamError
from mcp_common.http import is_offline, make_client
from pydantic import Field

_BASE = "https://codeberg.org/api/v1"
_TIMEOUT = 30.0


def _token():
    v = os.environ.get("CODEBERG_TOKEN")
    if not v:
        raise ConfigError("CODEBERG_TOKEN is not set")
    return v


def _headers():
    return {"Authorization": f"token {_token()}", "Accept": "application/json"}


def _raise_for(r):
    if r.status_code in (401, 403):
        raise AuthError(f"codeberg HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("codeberg not found")
    if r.status_code >= 400:
        raise UpstreamError(f"codeberg HTTP {r.status_code}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_repos(limit: Annotated[int, Field(ge=1, le=50)] = 20) -> dict:
        """List Codeberg repositories."""
        async with make_client("codeberg", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/repos/search", headers=_headers(), params={"limit": limit})
            _raise_for(r)
        data = r.json()
        return {
            "repos": [
                {
                    "id": p["id"],
                    "full_name": p["full_name"],
                    "description": p.get("description"),
                    "html_url": p.get("html_url"),
                }
                for p in data.get("data", [])
            ]
        }

    @mcp.tool
    async def get_repo(
        owner: Annotated[str, Field(min_length=1)], repo: Annotated[str, Field(min_length=1)]
    ) -> dict:
        """Get a Codeberg repo."""
        async with make_client("codeberg", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/repos/{owner}/{repo}", headers=_headers())
            _raise_for(r)
        return r.json()

    @mcp.tool
    async def list_issues(
        owner: Annotated[str, Field(min_length=1)],
        repo: Annotated[str, Field(min_length=1)],
        state: Annotated[str, Field(description="open | closed | all")] = "open",
    ) -> dict:
        """List Codeberg issues."""
        async with make_client("codeberg", timeout=_TIMEOUT) as c:
            r = await c.get(
                f"{_BASE}/repos/{owner}/{repo}/issues",
                headers=_headers(),
                params={"state": state, "type": "issues"},
            )
            _raise_for(r)
        data = r.json()
        return {
            "issues": [
                {
                    "number": i["number"],
                    "title": i.get("title"),
                    "state": i.get("state"),
                    "html_url": i.get("html_url"),
                }
                for i in data
            ]
        }
