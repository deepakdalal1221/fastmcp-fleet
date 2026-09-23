from __future__ import annotations

import os
from typing import Annotated, Any
from urllib.parse import unquote, urlparse

from pydantic import Field

from mcp_common.errors import ConfigError, NotFoundError, UpstreamError, ValidationError

try:
    import aiomysql
except ImportError:
    aiomysql = None

_MAX_ROWS = 1000


def _dsn_parts() -> dict[str, Any]:
    raw = os.environ.get("MYSQL_DSN", "").strip()
    if not raw:
        raise ConfigError("MYSQL_DSN is not set")
    parsed = urlparse(raw)
    if parsed.scheme not in {"mysql", "mysql+aiomysql"}:
        raise ConfigError("MYSQL_DSN must be mysql://user:pass@host:port/db")
    if not parsed.hostname or not parsed.path.lstrip("/"):
        raise ConfigError("MYSQL_DSN must include host and database name")
    return {
        "host": parsed.hostname,
        "port": parsed.port or 3306,
        "user": unquote(parsed.username or ""),
        "password": unquote(parsed.password or ""),
        "db": parsed.path.lstrip("/"),
    }


async def _connect():
    if aiomysql is None:
        raise ConfigError("aiomysql is not installed; add extras=[db]")
    return await aiomysql.connect(**_dsn_parts(), autocommit=True)


def register_tools(mcp) -> None:
    @mcp.tool
    async def query(
        sql: Annotated[str, Field(description="SQL to execute (use %s placeholders)")],
        params: Annotated[
            list[Any] | None, Field(description="Positional parameters for %s placeholders")
        ] = None,
        limit: Annotated[int, Field(description="Max rows returned (1-1000)")] = 100,
    ) -> dict:
        """Execute a query and return rows as dicts."""
        if not sql.strip():
            raise ValidationError("sql must not be empty")
        if not 1 <= limit <= _MAX_ROWS:
            raise ValidationError(f"limit must be between 1 and {_MAX_ROWS}")
        conn = await _connect()
        try:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(sql, tuple(params or ()))
                rows = await cur.fetchmany(_MAX_ROWS)
        except Exception as exc:
            raise UpstreamError(f"mysql query failed: {exc}") from exc
        finally:
            conn.close()
        truncated = len(rows) >= _MAX_ROWS
        return {"rows": rows[:limit], "row_count": min(len(rows), limit), "truncated": truncated}

    @mcp.tool
    async def list_tables() -> dict:
        """List tables in the current database."""
        conn = await _connect()
        try:
            async with conn.cursor() as cur:
                await cur.execute("SHOW TABLES")
                rows = await cur.fetchall()
        except Exception as exc:
            raise UpstreamError(f"mysql list_tables failed: {exc}") from exc
        finally:
            conn.close()
        return {"tables": [r[0] for r in rows]}

    @mcp.tool
    async def describe_table(
        table: Annotated[str, Field(description="Table name to describe")],
    ) -> dict:
        """Return column definitions for the given table."""
        if not table.strip():
            raise ValidationError("table must not be empty")
        conn = await _connect()
        try:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("DESCRIBE `%s`" % table.replace("`", ""))
                cols = await cur.fetchall()
        except Exception as exc:
            raise UpstreamError(f"mysql describe_table failed: {exc}") from exc
        finally:
            conn.close()
        if not cols:
            raise NotFoundError(f"table {table!r} not found")
        return {"table": table, "columns": cols}
