from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import NotFoundError
from mcp_common.http import is_offline
from pydantic import Field


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_products(limit: Annotated[int, Field(ge=1, le=1000)] = 25) -> dict:
        """list_products for woocommerce. Offline: local_store."""
        if is_offline():
            items = local_store.list_all("woocommerce", "products")
            return {"items": items, "count": len(items)}
        return {"note": "live mode not implemented in offline fleet"}

    @mcp.tool
    async def list_orders(limit: Annotated[int, Field(ge=1, le=1000)] = 25) -> dict:
        """list_orders for woocommerce. Offline: local_store."""
        if is_offline():
            items = local_store.list_all("woocommerce", "orders")
            return {"items": items, "count": len(items)}
        return {"note": "live mode not implemented in offline fleet"}
