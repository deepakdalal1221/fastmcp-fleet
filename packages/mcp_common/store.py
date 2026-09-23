"""SQLite-backed per-server writable state for offline mode.

Each server gets its own SQLite file at `servers/<id>/state.db` containing
a single KV table `store(collection, key, value)`. This lets mutation tools
(create/update/delete) persist changes so that read tools see them within
the same offline session.

Only meaningful when running with `MCP_OFFLINE=1`; in live mode the real
upstream API owns state and this layer is unused.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from mcp_common.registry import ROOT_DIR

_SCHEMA = """
CREATE TABLE IF NOT EXISTS store (
    collection TEXT NOT NULL,
    key        TEXT NOT NULL,
    value      TEXT NOT NULL,
    PRIMARY KEY (collection, key)
)
"""


def _db_path(server_id: str) -> Path:
    """Locate the sqlite state file for a server.

    If MCP_STATE_DIR is set (e.g. via a compose volume mount), state files
    live at $MCP_STATE_DIR/<server_id>.db and survive container restarts.
    """
    import os as _os

    override = _os.environ.get("MCP_STATE_DIR", "").strip()
    if override:
        d = Path(override)
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{server_id}.db"
    d = ROOT_DIR / "servers" / server_id
    d.mkdir(parents=True, exist_ok=True)
    return d / "state.db"


@contextmanager
def _conn(server_id: str) -> Iterator[sqlite3.Connection]:
    c = sqlite3.connect(_db_path(server_id))
    try:
        c.execute(_SCHEMA)
        yield c
        c.commit()
    finally:
        c.close()


def _put_sync(server_id: str, collection: str, key: str, value: dict) -> None:
    with _conn(server_id) as c:
        c.execute(
            "INSERT INTO store(collection,key,value) VALUES(?,?,?) "
            "ON CONFLICT(collection,key) DO UPDATE SET value=excluded.value",
            (collection, key, json.dumps(value)),
        )


def _get_sync(server_id: str, collection: str, key: str) -> dict | None:
    with _conn(server_id) as c:
        r = c.execute(
            "SELECT value FROM store WHERE collection=? AND key=?",
            (collection, key),
        ).fetchone()
    return json.loads(r[0]) if r else None


def _list_sync(server_id: str, collection: str) -> list[dict[str, Any]]:
    with _conn(server_id) as c:
        rows = c.execute(
            "SELECT key,value FROM store WHERE collection=? ORDER BY rowid",
            (collection,),
        ).fetchall()
    return [{"key": k, "value": json.loads(v)} for k, v in rows]


def _delete_sync(server_id: str, collection: str, key: str) -> bool:
    with _conn(server_id) as c:
        cur = c.execute(
            "DELETE FROM store WHERE collection=? AND key=?",
            (collection, key),
        )
    return cur.rowcount > 0


def _reset_sync(server_id: str, collection: str | None = None) -> int:
    with _conn(server_id) as c:
        if collection is None:
            cur = c.execute("DELETE FROM store")
        else:
            cur = c.execute("DELETE FROM store WHERE collection=?", (collection,))
    return cur.rowcount


async def put(server_id: str, collection: str, key: str, value: dict) -> None:
    await asyncio.to_thread(_put_sync, server_id, collection, key, value)


async def get(server_id: str, collection: str, key: str) -> dict | None:
    return await asyncio.to_thread(_get_sync, server_id, collection, key)


async def list_all(server_id: str, collection: str) -> list[dict[str, Any]]:
    return await asyncio.to_thread(_list_sync, server_id, collection)


async def delete(server_id: str, collection: str, key: str) -> bool:
    return await asyncio.to_thread(_delete_sync, server_id, collection, key)


async def reset(server_id: str, collection: str | None = None) -> int:
    return await asyncio.to_thread(_reset_sync, server_id, collection)


def next_id(server_id: str, collection: str) -> int:
    """Return a monotonically increasing integer id for a collection."""
    with _conn(server_id) as c:
        r = c.execute(
            "SELECT COUNT(*) FROM store WHERE collection=?",
            (collection,),
        ).fetchone()
    return int(r[0]) + 1
