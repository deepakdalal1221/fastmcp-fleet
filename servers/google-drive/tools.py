from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import AuthError, ConfigError, NotFoundError, RateLimitError, UpstreamError
from mcp_common.http import is_offline, make_client
from pydantic import Field

_BASE = "https://www.googleapis.com/drive/v3"
_TIMEOUT = 30.0


def _token() -> str:
    v = os.environ.get("GDRIVE_TOKEN")
    if not v:
        raise ConfigError("GDRIVE_TOKEN is not set")
    return v


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_token()}", "Accept": "application/json"}


def _raise_for(r: httpx.Response) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"google-drive auth failed: HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("google-drive resource not found")
    if r.status_code == 429:
        raise RateLimitError("google-drive rate limited")
    if r.status_code >= 400:
        raise UpstreamError(f"google-drive HTTP {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_files(page_size: Annotated[int, Field(ge=1, le=100)] = 20) -> dict:
        """List Google Drive files accessible to the token."""
        async with make_client("google-drive", timeout=_TIMEOUT) as c:
            r = await c.get(
                f"{_BASE}/files",
                headers=_headers(),
                params={
                    "pageSize": page_size,
                    "fields": "files(id,name,mimeType,size,modifiedTime)",
                },
            )
            _raise_for(r)
            data = r.json()
        return {"files": data.get("files", [])}

    @mcp.tool
    async def get_file(file_id: Annotated[str, Field(min_length=1)]) -> dict:
        """Get Google Drive file metadata by id."""
        async with make_client("google-drive", timeout=_TIMEOUT) as c:
            r = await c.get(
                f"{_BASE}/files/{file_id}",
                headers=_headers(),
                params={"fields": "id,name,mimeType,size,modifiedTime,webViewLink"},
            )
            _raise_for(r)
        return r.json()

    @mcp.tool
    async def search_files(
        query: Annotated[
            str, Field(min_length=1, description="Drive query: e.g. \"name contains 'report'\"")
        ],
        page_size: Annotated[int, Field(ge=1, le=100)] = 20,
    ) -> dict:
        """Search Google Drive files by query."""
        async with make_client("google-drive", timeout=_TIMEOUT) as c:
            r = await c.get(
                f"{_BASE}/files",
                headers=_headers(),
                params={"q": query, "pageSize": page_size, "fields": "files(id,name,mimeType)"},
            )
            _raise_for(r)
            data = r.json()
        return {"files": data.get("files", [])}
