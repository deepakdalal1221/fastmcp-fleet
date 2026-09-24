from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import UpstreamError
from mcp_common.http import is_offline, make_client
from pydantic import Field

_BASE = "https://api.duckduckgo.com/"
_TIMEOUT = 30.0


def _raise_for(r) -> None:
    if r.status_code >= 400:
        raise UpstreamError(f"duckduckgo HTTP {r.status_code}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def search(
        query: Annotated[str, Field(min_length=1, max_length=200)],
        limit: Annotated[int, Field(ge=1, le=50)] = 10,
    ) -> dict:
        """DuckDuckGo instant-answer search. Offline: reads local_store."""
        if is_offline():
            hits = [
                r
                for r in local_store.list_all("duckduckgo", "web")
                if query.lower() in r.get("title", "").lower()
                or query.lower() in r.get("snippet", "").lower()
            ]
            return {"query": query, "results": hits[:limit], "count": len(hits)}
        async with make_client("duckduckgo", timeout=_TIMEOUT) as c:
            r = await c.get(_BASE, params={"q": query, "format": "json", "no_html": "1"})
            _raise_for(r)
        return r.json()
