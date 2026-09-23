from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import AuthError, ConfigError, NotFoundError, RateLimitError, UpstreamError
from mcp_common.http import is_offline, make_client
from pydantic import Field

_TIMEOUT = 30.0


def _base() -> str:
    url = os.environ.get("GITLAB_URL", "https://gitlab.com").rstrip("/")
    return url + "/api/v4"


def _token() -> str:
    v = os.environ.get("GITLAB_TOKEN")
    if not v:
        raise ConfigError("GITLAB_TOKEN is not set")
    return v


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_token()}", "Accept": "application/json"}


def _raise_for(r: httpx.Response) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"gitlab-ci auth failed: HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("gitlab-ci resource not found")
    if r.status_code == 429:
        raise RateLimitError("gitlab-ci rate limited")
    if r.status_code >= 400:
        raise UpstreamError(f"gitlab-ci HTTP {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_pipelines(
        project_id: Annotated[
            str, Field(min_length=1, description="numeric id or URL-encoded 'group/project'")
        ],
        per_page: Annotated[int, Field(ge=1, le=100)] = 20,
        status: Annotated[
            str | None, Field(description="running | success | failed | canceled | manual")
        ] = None,
    ) -> dict:
        """List CI pipelines for a GitLab project."""
        params = {"per_page": per_page}
        if status:
            params["status"] = status
        async with make_client("gitlab-ci", timeout=_TIMEOUT) as c:
            r = await c.get(
                f"{_base()}/projects/{project_id}/pipelines", headers=_headers(), params=params
            )
            _raise_for(r)
            data = r.json()
        return {
            "pipelines": [
                {
                    "id": p["id"],
                    "status": p.get("status"),
                    "ref": p.get("ref"),
                    "sha": p.get("sha")[:8] if p.get("sha") else None,
                    "web_url": p.get("web_url"),
                }
                for p in data
            ]
        }

    @mcp.tool
    async def get_pipeline(
        project_id: Annotated[
            str, Field(min_length=1, description="numeric id or URL-encoded path")
        ],
        pipeline_id: Annotated[int, Field(ge=1, description="pipeline id")],
    ) -> dict:
        """Get a GitLab CI pipeline."""
        async with make_client("gitlab-ci", timeout=_TIMEOUT) as c:
            r = await c.get(
                f"{_base()}/projects/{project_id}/pipelines/{pipeline_id}", headers=_headers()
            )
            _raise_for(r)
            p = r.json()
        return {
            "id": p["id"],
            "status": p.get("status"),
            "ref": p.get("ref"),
            "sha": p.get("sha"),
            "web_url": p.get("web_url"),
            "duration": p.get("duration"),
            "created_at": p.get("created_at"),
        }

    @mcp.tool
    async def list_jobs(
        project_id: Annotated[
            str, Field(min_length=1, description="numeric id or URL-encoded path")
        ],
        pipeline_id: Annotated[int, Field(ge=1, description="pipeline id")],
    ) -> dict:
        """List jobs in a GitLab CI pipeline."""
        async with make_client("gitlab-ci", timeout=_TIMEOUT) as c:
            r = await c.get(
                f"{_base()}/projects/{project_id}/pipelines/{pipeline_id}/jobs", headers=_headers()
            )
            _raise_for(r)
            data = r.json()
        return {
            "jobs": [
                {
                    "id": j["id"],
                    "name": j.get("name"),
                    "stage": j.get("stage"),
                    "status": j.get("status"),
                    "duration": j.get("duration"),
                    "web_url": j.get("web_url"),
                }
                for j in data
            ]
        }
