from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import NotFoundError
from mcp_common.http import is_offline
from pydantic import Field


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_teams() -> dict:
        """list_teams for microsoft-teams. Offline: local_store."""
        if is_offline():
            items = local_store.list_all("microsoft-teams", "teams")
            return {"items": items, "count": len(items)}
        return {"note": "live mode not implemented in offline fleet"}

    @mcp.tool
    async def list_channels(team_id: Annotated[str, Field(min_length=1, max_length=500)]) -> dict:
        """list_channels for microsoft-teams. Offline: local_store."""
        if is_offline():
            items = local_store.list_all("microsoft-teams", "channels:" + team_id)
            return {"items": items, "count": len(items)}
        return {"note": "live mode not implemented in offline fleet"}

    @mcp.tool
    async def post_message(
        team_id: Annotated[str, Field(min_length=1, max_length=500)],
        channel_id: Annotated[str, Field(min_length=1, max_length=500)],
        text: Annotated[str, Field(min_length=1, max_length=500)],
    ) -> dict:
        """post_message for microsoft-teams. Offline: local_store."""
        if is_offline():
            rid = local_store.next_id("microsoft-teams", "post_message")
            record = {"id": str(rid)}
            for k, v in list(locals().items()):
                if k not in ("rid", "record") and not k.startswith("_") and k != "self":
                    record[k] = v
            local_store.put(
                "microsoft-teams", "messages:" + team_id + ":" + channel_id, str(rid), record
            )
            return {"created": record}
        return {"note": "live mode not implemented in offline fleet"}
