from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import NotFoundError
from mcp_common.http import is_offline
from pydantic import Field


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_notes(
        vault: Annotated[str, Field(min_length=1, max_length=500)] = "default",
    ) -> dict:
        """list_notes for obsidian. Offline: local_store."""
        if is_offline():
            items = local_store.list_all("obsidian", "notes:" + vault)
            return {"items": items, "count": len(items)}
        return {"note": "live mode not implemented in offline fleet"}

    @mcp.tool
    async def read_note(
        vault: Annotated[str, Field(min_length=1, max_length=500)],
        path: Annotated[str, Field(min_length=1, max_length=500)],
    ) -> dict:
        """read_note for obsidian. Offline: local_store."""
        if is_offline():
            rec = local_store.get("obsidian", "notes:" + vault, str(vault))
            if not rec:
                raise NotFoundError(f"obsidian record {vault} not found")
            return rec
        return {"note": "live mode not implemented in offline fleet"}

    @mcp.tool
    async def write_note(
        vault: Annotated[str, Field(min_length=1, max_length=500)],
        path: Annotated[str, Field(min_length=1, max_length=500)],
        content: Annotated[str, Field(min_length=1, max_length=500)],
    ) -> dict:
        """write_note for obsidian. Offline: local_store."""
        if is_offline():
            rid = local_store.next_id("obsidian", "write_note")
            record = {"id": str(rid)}
            for k, v in list(locals().items()):
                if k not in ("rid", "record") and not k.startswith("_") and k != "self":
                    record[k] = v
            local_store.put("obsidian", "notes:" + vault, str(rid), record)
            return {"created": record}
        return {"note": "live mode not implemented in offline fleet"}

    @mcp.tool
    async def search(
        vault: Annotated[str, Field(min_length=1, max_length=500)],
        query: Annotated[str, Field(min_length=1, max_length=500)],
    ) -> dict:
        """search for obsidian. Offline: local_store."""
        if is_offline():
            items = local_store.list_all("obsidian", "notes:" + vault)
            return {"items": items, "count": len(items)}
        return {"note": "live mode not implemented in offline fleet"}
