from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import AuthError, ConfigError, NotFoundError, UpstreamError
from mcp_common.http import is_offline, make_client
from pydantic import Field

_TIMEOUT = 30.0


def _base():
    v = os.environ.get("SPINNAKER_URL")
    if not v:
        raise ConfigError("SPINNAKER_URL is not set (Spinnaker Gate)")
    return v.rstrip("/")


def _headers():
    u = os.environ.get("SPINNAKER_USER", "anonymous")
    return {"X-Spinnaker-User": u, "Accept": "application/json"}


def _raise_for(r):
    if r.status_code in (401, 403):
        raise AuthError(f"spinnaker HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("spinnaker not found")
    if r.status_code >= 400:
        raise UpstreamError(f"spinnaker HTTP {r.status_code}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_applications() -> dict:
        """List Spinnaker applications."""
        async with make_client("spinnaker", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_base()}/applications", headers=_headers())
            _raise_for(r)
        return {
            "applications": [{"name": a.get("name"), "email": a.get("email")} for a in r.json()]
        }

    @mcp.tool
    async def list_pipelines(application: Annotated[str, Field(min_length=1)]) -> dict:
        """List Spinnaker pipelines for an application."""
        async with make_client("spinnaker", timeout=_TIMEOUT) as c:
            r = await c.get(
                f"{_base()}/applications/{application}/pipelineConfigs", headers=_headers()
            )
            _raise_for(r)
        return {
            "pipelines": [
                {"id": p.get("id"), "name": p.get("name"), "application": p.get("application")}
                for p in r.json()
            ]
        }

    @mcp.tool
    async def trigger_pipeline(
        application: Annotated[str, Field(min_length=1)],
        pipeline_id: Annotated[str, Field(min_length=1)],
    ) -> dict:
        """Trigger a Spinnaker pipeline."""
        async with make_client("spinnaker", timeout=_TIMEOUT) as c:
            r = await c.post(f"{_base()}/pipelines/{pipeline_id}", headers=_headers(), json={})
            _raise_for(r)
        return {"triggered": True, "pipeline_id": pipeline_id, "application": application}
