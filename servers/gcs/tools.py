from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import AuthError, ConfigError, NotFoundError, RateLimitError, UpstreamError
from mcp_common.http import is_offline, make_client
from pydantic import Field

_SID = "gcs"
_TIMEOUT = 30.0


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
    async def list_buckets() -> dict:
        """List buckets on gcs (offline stub)."""
        if is_offline():
            items = await local_store.list_all(_SID, "buckets")
            return {"items": items, "count": len(items)}
        raise ConfigError(f"list_buckets live mode not implemented for {_SID}; run offline")

    @mcp.tool
    async def list_objects(bucket: str) -> dict:
        """List objects on gcs (offline stub)."""
        if is_offline():
            items = await local_store.list_all(_SID, "objects")
            return {"items": items, "count": len(items)}
        raise ConfigError(f"list_objects live mode not implemented for {_SID}; run offline")

    @mcp.tool
    async def get_object(bucket: str, object_name: str) -> dict:
        """Get object on gcs (offline stub)."""
        if is_offline():
            rec = await local_store.get(_SID, "objects", str(bucket))
            if rec is None:
                raise NotFoundError(f"get_object: not found: {bucket}")
            return rec
        raise ConfigError(f"get_object live mode not implemented for {_SID}; run offline")

    @mcp.tool
    async def upload_object(bucket: str, object_name: str, content: str) -> dict:
        """Upload object on gcs (offline stub)."""
        if is_offline():
            n = local_store.next_id(_SID, "objects")
            record = {"id": n, "bucket": bucket, "object_name": object_name, "content": content}
            await local_store.put(_SID, "objects", str(n), record)
            return {"created": record}
        raise ConfigError(f"upload_object live mode not implemented for {_SID}; run offline")
