from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import NotFoundError
from mcp_common.http import is_offline
from pydantic import Field


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def send_message(
        chat_id: Annotated[str, Field(min_length=1, max_length=500)],
        text: Annotated[str, Field(min_length=1, max_length=500)],
    ) -> dict:
        """send_message for telegram. Offline: local_store."""
        if is_offline():
            rid = local_store.next_id("telegram", "send_message")
            record = {"id": str(rid), "sent": True}
            for k, v in list(locals().items()):
                if k not in ("rid", "record") and not k.startswith("_") and k != "self":
                    record[k] = v
            local_store.put("telegram", "sent", str(rid), record)
            return record
        return {"note": "live mode not implemented in offline fleet"}

    @mcp.tool
    async def get_updates(limit: Annotated[int, Field(ge=1, le=1000)] = 10) -> dict:
        """get_updates for telegram. Offline: local_store."""
        if is_offline():
            items = local_store.list_all("telegram", "updates")
            return {"items": items, "count": len(items)}
        return {"note": "live mode not implemented in offline fleet"}
