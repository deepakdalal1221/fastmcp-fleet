from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from pydantic import Field

from mcp_common.errors import AuthError, ConfigError, NotFoundError, RateLimitError, UpstreamError
from mcp_common.http import is_offline, make_client
from mcp_common import local_store

_TIMEOUT = 30.0


def _base() -> str:
    v = os.environ.get("VAULT_ADDR")
    if not v:
        raise ConfigError("VAULT_ADDR is not set (e.g. http://127.0.0.1:8200)")
    return v.rstrip("/") + "/v1"


def _token() -> str:
    v = os.environ.get("VAULT_TOKEN")
    if not v:
        raise ConfigError("VAULT_TOKEN is not set")
    return v


def _headers() -> dict[str, str]:
    return {"X-Vault-Token": _token(), "Accept": "application/json"}


def _raise_for(r: httpx.Response) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"vault auth failed: HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("vault resource not found")
    if r.status_code == 429:
        raise RateLimitError("vault rate limited")
    if r.status_code >= 400:
        raise UpstreamError(f"vault HTTP {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_secrets_engines() -> dict:
        """List enabled HashiCorp Vault secrets engines."""
        async with make_client("vault", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_base()}/sys/mounts", headers=_headers())
            _raise_for(r)
            data = r.json()
        raw = data.get("data") or data
        engines = []
        for path, info in raw.items():
            if isinstance(info, dict) and info.get("type"):
                engines.append({"path": path, "type": info.get("type"), "description": info.get("description")})
        return {"engines": engines}

    @mcp.tool
    async def list_secrets(
        mount: Annotated[str, Field(min_length=1, description="mount path, e.g. secret")],
        path: Annotated[str, Field(description="subpath under mount")] = "",
    ) -> dict:
        """List secret keys at a KV v2 path (LIST verb)."""
        p = path.strip("/")
        url = f"{_base()}/{mount.strip('/')}/metadata/{p}" if p else f"{_base()}/{mount.strip('/')}/metadata"
        async with make_client("vault", timeout=_TIMEOUT) as c:
            r = await c.request("LIST", url, headers=_headers())
            _raise_for(r)
            data = r.json()
        return {"keys": ((data.get("data") or {}).get("keys") or [])}

    @mcp.tool
    async def read_secret(
        mount: Annotated[str, Field(min_length=1, description="mount path, e.g. secret")],
        path: Annotated[str, Field(min_length=1, description="secret path")],
    ) -> dict:
        """Read a KV v2 secret. Values are redacted; only keys are returned."""
        url = f"{_base()}/{mount.strip('/')}/data/{path.strip('/')}"
        async with make_client("vault", timeout=_TIMEOUT) as c:
            r = await c.get(url, headers=_headers())
            _raise_for(r)
            data = r.json()
        inner = ((data.get("data") or {}).get("data") or {})
        return {"path": path, "keys": sorted(inner.keys()), "version": ((data.get("data") or {}).get("metadata") or {}).get("version")}
