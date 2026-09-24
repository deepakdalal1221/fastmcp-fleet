from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import AuthError, ConfigError, NotFoundError, RateLimitError, UpstreamError
from mcp_common.http import is_offline, make_client
from pydantic import Field

_BASE = "https://analyticsdata.googleapis.com/v1beta"
_TIMEOUT = 30.0


def _token() -> str:
    v = os.environ.get("GA_TOKEN")
    if not v:
        raise ConfigError("GA_TOKEN is not set")
    return v


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"}


def _property() -> str:
    v = os.environ.get("GA_PROPERTY_ID")
    if not v:
        raise ConfigError("GA_PROPERTY_ID is not set")
    return v


def _raise_for(r: httpx.Response) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"google-analytics auth failed: HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("google-analytics resource not found")
    if r.status_code == 429:
        raise RateLimitError("google-analytics rate limited")
    if r.status_code >= 400:
        raise UpstreamError(f"google-analytics HTTP {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def run_report(
        metrics: Annotated[
            list[str], Field(description="metric names, e.g. ['activeUsers','sessions']")
        ],
        dimensions: Annotated[list[str], Field(description="dimension names, e.g. ['country']")] = [
            "date"
        ],
        date_range_days: Annotated[int, Field(ge=1, le=365)] = 7,
    ) -> dict:
        """Run a GA4 report with given metrics + dimensions over the last N days."""
        body = {
            "metrics": [{"name": m} for m in metrics],
            "dimensions": [{"name": d} for d in dimensions],
            "dateRanges": [{"startDate": f"{date_range_days}daysAgo", "endDate": "today"}],
        }
        async with make_client("google-analytics", timeout=_TIMEOUT) as c:
            r = await c.post(
                f"{_BASE}/properties/{_property()}:runReport", headers=_headers(), json=body
            )
            _raise_for(r)
        return r.json()

    @mcp.tool
    async def list_dimensions() -> dict:
        """List available GA4 dimensions for the property."""
        async with make_client("google-analytics", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/properties/{_property()}/metadata", headers=_headers())
            _raise_for(r)
            data = r.json()
        return {
            "dimensions": [
                {"apiName": d.get("apiName"), "uiName": d.get("uiName")}
                for d in data.get("dimensions", [])
            ]
        }

    @mcp.tool
    async def list_metrics() -> dict:
        """List available GA4 metrics for the property."""
        async with make_client("google-analytics", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/properties/{_property()}/metadata", headers=_headers())
            _raise_for(r)
            data = r.json()
        return {
            "metrics": [
                {"apiName": m.get("apiName"), "uiName": m.get("uiName"), "type": m.get("type")}
                for m in data.get("metrics", [])
            ]
        }
