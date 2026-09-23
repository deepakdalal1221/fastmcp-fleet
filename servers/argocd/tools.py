from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from pydantic import Field

from mcp_common.errors import AuthError, ConfigError, NotFoundError, RateLimitError, UpstreamError
from mcp_common.http import is_offline, make_client
from mcp_common import local_store

_TIMEOUT = 30.0  # noqa
_TIMEOUT = 30.0


def _base() -> str:
    v = os.environ.get("ARGOCD_URL")
    if not v:
        raise ConfigError("ARGOCD_URL is not set (e.g. https://argocd.example.com)")
    return v.rstrip("/") + "/api/v1"


def _token() -> str:
    v = os.environ.get("ARGOCD_TOKEN")
    if not v:
        raise ConfigError("ARGOCD_TOKEN is not set")
    return v


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_token()}", "Accept": "application/json"}


def _raise_for(r: httpx.Response) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"argocd auth failed: HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("argocd resource not found")
    if r.status_code == 429:
        raise RateLimitError("argocd rate limited")
    if r.status_code >= 400:
        raise UpstreamError(f"argocd HTTP {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_applications() -> dict:
        """List ArgoCD applications."""
        async with make_client("argocd", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_base()}/applications", headers=_headers())
            _raise_for(r)
            data = r.json()
        return {"applications": [{"name": (p.get("metadata") or {}).get("name"), "namespace": (p.get("spec") or {}).get("destination", {}).get("namespace"), "sync_status": ((p.get("status") or {}).get("sync") or {}).get("status"), "health": ((p.get("status") or {}).get("health") or {}).get("status")} for p in data.get("items", [])]}

    @mcp.tool
    async def get_application(
        name: Annotated[str, Field(min_length=1, description="ArgoCD application name")],
    ) -> dict:
        """Get an ArgoCD application by name."""
        async with make_client("argocd", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_base()}/applications/{name}", headers=_headers())
            _raise_for(r)
            p = r.json()
        return {"name": (p.get("metadata") or {}).get("name"), "repo": (p.get("spec") or {}).get("source", {}).get("repoURL"), "path": (p.get("spec") or {}).get("source", {}).get("path"), "target_revision": (p.get("spec") or {}).get("source", {}).get("targetRevision"), "sync_status": ((p.get("status") or {}).get("sync") or {}).get("status"), "health": ((p.get("status") or {}).get("health") or {}).get("status")}

    @mcp.tool
    async def sync_application(
        name: Annotated[str, Field(min_length=1, description="ArgoCD application name")],
        prune: Annotated[bool, Field(description="prune resources not in git")] = False,
    ) -> dict:
        """Trigger an ArgoCD application sync."""
        body = {"prune": prune}
        async with make_client("argocd", timeout=_TIMEOUT) as c:
            r = await c.post(f"{_base()}/applications/{name}/sync", headers=_headers(), json=body)
            _raise_for(r)
            p = r.json()
        return {"name": (p.get("metadata") or {}).get("name"), "sync_started": True, "operation": ((p.get("status") or {}).get("operationState") or {}).get("phase")}
