from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import NotFoundError
from mcp_common.http import is_offline
from pydantic import Field


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def query(sql: Annotated[str, Field(min_length=1, max_length=500)]) -> dict:
        """query for cockroachdb. Offline: local_store."""
        if is_offline():
            rec = local_store.get("cockroachdb", "queries", str(sql))
            if not rec:
                raise NotFoundError(f"cockroachdb record {sql} not found")
            return rec
        return {"note": "live mode not implemented"}

    @mcp.tool
    async def list_tables(
        database: Annotated[str, Field(min_length=1, max_length=500)] = "defaultdb",
    ) -> dict:
        """list_tables for cockroachdb. Offline: local_store."""
        if is_offline():
            items = local_store.list_all("cockroachdb", "tables:" + database)
            return {"items": items, "count": len(items)}
        return {"note": "live mode not implemented"}
