from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import (
    AuthError,
    ConfigError,
    NotFoundError,
    RateLimitError,
    UpstreamError,
)
from mcp_common.http import is_offline, make_client
from pydantic import Field

_BASE = "https://api.airtable.com/v0"
_META = "https://api.airtable.com/v0/meta"
_TIMEOUT = 30.0


def _token() -> str:
    v = os.environ.get("AIRTABLE_TOKEN")
    if not v:
        raise ConfigError("AIRTABLE_TOKEN is not set")
    return v


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_token()}", "Accept": "application/json"}


def _raise_for(r: httpx.Response) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"airtable auth failed: HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("airtable resource not found")
    if r.status_code == 429:
        raise RateLimitError("airtable rate limited")
    if r.status_code >= 400:
        raise UpstreamError(f"airtable HTTP {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_bases() -> dict:
        """List Airtable bases accessible to the token."""
        async with make_client("airtable", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_META}/bases", headers=_headers())
            _raise_for(r)
            data = r.json()
        return {
            "bases": [
                {"id": b["id"], "name": b["name"], "permission_level": b.get("permissionLevel")}
                for b in data.get("bases", [])
            ]
        }

    @mcp.tool
    async def list_tables(
        base_id: Annotated[str, Field(description="Airtable base id (starts with 'app')")],
    ) -> dict:
        """List tables in an Airtable base."""
        async with make_client("airtable", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_META}/bases/{base_id}/tables", headers=_headers())
            _raise_for(r)
            data = r.json()
        return {
            "tables": [
                {"id": t["id"], "name": t["name"], "primary_field_id": t.get("primaryFieldId")}
                for t in data.get("tables", [])
            ]
        }

    @mcp.tool
    async def list_records(
        base_id: Annotated[str, Field(description="Airtable base id")],
        table: Annotated[str, Field(description="table id or name")],
        max_records: Annotated[int, Field(ge=1, le=100, description="max rows to return")] = 20,
    ) -> dict:
        """List records from an Airtable table."""
        async with make_client("airtable", timeout=_TIMEOUT) as c:
            r = await c.get(
                f"{_BASE}/{base_id}/{table}",
                headers=_headers(),
                params={"maxRecords": max_records},
            )
            _raise_for(r)
            data = r.json()
        return {
            "records": [
                {"id": rec["id"], "fields": rec.get("fields", {})}
                for rec in data.get("records", [])
            ],
            "offset": data.get("offset"),
        }

    @mcp.tool
    async def create_record(
        base_id: Annotated[str, Field(description="Airtable base id")],
        table: Annotated[str, Field(description="table id or name")],
        fields: Annotated[dict, Field(description="record field values as an object")],
    ) -> dict:
        """Create a new record in an Airtable table."""
        async with make_client("airtable", timeout=_TIMEOUT) as c:
            r = await c.post(
                f"{_BASE}/{base_id}/{table}",
                headers=_headers(),
                json={"fields": fields},
            )
            _raise_for(r)
            rec = r.json()
        return {"id": rec.get("id"), "fields": rec.get("fields", {})}

    @mcp.tool
    async def update_record(
        base_id: Annotated[str, Field(description="Airtable base id")],
        table: Annotated[str, Field(description="table id or name")],
        record_id: Annotated[str, Field(description="Airtable record id (starts with 'rec')")],
        fields: Annotated[dict, Field(description="fields to patch on the record")],
    ) -> dict:
        """Patch fields on an existing Airtable record."""
        async with make_client("airtable", timeout=_TIMEOUT) as c:
            r = await c.patch(
                f"{_BASE}/{base_id}/{table}/{record_id}",
                headers=_headers(),
                json={"fields": fields},
            )
            _raise_for(r)
            rec = r.json()
        return {"id": rec.get("id"), "fields": rec.get("fields", {})}

    @mcp.tool
    async def delete_record(
        base_id: Annotated[str, Field(min_length=1)],
        table: Annotated[str, Field(min_length=1)],
        record_id: Annotated[str, Field(min_length=1)],
    ) -> dict:
        """Delete an Airtable record."""
        async with make_client("airtable", timeout=_TIMEOUT) as c:
            r = await c.delete(f"{_BASE}/{base_id}/{table}/{record_id}", headers=_headers())
            _raise_for(r)
        return {"deleted": True, "id": record_id}
