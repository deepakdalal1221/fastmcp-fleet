from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from mcp_common.errors import AuthError, ConfigError, NotFoundError, RateLimitError, UpstreamError
from mcp_common.http import make_client
from pydantic import Field

_BASE = "https://api.sendgrid.com/v3"
_TIMEOUT = 30.0


def _key() -> str:
    v = os.environ.get("SENDGRID_API_KEY")
    if not v:
        raise ConfigError("SENDGRID_API_KEY is not set")
    return v


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_key()}", "Content-Type": "application/json"}


def _raise_for(r: httpx.Response) -> None:
    if r.status_code < 400:
        return
    if r.status_code in (401, 403):
        raise AuthError(f"sendgrid auth failed: {r.text[:200]}")
    if r.status_code == 404:
        raise NotFoundError(f"sendgrid not found: {r.text[:200]}")
    if r.status_code == 429:
        raise RateLimitError(f"sendgrid rate-limited: {r.text[:200]}")
    raise UpstreamError(f"sendgrid {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def send_email(
        to: Annotated[str, Field(description="Recipient email address")],
        subject: Annotated[str, Field(description="Email subject line")],
        body: Annotated[str, Field(description="Plain-text body")],
        from_email: Annotated[str, Field(description="Verified sender email address")],
    ) -> dict:
        """Send a plain-text email via SendGrid."""
        payload = {
            "personalizations": [{"to": [{"email": to}]}],
            "from": {"email": from_email},
            "subject": subject,
            "content": [{"type": "text/plain", "value": body}],
        }
        async with make_client("sendgrid", timeout=_TIMEOUT) as client:
            r = await client.post(f"{_BASE}/mail/send", headers=_headers(), json=payload)
        _raise_for(r)
        return {"status": "sent", "status_code": r.status_code}

    @mcp.tool
    async def list_templates() -> dict:
        """List SendGrid dynamic templates."""
        async with make_client("sendgrid", timeout=_TIMEOUT) as client:
            r = await client.get(
                f"{_BASE}/templates", headers=_headers(), params={"generations": "dynamic"}
            )
        _raise_for(r)
        return {
            "templates": [
                {"id": t.get("id"), "name": t.get("name"), "updated_at": t.get("updated_at")}
                for t in r.json().get("result", [])
            ]
        }
