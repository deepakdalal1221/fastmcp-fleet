from __future__ import annotations

import os
from typing import Annotated

from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import ConfigError, UpstreamError, ValidationError
from mcp_common.http import is_offline
from pydantic import Field


def _path():
    return os.environ.get("DUCKDB_PATH", ":memory:")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def query(sql: Annotated[str, Field(min_length=1)]) -> dict:
        """Execute a DuckDB SQL query."""
        try:
            import duckdb
        except ImportError:
            raise UpstreamError("duckdb package not installed; add `duckdb` to extras")
        con = duckdb.connect(_path())
        try:
            cur = con.execute(sql)
            cols = [d[0] for d in cur.description] if cur.description else []
            rows = [dict(zip(cols, r)) for r in cur.fetchall()][:500]
        finally:
            con.close()
        return {"columns": cols, "rows": rows, "count": len(rows)}

    @mcp.tool
    async def list_tables() -> dict:
        """List DuckDB tables."""
        return await query.fn(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
        )

    @mcp.tool
    async def describe_table(table: Annotated[str, Field(min_length=1)]) -> dict:
        """Describe columns of a DuckDB table."""
        return await query.fn(f"PRAGMA table_info('{table}')")
