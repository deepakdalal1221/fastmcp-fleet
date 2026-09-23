from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from pydantic import Field

from mcp_common.errors import AuthError, ConfigError, NotFoundError, RateLimitError, UpstreamError

_TIMEOUT = 30.0


def _api_key() -> str:
    v = os.environ.get("DATADOG_API_KEY")
    if not v:
        raise ConfigError("DATADOG_API_KEY is not set")
    return v


def _app_key() -> str:
    v = os.environ.get("DATADOG_APP_KEY")
    if not v:
        raise ConfigError("DATADOG_APP_KEY is not set")
    return v


def _base() -> str:
    site = os.environ.get("DATADOG_SITE", "datadoghq.com")
    return f"https://api.{site}"


def _headers() -> dict[str, str]:
    return {
        "DD-API-KEY": _api_key(),
        "DD-APPLICATION-KEY": _app_key(),
        "Content-Type": "application/json",
    }


def _raise_for(r: httpx.Response) -> None:
    if r.status_code < 400:
        return
    if r.status_code in (401, 403):
        raise AuthError(f"datadog auth failed: {r.text[:200]}")
    if r.status_code == 404:
        raise NotFoundError(f"datadog not found: {r.text[:200]}")
    if r.status_code == 429:
        raise RateLimitError(f"datadog rate-limited: {r.text[:200]}")
    raise UpstreamError(f"datadog {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def query_metric(
        query: Annotated[str, Field(description="Datadog metric query, e.g. 'avg:system.cpu.user{*}'")],
        from_seconds_ago: Annotated[int, Field(description="Window start relative to now", ge=1, le=86400)] = 3600,
    ) -> dict:
        """Run a Datadog metric query for the given time window."""
        import time
        now = int(time.time())
        params = {"from": now - from_seconds_ago, "to": now, "query": query}
        async with make_client("datadog", timeout=_TIMEOUT) as client:
            r = await client.get(f"{_base()}/api/v1/query", headers=_headers(), params=params)
        _raise_for(r)
        data = r.json()
        return {
            "query": query,
            "status": data.get("status"),
            "series": [
                {"metric": s.get("metric"), "points": s.get("pointlist", [])[:100], "scope": s.get("scope")}
                for s in data.get("series", [])
            ],
        }

    @mcp.tool
    async def list_monitors(
        name: Annotated[str | None, Field(description="Filter monitors by name substring")] = None,
    ) -> dict:
        """List Datadog monitors, optionally filtered by name."""
        params: dict[str, str] = {}
        if name:
            params["name"] = name
        async with make_client("datadog", timeout=_TIMEOUT) as client:
            r = await client.get(f"{_base()}/api/v1/monitor", headers=_headers(), params=params)
        _raise_for(r)
        return {
            "monitors": [
                {"id": m["id"], "name": m.get("name"), "type": m.get("type"), "overall_state": m.get("overall_state")}
                for m in r.json()
            ]
        }

    @mcp.tool
    async def search_logs(
        query: Annotated[str, Field(description="Datadog log search query")],
        from_seconds_ago: Annotated[int, Field(description="Window start relative to now", ge=1, le=86400)] = 900,
        limit: Annotated[int, Field(description="Max log lines to return", ge=1, le=1000)] = 50,
    ) -> dict:
        """Search Datadog logs within a time window."""
        import time
        now_ms = int(time.time() * 1000)
        payload = {
            "filter": {
                "query": query,
                "from": str(now_ms - from_seconds_ago * 1000),
                "to": str(now_ms),
            },
            "page": {"limit": limit},
        }
        async with make_client("datadog", timeout=_TIMEOUT) as client:
            r = await client.post(
                f"{_base()}/api/v2/logs/events/search", headers=_headers(), json=payload
            )
        _raise_for(r)
        data = r.json()
        return {
            "logs": [
                {
                    "id": l.get("id"),
                    "timestamp": l.get("attributes", {}).get("timestamp"),
                    "service": l.get("attributes", {}).get("service"),
                    "host": l.get("attributes", {}).get("host"),
                    "message": (l.get("attributes", {}).get("message") or "")[:500],
                }
                for l in data.get("data", [])
            ]
        }
