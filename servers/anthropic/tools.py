from __future__ import annotations

import os
from typing import Annotated, Any

import httpx
from fastmcp import FastMCP
from mcp_common.errors import (
    AuthError,
    ConfigError,
    RateLimitError,
    UpstreamError,
    ValidationError,
)
from mcp_common.http import make_client
from pydantic import Field

_BASE_URL = "https://api.anthropic.com/v1"
_API_VERSION = "2023-06-01"
_TIMEOUT = 120.0
_MAX_TOKENS_CAP = 8192


def _api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        raise ConfigError("ANTHROPIC_API_KEY is not set")
    return key


def _headers() -> dict[str, str]:
    return {
        "x-api-key": _api_key(),
        "anthropic-version": _API_VERSION,
        "content-type": "application/json",
        "user-agent": "mcp-anthropic/0.1.0",
    }


def _raise_for_status(response: httpx.Response) -> None:
    status = response.status_code
    if status < 400:
        return
    body = response.text[:500]
    if status == 401:
        raise AuthError(f"Anthropic auth failed: {body}")
    if status == 403:
        raise AuthError(f"Anthropic forbidden: {body}")
    if status == 429:
        raise RateLimitError(f"Anthropic rate limited: {body}")
    if status >= 500:
        raise UpstreamError(f"Anthropic upstream {status}: {body}")
    raise UpstreamError(f"Anthropic {status}: {body}")


def _clamp_max_tokens(n: int) -> int:
    if n < 1:
        return 1
    if n > _MAX_TOKENS_CAP:
        return _MAX_TOKENS_CAP
    return n


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def messages(
        prompt: Annotated[str, Field(description="User message content.")],
        model: Annotated[str, Field(description="Anthropic model id.")] = "claude-sonnet-4-6",
        system: Annotated[str, Field(description="Optional system prompt.")] = "",
        max_tokens: Annotated[int, Field(description="Max output tokens (1-8192).")] = 1024,
        temperature: Annotated[float, Field(description="Sampling temperature 0.0-1.0.")] = 0.7,
    ) -> dict[str, Any]:
        """Call Anthropic Messages API for a single-turn chat completion."""
        if not prompt.strip():
            raise ValidationError("prompt must not be empty")
        if temperature < 0.0 or temperature > 1.0:
            raise ValidationError("temperature must be between 0.0 and 1.0")

        body: dict[str, Any] = {
            "model": model,
            "max_tokens": _clamp_max_tokens(max_tokens),
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system.strip():
            body["system"] = system

        try:
            async with make_client("anthropic", timeout=_TIMEOUT) as client:
                response = await client.post(
                    f"{_BASE_URL}/messages",
                    headers=_headers(),
                    json=body,
                )
        except httpx.RequestError as exc:
            raise UpstreamError(f"Anthropic request failed: {exc}") from exc

        _raise_for_status(response)
        payload = response.json()

        content_blocks = payload.get("content", [])
        text = "".join(
            block.get("text", "") for block in content_blocks if block.get("type") == "text"
        )

        usage = payload.get("usage", {})
        return {
            "model": payload.get("model", model),
            "content": text,
            "stop_reason": payload.get("stop_reason"),
            "usage": {
                "input_tokens": usage.get("input_tokens"),
                "output_tokens": usage.get("output_tokens"),
            },
        }
