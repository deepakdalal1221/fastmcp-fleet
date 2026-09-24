from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import AuthError, ConfigError, NotFoundError, RateLimitError, UpstreamError
from mcp_common.http import is_offline, make_client
from pydantic import Field

_TIMEOUT = 30.0


def _base() -> str:
    v = os.environ.get("FRESHDESK_URL")
    if not v:
        raise ConfigError("FRESHDESK_URL is not set (e.g. https://<company>.freshdesk.com)")
    return v.rstrip("/") + "/api/v2"


def _auth() -> httpx.BasicAuth:
    k = os.environ.get("FRESHDESK_KEY")
    if not k:
        raise ConfigError("FRESHDESK_KEY is not set")
    return httpx.BasicAuth(k, "X")


def _raise_for(r: httpx.Response) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"freshdesk auth failed: HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("freshdesk resource not found")
    if r.status_code >= 400:
        raise UpstreamError(f"freshdesk HTTP {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_tickets(per_page: Annotated[int, Field(ge=1, le=100)] = 30) -> dict:
        """List Freshdesk tickets."""
        async with make_client("freshdesk", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_base()}/tickets", auth=_auth(), params={"per_page": per_page})
            _raise_for(r)
            data = r.json()
        return {
            "tickets": [
                {
                    "id": t["id"],
                    "subject": t.get("subject"),
                    "status": t.get("status"),
                    "priority": t.get("priority"),
                    "requester_id": t.get("requester_id"),
                }
                for t in data
            ]
        }

    @mcp.tool
    async def get_ticket(ticket_id: Annotated[int, Field(ge=1)]) -> dict:
        """Get a Freshdesk ticket by id."""
        async with make_client("freshdesk", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_base()}/tickets/{ticket_id}", auth=_auth())
            _raise_for(r)
            t = r.json()
        return {
            "id": t.get("id"),
            "subject": t.get("subject"),
            "description": t.get("description_text"),
            "status": t.get("status"),
            "priority": t.get("priority"),
            "created_at": t.get("created_at"),
        }

    @mcp.tool
    async def create_ticket(
        subject: Annotated[str, Field(min_length=1)],
        description: Annotated[str, Field(min_length=1)],
        email: Annotated[str, Field(min_length=1, description="requester email")],
        priority: Annotated[
            int, Field(ge=1, le=4, description="1=low, 2=med, 3=high, 4=urgent")
        ] = 2,
    ) -> dict:
        """Create a Freshdesk ticket."""
        body = {
            "subject": subject,
            "description": description,
            "email": email,
            "priority": priority,
            "status": 2,
        }
        async with make_client("freshdesk", timeout=_TIMEOUT) as c:
            r = await c.post(f"{_base()}/tickets", auth=_auth(), json=body)
            _raise_for(r)
            t = r.json()
        return {"id": t.get("id"), "subject": t.get("subject"), "status": t.get("status")}
