from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from mcp_common.errors import (
    AuthError,
    ConfigError,
    NotFoundError,
    RateLimitError,
    UpstreamError,
)
from mcp_common.http import make_client
from pydantic import Field

_TIMEOUT = 30.0


def _base() -> str:
    v = os.environ.get("CONFLUENCE_URL")
    if not v:
        raise ConfigError("CONFLUENCE_URL is not set (e.g. https://your-domain.atlassian.net)")
    return v.rstrip("/") + "/wiki/rest/api"


def _auth() -> httpx.BasicAuth:
    u = os.environ.get("CONFLUENCE_USER")
    t = os.environ.get("CONFLUENCE_TOKEN")
    if not u or not t:
        raise ConfigError("CONFLUENCE_USER and CONFLUENCE_TOKEN must be set")
    return httpx.BasicAuth(u, t)


def _headers() -> dict[str, str]:
    return {"Accept": "application/json"}


def _raise_for(r: httpx.Response) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"confluence auth failed: HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("confluence resource not found")
    if r.status_code == 429:
        raise RateLimitError("confluence rate limited")
    if r.status_code >= 400:
        raise UpstreamError(f"confluence HTTP {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_spaces(
        limit: Annotated[int, Field(ge=1, le=250)] = 25,
    ) -> dict:
        """List Confluence spaces visible to the caller."""
        async with make_client("confluence", timeout=_TIMEOUT) as c:
            r = await c.get(
                f"{_base()}/space", auth=_auth(), headers=_headers(), params={"limit": limit}
            )
            _raise_for(r)
            data = r.json()
        return {
            "spaces": [
                {"key": s["key"], "name": s["name"], "type": s.get("type")}
                for s in data.get("results", [])
            ]
        }

    @mcp.tool
    async def search_content(
        cql: Annotated[
            str,
            Field(min_length=1, description="Confluence CQL, e.g. 'type = page AND space = DOCS'"),
        ],
        limit: Annotated[int, Field(ge=1, le=100)] = 25,
    ) -> dict:
        """Search Confluence content with CQL."""
        async with make_client("confluence", timeout=_TIMEOUT) as c:
            r = await c.get(
                f"{_base()}/content/search",
                auth=_auth(),
                headers=_headers(),
                params={"cql": cql, "limit": limit},
            )
            _raise_for(r)
            data = r.json()
        return {
            "results": [
                {
                    "id": c["id"],
                    "type": c.get("type"),
                    "title": c.get("title"),
                    "space": (c.get("space") or {}).get("key"),
                    "web_url": ((c.get("_links") or {}).get("webui")),
                }
                for c in data.get("results", [])
            ]
        }

    @mcp.tool
    async def get_page(
        page_id: Annotated[str, Field(min_length=1, description="Confluence page id")],
    ) -> dict:
        """Get a single Confluence page (title + storage-format body)."""
        async with make_client("confluence", timeout=_TIMEOUT) as c:
            r = await c.get(
                f"{_base()}/content/{page_id}",
                auth=_auth(),
                headers=_headers(),
                params={"expand": "body.storage,version,space"},
            )
            _raise_for(r)
            p = r.json()
        body = ((p.get("body") or {}).get("storage") or {}).get("value") or ""
        return {
            "id": p.get("id"),
            "title": p.get("title"),
            "type": p.get("type"),
            "space": (p.get("space") or {}).get("key"),
            "version": (p.get("version") or {}).get("number"),
            "body_length": len(body),
            "body_preview": body[:400],
        }
