from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import AuthError, ConfigError, NotFoundError, UpstreamError
from mcp_common.http import is_offline, make_client
from pydantic import Field

_TIMEOUT = 30.0


def _base():
    v = os.environ.get("NEO4J_URL")
    if not v:
        raise ConfigError("NEO4J_URL is not set (e.g. http://localhost:7474)")
    return v.rstrip("/")


def _auth():
    u, p = os.environ.get("NEO4J_USER", "neo4j"), os.environ.get("NEO4J_PASSWORD")
    if not p:
        raise ConfigError("NEO4J_PASSWORD is not set")
    return httpx.BasicAuth(u, p)


def _raise_for(r):
    if r.status_code in (401, 403):
        raise AuthError(f"neo4j HTTP {r.status_code}")
    if r.status_code >= 400:
        raise UpstreamError(f"neo4j HTTP {r.status_code}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def cypher(
        query: Annotated[str, Field(min_length=1)],
        database: Annotated[str, Field(description="database name")] = "neo4j",
    ) -> dict:
        """Execute a Cypher query."""
        body = {"statements": [{"statement": query}]}
        async with make_client("neo4j", timeout=_TIMEOUT) as c:
            r = await c.post(
                f"{_base()}/db/{database}/tx/commit",
                auth=_auth(),
                json=body,
                headers={"Content-Type": "application/json"},
            )
            _raise_for(r)
        data = r.json()
        rows = []
        for res in data.get("results", []):
            cols = res.get("columns", [])
            for d in res.get("data", []):
                rows.append(dict(zip(cols, d.get("row", []))))
        return {"rows": rows, "count": len(rows)}

    @mcp.tool
    async def list_labels() -> dict:
        """List node labels in Neo4j."""
        return await cypher.fn("CALL db.labels()")

    @mcp.tool
    async def list_relationship_types() -> dict:
        """List relationship types in Neo4j."""
        return await cypher.fn("CALL db.relationshipTypes()")
