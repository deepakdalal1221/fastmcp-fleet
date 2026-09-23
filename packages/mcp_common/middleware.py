from __future__ import annotations

import asyncio
import time
from typing import Any

from mcp_common.auth import verify_bearer
from mcp_common.errors import McpError, RateLimitError
from mcp_common.logging import get_logger

log = get_logger("mcp_common.middleware")


class TimingLoggingMiddleware:
    def __init__(self, server_id: str) -> None:
        self.server_id = server_id

    async def __call__(self, context: Any, call_next: Any) -> Any:
        started = time.perf_counter()
        tool_name = getattr(context, "tool_name", None) or getattr(context, "name", "unknown")
        log.info("tool.start", server=self.server_id, tool=tool_name)
        try:
            result = await call_next(context)
        except McpError as e:
            elapsed_ms = (time.perf_counter() - started) * 1000
            log.warning(
                "tool.error",
                server=self.server_id,
                tool=tool_name,
                code=e.code,
                message=e.message,
                elapsed_ms=round(elapsed_ms, 2),
            )
            raise
        except Exception as e:
            elapsed_ms = (time.perf_counter() - started) * 1000
            log.exception(
                "tool.exception",
                server=self.server_id,
                tool=tool_name,
                error=str(e),
                elapsed_ms=round(elapsed_ms, 2),
            )
            raise
        elapsed_ms = (time.perf_counter() - started) * 1000
        log.info(
            "tool.end",
            server=self.server_id,
            tool=tool_name,
            elapsed_ms=round(elapsed_ms, 2),
        )
        return result


class _TokenBucket:
    __slots__ = ("capacity", "refill_per_sec", "tokens", "last_refill")

    def __init__(self, capacity: float, refill_per_sec: float) -> None:
        self.capacity = capacity
        self.refill_per_sec = refill_per_sec
        self.tokens = capacity
        self.last_refill = time.monotonic()

    def try_consume(self, amount: float = 1.0) -> bool:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_per_sec)
        self.last_refill = now
        if self.tokens >= amount:
            self.tokens -= amount
            return True
        return False


class RateLimitMiddleware:
    def __init__(
        self,
        server_id: str,
        capacity: float = 60.0,
        refill_per_sec: float = 1.0,
        per_tool: bool = True,
    ) -> None:
        self.server_id = server_id
        self.capacity = capacity
        self.refill_per_sec = refill_per_sec
        self.per_tool = per_tool
        self._buckets: dict[str, _TokenBucket] = {}
        self._lock = asyncio.Lock()

    def _key(self, tool_name: str) -> str:
        return tool_name if self.per_tool else "*"

    async def _bucket_for(self, tool_name: str) -> _TokenBucket:
        key = self._key(tool_name)
        async with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = _TokenBucket(self.capacity, self.refill_per_sec)
                self._buckets[key] = bucket
            return bucket

    async def __call__(self, context: Any, call_next: Any) -> Any:
        tool_name = getattr(context, "tool_name", None) or getattr(context, "name", "unknown")
        bucket = await self._bucket_for(tool_name)
        if not bucket.try_consume():
            log.warning(
                "tool.rate_limited",
                server=self.server_id,
                tool=tool_name,
                capacity=self.capacity,
                refill_per_sec=self.refill_per_sec,
            )
            raise RateLimitError(
                f"Rate limit exceeded for tool '{tool_name}' "
                f"(capacity={self.capacity}, refill={self.refill_per_sec}/s)"
            )
        return await call_next(context)


class BearerAuthMiddleware:
    def __init__(self, server_id: str, expected_token: str) -> None:
        self.server_id = server_id
        self.expected_token = expected_token

    def _extract_headers(self, context: Any) -> dict[str, str]:
        for path in (
            ("fastmcp_context", "request_context", "request", "headers"),
            ("request_context", "request", "headers"),
            ("request", "headers"),
            ("headers",),
        ):
            node: Any = context
            for attr in path:
                node = getattr(node, attr, None)
                if node is None:
                    break
            if node is not None:
                try:
                    return {str(k).lower(): str(v) for k, v in dict(node).items()}
                except Exception:
                    continue
        return {}

    async def __call__(self, context: Any, call_next: Any) -> Any:
        if not self.expected_token:
            return await call_next(context)
        headers = self._extract_headers(context)
        presented = headers.get("authorization", "")
        verify_bearer(presented, self.expected_token)
        return await call_next(context)
