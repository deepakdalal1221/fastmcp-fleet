from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import AuthError, ConfigError, NotFoundError, RateLimitError, UpstreamError
from mcp_common.http import is_offline, make_client
from pydantic import Field

_BASE = "https://api.replicate.com/v1"
_TIMEOUT = 30.0


def _token() -> str:
    v = os.environ.get("REPLICATE_API_TOKEN")
    if not v:
        raise ConfigError("REPLICATE_API_TOKEN is not set")
    return v


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Token {_token()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _raise_for(r: httpx.Response) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"replicate auth failed: HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("replicate resource not found")
    if r.status_code == 429:
        raise RateLimitError("replicate rate limited")
    if r.status_code >= 400:
        raise UpstreamError(f"replicate HTTP {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_models(
        limit: Annotated[int, Field(ge=1, le=100)] = 20,
    ) -> dict:
        """List Replicate models available."""
        async with make_client("replicate", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/models", headers=_headers())
            _raise_for(r)
            data = r.json()
        results = (data.get("results") or [])[:limit]
        return {
            "models": [
                {
                    "owner": m.get("owner"),
                    "name": m.get("name"),
                    "description": m.get("description"),
                    "run_count": m.get("run_count"),
                }
                for m in results
            ]
        }

    @mcp.tool
    async def run_prediction(
        version: Annotated[str, Field(min_length=1, description="model version sha")],
        input: Annotated[dict, Field(description="model input as a JSON object")],
    ) -> dict:
        """Create a Replicate prediction."""
        body = {"version": version, "input": input}
        async with make_client("replicate", timeout=_TIMEOUT) as c:
            r = await c.post(f"{_BASE}/predictions", headers=_headers(), json=body)
            _raise_for(r)
            p = r.json()
        return {
            "id": p.get("id"),
            "status": p.get("status"),
            "urls": p.get("urls"),
            "created_at": p.get("created_at"),
        }

    @mcp.tool
    async def get_prediction(
        prediction_id: Annotated[str, Field(min_length=1, description="Replicate prediction id")],
    ) -> dict:
        """Get a Replicate prediction (poll for completion)."""
        async with make_client("replicate", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/predictions/{prediction_id}", headers=_headers())
            _raise_for(r)
            p = r.json()
        return {
            "id": p.get("id"),
            "status": p.get("status"),
            "output": p.get("output"),
            "error": p.get("error"),
            "logs": (p.get("logs") or "")[:400],
        }
