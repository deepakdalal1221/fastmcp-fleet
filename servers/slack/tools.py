from __future__ import annotations

import os
from typing import Annotated, Any

import httpx
from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import AuthError, ConfigError, RateLimitError, UpstreamError, ValidationError
from mcp_common.http import is_offline, make_client
from pydantic import Field

_API_BASE = "https://slack.com/api"
_MAX_LIMIT = 200


def _token() -> str:
    token = os.environ.get("SLACK_BOT_TOKEN", "").strip()
    if not token:
        raise ConfigError("SLACK_BOT_TOKEN is not set")
    return token


def _headers(content_type: str = "application/json; charset=utf-8") -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_token()}",
        "Content-Type": content_type,
        "User-Agent": "fastmcp-platform/slack",
    }


def _clamp_limit(n: int) -> int:
    if n < 1:
        return 1
    if n > _MAX_LIMIT:
        return _MAX_LIMIT
    return n


def _raise_for_status(response: httpx.Response) -> None:
    if response.status_code == 401:
        raise AuthError("Slack authentication failed")
    if response.status_code == 429:
        raise RateLimitError("Slack rate limit exceeded")
    if response.status_code >= 500:
        raise UpstreamError(f"Slack upstream error: HTTP {response.status_code}")
    if response.status_code >= 400:
        raise UpstreamError(f"Slack HTTP {response.status_code}: {response.text[:200]}")


def _raise_for_slack_error(payload: dict[str, Any]) -> None:
    if payload.get("ok"):
        return
    err = str(payload.get("error", "unknown_error"))
    if err in {"invalid_auth", "not_authed", "token_revoked", "token_expired"}:
        raise AuthError(f"Slack auth error: {err}")
    if err in {"ratelimited", "rate_limited"}:
        raise RateLimitError("Slack rate limit exceeded")
    if err in {"missing_scope", "not_allowed_token_type"}:
        raise AuthError(f"Slack permission error: {err}")
    raise UpstreamError(f"Slack API error: {err}")


async def _get(client: httpx.AsyncClient, path: str, params: dict[str, Any]) -> dict[str, Any]:
    try:
        response = await client.get(f"{_API_BASE}/{path}", params=params, headers=_headers())
    except httpx.RequestError as exc:
        raise UpstreamError(f"Slack request failed: {exc}") from exc
    _raise_for_status(response)
    payload = response.json()
    _raise_for_slack_error(payload)
    return payload


async def _post_json(client: httpx.AsyncClient, path: str, body: dict[str, Any]) -> dict[str, Any]:
    try:
        response = await client.post(f"{_API_BASE}/{path}", json=body, headers=_headers())
    except httpx.RequestError as exc:
        raise UpstreamError(f"Slack request failed: {exc}") from exc
    _raise_for_status(response)
    payload = response.json()
    _raise_for_slack_error(payload)
    return payload


def _channel_slim(channel: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": channel.get("id"),
        "name": channel.get("name"),
        "is_private": channel.get("is_private"),
        "is_archived": channel.get("is_archived"),
        "num_members": channel.get("num_members"),
        "topic": (channel.get("topic") or {}).get("value"),
        "purpose": (channel.get("purpose") or {}).get("value"),
    }


def _user_slim(user: dict[str, Any]) -> dict[str, Any]:
    profile = user.get("profile") or {}
    return {
        "id": user.get("id"),
        "name": user.get("name"),
        "real_name": user.get("real_name") or profile.get("real_name"),
        "email": profile.get("email"),
        "is_bot": user.get("is_bot"),
        "deleted": user.get("deleted"),
    }


