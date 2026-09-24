from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import NotFoundError
from mcp_common.http import is_offline
from pydantic import Field


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_notebooks() -> dict:
        """list_notebooks for evernote. Offline: local_store."""
        if is_offline():
            items = local_store.list_all("evernote", "notebooks")
            return {"items": items, "count": len(items)}
        return {"note": "live mode not implemented"}

    @mcp.tool
    async def list_notes(
        notebook_guid: Annotated[str, Field(min_length=1, max_length=500)],
        limit: Annotated[int, Field(ge=1, le=1000)] = 25,
    ) -> dict:
        """list_notes for evernote. Offline: local_store."""
        if is_offline():
            items = local_store.list_all("evernote", "notes:" + notebook_guid)
            return {"items": items, "count": len(items)}
        return {"note": "live mode not implemented"}
