from __future__ import annotations

from mcp_common.http import is_offline

from mcp_common import local_store

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from pydantic import Field

from mcp_common.errors import AuthError, ConfigError, NotFoundError, RateLimitError, UpstreamError

_TIMEOUT = 30.0


def _sid() -> str:
    v = os.environ.get("TWILIO_ACCOUNT_SID")
    if not v:
        raise ConfigError("TWILIO_ACCOUNT_SID is not set")
    return v


def _token() -> str:
    v = os.environ.get("TWILIO_AUTH_TOKEN")
    if not v:
        raise ConfigError("TWILIO_AUTH_TOKEN is not set")
    return v


def _auth() -> httpx.BasicAuth:
    return httpx.BasicAuth(_sid(), _token())


def _base() -> str:
    return f"https://api.twilio.com/2010-04-01/Accounts/{_sid()}"


def _raise_for(r: httpx.Response) -> None:
    if r.status_code < 400:
        return
    if r.status_code in (401, 403):
        raise AuthError(f"twilio auth failed: {r.text[:200]}")
    if r.status_code == 404:
        raise NotFoundError(f"twilio not found: {r.text[:200]}")
    if r.status_code == 429:
        raise RateLimitError(f"twilio rate-limited: {r.text[:200]}")
    raise UpstreamError(f"twilio {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def send_sms(
        to: Annotated[str, Field(min_length=1, description="destination phone number in E.164")],
        from_: Annotated[str, Field(min_length=1, description="Twilio number in E.164")],
        body: Annotated[str, Field(min_length=1, description="SMS body")],
    ) -> dict:
        """Send an SMS via Twilio. Offline mode persists to local state for list_messages."""
        if is_offline():
            col = f"messages:{to}"
            n = local_store.next_id("twilio", col)
            sid = f"SMoffline{n:010d}"
            msg = {"sid": sid, "to": to, "from": from_, "body": body, "status": "queued", "direction": "outbound-api"}
            await local_store.put("twilio", col, sid, msg)
            return {"sid": sid, "to": to, "from": from_, "status": "queued"}
        data = {"To": to, "From": from_, "Body": body}
        async with make_client("twilio", timeout=_TIMEOUT) as c:
            r = await c.post(f"{_base()}/Messages.json", auth=_auth(), data=data)
            _raise_for(r)
            j = r.json()
        return {"sid": j.get("sid"), "to": j.get("to"), "from": j.get("from"), "status": j.get("status")}

    @mcp.tool
    async def list_messages(
        to: Annotated[str | None, Field(description="filter by destination number")] = None,
        limit: Annotated[int, Field(ge=1, le=100)] = 20,
    ) -> dict:
        """List Twilio messages. Offline mode returns locally-sent messages."""
        if is_offline():
            if to:
                stored = await local_store.list_all("twilio", f"messages:{to}")
            else:
                stored = []
            msgs = [row["value"] for row in stored][:limit]
            return {"messages": [{"sid": m["sid"], "to": m["to"], "from": m["from"], "body": m["body"], "status": m["status"]} for m in msgs]}
        params = {"PageSize": limit}
        if to:
            params["To"] = to
        async with make_client("twilio", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_base()}/Messages.json", auth=_auth(), params=params)
            _raise_for(r)
            j = r.json()
        return {"messages": [{"sid": m.get("sid"), "to": m.get("to"), "from": m.get("from"), "body": m.get("body"), "status": m.get("status")} for m in j.get("messages", [])]}

    @mcp.tool
    async def make_call(
        to: Annotated[str, Field(description="Callee phone number in E.164 format")],
        from_number: Annotated[str, Field(description="Twilio-owned phone number in E.164 format")],
        url: Annotated[str, Field(description="TwiML URL Twilio will fetch when the call connects")],
    ) -> dict:
        """Start an outbound voice call via Twilio."""
        async with make_client("twilio", timeout=_TIMEOUT) as client:
            r = await client.post(
                f"{_base()}/Calls.json",
                auth=_auth(),
                data={"To": to, "From": from_number, "Url": url},
            )
        _raise_for(r)
        j = r.json()
        return {"sid": j.get("sid"), "status": j.get("status"), "to": j.get("to"), "from": j.get("from")}
