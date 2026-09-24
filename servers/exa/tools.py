from __future__ import annotations

import os
from typing import Annotated

from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import AuthError, ConfigError, UpstreamError
from mcp_common.http import is_offline, make_client
from pydantic import Field

_BASE = "https://api.exa.ai"
_TIMEOUT = 30.0


def _key() -> str:
    v = os.environ.get("EXA_API_KEY")
    if not v:
        raise ConfigError("EXA_API_KEY is not set")
    return v


def _headers() -> dict[str, str]:
    return {"x-api-key": _key(), "Content-Type": "application/json"}


def _raise_for(r) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"exa HTTP {r.status_code}")
    if r.status_code >= 400:
        raise UpstreamError(f"exa HTTP {r.status_code}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def search(
        query: Annotated[str, Field(min_length=1, max_length=200)],
        limit: Annotated[int, Field(ge=1, le=50)] = 10,
    ) -> dict:
        """Semantic web search. Offline: reads local_store."""
        if is_offline():
            hits = [
                r
                for r in local_store.list_all("exa", "web")
                if query.lower() in r.get("title", "").lower()
            ]
            return {"query": query, "results": hits[:limit], "count": len(hits)}
        async with make_client("exa", timeout=_TIMEOUT) as c:
            r = await c.post(
                f"{_BASE}/search",
                headers=_headers(),
                json={"query": query, "numResults": limit},
            )
            _raise_for(r)
        return r.json()

    @mcp.tool
    async def find_similar(
        url: Annotated[str, Field(min_length=1, max_length=2000)],
        limit: Annotated[int, Field(ge=1, le=50)] = 10,
    ) -> dict:
        """Find pages similar to a URL. Offline: reads local_store."""
        if is_offline():
            hits = local_store.list_all("exa", f"similar:{url}")
            return {"url": url, "results": hits[:limit], "count": len(hits)}
        async with make_client("exa", timeout=_TIMEOUT) as c:
            r = await c.post(
                f"{_BASE}/findSimilar",
                headers=_headers(),
                json={"url": url, "numResults": limit},
            )
            _raise_for(r)
        return r.json()

    @mcp.tool
    async def contents(
        ids: Annotated[list[str], Field(min_length=1, max_length=50)],
    ) -> dict:
        """Fetch page contents by document ids. Offline: reads local_store."""
        if is_offline():
            out = []
            for i in ids:
                rec = local_store.get("exa", "contents", i)
                if rec:
                    out.append(rec)
            return {"contents": out, "count": len(out)}
        async with make_client("exa", timeout=_TIMEOUT) as c:
            r = await c.post(f"{_BASE}/contents", headers=_headers(), json={"ids": ids})
            _raise_for(r)
        return r.json()
