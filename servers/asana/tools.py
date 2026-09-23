from __future__ import annotations

from mcp_common.http import is_offline

from mcp_common import local_store

import os
from typing import Annotated

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

_BASE = "https://app.asana.com/api/1.0"
_TIMEOUT = 30.0


def _token() -> str:
    v = os.environ.get("ASANA_TOKEN")
    if not v:
        raise ConfigError("ASANA_TOKEN is not set")
    return v


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_token()}", "Accept": "application/json"}


def _raise_for(r: httpx.Response) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"asana auth failed: HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("asana resource not found")
    if r.status_code == 429:
        raise RateLimitError("asana rate limited")
    if r.status_code >= 400:
        raise UpstreamError(f"asana HTTP {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_workspaces() -> dict:
        """List Asana workspaces accessible to the caller."""
        async with make_client("asana", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/workspaces", headers=_headers())
            _raise_for(r)
            data = r.json().get("data", [])
        return {"workspaces": [{"gid": w["gid"], "name": w["name"]} for w in data]}

    @mcp.tool
    async def list_projects(
        workspace_id: Annotated[str, Field(description="Asana workspace gid")],
        limit: Annotated[int, Field(ge=1, le=100)] = 20,
    ) -> dict:
        """List Asana projects in a workspace."""
        async with make_client("asana", timeout=_TIMEOUT) as c:
            r = await c.get(
                f"{_BASE}/projects",
                headers=_headers(),
                params={"workspace": workspace_id, "limit": limit},
            )
            _raise_for(r)
            data = r.json().get("data", [])
        return {"projects": [{"gid": p["gid"], "name": p["name"]} for p in data]}

    @mcp.tool
    async def list_tasks(
        project_id: Annotated[str, Field(description="Asana project gid")],
        limit: Annotated[int, Field(ge=1, le=100)] = 20,
    ) -> dict:
        """List tasks in an Asana project. Offline mode returns locally-created tasks."""
        if is_offline():
            stored = await local_store.list_all("asana", f"tasks:{project_id}")
            tasks = [row["value"] for row in stored][:limit]
            return {"tasks": [{"gid": t["gid"], "name": t["name"]} for t in tasks]}
        async with make_client("asana", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/projects/{project_id}/tasks", headers=_headers(), params={"limit": limit})
            _raise_for(r)
            data = r.json().get("data", [])
        return {"tasks": [{"gid": t["gid"], "name": t["name"]} for t in data]}

    @mcp.tool
    async def create_task(
        project_id: Annotated[str, Field(description="Asana project gid")],
        name: Annotated[str, Field(min_length=1, description="task name")],
        notes: Annotated[str | None, Field(description="task notes/description")] = None,
        assignee: Annotated[str | None, Field(description="assignee user gid or email")] = None,
    ) -> dict:
        """Create an Asana task. Offline mode persists to local state."""
        if is_offline():
            col = f"tasks:{project_id}"
            n = local_store.next_id("asana", col)
            gid = f"1000{n}"
            task = {"gid": gid, "name": name, "notes": notes, "permalink_url": f"https://app.asana.com/0/{project_id}/{gid}"}
            await local_store.put("asana", col, gid, task)
            return {"gid": gid, "name": name, "permalink_url": task["permalink_url"]}
        data = {"name": name, "projects": [project_id]}
        if notes is not None:
            data["notes"] = notes
        if assignee is not None:
            data["assignee"] = assignee
        async with make_client("asana", timeout=_TIMEOUT) as c:
            r = await c.post(f"{_BASE}/tasks", headers=_headers(), json={"data": data})
            _raise_for(r)
            t = r.json().get("data", {})
        return {"gid": t.get("gid"), "name": t.get("name"), "permalink_url": t.get("permalink_url")}

