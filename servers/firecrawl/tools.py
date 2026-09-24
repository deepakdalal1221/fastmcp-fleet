from __future__ import annotations

import os
from typing import Annotated

from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import AuthError, ConfigError, UpstreamError
from mcp_common.http import is_offline, make_client
from pydantic import Field

_BASE = "https://api.firecrawl.dev/v1"
_TIMEOUT = 60.0


def _token() -> str:
    v = os.environ.get("FIRECRAWL_TOKEN")
    if not v:
        raise ConfigError("FIRECRAWL_TOKEN is not set")
    return v


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"}


def _raise_for(r) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"firecrawl HTTP {r.status_code}")
    if r.status_code >= 400:
        raise UpstreamError(f"firecrawl HTTP {r.status_code}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def scrape(
        url: Annotated[str, Field(min_length=1, max_length=2000)],
    ) -> dict:
        """Scrape a single URL. Offline: reads local_store."""
        if is_offline():
            rec = local_store.get("firecrawl", "scrapes", url)
            if rec:
                return rec
            return {"url": url, "markdown": "", "note": "no offline snapshot cached"}
        async with make_client("firecrawl", timeout=_TIMEOUT) as c:
            r = await c.post(f"{_BASE}/scrape", headers=_headers(), json={"url": url})
            _raise_for(r)
        return r.json()

    @mcp.tool
    async def crawl(
        url: Annotated[str, Field(min_length=1, max_length=2000)],
        limit: Annotated[int, Field(ge=1, le=100)] = 10,
    ) -> dict:
        """Start a crawl job. Offline: returns cached snapshot list."""
        if is_offline():
            snaps = local_store.list_all("firecrawl", f"crawl:{url}")
            return {"url": url, "pages": snaps[:limit], "count": len(snaps)}
        async with make_client("firecrawl", timeout=_TIMEOUT) as c:
            r = await c.post(
                f"{_BASE}/crawl", headers=_headers(), json={"url": url, "limit": limit}
            )
            _raise_for(r)
        return r.json()

    @mcp.tool
    async def map(
        url: Annotated[str, Field(min_length=1, max_length=2000)],
    ) -> dict:
        """Map a website's URLs. Offline: reads local_store."""
        if is_offline():
            urls = local_store.list_all("firecrawl", f"map:{url}")
            return {"url": url, "links": [u.get("link") for u in urls], "count": len(urls)}
        async with make_client("firecrawl", timeout=_TIMEOUT) as c:
            r = await c.post(f"{_BASE}/map", headers=_headers(), json={"url": url})
            _raise_for(r)
        return r.json()
