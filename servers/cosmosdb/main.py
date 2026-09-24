from __future__ import annotations

from mcp_common import create_server, parse_runtime_args, run

from .tools import register_tools

SERVER_ID = "cosmosdb"


def main() -> None:
    mcp, manifest, cfg = create_server(SERVER_ID)
    register_tools(mcp)
    args = parse_runtime_args(default_port=manifest.port)
    cfg = cfg.merge_cli(args)
    run(mcp, cfg)


if __name__ == "__main__":
    main()
