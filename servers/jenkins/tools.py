from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from mcp_common.errors import (
    AuthError,
    ConfigError,
    NotFoundError,
    RateLimitError,
    UpstreamError,
)
from mcp_common.http import make_client
from pydantic import Field

_TIMEOUT = 30.0


def _base() -> str:
    v = os.environ.get("JENKINS_URL")
    if not v:
        raise ConfigError("JENKINS_URL is not set")
    return v.rstrip("/")


def _auth() -> httpx.BasicAuth:
    user = os.environ.get("JENKINS_USER")
    token = os.environ.get("JENKINS_TOKEN")
    if not user or not token:
        raise ConfigError("JENKINS_USER and JENKINS_TOKEN must be set")
    return httpx.BasicAuth(user, token)


def _raise_for(r: httpx.Response) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"jenkins auth failed: HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("jenkins resource not found")
    if r.status_code == 429:
        raise RateLimitError("jenkins rate limited")
    if r.status_code >= 400 and r.status_code != 201:
        raise UpstreamError(f"jenkins HTTP {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_jobs() -> dict:
        """List Jenkins jobs on the configured server."""
        async with make_client("jenkins", timeout=_TIMEOUT) as c:
            r = await c.get(
                f"{_base()}/api/json",
                auth=_auth(),
                params={"tree": "jobs[name,url,color]"},
            )
            _raise_for(r)
            data = r.json()
        return {
            "jobs": [
                {"name": j["name"], "url": j.get("url"), "color": j.get("color")}
                for j in data.get("jobs", [])
            ]
        }

    @mcp.tool
    async def trigger_build(
        job_name: Annotated[str, Field(min_length=1, description="Jenkins job name")],
        parameters: Annotated[
            dict | None, Field(description="build parameters as JSON object")
        ] = None,
    ) -> dict:
        """Trigger a Jenkins build for the named job."""
        path = "buildWithParameters" if parameters else "build"
        async with make_client("jenkins", timeout=_TIMEOUT) as c:
            r = await c.post(
                f"{_base()}/job/{job_name}/{path}",
                auth=_auth(),
                params=parameters or None,
            )
            if r.status_code not in (200, 201):
                _raise_for(r)
        return {
            "triggered": True,
            "job": job_name,
            "queue_url": r.headers.get("Location"),
        }

    @mcp.tool
    async def get_build(
        job_name: Annotated[str, Field(min_length=1, description="Jenkins job name")],
        build_number: Annotated[int, Field(ge=1, description="build number")],
    ) -> dict:
        """Get Jenkins build metadata by job name and build number."""
        async with make_client("jenkins", timeout=_TIMEOUT) as c:
            r = await c.get(
                f"{_base()}/job/{job_name}/{build_number}/api/json",
                auth=_auth(),
            )
            _raise_for(r)
            b = r.json()
        return {
            "number": b.get("number"),
            "result": b.get("result"),
            "building": b.get("building"),
            "duration_ms": b.get("duration"),
            "timestamp": b.get("timestamp"),
            "url": b.get("url"),
        }
