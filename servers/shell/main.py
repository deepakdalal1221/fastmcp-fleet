from __future__ import annotations

from mcp_common import create_server, parse_runtime_args, run

from . import tools


def main() -> None:
    mcp, manifest, cfg = create_server("shell")
    tools.register_tools(mcp)
    cfg = parse_runtime_args(default_port=manifest.port).apply_overrides(cfg)
    run(mcp, cfg)


if __name__ == "__main__":
    main()
