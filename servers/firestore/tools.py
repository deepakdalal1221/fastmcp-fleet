from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import NotFoundError
from mcp_common.http import is_offline
from pydantic import Field


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def get_document(
        collection: Annotated[str, Field(min_length=1, max_length=500)],
        doc_id: Annotated[str, Field(min_length=1, max_length=500)],
    ) -> dict:
        """get_document for firestore. Offline: local_store."""
        if is_offline():
            rec = local_store.get("firestore", "docs:" + collection, str(collection))
            if not rec:
                raise NotFoundError(f"firestore record {collection} not found")
            return rec
        return {"note": "live mode not implemented"}

    @mcp.tool
    async def set_document(
        collection: Annotated[str, Field(min_length=1, max_length=500)],
        doc_id: Annotated[str, Field(min_length=1, max_length=500)],
        data: dict = {},
    ) -> dict:
        """set_document for firestore. Offline: local_store."""
        if is_offline():
            rid = local_store.next_id("firestore", "set_document")
            record = {"id": str(rid)}
            for _k, _v in list(locals().items()):
                if _k not in ("rid", "record") and not _k.startswith("_"):
                    record[_k] = _v
            local_store.put("firestore", "docs:" + collection, str(rid), record)
            return {"created": record}
        return {"note": "live mode not implemented"}

    @mcp.tool
    async def query_collection(
        collection: Annotated[str, Field(min_length=1, max_length=500)],
        limit: Annotated[int, Field(ge=1, le=1000)] = 25,
    ) -> dict:
        """query_collection for firestore. Offline: local_store."""
        if is_offline():
            items = local_store.list_all("firestore", "docs:" + collection)
            return {"items": items, "count": len(items)}
        return {"note": "live mode not implemented"}
