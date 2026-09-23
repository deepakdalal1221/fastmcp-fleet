from __future__ import annotations

import os
from typing import Annotated, Any

import httpx
from fastmcp import FastMCP
from pydantic import Field

from mcp_common.errors import (
    AuthError,
    ConfigError,
    RateLimitError,
    UpstreamError,
    ValidationError,
)

_API_BASE = "https://api.openai.com/v1"


def _token() -> str:
    token = os.environ.get("OPENAI_API_KEY", "").strip()
    if not token:
        raise ConfigError("OPENAI_API_KEY is not set")
    return token


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_token()}",
        "Content-Type": "application/json",
        "User-Agent": "fastmcp-platform/openai",
    }


def _raise_for_status(response: httpx.Response) -> None:
    if response.status_code == 401:
        raise AuthError("OpenAI authentication failed")
    if response.status_code == 403:
        raise AuthError("OpenAI permission denied")
    if response.status_code == 429:
        raise RateLimitError("OpenAI rate limit exceeded")
    if response.status_code >= 500:
        raise UpstreamError(f"OpenAI upstream error: HTTP {response.status_code}")
    if response.status_code >= 400:
        raise UpstreamError(f"OpenAI HTTP {response.status_code}: {response.text[:200]}")


async def _post(
    client: httpx.AsyncClient, path: str, body: dict[str, Any]
) -> dict[str, Any]:
    try:
        response = await client.post(f"{_API_BASE}{path}", json=body, headers=_headers())
    except httpx.RequestError as exc:
        raise UpstreamError(f"OpenAI request failed: {exc}") from exc
    _raise_for_status(response)
    return response.json()


def _clamp_max_tokens(n: int) -> int:
    return max(1, min(4096, n))


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def chat_completion(
        prompt: Annotated[str, Field(description="User prompt text")],
        model: Annotated[str, Field(description="OpenAI chat model")] = "gpt-4o-mini",
        system: Annotated[str, Field(description="Optional system prompt")] = "",
        max_tokens: Annotated[int, Field(description="Max output tokens (1-4096)")] = 1024,
        temperature: Annotated[float, Field(description="Sampling temperature 0.0-2.0")] = 0.7,
    ) -> dict:
        """Run an OpenAI chat completion."""
        if not prompt.strip():
            raise ValidationError("prompt must not be empty")
        if not 0.0 <= temperature <= 2.0:
            raise ValidationError("temperature must be between 0.0 and 2.0")
        messages: list[dict[str, str]] = []
        if system.strip():
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": _clamp_max_tokens(max_tokens),
            "temperature": temperature,
        }
        async with make_client("openai", timeout=120.0) as client:
            data = await _post(client, "/chat/completions", body)
        choices = data.get("choices") or []
        first = choices[0] if choices else {}
        message = first.get("message") or {}
        usage = data.get("usage") or {}
        return {
            "model": data.get("model"),
            "content": message.get("content"),
            "role": message.get("role"),
            "finish_reason": first.get("finish_reason"),
            "usage": {
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "total_tokens": usage.get("total_tokens"),
            },
        }

    @mcp.tool
    async def embed(
        input: Annotated[list[str], Field(description="Texts to embed (1-2048 items)")],
        model: Annotated[str, Field(description="Embedding model")] = "text-embedding-3-small",
    ) -> dict:
        """Generate embeddings for one or more texts."""
        if not input:
            raise ValidationError("input must not be empty")
        if len(input) > 2048:
            raise ValidationError("input length exceeds 2048 items")
        body = {"model": model, "input": input}
        async with make_client("openai", timeout=60.0) as client:
            data = await _post(client, "/embeddings", body)
        vectors = [(d.get("embedding") or []) for d in (data.get("data") or [])]
        usage = data.get("usage") or {}
        return {
            "model": data.get("model"),
            "count": len(vectors),
            "dimensions": len(vectors[0]) if vectors else 0,
            "embeddings": vectors,
            "usage": {
                "prompt_tokens": usage.get("prompt_tokens"),
                "total_tokens": usage.get("total_tokens"),
            },
        }

    @mcp.tool
    async def generate_image(
        prompt: Annotated[str, Field(description="Image description")],
        model: Annotated[str, Field(description="Image model")] = "dall-e-3",
        size: Annotated[str, Field(description="e.g. 1024x1024, 1792x1024, 1024x1792")] = "1024x1024",
        n: Annotated[int, Field(description="Number of images (1-4)")] = 1,
    ) -> dict:
        """Generate images via OpenAI image API."""
        if not prompt.strip():
            raise ValidationError("prompt must not be empty")
        n_clamped = max(1, min(4, n))
        body = {"model": model, "prompt": prompt, "size": size, "n": n_clamped}
        async with make_client("openai", timeout=120.0) as client:
            data = await _post(client, "/images/generations", body)
        images = [
            {"url": item.get("url"), "revised_prompt": item.get("revised_prompt")}
            for item in (data.get("data") or [])
        ]
        return {"model": model, "count": len(images), "images": images}
