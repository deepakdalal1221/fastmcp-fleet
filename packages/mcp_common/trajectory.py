"""Optional trajectory recording — dump every MCP tool call to a JSONL file.

Enable by setting `MCP_RECORD_TRAJECTORY=<dir>` in the environment. Each server
process writes one line per tool call to `<dir>/<server_id>.jsonl`. Directory is
created if missing. If the env var is not set, the middleware is a no-op.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from mcp_common.logging import get_logger

log = get_logger("mcp_common.trajectory")


def _record_dir() -> Path | None:
    d = os.environ.get("MCP_RECORD_TRAJECTORY", "").strip()
    if not d:
        return None
    p = Path(d)
    p.mkdir(parents=True, exist_ok=True)
    return p


class TrajectoryMiddleware:
    """Middleware that appends {ts, tool, args_len, duration_ms, error?} per tool call."""

    def __init__(self, server_id: str) -> None:
        self.server_id = server_id
        self._dir = _record_dir()
        if self._dir:
            self._path = self._dir / f"{server_id}.jsonl"
        else:
            self._path = None

    async def __call__(self, context: Any, call_next: Any) -> Any:
        if self._path is None:
            return await call_next(context)
        started = time.perf_counter()
        tool_name = getattr(context, "tool_name", None) or getattr(context, "name", "unknown")
        entry: dict[str, Any] = {"ts": time.time(), "server": self.server_id, "tool": tool_name}
        try:
            result = await call_next(context)
        except Exception as exc:
            entry["duration_ms"] = round((time.perf_counter() - started) * 1000, 2)
            entry["error"] = f"{type(exc).__name__}: {exc}"
            self._append(entry)
            raise
        entry["duration_ms"] = round((time.perf_counter() - started) * 1000, 2)
        self._append(entry)
        return result

    def _append(self, entry: dict[str, Any]) -> None:
        try:
            with self._path.open("a") as f:
                f.write(json.dumps(entry, default=str) + "\n")
        except Exception as exc:
            log.warning("trajectory.write_failed", server=self.server_id, error=str(exc))
