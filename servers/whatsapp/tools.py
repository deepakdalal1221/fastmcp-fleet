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
        to: Annotated[str, Field(min_length=1, max_length=500)],
        text: Annotated[str, Field(min_length=1, max_length=500)],
    ) -> dict:
        """send_message for whatsapp. Offline: local_store."""
        if is_offline():
            rid = local_store.next_id("whatsapp", "send_message")
            record = {"id": str(rid), "sent": True}
            for k, v in list(locals().items()):
                if k not in ("rid", "record") and not k.startswith("_") and k != "self":
                    record[k] = v
            local_store.put("whatsapp", "sent", str(rid), record)
            return record
        return {"note": "live mode not implemented in offline fleet"}

    @mcp.tool
    async def send_template(
        to: Annotated[str, Field(min_length=1, max_length=500)],
        template: Annotated[str, Field(min_length=1, max_length=500)],
    ) -> dict:
        """send_template for whatsapp. Offline: local_store."""
        if is_offline():
            rid = local_store.next_id("whatsapp", "send_template")
            record = {"id": str(rid), "sent": True}
            for k, v in list(locals().items()):
                if k not in ("rid", "record") and not k.startswith("_") and k != "self":
                    record[k] = v
            local_store.put("whatsapp", "sent", str(rid), record)
            return record
        return {"note": "live mode not implemented in offline fleet"}
