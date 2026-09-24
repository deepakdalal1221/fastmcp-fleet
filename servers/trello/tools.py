from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import AuthError, ConfigError, NotFoundError, RateLimitError, UpstreamError
from mcp_common.http import is_offline, make_client
from pydantic import Field

_BASE = "https://api.trello.com/1"
_TIMEOUT = 30.0


def _creds() -> dict[str, str]:
    k = os.environ.get("TRELLO_KEY")
    t = os.environ.get("TRELLO_TOKEN")
    if not k or not t:
        raise ConfigError("TRELLO_KEY and TRELLO_TOKEN must be set")
    return {"key": k, "token": t}


def _raise_for(r: httpx.Response) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"trello auth failed: HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("trello resource not found")
    if r.status_code >= 400:
        raise UpstreamError(f"trello HTTP {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_boards() -> dict:
        """List Trello boards accessible to the token owner."""
        async with make_client("trello", timeout=_TIMEOUT) as c:
            r = await c.get(
                f"{_BASE}/members/me/boards", params={**_creds(), "fields": "name,url,closed"}
            )
            _raise_for(r)
            data = r.json()
        return {
            "boards": [
                {"id": b["id"], "name": b["name"], "url": b.get("url"), "closed": b.get("closed")}
                for b in data
            ]
        }

    @mcp.tool
    async def list_cards(board_id: Annotated[str, Field(min_length=1)]) -> dict:
        """List Trello cards on a board."""
        async with make_client("trello", timeout=_TIMEOUT) as c:
            r = await c.get(
                f"{_BASE}/boards/{board_id}/cards",
                params={**_creds(), "fields": "name,desc,due,idList,url"},
            )
            _raise_for(r)
            data = r.json()
        return {
            "cards": [
                {
                    "id": card["id"],
                    "name": card["name"],
                    "desc": (card.get("desc") or "")[:200],
                    "due": card.get("due"),
                    "list_id": card.get("idList"),
                    "url": card.get("url"),
                }
                for card in data
            ]
        }

    @mcp.tool
    async def create_card(
        list_id: Annotated[str, Field(min_length=1, description="Trello list id")],
        name: Annotated[str, Field(min_length=1)],
        desc: Annotated[str | None, Field(description="card description")] = None,
    ) -> dict:
        """Create a Trello card in a list."""
        params = {**_creds(), "idList": list_id, "name": name}
        if desc:
            params["desc"] = desc
        async with make_client("trello", timeout=_TIMEOUT) as c:
            r = await c.post(f"{_BASE}/cards", params=params)
            _raise_for(r)
            card = r.json()
        return {
            "id": card.get("id"),
            "name": card.get("name"),
            "url": card.get("url"),
            "due": card.get("due"),
        }
