from __future__ import annotations

import os
from typing import Annotated, Any

import httpx
from fastmcp import FastMCP
from mcp_common.errors import (
    AuthError,
    ConfigError,
    NotFoundError,
    RateLimitError,
    UpstreamError,
    ValidationError,
)
from mcp_common.http import make_client
from pydantic import Field

_TIMEOUT = 30.0
_MAX_LIMIT = 100


def _token() -> str:
    token = os.environ.get("SENTRY_TOKEN", "").strip()
    if not token:
        raise ConfigError("SENTRY_TOKEN is not set")
    return token


def _base_url() -> str:
    base = os.environ.get("SENTRY_BASE_URL", "https://sentry.io").strip().rstrip("/")
    if not base.startswith(("http://", "https://")):
        raise ConfigError("SENTRY_BASE_URL must start with http:// or https://")
    return f"{base}/api/0"


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_token()}",
        "Accept": "application/json",
        "User-Agent": "mcp-sentry/0.1.0",
    }


def _raise_for_status(response: httpx.Response) -> None:
    status = response.status_code
    if status < 400:
        return
    body = response.text[:500]
    if status == 401:
        raise AuthError(f"Sentry auth failed: {body}")
    if status == 403:
        raise AuthError(f"Sentry forbidden: {body}")
    if status == 404:
        raise NotFoundError(f"Sentry resource not found: {body}")
    if status == 429:
        raise RateLimitError(f"Sentry rate limited: {body}")
    if status >= 500:
        raise UpstreamError(f"Sentry upstream {status}: {body}")
    raise UpstreamError(f"Sentry {status}: {body}")


def _clamp(n: int, lo: int, hi: int) -> int:
    if n < lo:
        return lo
    if n > hi:
        return hi
    return n


async def _get(client: httpx.AsyncClient, path: str, params: dict[str, Any] | None = None) -> Any:
    try:
        response = await client.get(f"{_base_url()}{path}", headers=_headers(), params=params)
    except httpx.RequestError as exc:
        raise UpstreamError(f"Sentry request failed: {exc}") from exc
    _raise_for_status(response)
    return response.json()


def _issue_slim(issue: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": issue.get("id"),
        "short_id": issue.get("shortId"),
        "title": issue.get("title"),
        "culprit": issue.get("culprit"),
        "level": issue.get("level"),
        "status": issue.get("status"),
        "count": issue.get("count"),
        "user_count": issue.get("userCount"),
        "first_seen": issue.get("firstSeen"),
        "last_seen": issue.get("lastSeen"),
        "permalink": issue.get("permalink"),
    }


def _event_slim(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": event.get("id") or event.get("eventID"),
        "event_id": event.get("eventID"),
        "message": event.get("message"),
        "platform": event.get("platform"),
        "date_created": event.get("dateCreated"),
        "user": event.get("user"),
        "tags": event.get("tags"),
    }


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_issues(
        organization_slug: Annotated[str, Field(description="Sentry organization slug.")],
        project_slug: Annotated[str, Field(description="Sentry project slug.")],
        query: Annotated[str, Field(description="Optional Sentry search query.")] = "is:unresolved",
        limit: Annotated[int, Field(description="Max issues to return (1-100).")] = 25,
    ) -> dict[str, Any]:
        """List Sentry issues for a project."""
        if not organization_slug.strip() or not project_slug.strip():
            raise ValidationError("organization_slug and project_slug are required")
        params = {"query": query, "limit": _clamp(limit, 1, _MAX_LIMIT)}
        async with make_client("sentry", timeout=_TIMEOUT) as client:
            data = await _get(
                client,
                f"/projects/{organization_slug}/{project_slug}/issues/",
                params=params,
            )
        return {
            "organization_slug": organization_slug,
            "project_slug": project_slug,
            "issues": [_issue_slim(i) for i in data],
            "count": len(data),
        }

    @mcp.tool
    async def get_issue(
        issue_id: Annotated[str, Field(description="Sentry issue numeric id or short id.")],
    ) -> dict[str, Any]:
        """Fetch a single Sentry issue by id."""
        if not issue_id.strip():
            raise ValidationError("issue_id must not be empty")
        async with make_client("sentry", timeout=_TIMEOUT) as client:
            data = await _get(client, f"/issues/{issue_id}/")
        return _issue_slim(data)

    @mcp.tool
    async def list_events(
        issue_id: Annotated[str, Field(description="Sentry issue id.")],
        limit: Annotated[int, Field(description="Max events to return (1-100).")] = 25,
    ) -> dict[str, Any]:
        """List events for a Sentry issue."""
        if not issue_id.strip():
            raise ValidationError("issue_id must not be empty")
        params = {"limit": _clamp(limit, 1, _MAX_LIMIT)}
        async with make_client("sentry", timeout=_TIMEOUT) as client:
            data = await _get(client, f"/issues/{issue_id}/events/", params=params)
        return {
            "issue_id": issue_id,
            "events": [_event_slim(e) for e in data],
            "count": len(data),
        }
