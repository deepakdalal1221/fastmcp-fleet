"""Single-process aggregator: mount every active server into one FastMCP on :9000.

Boots the entire fleet in one Python process for fast local development.
Skips servers whose manifest is not active or whose import fails.
"""

from __future__ import annotations

import argparse
import importlib
import os

from fastmcp import FastMCP
from mcp_common.logging import get_logger, setup_logging
from mcp_common.registry import load_catalogue


def build_all_in_one(only_active: bool = True) -> FastMCP:
    setup_logging(
        level=os.environ.get("MCP_LOG_LEVEL", "INFO"), fmt=os.environ.get("MCP_LOG_FORMAT", "text")
    )
    log = get_logger("all_in_one")
    main = FastMCP(name="fastmcp-fleet-all-in-one")

    mounted = 0
    skipped = 0
    for manifest in load_catalogue():
        if only_active and manifest.status != "active":
            continue
        try:
            mod = importlib.import_module(f"servers.{manifest.id}.tools")
        except Exception as exc:
            log.warning("skip.import", server=manifest.id, error=str(exc))
            skipped += 1
            continue
        sub = FastMCP(name=manifest.name)
        try:
            mod.register_tools(sub)
        except Exception as exc:
            log.warning("skip.register", server=manifest.id, error=str(exc))
            skipped += 1
            continue
        try:
            main.mount(sub, namespace=manifest.id.replace("-", "_"))
        except Exception as exc:
            log.warning("skip.mount", server=manifest.id, error=str(exc))
            skipped += 1
            continue
        mounted += 1

    log.info("all_in_one.ready", mounted=mounted, skipped=skipped)
    return main


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.environ.get("MCP_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("MCP_PORT", "9000")))
    parser.add_argument("--transport", default=os.environ.get("MCP_TRANSPORT", "streamable-http"))
    args = parser.parse_args()

    os.environ.setdefault("MCP_OFFLINE", "1")
    fleet = build_all_in_one(only_active=True)
    fleet.run(transport=args.transport, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
