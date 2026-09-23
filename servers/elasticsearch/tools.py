from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import AuthError, ConfigError, NotFoundError, RateLimitError, UpstreamError
from mcp_common.http import is_offline, make_client
from pydantic import Field

_TIMEOUT = 30.0


def _base() -> str:
    v = os.environ.get("ELASTIC_URL")
    if not v:
        raise ConfigError("ELASTIC_URL is not set (e.g. http://localhost:9200)")
    return v.rstrip("/")


def _auth() -> httpx.BasicAuth | None:
    u = os.environ.get("ELASTIC_USER")
    p = os.environ.get("ELASTIC_PASSWORD")
    if u and p:
        return httpx.BasicAuth(u, p)
    return None


def _raise_for(r: httpx.Response) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"elasticsearch auth failed: HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("elasticsearch resource not found")
    if r.status_code == 429:
        raise RateLimitError("elasticsearch rate limited")
    if r.status_code >= 400:
        raise UpstreamError(f"elasticsearch HTTP {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def search(
        index: Annotated[str, Field(min_length=1, description="index name or pattern")],
        query: Annotated[dict, Field(description="ES query DSL body; empty dict matches all")] = {},
        size: Annotated[int, Field(ge=1, le=1000)] = 10,
    ) -> dict:
        """Execute an Elasticsearch _search against an index."""
        body = {"query": query or {"match_all": {}}, "size": size}
        async with make_client("elasticsearch", timeout=_TIMEOUT) as c:
            r = await c.post(
                f"{_base()}/{index}/_search",
                auth=_auth(),
                json=body,
                headers={"Content-Type": "application/json"},
            )
            _raise_for(r)
            data = r.json()
        hits = (data.get("hits") or {}).get("hits") or []
        return {
            "total": ((data.get("hits") or {}).get("total") or {}).get("value")
            if isinstance((data.get("hits") or {}).get("total"), dict)
            else (data.get("hits") or {}).get("total"),
            "hits": [
                {
                    "_id": h.get("_id"),
                    "_index": h.get("_index"),
                    "_score": h.get("_score"),
                    "_source": h.get("_source"),
                }
                for h in hits
            ],
        }

    @mcp.tool
    async def list_indices() -> dict:
        """List Elasticsearch indices."""
        async with make_client("elasticsearch", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_base()}/_cat/indices", auth=_auth(), params={"format": "json"})
            _raise_for(r)
            data = r.json()
        rows = data if isinstance(data, list) else []
        return {
            "indices": [
                {
                    "index": i.get("index"),
                    "health": i.get("health"),
                    "status": i.get("status"),
                    "docs_count": i.get("docs.count"),
                }
                for i in rows
            ]
        }

    @mcp.tool
    async def get_index(
        index: Annotated[str, Field(min_length=1, description="index name")],
    ) -> dict:
        """Get metadata for a single Elasticsearch index."""
        async with make_client("elasticsearch", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_base()}/{index}", auth=_auth())
            _raise_for(r)
            data = r.json()
        info = data.get(index, {})
        return {
            "index": index,
            "aliases": list((info.get("aliases") or {}).keys()),
            "mappings_properties": list(
                (((info.get("mappings") or {}).get("properties")) or {}).keys()
            ),
            "settings_index": ((info.get("settings") or {}).get("index") or {}),
        }
