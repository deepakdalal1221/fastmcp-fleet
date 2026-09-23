from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from pydantic import Field

from mcp_common.errors import AuthError, ConfigError, NotFoundError, RateLimitError, UpstreamError
from mcp_common.http import is_offline, make_client
from mcp_common import local_store

_BASE = "https://api.mistral.ai/v1"
_TIMEOUT = 60.0


def _token() -> str:
    v = os.environ.get("MISTRAL_API_KEY")
    if not v:
        raise ConfigError("MISTRAL_API_KEY is not set")
    return v


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_token()}", "Accept": "application/json", "Content-Type": "application/json"}


def _raise_for(r: httpx.Response) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"mistral auth failed: HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("mistral resource not found")
    if r.status_code == 429:
        raise RateLimitError("mistral rate limited")
    if r.status_code >= 400:
        raise UpstreamError(f"mistral HTTP {r.status_code}: {r.text[:400]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def chat_completion(
        prompt: Annotated[str, Field(min_length=1, description="user prompt")],
        model: Annotated[str, Field(description="Mistral model id")] = "mistral-small-latest",
        temperature: Annotated[float, Field(ge=0.0, le=1.5)] = 0.7,
        max_tokens: Annotated[int, Field(ge=1, le=8192)] = 1024,
    ) -> dict:
        """Send a chat completion to Mistral."""
        body = {"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": temperature, "max_tokens": max_tokens}
        async with make_client("mistral", timeout=_TIMEOUT) as c:
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
    async def embed(
        text: Annotated[str, Field(min_length=1, description="text to embed")],
        model: Annotated[str, Field(description="Mistral embedding model")] = "mistral-embed",
    ) -> dict:
        """Embed a text string with Mistral."""
        body = {"model": model, "input": [text]}
        async with make_client("mistral", timeout=_TIMEOUT) as c:
            r = await c.post(f"{_BASE}/embeddings", headers=_headers(), json=body)
            _raise_for(r)
            data = r.json()
        emb = ((data.get("data") or [{}])[0].get("embedding") or [])
        return {"model": model, "dimensions": len(emb), "embedding_preview": emb[:8]}

    @mcp.tool
    async def list_models() -> dict:
        """List Mistral models available to the caller."""
        async with make_client("mistral", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/models", headers=_headers())
            _raise_for(r)
            data = r.json()
        return {"models": [{"id": m.get("id"), "created": m.get("created"), "owned_by": m.get("owned_by")} for m in data.get("data", [])]}
