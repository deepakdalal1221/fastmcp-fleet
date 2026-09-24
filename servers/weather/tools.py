from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import NotFoundError
from mcp_common.http import is_offline
from pydantic import Field


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def current(city: Annotated[str, Field(min_length=1, max_length=500)]) -> dict:
        """current for weather. Offline: local_store."""
        if is_offline():
            rec = local_store.get("weather", "current", str(city))
            if not rec:
                raise NotFoundError(f"weather record {city} not found")
            return rec
        return {"note": "live mode not implemented in offline fleet"}

    @mcp.tool
    async def forecast(city: Annotated[str, Field(min_length=1, max_length=500)]) -> dict:
        """forecast for weather. Offline: local_store."""
        if is_offline():
            rec = local_store.get("weather", "forecast", str(city))
            if not rec:
                raise NotFoundError(f"weather record {city} not found")
            return rec
        return {"note": "live mode not implemented in offline fleet"}
