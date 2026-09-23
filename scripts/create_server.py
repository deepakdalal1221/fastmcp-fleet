from __future__ import annotations

from pathlib import Path

import click
from mcp_common.registry import ServerManifest, load_manifest

_MAIN_TEMPLATE = """from __future__ import annotations

from mcp_common import create_server, load_manifest
from mcp_common.server import parse_runtime_args, run

from .tools import register_tools

SERVER_ID = "{server_id}"


def main() -> None:
    manifest = load_manifest(SERVER_ID)
    cfg = parse_runtime_args(default_port=manifest.port)
    mcp, _, _ = create_server(SERVER_ID, settings=cfg)
    register_tools(mcp)
    run(mcp, cfg)


if __name__ == "__main__":
    main()
"""

_TOOLS_HEADER = """from __future__ import annotations

from fastmcp import FastMCP

from mcp_common.errors import UpstreamError, ValidationError

{auth_line}

def register_tools(mcp: FastMCP) -> None:
"""

_TOOL_STUB = '''    @mcp.tool
    async def {tool_name}() -> dict:
        """{tool_name}: TODO — implement for {server_id}."""
        raise NotImplementedError("{server_id}.{tool_name} not implemented")

'''

_AUTH_LINES = {
    "none": "",
    "token": "from mcp_common.config import ServerSettings  # token auth: read secret from env",
    "bearer": "from mcp_common.config import ServerSettings  # bearer auth: read secret from env",
    "oauth": "from mcp_common.config import ServerSettings  # oauth: token exchange required",
    "connection_string": "from mcp_common.config import ServerSettings  # connection string: read DSN from env",
    "iam": "from mcp_common.config import ServerSettings  # IAM auth: use provider SDK default chain",
}


def _render_tools_file(manifest: ServerManifest) -> str:
    auth_line = _AUTH_LINES.get(manifest.auth.type, "")
    header = _TOOLS_HEADER.format(auth_line=auth_line).replace("\n\n\n", "\n\n")
    stubs = "".join(
        _TOOL_STUB.format(tool_name=name, server_id=manifest.id) for name in manifest.tools
    )
    if not stubs:
        stubs = "    pass\n"
    return header + stubs


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.argument("server_id")
@click.option("--force", is_flag=True, help="Overwrite existing server directory.")
def main(server_id: str, force: bool) -> None:
    """Scaffold a new MCP server from its registry manifest."""
    manifest = load_manifest(server_id)
    dest = _repo_root() / "servers" / server_id
    if dest.exists() and not force:
        raise click.ClickException(
            f"already exists: {dest.relative_to(_repo_root())} (use --force to overwrite)"
        )
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "__init__.py").write_text("", encoding="utf-8")
    (dest / "main.py").write_text(_MAIN_TEMPLATE.format(server_id=server_id), encoding="utf-8")
    (dest / "tools.py").write_text(_render_tools_file(manifest), encoding="utf-8")
    click.echo(
        f"scaffolded servers/{server_id}/ "
        f"(auth={manifest.auth.type}, tools={len(manifest.tools)}, port={manifest.port})"
    )


if __name__ == "__main__":
    main()
