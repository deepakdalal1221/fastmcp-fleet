from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from pydantic import Field

from mcp_common.errors import AuthError, ConfigError, NotFoundError, RateLimitError, UpstreamError

_TIMEOUT = 30.0


def _host() -> str:
    v = os.environ.get("OP_CONNECT_HOST")
    if not v:
        raise ConfigError("OP_CONNECT_HOST is not set")
    return v.rstrip("/")


def _token() -> str:
    v = os.environ.get("OP_CONNECT_TOKEN")
    if not v:
        raise ConfigError("OP_CONNECT_TOKEN is not set")
    return v


def _base() -> str:
    return f"{_host()}/v1"


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_token()}"}


def _raise_for(r: httpx.Response) -> None:
    if r.status_code < 400:
        return
    if r.status_code in (401, 403):
        raise AuthError(f"1password auth failed: {r.text[:200]}")
    if r.status_code == 404:
        raise NotFoundError(f"1password not found: {r.text[:200]}")
    if r.status_code == 429:
        raise RateLimitError(f"1password rate-limited: {r.text[:200]}")
    raise UpstreamError(f"1password {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_vaults() -> dict:
        """List 1Password vaults accessible via the Connect Server."""
        async with make_client("1password", timeout=_TIMEOUT) as client:
            r = await client.get(f"{_base()}/vaults", headers=_headers())
        _raise_for(r)
        return {
            "vaults": [
                {"id": v.get("id"), "name": v.get("name"), "description": v.get("description")}
                for v in r.json()
            ]
        }

    @mcp.tool
    async def list_items(
        vault_id: Annotated[str, Field(description="1Password vault id")],
    ) -> dict:
        """List items in a 1Password vault (titles + metadata only)."""
        async with make_client("1password", timeout=_TIMEOUT) as client:
            r = await client.get(f"{_base()}/vaults/{vault_id}/items", headers=_headers())
        _raise_for(r)
        return {
            "items": [
                {"id": i.get("id"), "title": i.get("title"), "category": i.get("category"), "updatedAt": i.get("updatedAt")}
                for i in r.json()
            ]
        }

    @mcp.tool
    async def get_item(
        vault_id: Annotated[str, Field(description="1Password vault id")],
        item_id: Annotated[str, Field(description="1Password item id")],
    ) -> dict:
        """Get a 1Password item's fields (CONCEALED values are redacted)."""
        async with make_client("1password", timeout=_TIMEOUT) as client:
            r = await client.get(f"{_base()}/vaults/{vault_id}/items/{item_id}", headers=_headers())
        _raise_for(r)
        it = r.json()
        fields = [
            {
                "id": f.get("id"),
                "label": f.get("label"),
                "type": f.get("type"),
                "value": "<redacted>" if f.get("type") == "CONCEALED" else f.get("value"),
            }
            for f in it.get("fields", [])
        ]
        return {"id": it.get("id"), "title": it.get("title"), "category": it.get("category"), "fields": fields}
