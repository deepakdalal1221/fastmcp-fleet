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


def _key() -> str:
    v = os.environ.get("MAILCHIMP_API_KEY")
    if not v:
        raise ConfigError("MAILCHIMP_API_KEY is not set")
    return v


def _server() -> str:
    v = os.environ.get("MAILCHIMP_SERVER")
    if not v:
        raise ConfigError("MAILCHIMP_SERVER is not set (e.g. 'us1')")
    return v


def _base() -> str:
    return f"https://{_server()}.api.mailchimp.com/3.0"


def _auth() -> httpx.BasicAuth:
    return httpx.BasicAuth("anystring", _key())


def _raise_for(r: httpx.Response) -> None:
    if r.status_code < 400:
        return
    if r.status_code in (401, 403):
        raise AuthError(f"mailchimp auth failed: {r.text[:200]}")
    if r.status_code == 404:
        raise NotFoundError(f"mailchimp not found: {r.text[:200]}")
    if r.status_code == 429:
        raise RateLimitError(f"mailchimp rate-limited: {r.text[:200]}")
    raise UpstreamError(f"mailchimp {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_audiences(
        count: Annotated[int, Field(description="Max audiences to return", ge=1, le=100)] = 10,
    ) -> dict:
        """List Mailchimp audiences (lists)."""
        async with make_client("mailchimp", timeout=_TIMEOUT) as client:
            r = await client.get(f"{_base()}/lists", auth=_auth(), params={"count": count})
        _raise_for(r)
        return {
            "audiences": [
                {
                    "id": a.get("id"),
                    "name": a.get("name"),
                    "member_count": a.get("stats", {}).get("member_count"),
                }
                for a in r.json().get("lists", [])
            ]
        }

    @mcp.tool
    async def list_campaigns(
        count: Annotated[int, Field(description="Max campaigns to return", ge=1, le=100)] = 10,
    ) -> dict:
        """List Mailchimp campaigns."""
        async with make_client("mailchimp", timeout=_TIMEOUT) as client:
            r = await client.get(f"{_base()}/campaigns", auth=_auth(), params={"count": count})
        _raise_for(r)
        return {
            "campaigns": [
                {
                    "id": c.get("id"),
                    "status": c.get("status"),
                    "subject_line": c.get("settings", {}).get("subject_line"),
                    "send_time": c.get("send_time"),
                }
                for c in r.json().get("campaigns", [])
            ]
        }

    @mcp.tool
    async def add_subscriber(
        list_id: Annotated[str, Field(description="Mailchimp audience/list id")],
        email: Annotated[str, Field(description="Subscriber email address")],
        status: Annotated[
            str,
            Field(description="Subscriber status: subscribed | pending | unsubscribed | cleaned"),
        ] = "subscribed",
    ) -> dict:
        """Add a subscriber to a Mailchimp audience."""
        async with make_client("mailchimp", timeout=_TIMEOUT) as client:
            r = await client.post(
                f"{_base()}/lists/{list_id}/members",
                auth=_auth(),
                json={"email_address": email, "status": status},
            )
        _raise_for(r)
        j = r.json()
        return {
            "id": j.get("id"),
            "email_address": j.get("email_address"),
            "status": j.get("status"),
        }

    @mcp.tool
    async def update_subscriber(
        list_id: Annotated[str, Field(min_length=1)],
        subscriber_hash: Annotated[str, Field(min_length=1, description="MD5 of lowercased email")],
        email_address: Annotated[str | None, Field(description="new email")] = None,
        merge_fields: Annotated[dict | None, Field(description="e.g. FNAME/LNAME")] = None,
    ) -> dict:
        """Update a Mailchimp subscriber."""
        body = {
            k: v
            for k, v in {"email_address": email_address, "merge_fields": merge_fields}.items()
            if v is not None
        }
        async with make_client("mailchimp", timeout=_TIMEOUT) as c:
            r = await c.patch(
                f"{_base()}/lists/{list_id}/members/{subscriber_hash}", auth=_auth(), json=body
            )
            _raise_for(r)
        return r.json()

    @mcp.tool
    async def unsubscribe(
        list_id: Annotated[str, Field(min_length=1)],
        subscriber_hash: Annotated[str, Field(min_length=1, description="MD5 of lowercased email")],
    ) -> dict:
        """Unsubscribe a Mailchimp subscriber (soft delete: sets status=unsubscribed)."""
        async with make_client("mailchimp", timeout=_TIMEOUT) as c:
            r = await c.patch(
                f"{_base()}/lists/{list_id}/members/{subscriber_hash}",
                auth=_auth(),
                json={"status": "unsubscribed"},
            )
            _raise_for(r)
        return {"list_id": list_id, "subscriber_hash": subscriber_hash, "status": "unsubscribed"}
