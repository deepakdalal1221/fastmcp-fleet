from __future__ import annotations

import os
from typing import Annotated

from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import ConfigError, UpstreamError
from mcp_common.http import is_offline
from pydantic import Field


def _dsn():
    v = os.environ.get("MARIADB_DSN")
    if not v:
        raise ConfigError("MARIADB_DSN is not set (mysql://user:pass@host:3306/db)")
    return v


async def _connect():
    try:
        import aiomysql
    except ImportError:
        raise UpstreamError("aiomysql not installed; part of --extra db")
    from urllib.parse import urlparse

    u = urlparse(_dsn())
    return await aiomysql.connect(
        host=u.hostname or "localhost",
        port=u.port or 3306,
        user=u.username or "root",
        password=u.password or "",
        db=(u.path or "/").lstrip("/") or None,
    )


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def query(sql: Annotated[str, Field(min_length=1)]) -> dict:
        """Execute a MariaDB query."""
        conn = await _connect()
        try:
            async with conn.cursor() as cur:
                await cur.execute(sql)
                if cur.description:
                    cols = [d[0] for d in cur.description]
                    rows = [dict(zip(cols, r)) for r in (await cur.fetchall())][:500]
                    return {"columns": cols, "rows": rows, "count": len(rows)}
                return {"affected": cur.rowcount}
        finally:
            conn.close()

    @mcp.tool
    async def list_tables() -> dict:
        """List MariaDB tables."""
        return await query.fn("SHOW TABLES")

    @mcp.tool
    async def describe_table(table: Annotated[str, Field(min_length=1)]) -> dict:
        """Describe columns of a MariaDB table."""
        return await query.fn(f"DESCRIBE `{table}`")
