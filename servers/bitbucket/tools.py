from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from pydantic import Field

from mcp_common.errors import AuthError, ConfigError, NotFoundError, RateLimitError, UpstreamError
from mcp_common.http import is_offline, make_client
from mcp_common import local_store

_BASE = "https://api.bitbucket.org/2.0"
_TIMEOUT = 30.0


def _token() -> str:
    v = os.environ.get("BITBUCKET_APP_PASSWORD")
    if not v:
        raise ConfigError("BITBUCKET_APP_PASSWORD is not set")
    return v


def _auth() -> httpx.BasicAuth:
    user = os.environ.get("BITBUCKET_USER")
    pwd = os.environ.get("BITBUCKET_APP_PASSWORD")
    if not user or not pwd:
        raise ConfigError("BITBUCKET_USER and BITBUCKET_APP_PASSWORD must be set")
    return httpx.BasicAuth(user, pwd)


def _headers() -> dict[str, str]:
    return {"Accept": "application/json"}


def _raise_for(r: httpx.Response) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"bitbucket auth failed: HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("bitbucket resource not found")
    if r.status_code == 429:
        raise RateLimitError("bitbucket rate limited")
    if r.status_code >= 400:
        raise UpstreamError(f"bitbucket HTTP {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_repositories(
        workspace: Annotated[str, Field(min_length=1, description="Bitbucket workspace slug")],
        pagelen: Annotated[int, Field(ge=1, le=100)] = 20,
    ) -> dict:
        """List Bitbucket repositories in a workspace."""
        async with make_client("bitbucket", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/repositories/{workspace}", auth=_auth(), headers=_headers(), params={"pagelen": pagelen})
            _raise_for(r)
            data = r.json()
        return {"repositories": [{"uuid": v.get("uuid"), "full_name": v.get("full_name"), "slug": v.get("slug"), "is_private": v.get("is_private"), "mainbranch": (v.get("mainbranch") or {}).get("name")} for v in data.get("values", [])]}

    @mcp.tool
    async def get_repository(
        workspace: Annotated[str, Field(min_length=1)],
        repo_slug: Annotated[str, Field(min_length=1)],
    ) -> dict:
        """Get a single Bitbucket repository."""
        async with make_client("bitbucket", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/repositories/{workspace}/{repo_slug}", auth=_auth(), headers=_headers())
            _raise_for(r)
            v = r.json()
        return {"uuid": v.get("uuid"), "full_name": v.get("full_name"), "description": v.get("description"), "size": v.get("size"), "is_private": v.get("is_private"), "mainbranch": (v.get("mainbranch") or {}).get("name")}

    @mcp.tool
    async def list_pullrequests(
        workspace: Annotated[str, Field(min_length=1)],
        repo_slug: Annotated[str, Field(min_length=1)],
        state: Annotated[str, Field(description="OPEN | MERGED | DECLINED | SUPERSEDED")] = "OPEN",
        pagelen: Annotated[int, Field(ge=1, le=50)] = 20,
    ) -> dict:
        """List Bitbucket pull requests."""
        async with make_client("bitbucket", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/repositories/{workspace}/{repo_slug}/pullrequests", auth=_auth(), headers=_headers(), params={"state": state, "pagelen": pagelen})
            _raise_for(r)
            data = r.json()
        return {"pullrequests": [{"id": v.get("id"), "title": v.get("title"), "state": v.get("state"), "author": (v.get("author") or {}).get("display_name"), "source_branch": ((v.get("source") or {}).get("branch") or {}).get("name"), "destination_branch": ((v.get("destination") or {}).get("branch") or {}).get("name")} for v in data.get("values", [])]}
