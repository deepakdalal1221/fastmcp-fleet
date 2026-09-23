# Server Guide

How to add or complete a server in the platform.

## 1. Confirm the manifest

Every server needs an entry in `registry/servers/<id>.yaml`. All 171 targeted
servers already have manifests. To inspect one:

```bash
cat registry/servers/github.yaml
```

Manifest fields:

- `id` — kebab-case identifier, matches file name and the `servers/<id>/` dir
- `name` — human-readable, used as `FastMCP(name=...)`
- `category` — one of the taxonomy categories (see `registry/index.yaml`)
- `description` — one-line summary
- `auth.type` + `auth.env` — required credentials (see architecture.md)
- `transport` — always `streamable-http` unless there is a reason
- `port` — assigned in catalogue order; do not change by hand
- `image` — `yourorg/mcp-<id>:<version>`
- `version` — SemVer
- `tools` — declared tool names; contract tests fail if this list is empty
- `docs` — upstream API docs URL
- `status` — `pilot | planned | active | deprecated`

To add a brand-new server, extend `scripts/build_registry.py` and re-run it.
Never hand-edit port assignments.

## 2. Scaffold the server

```bash
uv run mcp-create <server_id>
```

This creates `servers/<id>/{__init__.py, main.py, tools.py}` with:

- `main.py` — canonical entry point: `load_manifest -> parse_runtime_args ->
  create_server -> register_tools -> run`
- `tools.py` — one `@mcp.tool async def <name>() -> dict` stub per tool
  listed in the manifest, each raising `NotImplementedError`

Use `--force` to regenerate (will overwrite).

## 3. Implement tools

Each tool lives in `tools.py` inside a `register_tools(mcp)` function.

```python
from typing import Annotated
from pydantic import Field
from mcp_common.errors import ValidationError, UpstreamError


def register_tools(mcp):
    @mcp.tool
    async def do_thing(
        arg: Annotated[str, Field(description="Human-facing description")],
    ) -> dict:
        """One-line tool description surfaced to the LLM client."""
        if not arg:
            raise ValidationError("arg must not be empty")
        return {"ok": True}
```

Rules:

- Every `@mcp.tool` gets a one-line docstring — FastMCP surfaces it as the
  MCP tool description.
- Every parameter uses `Annotated[T, Field(description=...)]` — surfaced as
  MCP parameter descriptions.
- Raise typed errors from `mcp_common.errors`; never return raw error dicts.
- Read secrets from `os.environ`; raise `ConfigError` if unset.
- Enforce hard limits on output size (see `servers/filesystem/tools.py` and
  `servers/fetch/tools.py` for the pattern).

## 4. Run locally

```bash
# stdio for direct LLM client integration
uv run python -m servers.github.main --transport stdio

# streamable-http on the manifest's assigned port
uv run python -m servers.github.main
```

Every server exposes a `health` tool automatically.

## 5. Add to the gateway

Edit the gateway's server list (env or CLI):

```bash
GATEWAY_SERVERS=fetch,filesystem,time,github uv run mcp-gateway
```

Or pass `--servers fetch,filesystem,time,github`. The gateway will mount each
server; tool names on the wire become `<server_id>_<tool_name>`.

## 6. Docker

Build the per-server image:

```bash
docker build -f docker/Dockerfile.server \
  --build-arg SERVER_ID=github \
  -t yourorg/mcp-github:0.1.0 .
```

Or run the whole stack:

```bash
docker compose -f deployment/compose/docker-compose.yml up
```

## 7. Tests

- **Contract**: `uv run pytest tests/contract/` — enforces registry invariants
  (ids unique, ports disjoint, auth taxonomy, image naming, tool list
  non-empty). Runs on every catalogue change.
- **Unit**: `uv run pytest tests/unit/` — per-server logic.
- **Integration**: `uv run pytest tests/integration/` — hit real upstreams
  (skip when env vars are absent).

## 8. Promote to `active`

When a server has real tool implementations, unit tests, and a green
integration run against a live upstream, change `status: planned` to
`status: active` in its manifest.