def _message_slim(message: dict[str, Any]) -> dict[str, Any]:
    return {
        "ts": message.get("ts"),
        "user": message.get("user"),
        "text": message.get("text"),
        "type": message.get("type"),
        "subtype": message.get("subtype"),
        "thread_ts": message.get("thread_ts"),
        "reply_count": message.get("reply_count"),
    }


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_channels(
        types: Annotated[
            str,
            Field(description="Comma-separated: public_channel,private_channel,mpim,im"),
        ] = "public_channel",
        exclude_archived: Annotated[bool, Field(description="Skip archived channels")] = True,
        limit: Annotated[int, Field(description="Max channels to return (1-200)")] = 100,
    ) -> dict:
        """List Slack conversations (channels) visible to the bot."""
        params = {
            "types": types,
            "exclude_archived": "true" if exclude_archived else "false",
            "limit": _clamp_limit(limit),
        }
        async with make_client("slack", timeout=30.0) as client:
            payload = await _get(client, "conversations.list", params)
        channels = [_channel_slim(c) for c in payload.get("channels", [])]
        return {"channels": channels, "count": len(channels)}

    @mcp.tool
    async def post_message(
        channel: Annotated[str, Field(min_length=1, description="channel id or name")],
        text: Annotated[str, Field(min_length=1, description="message text")],
        thread_ts: Annotated[str | None, Field(description="parent thread ts")] = None,
    ) -> dict:
        """Post a Slack message. Offline mode persists to local state."""
        if is_offline():
            col = f"messages:{channel}"
            n = local_store.next_id("slack", col)
            ts = f"{1700000000 + n}.{n:06d}"
            msg = {
                "ts": ts,
                "channel": channel,
                "text": text,
                "thread_ts": thread_ts,
                "user": "U_OFFLINE",
            }
            await local_store.put("slack", col, ts, msg)
            return {"ok": True, "channel": channel, "ts": ts, "message": {"text": text}}
        payload = {"channel": channel, "text": text}
        if thread_ts:
            payload["thread_ts"] = thread_ts
        async with make_client("slack", timeout=_TIMEOUT) as c:
            r = await c.post(f"{_BASE}/chat.postMessage", headers=_headers(), json=payload)
            _raise_for(r)
            j = r.json()
        if not j.get("ok"):
            raise UpstreamError(f"slack error: {j.get('error')}")
        return {
            "ok": True,
            "channel": j.get("channel"),
            "ts": j.get("ts"),
            "message": j.get("message"),
        }

    @mcp.tool
    async def list_users(
        limit: Annotated[int, Field(description="Max users to return (1-200)")] = 100,
    ) -> dict:
        """List Slack workspace users."""
        params = {"limit": _clamp_limit(limit)}
        async with make_client("slack", timeout=30.0) as client:
            payload = await _get(client, "users.list", params)
        members = [_user_slim(u) for u in payload.get("members", [])]
        return {"users": members, "count": len(members)}

    @mcp.tool
    async def get_conversation(
        channel: Annotated[str, Field(min_length=1, description="channel id or name")],
        limit: Annotated[int, Field(ge=1, le=100)] = 20,
    ) -> dict:
        """Fetch Slack channel messages. Offline mode returns locally-posted messages."""
        if is_offline():
            stored = await local_store.list_all("slack", f"messages:{channel}")
            msgs = [row["value"] for row in stored][:limit]
            return {
                "messages": [{"ts": m["ts"], "user": m["user"], "text": m["text"]} for m in msgs]
            }
        async with make_client("slack", timeout=_TIMEOUT) as c:
            r = await c.get(
                f"{_BASE}/conversations.history",
                headers=_headers(),
                params={"channel": channel, "limit": limit},
            )
            _raise_for(r)
            j = r.json()
        if not j.get("ok"):
            raise UpstreamError(f"slack error: {j.get('error')}")
        return {
            "messages": [
                {"ts": m["ts"], "user": m.get("user"), "text": m.get("text", "")}
                for m in j.get("messages", [])
            ]
        }

    @mcp.tool
    async def edit_message(
        channel: Annotated[str, Field(min_length=1)],
        ts: Annotated[str, Field(min_length=1, description="message timestamp id")],
        text: Annotated[str, Field(min_length=1)],
    ) -> dict:
        """Edit a Slack message."""
        if is_offline():
            existing = await local_store.get("slack", f"messages:{channel}", ts)
            if not existing:
                raise NotFoundError(f"message {ts} not found")
            existing["text"] = text
            existing["edited"] = True
            await local_store.put("slack", f"messages:{channel}", ts, existing)
            return existing
        async with make_client("slack", timeout=_TIMEOUT) as c:
            r = await c.post(
                f"{_BASE}/chat.update",
                headers=_headers(),
                json={"channel": channel, "ts": ts, "text": text},
            )
            _raise_for(r)
        return r.json()

    @mcp.tool
    async def delete_message(
        channel: Annotated[str, Field(min_length=1)],
        ts: Annotated[str, Field(min_length=1, description="message timestamp id")],
    ) -> dict:
        """Delete a Slack message."""
        if is_offline():
            ok = await local_store.delete("slack", f"messages:{channel}", ts)
            return {"deleted": ok, "ts": ts}
        async with make_client("slack", timeout=_TIMEOUT) as c:
            r = await c.post(
                f"{_BASE}/chat.delete", headers=_headers(), json={"channel": channel, "ts": ts}
            )
            _raise_for(r)
        return {"deleted": True, "ts": ts}
