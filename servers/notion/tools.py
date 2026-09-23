from __future__ import annotations

import os
from typing import Annotated, Any

import httpx
from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import (
    AuthError,
    ConfigError,
    NotFoundError,
    RateLimitError,
    UpstreamError,
    ValidationError,
)
from mcp_common.http import is_offline, make_client
from pydantic import Field

_API_BASE = "https://api.notion.com/v1"
_NOTION_VERSION = "2022-06-28"
_MAX_PAGE_SIZE = 100


def _token() -> str:
    token = os.environ.get("NOTION_TOKEN", "").strip()
    if not token:
        raise ConfigError("NOTION_TOKEN is not set")
    return token


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_token()}",
        "Notion-Version": _NOTION_VERSION,
        "Content-Type": "application/json",
        "User-Agent": "fastmcp-platform/notion",
    }


def _clamp(n: int, lo: int = 1, hi: int = _MAX_PAGE_SIZE) -> int:
    return max(lo, min(hi, n))


def _raise_for_status(response: httpx.Response) -> None:
    if response.status_code == 401:
        raise AuthError("Notion authentication failed")
    if response.status_code == 403:
        raise AuthError("Notion permission denied")
    if response.status_code == 404:
        raise NotFoundError("Notion resource not found")
    if response.status_code == 429:
        raise RateLimitError("Notion rate limit exceeded")
    if response.status_code >= 500:
        raise UpstreamError(f"Notion upstream error: HTTP {response.status_code}")
    if response.status_code >= 400:
        raise UpstreamError(f"Notion HTTP {response.status_code}: {response.text[:200]}")


async def _request(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        response = await client.request(method, f"{_API_BASE}{path}", json=body, headers=_headers())
    except httpx.RequestError as exc:
        raise UpstreamError(f"Notion request failed: {exc}") from exc
    _raise_for_status(response)
    return response.json() if response.content else {}


def _title_text(properties: dict[str, Any]) -> str | None:
    for prop in properties.values():
        if prop.get("type") == "title":
            parts = prop.get("title") or []
            if parts:
                return "".join(p.get("plain_text", "") for p in parts)
    return None


def _result_slim(item: dict[str, Any]) -> dict[str, Any]:
    obj = item.get("object")
    props = item.get("properties") or {}
    slim: dict[str, Any] = {
        "id": item.get("id"),
        "object": obj,
        "url": item.get("url"),
        "created_time": item.get("created_time"),
        "last_edited_time": item.get("last_edited_time"),
        "archived": item.get("archived"),
    }
    if obj == "database":
        title_parts = item.get("title") or []
        slim["title"] = "".join(p.get("plain_text", "") for p in title_parts)
    else:
        slim["title"] = _title_text(props)
    return slim


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def search(
        query: Annotated[str, Field(description="text query; empty returns recent pages")] = "",
        parent_id: Annotated[str | None, Field(description="offline: filter by parent id")] = None,
        limit: Annotated[int, Field(ge=1, le=100)] = 20,
    ) -> dict:
        """Search Notion. Offline mode returns locally-created pages, optionally filtered by parent."""
        if is_offline():
            if parent_id:
                stored = await local_store.list_all("notion", f"pages:{parent_id}")
                pages = [row["value"] for row in stored]
            else:
                pages = []
            if query:
                q = query.lower()
                pages = [p for p in pages if q in (p.get("title", "") or "").lower()]
            pages = pages[:limit]
            return {
                "results": [
                    {"id": p["id"], "title": p.get("title"), "url": p.get("url")} for p in pages
                ]
            }
        payload = {"query": query, "page_size": limit}
        async with make_client("notion", timeout=_TIMEOUT) as c:
            r = await c.post(f"{_BASE}/search", headers=_headers(), json=payload)
            _raise_for(r)
            data = r.json()
        results = []
        for p in data.get("results", []):
            title = ""
            props = p.get("properties") or {}
            title_prop = props.get("title") or props.get("Name")
            if title_prop and title_prop.get("title"):
                title = "".join(t.get("plain_text", "") for t in title_prop["title"])
            results.append({"id": p.get("id"), "title": title, "url": p.get("url")})
        return {"results": results}

    @mcp.tool
    async def get_page(
        page_id: Annotated[str, Field(description="Notion page ID (with or without dashes)")],
    ) -> dict:
        """Retrieve a Notion page by ID."""
        if not page_id.strip():
            raise ValidationError("page_id must not be empty")
        async with make_client("notion", timeout=30.0) as client:
            data = await _request(client, "GET", f"/pages/{page_id}")
        return _result_slim(data)

    @mcp.tool
    async def create_page(
        parent_id: Annotated[str, Field(min_length=1, description="parent page id or database id")],
        title: Annotated[str, Field(min_length=1, description="page title")],
        parent_type: Annotated[str, Field(description="page_id | database_id")] = "page_id",
    ) -> dict:
        """Create a Notion page. Offline mode persists to local state for search."""
        if is_offline():
            col = f"pages:{parent_id}"
            n = local_store.next_id("notion", col)
            pid = f"offline-page-{n:04d}"
            page = {
                "id": pid,
                "object": "page",
                "parent": {parent_type: parent_id},
                "properties": {"title": [{"plain_text": title}]},
                "title": title,
                "url": f"https://www.notion.so/offline/{pid}",
            }
            await local_store.put("notion", col, pid, page)
            return {"id": pid, "title": title, "url": page["url"]}
        payload = {
            "parent": {parent_type: parent_id},
            "properties": {"title": {"title": [{"text": {"content": title}}]}},
        }
        async with make_client("notion", timeout=_TIMEOUT) as c:
            r = await c.post(f"{_BASE}/pages", headers=_headers(), json=payload)
            _raise_for(r)
            p = r.json()
        return {"id": p.get("id"), "title": title, "url": p.get("url")}

    @mcp.tool
    async def query_database(
        database_id: Annotated[str, Field(description="Notion database ID")],
        page_size: Annotated[int, Field(description="Max rows (1-100)")] = 25,
    ) -> dict:
        """Query rows from a Notion database."""
        if not database_id.strip():
            raise ValidationError("database_id must not be empty")
        body = {"page_size": _clamp(page_size)}
        async with make_client("notion", timeout=30.0) as client:
            data = await _request(client, "POST", f"/databases/{database_id}/query", body=body)
        results = [_result_slim(r) for r in (data.get("results") or [])]
        return {
            "database_id": database_id,
            "results": results,
            "count": len(results),
            "has_more": bool(data.get("has_more")),
            "next_cursor": data.get("next_cursor"),
        }
