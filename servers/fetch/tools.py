from __future__ import annotations

import re
from typing import Annotated

import httpx
from fastmcp import FastMCP
from mcp_common.errors import UpstreamError, ValidationError
from pydantic import Field

_MAX_BYTES = 100_000
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _validate_url(url: str) -> None:
    if not url.startswith(("http://", "https://")):
        raise ValidationError("url must start with http:// or https://")


async def _get(url: str, timeout: float) -> httpx.Response:
    async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
        try:
            r = await client.get(url)
        except httpx.RequestError as exc:
            raise UpstreamError(f"request failed: {type(exc).__name__}: {exc}") from exc
    if r.status_code >= 500:
        raise UpstreamError(f"upstream {r.status_code}: {url}")
    return r


def _truncate(text: str, limit: int = _MAX_BYTES) -> tuple[str, bool]:
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= limit:
        return text, False
    return encoded[:limit].decode("utf-8", errors="replace"), True


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def fetch(
        url: Annotated[str, Field(description="Absolute HTTP(S) URL to fetch")],
        timeout: Annotated[
            float, Field(ge=0.1, le=120.0, description="Request timeout in seconds")
        ] = 30.0,
    ) -> dict:
        """Fetch a URL and return the response body as text with status and content-type."""
        _validate_url(url)
        r = await _get(url, timeout)
        text, truncated = _truncate(r.text)
        return {
            "status": r.status_code,
            "content_type": r.headers.get("content-type", ""),
            "url": str(r.url),
            "text": text,
            "truncated": truncated,
        }

    @mcp.tool
    async def fetch_markdown(
        url: Annotated[
            str, Field(description="Absolute HTTP(S) URL to fetch and convert to plain text")
        ],
        timeout: Annotated[
            float, Field(ge=0.1, le=120.0, description="Request timeout in seconds")
        ] = 30.0,
    ) -> dict:
        """Fetch a URL and return its HTML stripped to plain text."""
        _validate_url(url)
        r = await _get(url, timeout)
        stripped = _TAG_RE.sub(" ", r.text)
        cleaned = _WS_RE.sub(" ", stripped).strip()
        text, truncated = _truncate(cleaned)
        return {
            "status": r.status_code,
            "url": str(r.url),
            "text": text,
            "truncated": truncated,
        }
