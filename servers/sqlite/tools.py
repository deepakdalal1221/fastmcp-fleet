from __future__ import annotations

import asyncio
import os
import sqlite3
from pathlib import Path
from typing import Annotated, Any

from mcp_common.errors import ConfigError, NotFoundError, ValidationError
from pydantic import Field

_MAX_ROWS = 1000


def _db_path() -> Path:
    raw = os.environ.get("SQLITE_PATH", "").strip()
    if not raw:
        raise ConfigError("SQLITE_PATH is not set")
    path = Path(raw).expanduser().resolve()
    if not path.exists():
        raise NotFoundError(f"sqlite database not found at {path}")
    return path


def _run_sync(fn):
    return asyncio.get_running_loop().run_in_executor(None, fn)


def register_tools(mcp) -> None:
    @mcp.tool
    async def query(
        sql: Annotated[str, Field(description="SQL to execute (use ? placeholders for params)")],
        params: Annotated[
            list[Any] | None,
            Field(description="Positional parameters for ? placeholders"),
        ] = None,
        limit: Annotated[int, Field(description="Max rows returned (1-1000)")] = 100,
    ) -> dict:
        """Execute a read query against the SQLite database and return rows."""
        if not sql.strip():
            raise ValidationError("sql must not be empty")
        if not 1 <= limit <= 1000:
            raise ValidationError("limit must be between 1 and 1000")
        path = _db_path()
        args = tuple(params or ())

        def _do() -> list[dict]:
            conn = sqlite3.connect(str(path))
            try:
                conn.row_factory = sqlite3.Row
                cur = conn.execute(sql, args)
                rows = cur.fetchmany(_MAX_ROWS)
                return [dict(r) for r in rows]
            finally:
                conn.close()

        rows = await _run_sync(_do)
        truncated = len(rows) >= _MAX_ROWS
        return {"rows": rows[:limit], "row_count": min(len(rows), limit), "truncated": truncated}

    @mcp.tool
    async def list_tables() -> dict:
        """List all user tables in the SQLite database."""
        path = _db_path()

        def _do() -> list[str]:
            conn = sqlite3.connect(str(path))
            try:
                cur = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                )
                return [row[0] for row in cur.fetchall()]
            finally:
                conn.close()

        return {"tables": await _run_sync(_do)}

    @mcp.tool
    async def describe_table(
        table: Annotated[str, Field(description="Table name to describe")],
    ) -> dict:
        """Return column definitions for the given table."""
        if not table.strip():
            raise ValidationError("table must not be empty")
        path = _db_path()

        def _do() -> list[dict]:
            conn = sqlite3.connect(str(path))
            try:
                cur = conn.execute(f"PRAGMA table_info({table})")
                return [
                    {
                        "name": r[1],
                        "type": r[2],
                        "not_null": bool(r[3]),
                        "default": r[4],
                        "primary_key": bool(r[5]),
                    }
                    for r in cur.fetchall()
                ]
            finally:
                conn.close()

        cols = await _run_sync(_do)
        if not cols:
            raise NotFoundError(f"table {table!r} not found")
        return {"table": table, "columns": cols}
