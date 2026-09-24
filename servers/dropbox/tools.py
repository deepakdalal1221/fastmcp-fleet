from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import AuthError, ConfigError, NotFoundError, UpstreamError
from mcp_common.http import is_offline, make_client
from pydantic import Field

_BASE = "https://api.dropboxapi.com/2"
_CONTENT = "https://content.dropboxapi.com/2"
_TIMEOUT = 30.0


def _token():
    v = os.environ.get("DROPBOX_TOKEN")
    if not v:
        raise ConfigError("DROPBOX_TOKEN is not set")
    return v


def _headers():
    return {"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"}


def _raise_for(r):
    if r.status_code in (401, 403):
        raise AuthError(f"dropbox HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("dropbox not found")
    if r.status_code >= 400:
        raise UpstreamError(f"dropbox HTTP {r.status_code}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_files(
        path: Annotated[str, Field(description="Dropbox path; use '' for root")] = "",
    ) -> dict:
        """List files/folders in a Dropbox path."""
        async with make_client("dropbox", timeout=_TIMEOUT) as c:
            r = await c.post(f"{_BASE}/files/list_folder", headers=_headers(), json={"path": path})
            _raise_for(r)
        d = r.json()
        return {
            "entries": [
                {
                    "name": e.get("name"),
                    "path": e.get("path_display"),
                    "tag": e.get(".tag"),
                    "size": e.get("size"),
                }
                for e in d.get("entries", [])
            ]
        }

    @mcp.tool
    async def download(path: Annotated[str, Field(min_length=1)]) -> dict:
        """Download a Dropbox file (returns content preview + metadata)."""
        headers = {
            "Authorization": f"Bearer {_token()}",
            "Dropbox-API-Arg": '{"path": "' + path + '"}',
        }
        async with make_client("dropbox", timeout=_TIMEOUT) as c:
            r = await c.post(f"{_CONTENT}/files/download", headers=headers)
            _raise_for(r)
        return {
            "path": path,
            "size": len(r.content),
            "content_preview": r.text[:400] if isinstance(r.text, str) else "",
        }

    @mcp.tool
    async def upload(
        path: Annotated[str, Field(min_length=1)],
        content: Annotated[str, Field(description="UTF-8 text content")],
    ) -> dict:
        """Upload text content to Dropbox."""
        headers = {
            "Authorization": f"Bearer {_token()}",
            "Dropbox-API-Arg": '{"path": "' + path + '", "mode": "overwrite"}',
            "Content-Type": "application/octet-stream",
        }
        async with make_client("dropbox", timeout=_TIMEOUT) as c:
            r = await c.post(
                f"{_CONTENT}/files/upload", headers=headers, content=content.encode("utf-8")
            )
            _raise_for(r)
        return r.json()
