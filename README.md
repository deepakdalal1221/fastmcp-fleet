# FastMCP Platform

Production-grade platform hosting **171 MCP servers** built on [FastMCP](https://gofastmcp.com), unified by a shared SDK (`mcp_common`), a routing gateway, and a single-image-per-server deployment story.

## Layout

```
fastmcp-platform/
├── packages/mcp_common/   # shared SDK: server bootstrap, config, auth, logging, errors, health, middleware, testing
├── servers/               # 171 MCP servers (one directory per server)
├── gateway/               # aggregation gateway (mounts all servers, namespaced tools)
├── registry/servers/      # per-server YAML manifests (single source of truth)
├── scripts/               # scaffolding + operational scripts
├── tests/                 # unit / integration / contract / docker / trajectory
├── deployment/            # docker, compose, helm, k8s
└── docs/
```

## Key decisions (locked)

| # | Decision | Value |
|---|----------|-------|
| 1 | Transport | `streamable-http` primary, `--transport=stdio` flag for local dev |
| 2 | Docker | One image per server: `yourorg/mcp-<name>:<version>` |
| 3 | Gateway | Minimal stub from Phase 5 (pass-through + namespacing) |
| 4 | Tool namespacing | `<server_id>.<tool_name>` dot-notation |
| 5 | Registry format | Split into `registry/servers/*.yaml` — one file per server |
| 6 | Python | `uv` + Python 3.12+ |

## Quick start

```bash
uv sync --all-extras
uv run mcp-create --name my-server        # scaffold a new server
uv run python -m servers.fetch            # run the fetch pilot
uv run mcp-gateway                        # run the aggregation gateway
uv run pytest -m unit                     # run unit tests
```

## Server catalogue

171 servers across 16 domains. See `registry/servers/*.yaml` for the authoritative list.

## Pilot servers (Phase 5)

`fetch`, `filesystem`, `time`, `github`, `postgres` — each demonstrates one pattern (HTTP, local I/O, trivial, REST+auth, DB pool).
