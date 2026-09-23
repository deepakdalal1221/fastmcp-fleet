from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from pydantic import Field

from mcp_common.errors import AuthError, ConfigError, NotFoundError, RateLimitError, UpstreamError

_BASE = "https://api.cloudflare.com/client/v4"
_TIMEOUT = 30.0


def _token() -> str:
    tok = os.environ.get("CLOUDFLARE_API_TOKEN")
    if not tok:
        raise ConfigError("CLOUDFLARE_API_TOKEN is not set")
    return tok


def _account_id() -> str:
    acc = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    if not acc:
        raise ConfigError("CLOUDFLARE_ACCOUNT_ID is not set")
    return acc


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"}


def _raise_for(r: httpx.Response) -> None:
    if r.status_code < 400:
        return
    if r.status_code == 401:
        raise AuthError(f"cloudflare auth failed: {r.text[:200]}")
    if r.status_code == 404:
        raise NotFoundError(f"cloudflare not found: {r.text[:200]}")
    if r.status_code == 429:
        raise RateLimitError(f"cloudflare rate-limited: {r.text[:200]}")
    raise UpstreamError(f"cloudflare {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_zones(
        name: Annotated[str | None, Field(description="Optional zone name filter")] = None,
        per_page: Annotated[int, Field(description="Page size (1-50)", ge=1, le=50)] = 20,
    ) -> dict:
        """List Cloudflare zones (domains) on the account."""
        params: dict[str, str | int] = {"per_page": per_page}
        if name:
            params["name"] = name
        async with make_client("cloudflare", timeout=_TIMEOUT) as client:
            r = await client.get(f"{_BASE}/zones", headers=_headers(), params=params)
        _raise_for(r)
        data = r.json()
        return {"zones": [{"id": z["id"], "name": z["name"], "status": z["status"]} for z in data.get("result", [])]}

    @mcp.tool
    async def list_dns_records(
        zone_id: Annotated[str, Field(description="Cloudflare zone id")],
        record_type: Annotated[str | None, Field(description="Filter by record type (A, AAAA, CNAME, etc.)")] = None,
    ) -> dict:
        """List DNS records for a zone."""
        params: dict[str, str] = {}
        if record_type:
            params["type"] = record_type
        async with make_client("cloudflare", timeout=_TIMEOUT) as client:
            r = await client.get(
                f"{_BASE}/zones/{zone_id}/dns_records", headers=_headers(), params=params
            )
        _raise_for(r)
        data = r.json()
        return {
            "records": [
                {
                    "id": rec["id"],
                    "type": rec["type"],
                    "name": rec["name"],
                    "content": rec.get("content"),
                    "ttl": rec.get("ttl"),
                    "proxied": rec.get("proxied"),
                }
                for rec in data.get("result", [])
            ]
        }

    @mcp.tool
    async def list_workers() -> dict:
        """List Cloudflare Workers scripts on the account."""
        async with make_client("cloudflare", timeout=_TIMEOUT) as client:
            r = await client.get(
                f"{_BASE}/accounts/{_account_id()}/workers/scripts", headers=_headers()
            )
        _raise_for(r)
        data = r.json()
        return {
            "workers": [
                {"id": w["id"], "created_on": w.get("created_on"), "modified_on": w.get("modified_on")}
                for w in data.get("result", [])
            ]
        }
