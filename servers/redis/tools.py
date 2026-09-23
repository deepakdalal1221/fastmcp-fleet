from __future__ import annotations

import os
from typing import Annotated, Any

from mcp_common.errors import ConfigError, UpstreamError, ValidationError
from pydantic import Field

try:
    import redis.asyncio as aioredis
except ImportError:
    aioredis = None

_MAX_KEYS = 500


def _url() -> str:
    raw = os.environ.get("REDIS_URL", "").strip()
    if not raw:
        raise ConfigError("REDIS_URL is not set")
    return raw


def _client():
    if aioredis is None:
        raise ConfigError("redis is not installed; add extras=[db]")
    return aioredis.from_url(_url(), decode_responses=True)


def register_tools(mcp) -> None:
    @mcp.tool
    async def get(
        key: Annotated[str, Field(description="Redis key")],
    ) -> dict:
        """Return the string value at key, or null if missing."""
        if not key:
            raise ValidationError("key must not be empty")
        client = _client()
        try:
            value = await client.get(key)
        except Exception as exc:
            raise UpstreamError(f"redis GET failed: {exc}") from exc
        finally:
            await client.close()
        return {"key": key, "value": value}

    @mcp.tool
    async def set(
        key: Annotated[str, Field(description="Redis key")],
        value: Annotated[str, Field(description="Value to store")],
        ttl_seconds: Annotated[int | None, Field(description="Optional TTL in seconds")] = None,
    ) -> dict:
        """Set a string value at key, optionally with TTL."""
        if not key:
            raise ValidationError("key must not be empty")
        client = _client()
        try:
            await client.set(key, value, ex=ttl_seconds)
        except Exception as exc:
            raise UpstreamError(f"redis SET failed: {exc}") from exc
        finally:
            await client.close()
        return {"key": key, "ok": True}

    @mcp.tool
    async def delete(
        key: Annotated[str, Field(description="Redis key to delete")],
    ) -> dict:
        """Delete a key. Returns number of keys removed (0 or 1)."""
        if not key:
            raise ValidationError("key must not be empty")
        client = _client()
        try:
            count = await client.delete(key)
        except Exception as exc:
            raise UpstreamError(f"redis DEL failed: {exc}") from exc
        finally:
            await client.close()
        return {"key": key, "removed": int(count)}

    @mcp.tool
    async def keys(
        pattern: Annotated[str, Field(description="Glob-style pattern (e.g. user:*)")] = "*",
    ) -> dict:
        """Scan keys matching pattern (capped at 500)."""
        client = _client()
        found: list[str] = []
        try:
            async for k in client.scan_iter(match=pattern, count=200):
                found.append(k)
                if len(found) >= _MAX_KEYS:
                    break
        except Exception as exc:
            raise UpstreamError(f"redis SCAN failed: {exc}") from exc
        finally:
            await client.close()
        return {"pattern": pattern, "keys": found, "truncated": len(found) >= _MAX_KEYS}

    @mcp.tool
    async def hget(
        key: Annotated[str, Field(description="Hash key")],
        field: Annotated[str, Field(description="Field within the hash")],
    ) -> dict:
        """Return a single field from a hash."""
        if not key or not field:
            raise ValidationError("key and field must not be empty")
        client = _client()
        try:
            value = await client.hget(key, field)
        except Exception as exc:
            raise UpstreamError(f"redis HGET failed: {exc}") from exc
        finally:
            await client.close()
        return {"key": key, "field": field, "value": value}

    @mcp.tool
    async def hset(
        key: Annotated[str, Field(description="Hash key")],
        field: Annotated[str, Field(description="Field within the hash")],
        value: Annotated[str, Field(description="Value to store")],
    ) -> dict:
        """Set a single field on a hash."""
        if not key or not field:
            raise ValidationError("key and field must not be empty")
        client = _client()
        try:
            added = await client.hset(key, field, value)
        except Exception as exc:
            raise UpstreamError(f"redis HSET failed: {exc}") from exc
        finally:
            await client.close()
        return {"key": key, "field": field, "added": int(added)}
