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
    v = os.environ.get("INFLUX_URL")
    if not v:
        raise ConfigError("INFLUX_URL is not set (e.g. http://localhost:8086)")
    return v.rstrip("/") + "/api/v2"


def _token():
    v = os.environ.get("INFLUX_TOKEN")
    if not v:
        raise ConfigError("INFLUX_TOKEN is not set")
    return v


def _org():
    v = os.environ.get("INFLUX_ORG")
    if not v:
        raise ConfigError("INFLUX_ORG is not set")
    return v


def _headers():
    return {"Authorization": f"Token {_token()}", "Accept": "application/json"}


def _raise_for(r):
    if r.status_code in (401, 403):
        raise AuthError(f"influxdb HTTP {r.status_code}")
    if r.status_code >= 400:
        raise UpstreamError(f"influxdb HTTP {r.status_code}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def query(flux: Annotated[str, Field(min_length=1, description="Flux query")]) -> dict:
        """Execute a Flux query against InfluxDB 2.x."""
        async with make_client("influxdb", timeout=_TIMEOUT) as c:
            r = await c.post(
                f"{_base()}/query",
                headers={**_headers(), "Content-Type": "application/vnd.flux"},
                params={"org": _org()},
                content=flux,
            )
            _raise_for(r)
        text = r.text
        return {"csv": text[:2000], "truncated": len(text) > 2000}

    @mcp.tool
    async def write(
        bucket: Annotated[str, Field(min_length=1)],
        line_protocol: Annotated[str, Field(min_length=1, description="Line Protocol payload")],
    ) -> dict:
        """Write points to an InfluxDB bucket."""
        async with make_client("influxdb", timeout=_TIMEOUT) as c:
            r = await c.post(
                f"{_base()}/write",
                headers={**_headers(), "Content-Type": "text/plain"},
                params={"org": _org(), "bucket": bucket, "precision": "ns"},
                content=line_protocol,
            )
            _raise_for(r)
        return {"written": True, "bucket": bucket, "lines": line_protocol.count("\n") + 1}

    @mcp.tool
    async def list_buckets(limit: Annotated[int, Field(ge=1, le=100)] = 20) -> dict:
        """List InfluxDB buckets."""
        async with make_client("influxdb", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_base()}/buckets", headers=_headers(), params={"limit": limit})
            _raise_for(r)
        data = r.json()
        return {
            "buckets": [
                {
                    "id": b["id"],
                    "name": b["name"],
                    "retention_seconds": (b.get("retentionRules") or [{}])[0].get("everySeconds"),
                }
                for b in data.get("buckets", [])
            ]
        }
