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
    v = os.environ.get("SURREAL_URL")
    if not v:
        raise ConfigError("SURREAL_URL is not set (e.g. http://localhost:8000)")
    return v.rstrip("/")


def _token():
    v = os.environ.get("SURREAL_TOKEN")
    if not v:
        raise ConfigError("SURREAL_TOKEN is not set")
    return v


def _headers():
    return {
        "Authorization": f"Bearer {_token()}",
        "Accept": "application/json",
        "NS": os.environ.get("SURREAL_NS", "test"),
        "DB": os.environ.get("SURREAL_DB", "test"),
        "Content-Type": "application/json",
    }


def _raise_for(r):
    if r.status_code in (401, 403):
        raise AuthError(f"surrealdb HTTP {r.status_code}")
    if r.status_code >= 400:
        raise UpstreamError(f"surrealdb HTTP {r.status_code}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def sql(
        query: Annotated[str, Field(min_length=1, description="SurrealQL query")],
    ) -> dict:
        """Execute a SurrealQL query."""
        async with make_client("surrealdb", timeout=_TIMEOUT) as c:
            r = await c.post(f"{_base()}/sql", headers=_headers(), content=query)
            _raise_for(r)
        return {"result": r.json()}

    @mcp.tool
    async def list_tables() -> dict:
        """List tables in the current SurrealDB namespace/db."""
        return await sql.fn("INFO FOR DB")
