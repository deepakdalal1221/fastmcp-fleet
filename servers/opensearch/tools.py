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
    v = os.environ.get("OPENSEARCH_URL")
    if not v:
        raise ConfigError("OPENSEARCH_URL is not set")
    return v.rstrip("/")


def _auth():
    u, p = os.environ.get("OPENSEARCH_USER"), os.environ.get("OPENSEARCH_PASSWORD")
    if u and p:
        return httpx.BasicAuth(u, p)
    return None


def _raise_for(r):
    if r.status_code in (401, 403):
        raise AuthError(f"opensearch HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("opensearch not found")
    if r.status_code >= 400:
        raise UpstreamError(f"opensearch HTTP {r.status_code}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def search(
        index: Annotated[str, Field(min_length=1)],
        query: Annotated[dict, Field(description="OpenSearch query DSL")] = {},
        size: Annotated[int, Field(ge=1, le=1000)] = 10,
    ) -> dict:
        """Search an OpenSearch index."""
        body = {"query": query or {"match_all": {}}, "size": size}
        async with make_client("opensearch", timeout=_TIMEOUT) as c:
            r = await c.post(
                f"{_base()}/{index}/_search",
                auth=_auth(),
                json=body,
                headers={"Content-Type": "application/json"},
            )
            _raise_for(r)
        d = r.json()
        return {
            "hits": [
                {"_id": h.get("_id"), "_source": h.get("_source")}
                for h in ((d.get("hits") or {}).get("hits") or [])
            ]
        }

    @mcp.tool
    async def list_indices() -> dict:
        """List OpenSearch indices."""
        async with make_client("opensearch", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_base()}/_cat/indices", auth=_auth(), params={"format": "json"})
            _raise_for(r)
        return {
            "indices": [
                {
                    "index": i.get("index"),
                    "health": i.get("health"),
                    "docs_count": i.get("docs.count"),
                }
                for i in r.json()
            ]
        }

    @mcp.tool
    async def get_index(index: Annotated[str, Field(min_length=1)]) -> dict:
        """Get OpenSearch index metadata."""
        async with make_client("opensearch", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_base()}/{index}", auth=_auth())
            _raise_for(r)
        info = r.json().get(index, {})
        return {
            "index": index,
            "aliases": list((info.get("aliases") or {}).keys()),
            "settings": info.get("settings", {}).get("index", {}),
        }
