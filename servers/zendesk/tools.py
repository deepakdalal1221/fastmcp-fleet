from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import NotFoundError
from mcp_common.http import is_offline
from pydantic import Field


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_tickets() -> dict:
        """list_tickets for zendesk. Offline: local_store."""
        if is_offline():
            items = local_store.list_all("zendesk", "tickets")
            return {"items": items, "count": len(items)}
        return {"note": "live mode not implemented in offline fleet"}

    @mcp.tool
    async def create_ticket(
        subject: Annotated[str, Field(min_length=1, max_length=500)],
        description: Annotated[str, Field(min_length=1, max_length=500)],
    ) -> dict:
        """create_ticket for zendesk. Offline: local_store."""
        if is_offline():
            rid = local_store.next_id("zendesk", "create_ticket")
            record = {"id": str(rid)}
            for k, v in list(locals().items()):
                if k not in ("rid", "record") and not k.startswith("_") and k != "self":
                    record[k] = v
            local_store.put("zendesk", "tickets", str(rid), record)
            return {"created": record}
        return {"note": "live mode not implemented in offline fleet"}

    @mcp.tool
    async def list_users() -> dict:
        """list_users for zendesk. Offline: local_store."""
        if is_offline():
            items = local_store.list_all("zendesk", "users")
            return {"items": items, "count": len(items)}
        return {"note": "live mode not implemented in offline fleet"}
