from __future__ import annotations

import os
from typing import Annotated, Any

import httpx
from fastmcp import FastMCP
from pydantic import Field

from mcp_common.errors import (
    AuthError,
    ConfigError,
    RateLimitError,
    UpstreamError,
    ValidationError,
)

_API_BASE = "https://api.search.brave.com/res/v1"
_MAX_COUNT = 20


def _api_key() -> str:
    key = os.environ.get("BRAVE_API_KEY", "").strip()
    if not key:
        raise ConfigError("BRAVE_API_KEY is not set")
    return key


def _headers() -> dict[str, str]:
    return {
        "X-Subscription-Token": _api_key(),
        "Accept": "application/json",
        "User-Agent": "fastmcp-platform/brave-search",
    }


def _clamp(n: int, lo: int = 1, hi: int = _MAX_COUNT) -> int:
    return max(lo, min(hi, n))


def _raise_for_status(response: httpx.Response) -> None:
    if response.status_code == 401:
        raise AuthError("Brave Search authentication failed")
    if response.status_code == 403:
        raise AuthError("Brave Search subscription forbidden or exceeded")
    if response.status_code == 429:
        raise RateLimitError("Brave Search rate limit exceeded")
    if response.status_code >= 500:
        raise UpstreamError(f"Brave Search upstream error: HTTP {response.status_code}")
    if response.status_code >= 400:
        raise UpstreamError(
            f"Brave Search HTTP {response.status_code}: {response.text[:200]}"
        )


async def _get(
    client: httpx.AsyncClient, path: str, params: dict[str, Any]
) -> dict[str, Any]:
    try:
        response = await client.get(f"{_API_BASE}{path}", params=params, headers=_headers())
    except httpx.RequestError as exc:
        raise UpstreamError(f"Brave Search request failed: {exc}") from exc
    _raise_for_status(response)
    return response.json()


def _web_result_slim(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": result.get("title"),
        "url": result.get("url"),
        "description": result.get("description"),
        "age": result.get("age"),
        "language": result.get("language"),
    }


def _news_result_slim(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": result.get("title"),
        "url": result.get("url"),
        "description": result.get("description"),
        "age": result.get("age"),
        "source": (result.get("meta_url") or {}).get("hostname"),
        "published": result.get("page_age"),
    }


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def web_search(
        query: Annotated[str, Field(description="Search query text")],
        count: Annotated[int, Field(description="Max results (1-20)")] = 10,
        country: Annotated[str, Field(description="Country code, e.g. US, GB")] = "US",
    ) -> dict:
        """Web search via Brave Search API."""
        if not query.strip():
            raise ValidationError("query must not be empty")
        params = {"q": query, "count": _clamp(count), "country": country}
        async with make_client("brave-search", timeout=30.0) as client:
            data = await _get(client, "/web/search", params)
        web = (data.get("web") or {}).get("results") or []
        results = [_web_result_slim(r) for r in web]
        return {"query": query, "results": results, "count": len(results)}

    @mcp.tool
    async def news_search(
        query: Annotated[str, Field(description="News query text")],
        count: Annotated[int, Field(description="Max results (1-20)")] = 10,
        country: Annotated[str, Field(description="Country code, e.g. US, GB")] = "US",
    ) -> dict:
        """News search via Brave Search API."""
        if not query.strip():
            raise ValidationError("query must not be empty")
        params = {"q": query, "count": _clamp(count), "country": country}
        async with make_client("brave-search", timeout=30.0) as client:
            data = await _get(client, "/news/search", params)
        news = data.get("results") or []
        results = [_news_result_slim(r) for r in news]
        return {"query": query, "results": results, "count": len(results)}
