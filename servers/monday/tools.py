from __future__ import annotations

import os
from typing import Annotated

from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import AuthError, ConfigError, NotFoundError, UpstreamError
from mcp_common.http import is_offline, make_client
from pydantic import Field

_BASE = "https://api.monday.com/v2"
_TIMEOUT = 30.0


def _token() -> str:
    v = os.environ.get("MONDAY_TOKEN")
    if not v:
        raise ConfigError("MONDAY_TOKEN is not set")
    return v


def _headers() -> dict[str, str]:
    return {"Authorization": _token(), "Content-Type": "application/json"}


def _raise_for(r) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"monday HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("monday resource not found")
    if r.status_code >= 400:
        raise UpstreamError(f"monday HTTP {r.status_code}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_boards(
        limit: Annotated[int, Field(ge=1, le=100)] = 25,
    ) -> dict:
        """List monday.com boards. Offline: reads local_store."""
        if is_offline():
            stored = local_store.list_all("monday", "boards")
            return {"boards": stored[:limit], "count": len(stored)}
        query = f"{{ boards(limit: {limit}) {{ id name state }} }}"
        async with make_client("monday", timeout=_TIMEOUT) as c:
            r = await c.post(_BASE, headers=_headers(), json={"query": query})
            _raise_for(r)
        return r.json().get("data", {})

    @mcp.tool
    async def list_items(
        board_id: Annotated[str, Field(min_length=1)],
        limit: Annotated[int, Field(ge=1, le=100)] = 25,
    ) -> dict:
        """List items on a monday.com board. Offline: reads local_store."""
        if is_offline():
            items = local_store.list_all("monday", f"items:{board_id}")
            return {"board_id": board_id, "items": items[:limit], "count": len(items)}
        query = (
            f"{{ boards(ids: {board_id}) {{ items_page(limit: {limit}) "
            f"{{ items {{ id name state }} }} }} }}"
        )
        async with make_client("monday", timeout=_TIMEOUT) as c:
            r = await c.post(_BASE, headers=_headers(), json={"query": query})
            _raise_for(r)
        return r.json().get("data", {})

    @mcp.tool
    async def create_item(
        board_id: Annotated[str, Field(min_length=1)],
        name: Annotated[str, Field(min_length=1, max_length=255)],
    ) -> dict:
        """Create a new item on a monday.com board. Offline: writes to local_store."""
        if is_offline():
            item_id = local_store.next_id("monday", "item")
            record = {"id": str(item_id), "board_id": board_id, "name": name, "state": "active"}
            local_store.put("monday", f"items:{board_id}", str(item_id), record)
            return {"created": record}
        mutation = (
            f'mutation {{ create_item(board_id: {board_id}, item_name: "{name}") {{ id name }} }}'
        )
        async with make_client("monday", timeout=_TIMEOUT) as c:
            r = await c.post(_BASE, headers=_headers(), json={"query": mutation})
            _raise_for(r)
        return r.json().get("data", {})
