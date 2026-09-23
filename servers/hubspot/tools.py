from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from mcp_common.errors import AuthError, ConfigError, NotFoundError, RateLimitError, UpstreamError
from mcp_common.http import make_client
from pydantic import Field

_BASE = "https://api.hubapi.com/crm/v3"
_TIMEOUT = 30.0


def _token() -> str:
    v = os.environ.get("HUBSPOT_TOKEN")
    if not v:
        raise ConfigError("HUBSPOT_TOKEN is not set")
    return v


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"}


def _raise_for(r: httpx.Response) -> None:
    if r.status_code < 400:
        return
    if r.status_code in (401, 403):
        raise AuthError(f"hubspot auth failed: {r.text[:200]}")
    if r.status_code == 404:
        raise NotFoundError(f"hubspot not found: {r.text[:200]}")
    if r.status_code == 429:
        raise RateLimitError(f"hubspot rate-limited: {r.text[:200]}")
    raise UpstreamError(f"hubspot {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_contacts(
        limit: Annotated[int, Field(description="Max contacts to return", ge=1, le=100)] = 20,
    ) -> dict:
        """List HubSpot contacts."""
        async with make_client("hubspot", timeout=_TIMEOUT) as client:
            r = await client.get(
                f"{_BASE}/objects/contacts", headers=_headers(), params={"limit": limit}
            )
        _raise_for(r)
        return {
            "contacts": [
                {
                    "id": c.get("id"),
                    "firstname": c.get("properties", {}).get("firstname"),
                    "lastname": c.get("properties", {}).get("lastname"),
                    "email": c.get("properties", {}).get("email"),
                    "createdAt": c.get("createdAt"),
                }
                for c in r.json().get("results", [])
            ]
        }

    @mcp.tool
    async def list_deals(
        limit: Annotated[int, Field(description="Max deals to return", ge=1, le=100)] = 20,
    ) -> dict:
        """List HubSpot deals."""
        async with make_client("hubspot", timeout=_TIMEOUT) as client:
            r = await client.get(
                f"{_BASE}/objects/deals", headers=_headers(), params={"limit": limit}
            )
        _raise_for(r)
        return {
            "deals": [
                {
                    "id": d.get("id"),
                    "dealname": d.get("properties", {}).get("dealname"),
                    "amount": d.get("properties", {}).get("amount"),
                    "dealstage": d.get("properties", {}).get("dealstage"),
                }
                for d in r.json().get("results", [])
            ]
        }

    @mcp.tool
    async def list_companies(
        limit: Annotated[int, Field(description="Max companies to return", ge=1, le=100)] = 20,
    ) -> dict:
        """List HubSpot companies."""
        async with make_client("hubspot", timeout=_TIMEOUT) as client:
            r = await client.get(
                f"{_BASE}/objects/companies", headers=_headers(), params={"limit": limit}
            )
        _raise_for(r)
        return {
            "companies": [
                {
                    "id": c.get("id"),
                    "name": c.get("properties", {}).get("name"),
                    "domain": c.get("properties", {}).get("domain"),
                }
                for c in r.json().get("results", [])
            ]
        }
