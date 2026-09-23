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
    url = os.environ.get("GRAFANA_URL")
    if not url:
        raise ConfigError("GRAFANA_URL is not set")
    return url.rstrip("/") + "/api"


def _token() -> str:
    t = os.environ.get("GRAFANA_TOKEN")
    if not t:
        raise ConfigError("GRAFANA_TOKEN is not set")
    return t


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"}


def _raise_for(r: httpx.Response) -> None:
    if r.status_code < 400:
        return
    if r.status_code in (401, 403):
        raise AuthError(f"grafana auth failed: {r.text[:200]}")
    if r.status_code == 404:
        raise NotFoundError(f"grafana not found: {r.text[:200]}")
    if r.status_code == 429:
        raise RateLimitError(f"grafana rate-limited: {r.text[:200]}")
    raise UpstreamError(f"grafana {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_dashboards(
        query: Annotated[str | None, Field(description="Optional search substring")] = None,
    ) -> dict:
        """List Grafana dashboards matching an optional query string."""
        params: dict[str, str] = {"type": "dash-db"}
        if query:
            params["query"] = query
        async with make_client("grafana", timeout=_TIMEOUT) as client:
            r = await client.get(f"{_base()}/search", headers=_headers(), params=params)
        _raise_for(r)
        return {
            "dashboards": [
                {
                    "uid": d.get("uid"),
                    "title": d.get("title"),
                    "url": d.get("url"),
                    "folder": d.get("folderTitle"),
                }
                for d in r.json()
            ]
        }

    @mcp.tool
    async def query_datasource(
        datasource_uid: Annotated[str, Field(description="Grafana datasource UID")],
        query: Annotated[str, Field(description="Datasource query expression")],
        from_seconds_ago: Annotated[
            int, Field(description="Window start relative to now", ge=1, le=86400)
        ] = 3600,
    ) -> dict:
        """Query a Grafana datasource with a PromQL/SQL/LogQL expression."""
        now_ms = int(time.time() * 1000)
        payload = {
            "queries": [{"refId": "A", "datasource": {"uid": datasource_uid}, "expr": query}],
            "from": str(now_ms - from_seconds_ago * 1000),
            "to": str(now_ms),
        }
        async with make_client("grafana", timeout=_TIMEOUT) as client:
            r = await client.post(f"{_base()}/ds/query", headers=_headers(), json=payload)
        _raise_for(r)
        data = r.json()
        return {"results": data.get("results", {})}
