"""Single-process aggregator: mount every implemented server into one FastMCP on :9000.

Walks servers/*/tools.py directly (not the registry). Skips servers whose module
fails to import or lacks register_tools.
"""

from __future__ import annotations

import argparse
import importlib
import os
import sys

from fastmcp import FastMCP
from mcp_common.logging import get_logger, setup_logging
from mcp_common.registry import ROOT_DIR


def build_all_in_one() -> FastMCP:
    setup_logging(
        level=os.environ.get("MCP_LOG_LEVEL", "INFO"), fmt=os.environ.get("MCP_LOG_FORMAT", "text")
    )
    log = get_logger("all_in_one")
    main = FastMCP(name="fastmcp-fleet-all-in-one")

    servers_dir = ROOT_DIR / "servers"
    if str(ROOT_DIR) not in sys.path:
        sys.path.insert(0, str(ROOT_DIR))

    mounted = 0
    skipped = 0
    for server_dir in sorted(servers_dir.iterdir()):
        if not server_dir.is_dir():
            continue
        tools_py = server_dir / "tools.py"
        if not tools_py.exists():
            continue
        sid = server_dir.name
        # Skip stub servers still using NotImplementedError
        if "NotImplementedError" in tools_py.read_text():
            skipped += 1
            continue
        try:
            mod = importlib.import_module(f"servers.{sid}.tools")
        except Exception as exc:
            log.warning("skip.import", server=sid, error=str(exc))
            skipped += 1
            continue
        if not hasattr(mod, "register_tools"):
            skipped += 1
            continue
        sub = FastMCP(name=sid)
        try:
            mod.register_tools(sub)
            main.mount(sub, sid.replace("-", "_"))
        except Exception as exc:
            log.warning("skip.mount", server=sid, error=str(exc))
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
    fleet = build_all_in_one()
    fleet.run(transport=args.transport, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
