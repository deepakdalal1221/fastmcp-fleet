from __future__ import annotations

import os
from typing import Annotated, Any

import httpx
from fastmcp import FastMCP
from pydantic import Field

from mcp_common.errors import (
    AuthError,
    ConfigError,
    NotFoundError,
    RateLimitError,
    UpstreamError,
    ValidationError,
)

_API_BASE = "https://discord.com/api/v10"
_MAX_LIMIT = 100


def _token() -> str:
    token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    if not token:
        raise ConfigError("DISCORD_BOT_TOKEN is not set")
    return token


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bot {_token()}",
        "Content-Type": "application/json",
        "User-Agent": "fastmcp-platform/discord (https://example.invalid, 0.1.0)",
    }


def _clamp_limit(n: int) -> int:
    if n < 1:
        return 1
    if n > _MAX_LIMIT:
        return _MAX_LIMIT
    return n


def _raise_for_status(response: httpx.Response) -> None:
    if response.status_code == 401:
        raise AuthError("Discord authentication failed")
    if response.status_code == 403:
        raise AuthError("Discord permission denied")
    if response.status_code == 404:
        raise NotFoundError("Discord resource not found")
    if response.status_code == 429:
        raise RateLimitError("Discord rate limit exceeded")
    if response.status_code >= 500:
        raise UpstreamError(f"Discord upstream error: HTTP {response.status_code}")
    if response.status_code >= 400:
        raise UpstreamError(
            f"Discord HTTP {response.status_code}: {response.text[:200]}"
        )


async def _get(client: httpx.AsyncClient, path: str, params: dict[str, Any] | None = None) -> Any:
    try:
        response = await client.get(f"{_API_BASE}{path}", params=params, headers=_headers())
    except httpx.RequestError as exc:
        raise UpstreamError(f"Discord request failed: {exc}") from exc
    _raise_for_status(response)
    return response.json()


async def _post(client: httpx.AsyncClient, path: str, body: dict[str, Any]) -> Any:
    try:
        response = await client.post(f"{_API_BASE}{path}", json=body, headers=_headers())
    except httpx.RequestError as exc:
        raise UpstreamError(f"Discord request failed: {exc}") from exc
    _raise_for_status(response)
    return response.json()


def _guild_slim(guild: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": guild.get("id"),
        "name": guild.get("name"),
        "owner": guild.get("owner"),
        "permissions": guild.get("permissions"),
        "features": guild.get("features"),
    }


def _channel_slim(channel: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": channel.get("id"),
        "name": channel.get("name"),
        "type": channel.get("type"),
        "guild_id": channel.get("guild_id"),
        "parent_id": channel.get("parent_id"),
        "topic": channel.get("topic"),
        "nsfw": channel.get("nsfw"),
        "position": channel.get("position"),
    }


def _message_slim(message: dict[str, Any]) -> dict[str, Any]:
    author = message.get("author") or {}
    return {
        "id": message.get("id"),
        "channel_id": message.get("channel_id"),
        "content": message.get("content"),
        "timestamp": message.get("timestamp"),
        "edited_timestamp": message.get("edited_timestamp"),
        "author": {
            "id": author.get("id"),
            "username": author.get("username"),
            "bot": author.get("bot"),
        },
    }


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_guilds(
        limit: Annotated[int, Field(description="Max guilds to return (1-100)")] = 100,
    ) -> dict:
        """List Discord guilds (servers) the bot is a member of."""
        params = {"limit": _clamp_limit(limit)}
        async with make_client("discord", timeout=30.0) as client:
            data = await _get(client, "/users/@me/guilds", params=params)
        guilds = [_guild_slim(g) for g in (data or [])]
        return {"guilds": guilds, "count": len(guilds)}

    @mcp.tool
    async def list_channels(
        guild_id: Annotated[str, Field(description="Discord guild (server) ID")],
    ) -> dict:
        """List channels within a Discord guild."""
        if not guild_id.strip():
            raise ValidationError("guild_id must not be empty")
        async with make_client("discord", timeout=30.0) as client:
            data = await _get(client, f"/guilds/{guild_id}/channels")
        channels = [_channel_slim(c) for c in (data or [])]
        return {"guild_id": guild_id, "channels": channels, "count": len(channels)}

    @mcp.tool
    async def post_message(
        channel_id: Annotated[str, Field(description="Discord channel ID")],
        content: Annotated[str, Field(description="Message content (max 2000 chars)")],
    ) -> dict:
        """Post a message to a Discord channel."""
        if not channel_id.strip():
            raise ValidationError("channel_id must not be empty")
        if not content.strip():
            raise ValidationError("content must not be empty")
        if len(content) > 2000:
            raise ValidationError("content exceeds 2000 character Discord limit")
        async with make_client("discord", timeout=30.0) as client:
            data = await _post(client, f"/channels/{channel_id}/messages", {"content": content})
        return _message_slim(data or {})
