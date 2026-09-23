from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from pydantic import Field

from mcp_common.errors import (
    AuthError,
    ConfigError,
    NotFoundError,
    RateLimitError,
    UpstreamError,
)

_BASE = "https://huggingface.co/api"
_TIMEOUT = 30.0


def _token() -> str:
    v = os.environ.get("HUGGINGFACE_TOKEN") or os.environ.get("HF_TOKEN")
    if not v:
        raise ConfigError("HUGGINGFACE_TOKEN is not set")
    return v


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_token()}", "Accept": "application/json"}


def _raise_for(r: httpx.Response) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"huggingface auth failed: HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("huggingface resource not found")
    if r.status_code == 429:
        raise RateLimitError("huggingface rate limited")
    if r.status_code >= 400:
        raise UpstreamError(f"huggingface HTTP {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_models(
        search: Annotated[str | None, Field(description="text query to filter models")] = None,
        author: Annotated[str | None, Field(description="filter by author/org")] = None,
        limit: Annotated[int, Field(ge=1, le=100)] = 20,
    ) -> dict:
        """List Hugging Face models with optional search filter."""
        params: dict[str, object] = {"limit": limit}
        if search:
            params["search"] = search
        if author:
            params["author"] = author
        async with make_client("huggingface", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/models", headers=_headers(), params=params)
            _raise_for(r)
            data = r.json()
        return {
            "models": [
                {
                    "id": m["id"],
                    "downloads": m.get("downloads"),
                    "likes": m.get("likes"),
                    "pipeline_tag": m.get("pipeline_tag"),
                }
                for m in data
            ]
        }

    @mcp.tool
    async def get_model(
        model_id: Annotated[str, Field(min_length=1, description="model id like 'meta-llama/Llama-3-8B'")],
    ) -> dict:
        """Get a single Hugging Face model by id."""
        async with make_client("huggingface", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/models/{model_id}", headers=_headers())
            _raise_for(r)
            m = r.json()
        return {
            "id": m.get("id") or m.get("modelId"),
            "author": m.get("author"),
            "downloads": m.get("downloads"),
            "likes": m.get("likes"),
            "library": m.get("library_name"),
            "pipeline_tag": m.get("pipeline_tag"),
            "tags": (m.get("tags") or [])[:20],
        }

    @mcp.tool
    async def whoami() -> dict:
        """Return the authenticated Hugging Face user profile."""
        async with make_client("huggingface", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/whoami-v2", headers=_headers())
            _raise_for(r)
            u = r.json()
        return {
            "name": u.get("name"),
            "email": u.get("email"),
            "orgs": [o.get("name") for o in (u.get("orgs") or [])],
        }
