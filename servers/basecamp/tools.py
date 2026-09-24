from __future__ import annotations

import os
from typing import Annotated

from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import AuthError, ConfigError, NotFoundError, UpstreamError
from mcp_common.http import is_offline, make_client
from pydantic import Field

_TIMEOUT = 30.0


def _account() -> str:
    v = os.environ.get("BASECAMP_ACCOUNT_ID")
    if not v:
        raise ConfigError("BASECAMP_ACCOUNT_ID is not set")
    return v


def _token() -> str:
    v = os.environ.get("BASECAMP_TOKEN")
    if not v:
        raise ConfigError("BASECAMP_TOKEN is not set")
    return v


def _base() -> str:
    return f"https://3.basecampapi.com/{_account()}"


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_token()}", "User-Agent": "fastmcp-fleet (dev@localhost)"}


def _raise_for(r) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"basecamp HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("basecamp resource not found")
    if r.status_code >= 400:
        raise UpstreamError(f"basecamp HTTP {r.status_code}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_projects() -> dict:
        """List Basecamp projects. Offline: reads local_store."""
        if is_offline():
            projects = local_store.list_all("basecamp", "projects")
            return {"projects": projects, "count": len(projects)}
        async with make_client("basecamp", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_base()}/projects.json", headers=_headers())
            _raise_for(r)
        return {"projects": r.json()}

    @mcp.tool
    async def list_todos(
        project_id: Annotated[str, Field(min_length=1)],
        todolist_id: Annotated[str, Field(min_length=1)],
    ) -> dict:
        """List todos on a Basecamp todolist. Offline: reads local_store."""
        key = f"todos:{project_id}:{todolist_id}"
        if is_offline():
            todos = local_store.list_all("basecamp", key)
            return {
                "project_id": project_id,
                "todolist_id": todolist_id,
                "todos": todos,
                "count": len(todos),
            }
        async with make_client("basecamp", timeout=_TIMEOUT) as c:
            r = await c.get(
                f"{_base()}/buckets/{project_id}/todolists/{todolist_id}/todos.json",
                headers=_headers(),
            )
            _raise_for(r)
        return {"todos": r.json()}

    @mcp.tool
    async def create_todo(
        project_id: Annotated[str, Field(min_length=1)],
        todolist_id: Annotated[str, Field(min_length=1)],
        content: Annotated[str, Field(min_length=1, max_length=500)],
    ) -> dict:
        """Create a Basecamp todo. Offline: writes to local_store."""
        if is_offline():
            tid = local_store.next_id("basecamp", "todo")
            rec = {
                "id": str(tid),
                "project_id": project_id,
                "todolist_id": todolist_id,
                "content": content,
                "completed": False,
            }
            local_store.put("basecamp", f"todos:{project_id}:{todolist_id}", str(tid), rec)
            return {"created": rec}
        async with make_client("basecamp", timeout=_TIMEOUT) as c:
            r = await c.post(
                f"{_base()}/buckets/{project_id}/todolists/{todolist_id}/todos.json",
                headers=_headers(),
                json={"content": content},
            )
            _raise_for(r)
        return r.json()
