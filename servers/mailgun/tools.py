from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import NotFoundError
from mcp_common.http import is_offline
from pydantic import Field


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def send_email(
        to: Annotated[str, Field(min_length=1, max_length=500)],
        subject: Annotated[str, Field(min_length=1, max_length=500)],
        text: Annotated[str, Field(min_length=1, max_length=500)],
    ) -> dict:
        """send_email for mailgun. Offline: local_store."""
        if is_offline():
            rid = local_store.next_id("mailgun", "send_email")
            record = {"id": str(rid), "sent": True}
            for k, v in list(locals().items()):
                if k not in ("rid", "record") and not k.startswith("_") and k != "self":
                    record[k] = v
            local_store.put("mailgun", "sent", str(rid), record)
            return record
        return {"note": "live mode not implemented in offline fleet"}

    @mcp.tool
    async def list_events(limit: Annotated[int, Field(ge=1, le=1000)] = 25) -> dict:
        """list_events for mailgun. Offline: local_store."""
        if is_offline():
            items = local_store.list_all("mailgun", "events")
            return {"items": items, "count": len(items)}
        return {"note": "live mode not implemented in offline fleet"}
