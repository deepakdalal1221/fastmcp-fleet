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

_SID = "ssh"
_TIMEOUT = 30.0
_BASE = None


def _env(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        raise ConfigError(f"{name} is not set")
    return v


def _raise_for(r: httpx.Response) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"auth failed: HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("not found")
    if r.status_code == 429:
        raise RateLimitError("rate limited by upstream")
    if r.status_code >= 400:
        raise UpstreamError(f"HTTP {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def run_command(cmd: str) -> dict:
        """Run command (create)."""
        if is_offline():
            n = local_store.next_id(_SID, "runs")
            record = {"id": n, "cmd": cmd}
            await local_store.put(_SID, "runs", str(n), record)
            return {"created": record}
        raise ConfigError("live mode not implemented; run offline")

    @mcp.tool
    async def put_file(local_path: str, remote_path: str) -> dict:
        """Put file (send)."""
        if is_offline():
            n = local_store.next_id(_SID, "uploads")
            record = {"id": n, "local_path": local_path, "remote_path": remote_path, "sent": True}
            await local_store.put(_SID, "uploads", str(n), record)
            return record
        raise ConfigError("live mode not implemented; run offline")

    @mcp.tool
    async def get_file(remote_path: str, local_path: str) -> dict:
        """Get file (send)."""
        if is_offline():
            n = local_store.next_id(_SID, "downloads")
            record = {"id": n, "remote_path": remote_path, "local_path": local_path, "sent": True}
            await local_store.put(_SID, "downloads", str(n), record)
            return record
        raise ConfigError("live mode not implemented; run offline")
