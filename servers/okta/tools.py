from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from pydantic import Field

from mcp_common.errors import AuthError, ConfigError, NotFoundError, RateLimitError, UpstreamError

_TIMEOUT = 30.0


def _url() -> str:
    v = os.environ.get("OKTA_URL")
    if not v:
        raise ConfigError("OKTA_URL is not set")
    return v.rstrip("/")


def _token() -> str:
    v = os.environ.get("OKTA_TOKEN")
    if not v:
        raise ConfigError("OKTA_TOKEN is not set")
    return v


def _base() -> str:
    return f"{_url()}/api/v1"


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"SSWS {_token()}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _raise_for(r: httpx.Response) -> None:
    if r.status_code < 400:
        return
    if r.status_code in (401, 403):
        raise AuthError(f"okta auth failed: {r.text[:200]}")
    if r.status_code == 404:
        raise NotFoundError(f"okta not found: {r.text[:200]}")
    if r.status_code == 429:
        raise RateLimitError(f"okta rate-limited: {r.text[:200]}")
    raise UpstreamError(f"okta {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_users(
        limit: Annotated[int, Field(description="Max users to return", ge=1, le=200)] = 25,
    ) -> dict:
        """List Okta users."""
        async with make_client("okta", timeout=_TIMEOUT) as client:
            r = await client.get(f"{_base()}/users", headers=_headers(), params={"limit": limit})
        _raise_for(r)
        return {
            "users": [
                {
                    "id": u.get("id"),
                    "status": u.get("status"),
                    "email": u.get("profile", {}).get("email"),
                    "firstName": u.get("profile", {}).get("firstName"),
                    "lastName": u.get("profile", {}).get("lastName"),
                    "created": u.get("created"),
                }
                for u in r.json()
            ]
        }

    @mcp.tool
    async def list_groups(
        limit: Annotated[int, Field(description="Max groups to return", ge=1, le=200)] = 25,
    ) -> dict:
        """List Okta groups."""
        async with make_client("okta", timeout=_TIMEOUT) as client:
            r = await client.get(f"{_base()}/groups", headers=_headers(), params={"limit": limit})
        _raise_for(r)
        return {
            "groups": [
                {
                    "id": g.get("id"),
                    "name": g.get("profile", {}).get("name"),
                    "description": g.get("profile", {}).get("description"),
                }
                for g in r.json()
            ]
        }

    @mcp.tool
    async def list_apps(
        limit: Annotated[int, Field(description="Max apps to return", ge=1, le=200)] = 25,
    ) -> dict:
        """List Okta applications."""
        async with make_client("okta", timeout=_TIMEOUT) as client:
            r = await client.get(f"{_base()}/apps", headers=_headers(), params={"limit": limit})
        _raise_for(r)
        return {
            "apps": [
                {
                    "id": a.get("id"),
                    "label": a.get("label"),
                    "status": a.get("status"),
                    "signOnMode": a.get("signOnMode"),
                }
                for a in r.json()
            ]
        }
