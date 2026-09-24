from __future__ import annotations

from mcp_common import create_server, parse_runtime_args, run

from . import tools


def main() -> None:
    mcp, manifest, cfg = create_server("git-local")
    tools.register_tools(mcp)
    cfg = parse_runtime_args(manifest.port)
    run(mcp, cfg)


if __name__ == "__main__":
    main()
