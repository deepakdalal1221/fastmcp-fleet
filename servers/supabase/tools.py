from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from pydantic import Field

from mcp_common.errors import AuthError, ConfigError, NotFoundError, RateLimitError, UpstreamError
from mcp_common.http import is_offline, make_client
from mcp_common import local_store

_TIMEOUT = 30.0


def _base() -> str:
    v = os.environ.get("SUPABASE_URL")
    if not v:
        raise ConfigError("SUPABASE_URL is not set (e.g. https://xyz.supabase.co)")
    return v.rstrip("/") + "/rest/v1"


def _key() -> str:
    v = os.environ.get("SUPABASE_KEY")
    if not v:
        raise ConfigError("SUPABASE_KEY is not set (service_role or anon key)")
    return v


def _headers() -> dict[str, str]:
    k = _key()
    return {"apikey": k, "Authorization": f"Bearer {k}", "Content-Type": "application/json", "Accept": "application/json"}


def _raise_for(r: httpx.Response) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"supabase auth failed: HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("supabase resource not found")
    if r.status_code == 429:
        raise RateLimitError("supabase rate limited")
    if r.status_code >= 400:
        raise UpstreamError(f"supabase HTTP {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def select_from(
        table: Annotated[str, Field(min_length=1, description="table name")],
        select: Annotated[str, Field(description="columns to select, e.g. 'id,name'")] = "*",
        limit: Annotated[int, Field(ge=1, le=1000)] = 100,
        filter: Annotated[str | None, Field(description="PostgREST filter, e.g. 'name.eq.foo'")] = None,
    ) -> dict:
        """Select rows from a Supabase table via PostgREST."""
        params: dict[str, str | int] = {"select": select, "limit": limit}
        if filter:
            k, _, v = filter.partition("=")
            if v:
                params[k] = v
        async with make_client("supabase", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_base()}/{table}", headers=_headers(), params=params)
            _raise_for(r)
            rows = r.json()
        return {"rows": rows if isinstance(rows, list) else [rows], "count": len(rows) if isinstance(rows, list) else 1}

    @mcp.tool
    async def insert_into(
        table: Annotated[str, Field(min_length=1, description="table name")],
        row: Annotated[dict, Field(description="row to insert as an object")],
    ) -> dict:
        """Insert a row into a Supabase table."""
        async with make_client("supabase", timeout=_TIMEOUT) as c:
            r = await c.post(f"{_base()}/{table}", headers={**_headers(), "Prefer": "return=representation"}, json=row)
            _raise_for(r)
            data = r.json()
        return {"inserted": data if isinstance(data, list) else [data]}

    @mcp.tool
    async def list_tables() -> dict:
        """List Supabase tables via the pg_meta REST endpoint (falls back to synthetic offline)."""
        # pg_meta path
        base_no_v1 = _base().rsplit("/rest/v1", 1)[0]
        async with make_client("supabase", timeout=_TIMEOUT) as c:
            r = await c.get(f"{base_no_v1}/pg-meta/default/tables", headers={"apikey": _key(), "Authorization": f"Bearer {_key()}"})
            _raise_for(r)
            data = r.json()
        rows = data if isinstance(data, list) else []
        return {"tables": [{"schema": t.get("schema"), "name": t.get("name"), "rls_enabled": t.get("rls_enabled")} for t in rows]}
