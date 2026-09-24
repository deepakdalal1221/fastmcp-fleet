from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import NotFoundError
from mcp_common.http import is_offline
from pydantic import Field


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_conversations() -> dict:
        """list_conversations for intercom. Offline: local_store."""
        if is_offline():
            items = local_store.list_all("intercom", "conversations")
            return {"items": items, "count": len(items)}
        return {"note": "live mode not implemented in offline fleet"}

    @mcp.tool
    async def list_contacts() -> dict:
        """list_contacts for intercom. Offline: local_store."""
        if is_offline():
            items = local_store.list_all("intercom", "contacts")
            return {"items": items, "count": len(items)}
        return {"note": "live mode not implemented in offline fleet"}
