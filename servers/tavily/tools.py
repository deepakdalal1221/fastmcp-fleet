from __future__ import annotations

import os
from typing import Annotated, Any

import httpx
from fastmcp import FastMCP
from mcp_common.errors import (
    AuthError,
    ConfigError,
    RateLimitError,
    UpstreamError,
    ValidationError,
)
from mcp_common.http import make_client
from pydantic import Field

_API_BASE = "https://api.tavily.com"
_MAX_RESULTS = 20
_MAX_URLS = 20


def _api_key() -> str:
    key = os.environ.get("TAVILY_API_KEY", "").strip()
    if not key:
        raise ConfigError("TAVILY_API_KEY is not set")
    return key


def _headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "User-Agent": "fastmcp-platform/tavily",
    }


def _clamp(n: int, lo: int = 1, hi: int = _MAX_RESULTS) -> int:
    return max(lo, min(hi, n))


def _raise_for_status(response: httpx.Response) -> None:
    if response.status_code == 401:
        raise AuthError("Tavily authentication failed")
    if response.status_code == 403:
        raise AuthError("Tavily quota exceeded or forbidden")
    if response.status_code == 429:
        raise RateLimitError("Tavily rate limit exceeded")
    if response.status_code >= 500:
        raise UpstreamError(f"Tavily upstream error: HTTP {response.status_code}")
    if response.status_code >= 400:
        raise UpstreamError(f"Tavily HTTP {response.status_code}: {response.text[:200]}")


async def _post(client: httpx.AsyncClient, path: str, body: dict[str, Any]) -> dict[str, Any]:
    body_with_key = {"api_key": _api_key(), **body}
    try:
        response = await client.post(f"{_API_BASE}{path}", json=body_with_key, headers=_headers())
    except httpx.RequestError as exc:
        raise UpstreamError(f"Tavily request failed: {exc}") from exc
    _raise_for_status(response)
    return response.json()


def _search_result_slim(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": result.get("title"),
        "url": result.get("url"),
        "content": result.get("content"),
        "score": result.get("score"),
        "published_date": result.get("published_date"),
    }


def _extract_result_slim(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "url": result.get("url"),
        "raw_content": result.get("raw_content"),
        "content_length": len(result.get("raw_content") or ""),
    }


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def search(
        query: Annotated[str, Field(description="Search query text")],
        max_results: Annotated[int, Field(description="Max results (1-20)")] = 10,
        search_depth: Annotated[
            str, Field(description="'basic' (faster) or 'advanced' (deeper)")
        ] = "basic",
        include_answer: Annotated[
            bool, Field(description="Include LLM-generated answer summary")
        ] = False,
    ) -> dict:
        """Web search via Tavily AI-optimized search API."""
        if not query.strip():
            raise ValidationError("query must not be empty")
        if search_depth not in {"basic", "advanced"}:
            raise ValidationError("search_depth must be 'basic' or 'advanced'")
        body: dict[str, Any] = {
            "query": query,
            "max_results": _clamp(max_results),
            "search_depth": search_depth,
            "include_answer": include_answer,
        }
        async with make_client("tavily", timeout=60.0) as client:
            data = await _post(client, "/search", body)
        results = [_search_result_slim(r) for r in (data.get("results") or [])]
        return {
            "query": query,
            "answer": data.get("answer"),
            "results": results,
            "count": len(results),
        }

    @mcp.tool
    async def extract(
        urls: Annotated[list[str], Field(description="URLs to fetch and clean (1-20)")],
    ) -> dict:
        """Extract cleaned content from URLs via Tavily."""
        if not urls:
            raise ValidationError("urls must not be empty")
        if len(urls) > _MAX_URLS:
            raise ValidationError(f"urls length exceeds {_MAX_URLS}")
        for u in urls:
            if not u.startswith(("http://", "https://")):
                raise ValidationError(f"invalid URL: {u}")
        body = {"urls": urls}
        async with make_client("tavily", timeout=60.0) as client:
            data = await _post(client, "/extract", body)
        results = [_extract_result_slim(r) for r in (data.get("results") or [])]
        failed = data.get("failed_results") or []
        return {
            "results": results,
            "count": len(results),
            "failed": failed,
            "failed_count": len(failed),
        }
