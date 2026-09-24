from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import NotFoundError
from mcp_common.http import is_offline
from pydantic import Field


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def soql(q: Annotated[str, Field(min_length=1, max_length=500)]) -> dict:
        """soql for salesforce. Offline: local_store."""
        if is_offline():
            rec = local_store.get("salesforce", "queries", str(q))
            if not rec:
                raise NotFoundError(f"salesforce record {q} not found")
            return rec
        return {"note": "live mode not implemented in offline fleet"}

    @mcp.tool
    async def get_record(
        sobject: Annotated[str, Field(min_length=1, max_length=500)],
        record_id: Annotated[str, Field(min_length=1, max_length=500)],
    ) -> dict:
        """get_record for salesforce. Offline: local_store."""
        if is_offline():
            rec = local_store.get("salesforce", "records:" + sobject, str(sobject))
            if not rec:
                raise NotFoundError(f"salesforce record {sobject} not found")
            return rec
        return {"note": "live mode not implemented in offline fleet"}

    @mcp.tool
    async def create_record(
        sobject: Annotated[str, Field(min_length=1, max_length=500)], data: dict = {}
    ) -> dict:
        """create_record for salesforce. Offline: local_store."""
        if is_offline():
            rid = local_store.next_id("salesforce", "create_record")
            record = {"id": str(rid)}
            for k, v in list(locals().items()):
                if k not in ("rid", "record") and not k.startswith("_") and k != "self":
                    record[k] = v
            local_store.put("salesforce", "records:" + sobject, str(rid), record)
            return {"created": record}
        return {"note": "live mode not implemented in offline fleet"}

    @mcp.tool
    async def update_record(
        sobject: Annotated[str, Field(min_length=1, max_length=500)],
        record_id: Annotated[str, Field(min_length=1, max_length=500)],
        data: dict = {},
    ) -> dict:
        """update_record for salesforce. Offline: local_store."""
        if is_offline():
            rid = local_store.next_id("salesforce", "update_record")
            record = {"id": str(rid)}
            for k, v in list(locals().items()):
                if k not in ("rid", "record") and not k.startswith("_") and k != "self":
                    record[k] = v
            local_store.put("salesforce", "records:" + sobject, str(rid), record)
            return {"created": record}
        return {"note": "live mode not implemented in offline fleet"}
