from __future__ import annotations

import os
from typing import Annotated, Any

from fastmcp import FastMCP
from mcp_common.errors import ConfigError, NotFoundError, UpstreamError, ValidationError
from pydantic import Field

try:
    import asyncpg
except ImportError:
    asyncpg = None

_MAX_ROWS = 1000
_DEFAULT_ROWS = 100
_pool: Any = None


def _dsn() -> str:
    dsn = os.environ.get("POSTGRES_DSN", "").strip()
    if not dsn:
        raise ConfigError("POSTGRES_DSN is not set")
    return dsn


async def _get_pool() -> Any:
    global _pool
    if asyncpg is None:
        raise ConfigError("asyncpg is not installed; add extras=[db]")
    if _pool is None:
        try:
            _pool = await asyncpg.create_pool(dsn=_dsn(), min_size=1, max_size=5, timeout=10.0)
        except Exception as exc:
            raise UpstreamError(f"postgres pool failed: {exc}") from exc
    return _pool


def _row_to_dict(row: Any) -> dict[str, Any]:
    return {k: _serialize(v) for k, v in dict(row).items()}


def _serialize(v: Any) -> Any:
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    return str(v)


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def query(
        sql: Annotated[str, Field(description="Parameterized SQL. Use $1, $2 for params.")],
        params: Annotated[
            list[Any] | None, Field(description="Positional parameter values")
        ] = None,
        limit: Annotated[
            int, Field(description=f"Max rows to return (1-{_MAX_ROWS})")
        ] = _DEFAULT_ROWS,
    ) -> dict:
        """Execute a read-only SQL query and return rows as list of dicts."""
        if not sql.strip():
            raise ValidationError("sql must not be empty")
        if limit < 1 or limit > _MAX_ROWS:
            raise ValidationError(f"limit must be between 1 and {_MAX_ROWS}")
        pool = await _get_pool()
        try:
            async with pool.acquire() as conn:
                rows = await conn.fetch(sql, *(params or []))
        except Exception as exc:
            raise UpstreamError(f"query failed: {exc}") from exc
        truncated = len(rows) > limit
        return {
            "rows": [_row_to_dict(r) for r in rows[:limit]],
            "row_count": min(len(rows), limit),
            "truncated": truncated,
        }

    @mcp.tool
    async def list_tables(
        schema: Annotated[str, Field(description="Schema name, defaults to public")] = "public",
    ) -> dict:
        """List tables in a schema."""
        pool = await _get_pool()
        try:
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = $1 AND table_type = 'BASE TABLE' "
                    "ORDER BY table_name",
                    schema,
                )
        except Exception as exc:
            raise UpstreamError(f"list_tables failed: {exc}") from exc
        return {"schema": schema, "tables": [r["table_name"] for r in rows]}

    @mcp.tool
    async def describe_table(
        table: Annotated[str, Field(description="Table name")],
        schema: Annotated[str, Field(description="Schema name, defaults to public")] = "public",
    ) -> dict:
        """Describe columns of a table (name, type, nullable, default)."""
        pool = await _get_pool()
        try:
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT column_name, data_type, is_nullable, column_default "
                    "FROM information_schema.columns "
                    "WHERE table_schema = $1 AND table_name = $2 "
                    "ORDER BY ordinal_position",
                    schema,
                    table,
                )
        except Exception as exc:
            raise UpstreamError(f"describe_table failed: {exc}") from exc
        if not rows:
            raise NotFoundError(f"table not found: {schema}.{table}")
        return {
            "schema": schema,
            "table": table,
            "columns": [
                {
                    "name": r["column_name"],
                    "type": r["data_type"],
                    "nullable": r["is_nullable"] == "YES",
                    "default": r["column_default"],
                }
                for r in rows
            ],
        }

    @mcp.tool
    async def list_schemas() -> dict:
        """List schemas in the database (excluding system schemas)."""
        pool = await _get_pool()
        try:
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT schema_name FROM information_schema.schemata "
                    "WHERE schema_name NOT IN ('pg_catalog', 'information_schema') "
                    "AND schema_name NOT LIKE 'pg_toast%' "
                    "AND schema_name NOT LIKE 'pg_temp%' "
                    "ORDER BY schema_name"
                )
        except Exception as exc:
            raise UpstreamError(f"list_schemas failed: {exc}") from exc
        return {"schemas": [r["schema_name"] for r in rows]}
