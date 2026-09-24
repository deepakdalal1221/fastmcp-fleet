from __future__ import annotations

import os
from typing import Annotated

from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import AuthError, ConfigError, NotFoundError, UpstreamError
from mcp_common.http import is_offline, make_client
from pydantic import Field

_BASE = "https://sandbox-quickbooks.api.intuit.com/v3/company"
_TIMEOUT = 30.0


def _token() -> str:
    v = os.environ.get("QB_TOKEN")
    if not v:
        raise ConfigError("QB_TOKEN is not set")
    return v


def _realm() -> str:
    v = os.environ.get("QB_REALM_ID")
    if not v:
        raise ConfigError("QB_REALM_ID is not set")
    return v


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_token()}",
        "Accept": "application/json",
    }


def _raise_for(r) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"quickbooks HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("quickbooks resource not found")
    if r.status_code >= 400:
        raise UpstreamError(f"quickbooks HTTP {r.status_code}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_invoices(
        limit: Annotated[int, Field(ge=1, le=100)] = 25,
    ) -> dict:
        """List QuickBooks invoices. Offline: reads local_store."""
        if is_offline():
            invs = local_store.list_all("quickbooks", "invoices")
            return {"invoices": invs[:limit], "count": len(invs)}
        q = f"SELECT * FROM Invoice MAXRESULTS {limit}"
        async with make_client("quickbooks", timeout=_TIMEOUT) as c:
            r = await c.get(
                f"{_BASE}/{_realm()}/query",
                headers=_headers(),
                params={"query": q},
            )
            _raise_for(r)
        return r.json()

    @mcp.tool
    async def list_customers(
        limit: Annotated[int, Field(ge=1, le=100)] = 25,
    ) -> dict:
        """List QuickBooks customers. Offline: reads local_store."""
        if is_offline():
            cs = local_store.list_all("quickbooks", "customers")
            return {"customers": cs[:limit], "count": len(cs)}
        q = f"SELECT * FROM Customer MAXRESULTS {limit}"
        async with make_client("quickbooks", timeout=_TIMEOUT) as c:
            r = await c.get(
                f"{_BASE}/{_realm()}/query",
                headers=_headers(),
                params={"query": q},
            )
            _raise_for(r)
        return r.json()
