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

_BASE = "https://generativelanguage.googleapis.com/v1beta"
_TIMEOUT = 60.0


def _key() -> str:
    v = os.environ.get("GEMINI_API_KEY")
    if not v:
        raise ConfigError("GEMINI_API_KEY is not set")
    return v


def _raise_for(r: httpx.Response) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"gemini auth failed: HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("gemini resource not found")
    if r.status_code == 429:
        raise RateLimitError("gemini rate limited")
    if r.status_code >= 400:
        raise UpstreamError(f"gemini HTTP {r.status_code}: {r.text[:400]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def generate_content(
        prompt: Annotated[str, Field(min_length=1, description="user prompt")],
        model: Annotated[str, Field(description="Gemini model id")] = "gemini-1.5-flash",
        temperature: Annotated[float, Field(ge=0.0, le=2.0)] = 0.7,
        max_output_tokens: Annotated[int, Field(ge=1, le=8192)] = 1024,
    ) -> dict:
        """Generate content with a Gemini model given a text prompt."""
        body = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_output_tokens,
            },
        }
        async with make_client("gemini", timeout=_TIMEOUT) as c:
            r = await c.post(
                f"{_BASE}/models/{model}:generateContent",
                params={"key": _key()},
                json=body,
            )
            _raise_for(r)
            data = r.json()
        candidates = data.get("candidates", [])
        text = ""
        finish = None
        if candidates:
            parts = (candidates[0].get("content") or {}).get("parts") or []
            text = "".join(p.get("text", "") for p in parts)
            finish = candidates[0].get("finishReason")
        usage = data.get("usageMetadata", {})
        return {
            "text": text,
            "finish_reason": finish,
            "model": model,
            "usage": {
                "prompt_tokens": usage.get("promptTokenCount"),
                "output_tokens": usage.get("candidatesTokenCount"),
                "total_tokens": usage.get("totalTokenCount"),
            },
        }

    @mcp.tool
    async def embed_content(
        text: Annotated[str, Field(min_length=1, description="text to embed")],
        model: Annotated[
            str, Field(description="Gemini embedding model id")
        ] = "text-embedding-004",
    ) -> dict:
        """Embed a text string with a Gemini embedding model."""
        body = {"content": {"parts": [{"text": text}]}}
        async with make_client("gemini", timeout=_TIMEOUT) as c:
            r = await c.post(
                f"{_BASE}/models/{model}:embedContent",
                params={"key": _key()},
                json=body,
            )
            _raise_for(r)
            data = r.json()
        emb = (data.get("embedding") or {}).get("values") or []
        return {"model": model, "dimensions": len(emb), "embedding_preview": emb[:8]}

    @mcp.tool
    async def list_models() -> dict:
        """List Gemini models available to the caller."""
        async with make_client("gemini", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/models", params={"key": _key()})
            _raise_for(r)
            data = r.json()
        return {
            "models": [
                {
                    "name": m.get("name"),
                    "display_name": m.get("displayName"),
                    "input_token_limit": m.get("inputTokenLimit"),
                    "output_token_limit": m.get("outputTokenLimit"),
                }
                for m in data.get("models", [])
            ]
        }
