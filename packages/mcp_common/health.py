from __future__ import annotations

import time
from typing import Any

_STARTED_AT = time.time()


def build_health_payload(server_id: str, version: str) -> dict[str, Any]:
    return {
        "status": "ok",
        "server_id": server_id,
        "version": version,
        "uptime_seconds": round(time.time() - _STARTED_AT, 3),
    }


def register_health(mcp: Any, server_id: str, version: str) -> None:
    @mcp.tool
    def health() -> dict[str, Any]:
        """Return server health, version, and uptime."""
        return build_health_payload(server_id, version)
