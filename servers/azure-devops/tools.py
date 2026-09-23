from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import AuthError, ConfigError, NotFoundError, RateLimitError, UpstreamError
from mcp_common.http import is_offline, make_client
from pydantic import Field

_TIMEOUT = 30.0  # noqa
_TIMEOUT = 30.0


def _org() -> str:
    v = os.environ.get("AZURE_DEVOPS_ORG")
    if not v:
        raise ConfigError("AZURE_DEVOPS_ORG is not set")
    return v


def _token() -> str:
    v = os.environ.get("AZURE_DEVOPS_TOKEN")
    if not v:
        raise ConfigError("AZURE_DEVOPS_TOKEN is not set")
    return v


def _base() -> str:
    return f"https://dev.azure.com/{_org()}"


def _auth() -> httpx.BasicAuth:
    # Azure DevOps uses HTTP Basic with empty username + PAT
    return httpx.BasicAuth("", _token())


def _headers() -> dict[str, str]:
    return {"Accept": "application/json"}


def _raise_for(r: httpx.Response) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"azure-devops auth failed: HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("azure-devops resource not found")
    if r.status_code == 429:
        raise RateLimitError("azure-devops rate limited")
    if r.status_code >= 400:
        raise UpstreamError(f"azure-devops HTTP {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_projects() -> dict:
        """List Azure DevOps projects in the configured organization."""
        async with make_client("azure-devops", timeout=_TIMEOUT) as c:
            r = await c.get(
                f"{_base()}/_apis/projects",
                auth=_auth(),
                headers=_headers(),
                params={"api-version": "7.1"},
            )
            _raise_for(r)
            data = r.json()
        return {
            "projects": [
                {
                    "id": p["id"],
                    "name": p["name"],
                    "state": p.get("state"),
                    "visibility": p.get("visibility"),
                }
                for p in data.get("value", [])
            ]
        }

    @mcp.tool
    async def list_repos(
        project: Annotated[str, Field(min_length=1, description="Azure DevOps project name or id")],
    ) -> dict:
        """List Azure DevOps repositories in a project."""
        async with make_client("azure-devops", timeout=_TIMEOUT) as c:
            r = await c.get(
                f"{_base()}/{project}/_apis/git/repositories",
                auth=_auth(),
                headers=_headers(),
                params={"api-version": "7.1"},
            )
            _raise_for(r)
            data = r.json()
        return {
            "repos": [
                {
                    "id": p["id"],
                    "name": p["name"],
                    "default_branch": p.get("defaultBranch"),
                    "size": p.get("size"),
                    "url": p.get("webUrl"),
                }
                for p in data.get("value", [])
            ]
        }

    @mcp.tool
    async def list_pipelines(
        project: Annotated[str, Field(min_length=1, description="Azure DevOps project name or id")],
    ) -> dict:
        """List Azure DevOps pipelines in a project."""
        async with make_client("azure-devops", timeout=_TIMEOUT) as c:
            r = await c.get(
                f"{_base()}/{project}/_apis/pipelines",
                auth=_auth(),
                headers=_headers(),
                params={"api-version": "7.1"},
            )
            _raise_for(r)
            data = r.json()
        return {
            "pipelines": [
                {
                    "id": p["id"],
                    "name": p["name"],
                    "folder": p.get("folder"),
                    "revision": p.get("revision"),
                }
                for p in data.get("value", [])
            ]
        }
