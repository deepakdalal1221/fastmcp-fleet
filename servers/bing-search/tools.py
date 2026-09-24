from __future__ import annotations

import os
from typing import Annotated

from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import AuthError, ConfigError, UpstreamError
from mcp_common.http import is_offline, make_client
from pydantic import Field

_BASE = "https://api.bing.microsoft.com/v7.0"
_TIMEOUT = 30.0


def _key() -> str:
    v = os.environ.get("BING_API_KEY")
    if not v:
        raise ConfigError("BING_API_KEY is not set")
    return v


def _headers() -> dict[str, str]:
    return {"Ocp-Apim-Subscription-Key": _key()}


def _raise_for(r) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"bing HTTP {r.status_code}")
    if r.status_code >= 400:
        raise UpstreamError(f"bing HTTP {r.status_code}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def web_search(
        query: Annotated[str, Field(min_length=1, max_length=200)],
        limit: Annotated[int, Field(ge=1, le=50)] = 10,
    ) -> dict:
        """Bing web search. Offline: reads local_store."""
        if is_offline():
            hits = [
                r
                for r in local_store.list_all("bing-search", "web")
                if query.lower() in r.get("title", "").lower()
                or query.lower() in r.get("snippet", "").lower()
            ]
            return {"query": query, "results": hits[:limit], "count": len(hits)}
        async with make_client("bing-search", timeout=_TIMEOUT) as c:
            r = await c.get(
                f"{_BASE}/search",
                headers=_headers(),
                params={"q": query, "count": limit},
            )
            _raise_for(r)
        return r.json()

    @mcp.tool
    async def news_search(
        query: Annotated[str, Field(min_length=1, max_length=200)],
        limit: Annotated[int, Field(ge=1, le=50)] = 10,
    ) -> dict:
        """Bing news search. Offline: reads local_store."""
        if is_offline():
            hits = [
                r
                for r in local_store.list_all("bing-search", "news")
                if query.lower() in r.get("title", "").lower()
            ]
            return {"query": query, "results": hits[:limit], "count": len(hits)}
        async with make_client("bing-search", timeout=_TIMEOUT) as c:
            r = await c.get(
                f"{_BASE}/news/search",
                headers=_headers(),
                params={"q": query, "count": limit},
            )
            _raise_for(r)
        return r.json()
