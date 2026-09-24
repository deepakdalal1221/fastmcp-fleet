from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import NotFoundError
from mcp_common.http import is_offline
from pydantic import Field


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_tables() -> dict:
        """list_tables for dynamodb. Offline: local_store."""
        if is_offline():
            items = local_store.list_all("dynamodb", "tables")
            return {"items": items, "count": len(items)}
        return {"note": "live mode not implemented"}

    @mcp.tool
    async def get_item(
        table: Annotated[str, Field(min_length=1, max_length=500)],
        key: Annotated[str, Field(min_length=1, max_length=500)],
    ) -> dict:
        """get_item for dynamodb. Offline: local_store."""
        if is_offline():
            rec = local_store.get("dynamodb", "items:" + table, str(table))
            if not rec:
                raise NotFoundError(f"dynamodb record {table} not found")
            return rec
        return {"note": "live mode not implemented"}

    @mcp.tool
    async def put_item(
        table: Annotated[str, Field(min_length=1, max_length=500)], item: dict = {}
    ) -> dict:
        """put_item for dynamodb. Offline: local_store."""
        if is_offline():
            rid = local_store.next_id("dynamodb", "put_item")
            record = {"id": str(rid)}
            for _k, _v in list(locals().items()):
                if _k not in ("rid", "record") and not _k.startswith("_"):
                    record[_k] = _v
            local_store.put("dynamodb", "items:" + table, str(rid), record)
            return {"created": record}
        return {"note": "live mode not implemented"}

    @mcp.tool
    async def query(
        table: Annotated[str, Field(min_length=1, max_length=500)],
        expression: Annotated[str, Field(min_length=1, max_length=500)],
    ) -> dict:
        """query for dynamodb. Offline: local_store."""
        if is_offline():
            rec = local_store.get("dynamodb", "queries:" + table, str(table))
            if not rec:
                raise NotFoundError(f"dynamodb record {table} not found")
            return rec
        return {"note": "live mode not implemented"}

    @mcp.tool
    async def scan(
        table: Annotated[str, Field(min_length=1, max_length=500)],
        limit: Annotated[int, Field(ge=1, le=1000)] = 25,
    ) -> dict:
        """scan for dynamodb. Offline: local_store."""
        if is_offline():
            items = local_store.list_all("dynamodb", "items:" + table)
            return {"items": items, "count": len(items)}
        return {"note": "live mode not implemented"}
