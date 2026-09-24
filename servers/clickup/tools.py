from __future__ import annotations

import os
from typing import Annotated

from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import AuthError, ConfigError, NotFoundError, UpstreamError
from mcp_common.http import is_offline, make_client
from pydantic import Field

_BASE = "https://api.clickup.com/api/v2"
_TIMEOUT = 30.0


def _token() -> str:
    v = os.environ.get("CLICKUP_TOKEN")
    if not v:
        raise ConfigError("CLICKUP_TOKEN is not set")
    return v


def _headers() -> dict[str, str]:
    return {"Authorization": _token(), "Content-Type": "application/json"}


def _raise_for(r) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"clickup HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("clickup resource not found")
    if r.status_code >= 400:
        raise UpstreamError(f"clickup HTTP {r.status_code}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_teams() -> dict:
        """List ClickUp teams. Offline: reads local_store."""
        if is_offline():
            teams = await local_store.list_all("clickup", "teams")
            return {"teams": teams, "count": len(teams)}
        async with make_client("clickup", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/team", headers=_headers())
            _raise_for(r)
        return r.json()

    @mcp.tool
    async def list_tasks(
        list_id: Annotated[str, Field(min_length=1)],
    ) -> dict:
        """List tasks in a ClickUp list. Offline: reads local_store."""
        if is_offline():
            tasks = await local_store.list_all("clickup", f"tasks:{list_id}")
            return {"list_id": list_id, "tasks": tasks, "count": len(tasks)}
        async with make_client("clickup", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/list/{list_id}/task", headers=_headers())
            _raise_for(r)
        return r.json()

    @mcp.tool
    async def create_task(
        list_id: Annotated[str, Field(min_length=1)],
        name: Annotated[str, Field(min_length=1, max_length=255)],
        description: Annotated[str, Field(max_length=2000)] = "",
    ) -> dict:
        """Create a new task in a ClickUp list. Offline: writes to local_store."""
        if is_offline():
            tid = local_store.next_id("clickup", "task")
            rec = {
                "id": str(tid),
                "list_id": list_id,
                "name": name,
                "description": description,
                "status": "open",
            }
            await local_store.put("clickup", f"tasks:{list_id}", str(tid), rec)
            return {"created": rec}
        payload = {"name": name, "description": description}
        async with make_client("clickup", timeout=_TIMEOUT) as c:
            r = await c.post(f"{_BASE}/list/{list_id}/task", headers=_headers(), json=payload)
            _raise_for(r)
        return r.json()
