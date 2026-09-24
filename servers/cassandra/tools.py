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
    v = os.environ.get("CASSANDRA_HTTP_URL")
    if not v:
        raise ConfigError("CASSANDRA_HTTP_URL is not set")
    return v.rstrip("/")


def _headers() -> dict[str, str]:
    tok = os.environ.get("CASSANDRA_TOKEN", "")
    h = {"Content-Type": "application/json"}
    if tok:
        h["X-Cassandra-Token"] = tok
    return h


def _raise_for(r) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"cassandra HTTP {r.status_code}")
    if r.status_code >= 400:
        raise UpstreamError(f"cassandra HTTP {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def query(
        cql: Annotated[str, Field(min_length=1, max_length=10000)],
    ) -> dict:
        """Execute a CQL query. Offline: reads cached results from local_store."""
        if is_offline():
            rec = local_store.get("cassandra", "queries", cql.strip()[:200])
            if rec:
                return rec
            return {"cql": cql, "rows": [], "note": "no offline result cached"}
        async with make_client("cassandra", timeout=_TIMEOUT) as c:
            r = await c.post(f"{_base()}/query", headers=_headers(), json={"cql": cql})
            _raise_for(r)
        return r.json()

    @mcp.tool
    async def list_keyspaces() -> dict:
        """List Cassandra keyspaces. Offline: reads local_store."""
        if is_offline():
            ks = local_store.list_all("cassandra", "keyspaces")
            return {"keyspaces": ks, "count": len(ks)}
        async with make_client("cassandra", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_base()}/keyspaces", headers=_headers())
            _raise_for(r)
        return r.json()

    @mcp.tool
    async def list_tables(
        keyspace: Annotated[str, Field(min_length=1, max_length=64)],
    ) -> dict:
        """List tables in a keyspace. Offline: reads local_store."""
        if is_offline():
            tables = local_store.list_all("cassandra", f"tables:{keyspace}")
            return {"keyspace": keyspace, "tables": tables, "count": len(tables)}
        async with make_client("cassandra", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_base()}/keyspaces/{keyspace}/tables", headers=_headers())
            _raise_for(r)
        return r.json()
