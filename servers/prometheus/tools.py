from __future__ import annotations

import os
import time
from typing import Annotated

import httpx
from fastmcp import FastMCP
from mcp_common.errors import AuthError, ConfigError, NotFoundError, RateLimitError, UpstreamError
from mcp_common.http import make_client
from pydantic import Field

_TIMEOUT = 30.0


def _base() -> str:
    url = os.environ.get("PROMETHEUS_URL")
    if not url:
        raise ConfigError("PROMETHEUS_URL is not set")
    return url.rstrip("/") + "/api/v1"


def _headers() -> dict[str, str]:
    return {"Accept": "application/json"}


def _raise_for(r: httpx.Response) -> None:
    if r.status_code < 400:
        return
    if r.status_code in (401, 403):
        raise AuthError(f"prometheus auth failed: {r.text[:200]}")
    if r.status_code == 404:
        raise NotFoundError(f"prometheus not found: {r.text[:200]}")
    if r.status_code == 429:
        raise RateLimitError(f"prometheus rate-limited: {r.text[:200]}")
    raise UpstreamError(f"prometheus {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def query(
        query: Annotated[str, Field(description="PromQL expression")],
    ) -> dict:
        """Execute an instant PromQL query."""
        async with make_client("prometheus", timeout=_TIMEOUT) as client:
            r = await client.get(f"{_base()}/query", headers=_headers(), params={"query": query})
        _raise_for(r)
        data = r.json()
        return {
            "status": data.get("status"),
            "result": data.get("data", {}).get("result", [])[:200],
        }

    @mcp.tool
    async def query_range(
        query: Annotated[str, Field(description="PromQL expression")],
        from_seconds_ago: Annotated[
            int, Field(description="Window start relative to now", ge=1, le=86400)
        ] = 3600,
        step: Annotated[str, Field(description="Resolution step, e.g. '60s'")] = "60s",
    ) -> dict:
        """Execute a range PromQL query over a time window."""
        now = int(time.time())
        params = {"query": query, "start": now - from_seconds_ago, "end": now, "step": step}
        async with make_client("prometheus", timeout=_TIMEOUT) as client:
            r = await client.get(f"{_base()}/query_range", headers=_headers(), params=params)
        _raise_for(r)
        data = r.json()
        return {
            "status": data.get("status"),
            "result": data.get("data", {}).get("result", [])[:200],
        }

    @mcp.tool
    async def list_targets() -> dict:
        """List Prometheus scrape targets and their health status."""
        async with make_client("prometheus", timeout=_TIMEOUT) as client:
            r = await client.get(f"{_base()}/targets", headers=_headers())
        _raise_for(r)
        data = r.json()
        active = data.get("data", {}).get("activeTargets", [])
        return {
            "targets": [
                {
                    "job": t.get("labels", {}).get("job"),
                    "instance": t.get("labels", {}).get("instance"),
                    "health": t.get("health"),
                    "last_scrape": t.get("lastScrape"),
                }
                for t in active[:200]
            ]
        }
