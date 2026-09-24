from __future__ import annotations

import os
from typing import Annotated

from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import AuthError, ConfigError, UpstreamError
from mcp_common.http import is_offline, make_client
from pydantic import Field

_TIMEOUT = 30.0


def _base() -> str:
    v = os.environ.get("CLICKHOUSE_URL")
    if not v:
        raise ConfigError("CLICKHOUSE_URL is not set")
    return v.rstrip("/")


def _auth() -> tuple[str, str] | None:
    u = os.environ.get("CLICKHOUSE_USER")
    p = os.environ.get("CLICKHOUSE_PASSWORD")
    if u:
        return (u, p or "")
    return None


def _raise_for(r) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"clickhouse HTTP {r.status_code}")
    if r.status_code >= 400:
        raise UpstreamError(f"clickhouse HTTP {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def query(
        sql: Annotated[str, Field(min_length=1, max_length=10000)],
    ) -> dict:
        """Execute a ClickHouse SQL query. Offline: reads canned results from local_store."""
        if is_offline():
            rec = local_store.get("clickhouse", "queries", sql.strip()[:200])
            if rec:
                return rec
            return {
                "sql": sql,
                "rows": [],
                "note": "no offline result cached; query returned empty",
            }
        client_kwargs = {"timeout": _TIMEOUT}
        async with make_client("clickhouse", **client_kwargs) as c:
            r = await c.post(_base(), content=sql.encode("utf-8"), auth=_auth())
            _raise_for(r)
        return {"sql": sql, "raw_output": r.text[:4000]}

    @mcp.tool
    async def list_tables(
        database: Annotated[str, Field(min_length=1, max_length=64)] = "default",
    ) -> dict:
        """List ClickHouse tables in a database. Offline: reads local_store."""
        if is_offline():
            tables = local_store.list_all("clickhouse", f"tables:{database}")
            return {"database": database, "tables": tables, "count": len(tables)}
        sql = f"SHOW TABLES FROM `{database}` FORMAT JSONEachRow"
        async with make_client("clickhouse", timeout=_TIMEOUT) as c:
            r = await c.post(_base(), content=sql.encode("utf-8"), auth=_auth())
            _raise_for(r)
        return {"database": database, "raw_output": r.text[:4000]}
