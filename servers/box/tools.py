from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import NotFoundError
from mcp_common.http import is_offline
from pydantic import Field


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_folder(
        folder_id: Annotated[str, Field(min_length=1, max_length=500)] = "0",
    ) -> dict:
        """list_folder for box. Offline: local_store."""
        if is_offline():
            items = local_store.list_all("box", "folders:" + folder_id)
            return {"items": items, "count": len(items)}
        return {"note": "live mode not implemented in offline fleet"}

    @mcp.tool
    async def upload(
        folder_id: Annotated[str, Field(min_length=1, max_length=500)],
        name: Annotated[str, Field(min_length=1, max_length=500)],
        content: Annotated[str, Field(min_length=1, max_length=500)],
    ) -> dict:
        """upload for box. Offline: local_store."""
        if is_offline():
            rid = local_store.next_id("box", "upload")
            record = {"id": str(rid)}
            for k, v in list(locals().items()):
                if k not in ("rid", "record") and not k.startswith("_") and k != "self":
                    record[k] = v
            local_store.put("box", "files:" + folder_id, str(rid), record)
            return {"created": record}
        return {"note": "live mode not implemented in offline fleet"}

    @mcp.tool
    async def download(file_id: Annotated[str, Field(min_length=1, max_length=500)]) -> dict:
        """download for box. Offline: local_store."""
        if is_offline():
            rec = local_store.get("box", "files", str(file_id))
            if not rec:
                raise NotFoundError(f"box record {file_id} not found")
            return rec
        return {"note": "live mode not implemented in offline fleet"}
