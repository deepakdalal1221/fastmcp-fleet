"""Shared httpx.AsyncClient factory that respects MCP_OFFLINE."""

from __future__ import annotations

import os

import httpx

from mcp_common.offline import OfflineTransport


def _offline_from_env() -> bool:
    return os.environ.get("MCP_OFFLINE", "").strip() in ("1", "true", "yes")


def make_client(server_id: str, timeout: float = 30.0, **kwargs) -> httpx.AsyncClient:
    """Build an httpx.AsyncClient.

    When MCP_OFFLINE=1, requests are handled by OfflineTransport instead of
    hitting the real network. Otherwise behaves like a normal AsyncClient.
    """
    if _offline_from_env():
        transport = OfflineTransport(server_id)
        return httpx.AsyncClient(transport=transport, timeout=timeout, **kwargs)
    return httpx.AsyncClient(timeout=timeout, **kwargs)


def is_offline() -> bool:
    """Return True when running in offline mode."""
    return _offline_from_env()


def get_random(server_id: str, seed: int | None = None):
    """Return a per-server seeded random.Random instance for deterministic mock variance."""
    import random as _r

    base = seed if seed is not None else int(os.environ.get("MCP_SEED", "42"))
    return _r.Random(base + hash(server_id))
