from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from pydantic import Field

from mcp_common.errors import AuthError, ConfigError, NotFoundError, RateLimitError, UpstreamError

_TIMEOUT = 30.0


def _domain() -> str:
    v = os.environ.get("AUTH0_DOMAIN")
    if not v:
        raise ConfigError("AUTH0_DOMAIN is not set")
    return v


def _token() -> str:
    v = os.environ.get("AUTH0_TOKEN")
    if not v:
        raise ConfigError("AUTH0_TOKEN is not set")
    return v


def _base() -> str:
    return f"https://{_domain()}/api/v2"


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"}


def _raise_for(r: httpx.Response) -> None:
    if r.status_code < 400:
        return
    if r.status_code in (401, 403):
        raise AuthError(f"auth0 auth failed: {r.text[:200]}")
    if r.status_code == 404:
        raise NotFoundError(f"auth0 not found: {r.text[:200]}")
    if r.status_code == 429:
        raise RateLimitError(f"auth0 rate-limited: {r.text[:200]}")
    raise UpstreamError(f"auth0 {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_users(
        per_page: Annotated[int, Field(description="Users per page", ge=1, le=100)] = 25,
    ) -> dict:
        """List Auth0 users."""
        async with make_client("auth0", timeout=_TIMEOUT) as client:
            r = await client.get(f"{_base()}/users", headers=_headers(), params={"per_page": per_page})
        _raise_for(r)
        return {
            "users": [
                {
                    "user_id": u.get("user_id"),
                    "email": u.get("email"),
                    "name": u.get("name"),
                    "created_at": u.get("created_at"),
                    "last_login": u.get("last_login"),
                }
                for u in r.json()
            ]
        }

    @mcp.tool
    async def list_clients(
        per_page: Annotated[int, Field(description="Clients per page", ge=1, le=100)] = 25,
    ) -> dict:
        """List Auth0 applications (clients)."""
        async with make_client("auth0", timeout=_TIMEOUT) as client:
            r = await client.get(f"{_base()}/clients", headers=_headers(), params={"per_page": per_page})
        _raise_for(r)
        return {
            "clients": [
                {"client_id": c.get("client_id"), "name": c.get("name"), "app_type": c.get("app_type")}
                for c in r.json()
            ]
        }

    @mcp.tool
    async def list_rules() -> dict:
        """List Auth0 rules."""
        async with make_client("auth0", timeout=_TIMEOUT) as client:
            r = await client.get(f"{_base()}/rules", headers=_headers())
        _raise_for(r)
        return {
            "rules": [
                {"id": r_.get("id"), "name": r_.get("name"), "enabled": r_.get("enabled"), "stage": r_.get("stage")}
                for r_ in r.json()
            ]
        }
