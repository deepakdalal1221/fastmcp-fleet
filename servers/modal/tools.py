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

_BASE = "https://api.modal.com"
_TIMEOUT = 30.0


def _token() -> str:
    v = os.environ.get("MODAL_TOKEN")
    if not v:
        raise ConfigError("MODAL_TOKEN is not set")
    return v


def _headers() -> dict[str, str]:
    tid = os.environ.get("MODAL_TOKEN_ID", "")
    return {
        "Authorization": f"Bearer {_token()}",
        "Modal-Token-Id": tid,
        "Accept": "application/json",
    }


def _raise_for(r: httpx.Response) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"modal auth failed: HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("modal resource not found")
    if r.status_code == 429:
        raise RateLimitError("modal rate limited")
    if r.status_code >= 400:
        raise UpstreamError(f"modal HTTP {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_apps() -> dict:
        """List Modal apps for the authenticated workspace."""
        async with make_client("modal", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/apps", headers=_headers())
            _raise_for(r)
            data = r.json()
        return {
            "apps": [
                {
                    "id": p.get("app_id"),
                    "name": p.get("name"),
                    "state": p.get("state"),
                    "created_at": p.get("created_at"),
                }
                for p in data.get("apps", [])
            ]
        }

    @mcp.tool
    async def get_function_stats(
        function_id: Annotated[str, Field(min_length=1, description="Modal function id")],
    ) -> dict:
        """Get runtime stats for a Modal function."""
        async with make_client("modal", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/functions/{function_id}/stats", headers=_headers())
            _raise_for(r)
            p = r.json()
        return {
            "function_id": function_id,
            "backlog": p.get("backlog"),
            "num_active_runners": p.get("num_active_runners"),
            "num_total_tasks": p.get("num_total_tasks"),
        }
