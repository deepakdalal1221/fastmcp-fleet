from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import NotFoundError
from mcp_common.http import is_offline
from pydantic import Field


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_jobs(
        account_id: Annotated[str, Field(min_length=1, max_length=500)] = "default",
    ) -> dict:
        """list_jobs for dbt. Offline: local_store."""
        if is_offline():
            items = local_store.list_all("dbt", "jobs:" + account_id)
            return {"items": items, "count": len(items)}
        return {"note": "live mode not implemented"}

    @mcp.tool
    async def trigger_job(
        job_id: Annotated[str, Field(min_length=1, max_length=500)],
        cause: Annotated[str, Field(min_length=1, max_length=500)] = "manual",
    ) -> dict:
        """trigger_job for dbt. Offline: local_store."""
        if is_offline():
            rid = local_store.next_id("dbt", "trigger_job")
            record = {"id": str(rid)}
            for _k, _v in list(locals().items()):
                if _k not in ("rid", "record") and not _k.startswith("_"):
                    record[_k] = _v
            local_store.put("dbt", "runs:" + job_id, str(rid), record)
            return {"created": record}
        return {"note": "live mode not implemented"}

    @mcp.tool
    async def list_runs(
        account_id: Annotated[str, Field(min_length=1, max_length=500)] = "default",
        limit: Annotated[int, Field(ge=1, le=1000)] = 25,
    ) -> dict:
        """list_runs for dbt. Offline: local_store."""
        if is_offline():
            items = local_store.list_all("dbt", "runs:" + account_id)
            return {"items": items, "count": len(items)}
        return {"note": "live mode not implemented"}
