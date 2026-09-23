"""Offline HTTP transport that returns fixture JSON responses.

When MCP_OFFLINE=1, network calls are intercepted and answered from
`servers/<id>/fixtures/<slug>.json`. This lets every MCP server run
without any live third-party API, cloud account, or credential.

Fixture lookup order:
  1. `servers/<server_id>/fixtures/<METHOD>_<path-slug>.json`
  2. `servers/<server_id>/fixtures/<tool_name>.json` (if provided via header)
  3. `servers/<server_id>/fixtures/default.json`
  4. Synthetic `{"offline": true, ...}` payload
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import httpx


def _slug(method: str, path: str) -> str:
    body = re.sub(r"[^a-z0-9]+", "_", path.lower()).strip("_")
    return f"{method.lower()}_{body}"[:120] or f"{method.lower()}_root"


class OfflineTransport(httpx.AsyncBaseTransport):
    """httpx transport that returns fixture JSON instead of hitting the network."""

    def __init__(self, server_id: str, fixture_dir: str | Path | None = None) -> None:
        self.server_id = server_id
        if fixture_dir:
            self.dir = Path(fixture_dir)
        else:
            from mcp_common.registry import ROOT_DIR

            self.dir = ROOT_DIR / "servers" / server_id / "fixtures"

    def _lookup(self, request: httpx.Request) -> dict[str, Any]:
        slug = _slug(request.method, request.url.path)
        candidates = [
            self.dir / f"{slug}.json",
            self.dir / "default.json",
        ]
        for p in candidates:
            if p.is_file():
                try:
                    return json.loads(p.read_text())
                except json.JSONDecodeError:
                    continue
        return {
            "offline": True,
            "server_id": self.server_id,
            "method": request.method,
            "path": request.url.path,
            "note": (
                f"no fixture for {slug}; add "
                f"servers/{self.server_id}/fixtures/{slug}.json to customize"
            ),
        }

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        payload = self._lookup(request)
        return httpx.Response(
            status_code=200,
            headers={"content-type": "application/json"},
            content=json.dumps(payload).encode("utf-8"),
            request=request,
        )
