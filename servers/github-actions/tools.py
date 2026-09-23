from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from pydantic import Field

from mcp_common.errors import AuthError, ConfigError, NotFoundError, RateLimitError, UpstreamError
from mcp_common.http import is_offline, make_client
from mcp_common import local_store

_BASE = "https://api.github.com"
_TIMEOUT = 30.0


def _token() -> str:
    v = os.environ.get("GITHUB_TOKEN")
    if not v:
        raise ConfigError("GITHUB_TOKEN is not set")
    return v


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_token()}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}


def _raise_for(r: httpx.Response) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"github-actions auth failed: HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("github-actions resource not found")
    if r.status_code == 429:
        raise RateLimitError("github-actions rate limited")
    if r.status_code >= 400:
        raise UpstreamError(f"github-actions HTTP {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_workflows(
        owner: Annotated[str, Field(min_length=1, description="repo owner")],
        repo: Annotated[str, Field(min_length=1, description="repo name")],
    ) -> dict:
        """List GitHub Actions workflows for a repo."""
        async with make_client("github-actions", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/repos/{owner}/{repo}/actions/workflows", headers=_headers())
            _raise_for(r)
            data = r.json()
        return {"workflows": [{"id": w["id"], "name": w["name"], "path": w.get("path"), "state": w.get("state")} for w in data.get("workflows", [])]}

    @mcp.tool
    async def list_workflow_runs(
        owner: Annotated[str, Field(min_length=1)],
        repo: Annotated[str, Field(min_length=1)],
        workflow_id: Annotated[int | str, Field(description="workflow id or filename")] = "",
        per_page: Annotated[int, Field(ge=1, le=100)] = 20,
    ) -> dict:
        """List recent workflow runs for a repo or a specific workflow."""
        path = f"/repos/{owner}/{repo}/actions/runs" if not workflow_id else f"/repos/{owner}/{repo}/actions/workflows/{workflow_id}/runs"
        async with make_client("github-actions", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}{path}", headers=_headers(), params={"per_page": per_page})
            _raise_for(r)
            data = r.json()
        return {"runs": [{"id": p["id"], "name": p.get("name"), "status": p.get("status"), "conclusion": p.get("conclusion"), "head_branch": p.get("head_branch"), "head_sha": (p.get("head_sha") or "")[:8], "created_at": p.get("created_at"), "html_url": p.get("html_url")} for p in data.get("workflow_runs", [])]}

    @mcp.tool
    async def get_workflow_run(
        owner: Annotated[str, Field(min_length=1)],
        repo: Annotated[str, Field(min_length=1)],
        run_id: Annotated[int, Field(ge=1, description="workflow run id")],
    ) -> dict:
        """Get a single GitHub Actions workflow run."""
        async with make_client("github-actions", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/repos/{owner}/{repo}/actions/runs/{run_id}", headers=_headers())
            _raise_for(r)
            p = r.json()
        return {"id": p.get("id"), "name": p.get("name"), "status": p.get("status"), "conclusion": p.get("conclusion"), "head_branch": p.get("head_branch"), "run_number": p.get("run_number"), "html_url": p.get("html_url"), "created_at": p.get("created_at"), "updated_at": p.get("updated_at")}
