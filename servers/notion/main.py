from __future__ import annotations

from mcp_common import create_server, load_manifest
from mcp_common.server import parse_runtime_args, run

from .tools import register_tools

SERVER_ID = "notion"


def main() -> None:
    manifest = load_manifest(SERVER_ID)
    cfg = parse_runtime_args(default_port=manifest.port)
    mcp, _, _ = create_server(SERVER_ID, settings=cfg)
    register_tools(mcp)
    run(mcp, cfg)


if __name__ == "__main__":
    main()
