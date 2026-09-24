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
    v = os.environ.get("GITEA_URL")
    if not v:
        raise ConfigError("GITEA_URL is not set (e.g. https://gitea.example.com)")
    return v.rstrip("/") + "/api/v1"


def _token() -> str:
    v = os.environ.get("GITEA_TOKEN")
    if not v:
        raise ConfigError("GITEA_TOKEN is not set")
    return v


def _headers() -> dict[str, str]:
    return {"Authorization": f"token {_token()}", "Accept": "application/json"}


def _raise_for(r: httpx.Response) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"gitea auth failed: HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("gitea resource not found")
    if r.status_code == 429:
        raise RateLimitError("gitea rate limited")
    if r.status_code >= 400:
        raise UpstreamError(f"gitea HTTP {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_repos(
        limit: Annotated[int, Field(ge=1, le=50)] = 20,
    ) -> dict:
        """List Gitea repositories accessible to the token owner."""
        async with make_client("gitea", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_base()}/repos/search", headers=_headers(), params={"limit": limit})
            _raise_for(r)
            data = r.json()
        return {
            "repos": [
                {
                    "id": p["id"],
                    "full_name": p["full_name"],
                    "description": p.get("description"),
                    "private": p.get("private"),
                    "default_branch": p.get("default_branch"),
                    "html_url": p.get("html_url"),
                }
                for p in data.get("data", [])
            ]
        }

    @mcp.tool
    async def get_repo(
        owner: Annotated[str, Field(min_length=1, description="repo owner (user or org)")],
        repo: Annotated[str, Field(min_length=1, description="repo name")],
    ) -> dict:
        """Get a Gitea repository by owner/name."""
        async with make_client("gitea", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_base()}/repos/{owner}/{repo}", headers=_headers())
            _raise_for(r)
            p = r.json()
        return {
            "id": p.get("id"),
            "full_name": p.get("full_name"),
            "description": p.get("description"),
            "private": p.get("private"),
            "default_branch": p.get("default_branch"),
            "stars": p.get("stars_count"),
            "forks": p.get("forks_count"),
            "html_url": p.get("html_url"),
        }

    @mcp.tool
    async def list_issues(
        owner: Annotated[str, Field(min_length=1, description="repo owner")],
        repo: Annotated[str, Field(min_length=1, description="repo name")],
        state: Annotated[str, Field(description="open | closed | all")] = "open",
        limit: Annotated[int, Field(ge=1, le=50)] = 20,
    ) -> dict:
        """List issues on a Gitea repository."""
        async with make_client("gitea", timeout=_TIMEOUT) as c:
            r = await c.get(
                f"{_base()}/repos/{owner}/{repo}/issues",
                headers=_headers(),
                params={"state": state, "limit": limit, "type": "issues"},
            )
            _raise_for(r)
            data = r.json()
        return {
            "issues": [
                {
                    "number": i["number"],
                    "title": i["title"],
                    "state": i.get("state"),
                    "user": (i.get("user") or {}).get("login"),
                    "html_url": i.get("html_url"),
                }
                for i in data
            ]
        }

    @mcp.tool
    async def create_issue(
        owner: Annotated[str, Field(min_length=1)],
        repo: Annotated[str, Field(min_length=1)],
        title: Annotated[str, Field(min_length=1)],
        body: Annotated[str | None, Field(description="issue body")] = None,
    ) -> dict:
        """Create a Gitea issue."""
        payload = {"title": title}
        if body is not None:
            payload["body"] = body
        async with make_client("gitea", timeout=_TIMEOUT) as c:
            r = await c.post(
                f"{_base()}/repos/{owner}/{repo}/issues", headers=_headers(), json=payload
            )
            _raise_for(r)
        return r.json()

    @mcp.tool
    async def close_issue(
        owner: Annotated[str, Field(min_length=1)],
        repo: Annotated[str, Field(min_length=1)],
        number: Annotated[int, Field(ge=1)],
    ) -> dict:
        """Close a Gitea issue."""
        async with make_client("gitea", timeout=_TIMEOUT) as c:
            r = await c.patch(
                f"{_base()}/repos/{owner}/{repo}/issues/{number}",
                headers=_headers(),
                json={"state": "closed"},
            )
            _raise_for(r)
        return r.json()
