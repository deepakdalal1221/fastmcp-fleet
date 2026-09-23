from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from pydantic import Field

from mcp_common.errors import AuthError, ConfigError, NotFoundError, RateLimitError, UpstreamError
from mcp_common.http import is_offline, make_client
from mcp_common import local_store

_BASE = "https://openrouter.ai/api/v1"
_TIMEOUT = 30.0


def _token() -> str:
    v = os.environ.get("OPENROUTER_API_KEY")
    if not v:
        raise ConfigError("OPENROUTER_API_KEY is not set")
    return v


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_token()}", "Content-Type": "application/json", "Accept": "application/json", "X-Title": "fastmcp-fleet"}


def _raise_for(r: httpx.Response) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"openrouter auth failed: HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("openrouter resource not found")
    if r.status_code == 429:
        raise RateLimitError("openrouter rate limited")
    if r.status_code >= 400:
        raise UpstreamError(f"openrouter HTTP {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def chat_completion(
        prompt: Annotated[str, Field(min_length=1, description="user prompt")],
        model: Annotated[str, Field(description="model id")] = "anthropic/claude-3.5-sonnet",
        temperature: Annotated[float, Field(ge=0.0, le=2.0)] = 0.7,
        max_tokens: Annotated[int, Field(ge=1, le=8192)] = 1024,
    ) -> dict:
        """Chat completion (OpenAI-compatible schema)."""
        body = {"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": temperature, "max_tokens": max_tokens}
        async with make_client("openrouter", timeout=60.0) as c:
            r = await c.post(f"{_BASE}/chat/completions", headers=_headers(), json=body)
            _raise_for(r)
            data = r.json()
        choices = data.get("choices", [])
        text = ""
        finish = None
        if choices:
            text = ((choices[0].get("message") or {}).get("content") or "")
            finish = choices[0].get("finish_reason")
        usage = data.get("usage", {})
        return {"text": text, "model": data.get("model", model), "finish_reason": finish, "usage": {"prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens"), "total_tokens": usage.get("total_tokens")}}

    @mcp.tool
    async def list_models() -> dict:
        """List models available."""
        async with make_client("openrouter", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/models", headers=_headers())
            _raise_for(r)
            data = r.json()
        return {"models": [{"id": m.get("id"), "created": m.get("created"), "owned_by": m.get("owned_by")} for m in data.get("data", [])]}
