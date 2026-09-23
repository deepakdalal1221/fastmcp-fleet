from __future__ import annotations

import os
from typing import Annotated
from urllib.parse import quote

import httpx
from fastmcp import FastMCP
from pydantic import Field

from mcp_common.errors import (
    AuthError,
    ConfigError,
    NotFoundError,
    RateLimitError,
    UpstreamError,
)

_BASE = "https://gitlab.com/api/v4"
_TIMEOUT = 30.0


def _token() -> str:
    v = os.environ.get("GITLAB_TOKEN")
    if not v:
        raise ConfigError("GITLAB_TOKEN is not set")
    return v


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_token()}", "Accept": "application/json"}


def _raise_for(r: httpx.Response) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"gitlab auth failed: HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("gitlab resource not found")
    if r.status_code == 429:
        raise RateLimitError("gitlab rate limited")
    if r.status_code >= 400:
        raise UpstreamError(f"gitlab HTTP {r.status_code}: {r.text[:200]}")


def _pid(id_or_path: str) -> str:
    return quote(str(id_or_path), safe="")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_projects(
        per_page: Annotated[int, Field(ge=1, le=100, description="page size")] = 20,
        membership: Annotated[bool, Field(description="only projects the token owner belongs to")] = True,
    ) -> dict:
        """List GitLab projects visible to the caller."""
        async with make_client("gitlab", timeout=_TIMEOUT) as c:
            r = await c.get(
                f"{_BASE}/projects",
                headers=_headers(),
                params={"per_page": per_page, "membership": str(membership).lower()},
            )
            _raise_for(r)
            data = r.json()
        return {
            "projects": [
                {
                    "id": p["id"],
                    "path": p["path_with_namespace"],
                    "name": p["name"],
                    "visibility": p.get("visibility"),
                    "default_branch": p.get("default_branch"),
                }
                for p in data
            ]
        }

    @mcp.tool
    async def get_project(
        id_or_path: Annotated[str, Field(description="numeric id or 'group/project'")],
    ) -> dict:
        """Get a GitLab project by numeric id or URL-encoded path."""
        async with make_client("gitlab", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/projects/{_pid(id_or_path)}", headers=_headers())
            _raise_for(r)
            p = r.json()
        return {
            "id": p["id"],
            "path": p["path_with_namespace"],
            "name": p["name"],
            "description": p.get("description"),
            "visibility": p.get("visibility"),
            "default_branch": p.get("default_branch"),
            "web_url": p.get("web_url"),
            "star_count": p.get("star_count"),
            "forks_count": p.get("forks_count"),
        }

    @mcp.tool
    async def list_issues(
        project_id: Annotated[str, Field(description="numeric id or 'group/project'")],
        state: Annotated[str, Field(description="opened | closed | all")] = "opened",
        per_page: Annotated[int, Field(ge=1, le=100)] = 20,
    ) -> dict:
        """List issues on a GitLab project."""
        async with make_client("gitlab", timeout=_TIMEOUT) as c:
            r = await c.get(
                f"{_BASE}/projects/{_pid(project_id)}/issues",
                headers=_headers(),
                params={"state": state, "per_page": per_page},
            )
            _raise_for(r)
            data = r.json()
        return {
            "issues": [
                {
                    "iid": i["iid"],
                    "title": i["title"],
                    "state": i["state"],
                    "author": (i.get("author") or {}).get("username"),
                    "web_url": i.get("web_url"),
                }
                for i in data
            ]
        }

    @mcp.tool
    async def create_issue(
        project_id: Annotated[str, Field(description="numeric id or 'group/project'")],
        title: Annotated[str, Field(min_length=1, description="issue title")],
        description: Annotated[str | None, Field(description="markdown body")] = None,
        labels: Annotated[str | None, Field(description="comma-separated labels")] = None,
    ) -> dict:
        """Create a new issue on a GitLab project."""
        payload: dict[str, object] = {"title": title}
        if description is not None:
            payload["description"] = description
        if labels is not None:
            payload["labels"] = labels
        async with make_client("gitlab", timeout=_TIMEOUT) as c:
            r = await c.post(
                f"{_BASE}/projects/{_pid(project_id)}/issues",
                headers=_headers(),
                json=payload,
            )
            _raise_for(r)
            i = r.json()
        return {"iid": i["iid"], "title": i["title"], "state": i["state"], "web_url": i.get("web_url")}

    @mcp.tool
    async def list_merge_requests(
        project_id: Annotated[str, Field(description="numeric id or 'group/project'")],
        state: Annotated[str, Field(description="opened | closed | merged | all")] = "opened",
        per_page: Annotated[int, Field(ge=1, le=100)] = 20,
    ) -> dict:
        """List merge requests on a GitLab project."""
        async with make_client("gitlab", timeout=_TIMEOUT) as c:
            r = await c.get(
                f"{_BASE}/projects/{_pid(project_id)}/merge_requests",
                headers=_headers(),
                params={"state": state, "per_page": per_page},
            )
            _raise_for(r)
            data = r.json()
        return {
            "merge_requests": [
                {
                    "iid": m["iid"],
                    "title": m["title"],
                    "state": m["state"],
                    "source_branch": m.get("source_branch"),
                    "target_branch": m.get("target_branch"),
                    "author": (m.get("author") or {}).get("username"),
                    "web_url": m.get("web_url"),
                }
                for m in data
            ]
        }
