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
    v = os.environ.get("WP_URL")
    if not v:
        raise ConfigError("WP_URL is not set (e.g. https://your-site.com)")
    return v.rstrip("/") + "/wp-json/wp/v2"


def _auth() -> httpx.BasicAuth:
    u = os.environ.get("WP_USER")
    p = os.environ.get("WP_PASSWORD")
    if not u or not p:
        raise ConfigError("WP_USER and WP_PASSWORD must be set")
    return httpx.BasicAuth(u, p)


def _raise_for(r: httpx.Response) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"wordpress auth failed: HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("wordpress resource not found")
    if r.status_code >= 400:
        raise UpstreamError(f"wordpress HTTP {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_posts(per_page: Annotated[int, Field(ge=1, le=100)] = 20) -> dict:
        """List WordPress posts."""
        async with make_client("wordpress", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_base()}/posts", auth=_auth(), params={"per_page": per_page})
            _raise_for(r)
            data = r.json()
        return {
            "posts": [
                {
                    "id": p["id"],
                    "title": (p.get("title") or {}).get("rendered"),
                    "status": p.get("status"),
                    "link": p.get("link"),
                }
                for p in data
            ]
        }

    @mcp.tool
    async def create_post(
        title: Annotated[str, Field(min_length=1)],
        content: Annotated[str, Field(min_length=1)],
        status: Annotated[str, Field(description="publish|draft|private")] = "draft",
    ) -> dict:
        """Create a WordPress post."""
        async with make_client("wordpress", timeout=_TIMEOUT) as c:
            r = await c.post(
                f"{_base()}/posts",
                auth=_auth(),
                json={"title": title, "content": content, "status": status},
            )
            _raise_for(r)
            p = r.json()
        return {
            "id": p["id"],
            "title": (p.get("title") or {}).get("rendered"),
            "status": p.get("status"),
            "link": p.get("link"),
        }

    @mcp.tool
    async def list_pages(per_page: Annotated[int, Field(ge=1, le=100)] = 20) -> dict:
        """List WordPress pages."""
        async with make_client("wordpress", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_base()}/pages", auth=_auth(), params={"per_page": per_page})
            _raise_for(r)
            data = r.json()
        return {
            "pages": [
                {
                    "id": p["id"],
                    "title": (p.get("title") or {}).get("rendered"),
                    "status": p.get("status"),
                    "link": p.get("link"),
                }
                for p in data
            ]
        }
