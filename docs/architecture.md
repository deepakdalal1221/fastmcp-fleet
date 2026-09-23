# Architecture

## Overview

`fastmcp-platform` is a monorepo that packages 171 MCP servers behind a single
FastMCP gateway. Every server is an independently deployable process that
exposes tools over MCP; the gateway aggregates them into one endpoint for
clients.

```
+------------------+       +----------------------+
| MCP client (LLM) | <---> | gateway (:8000)      |
+------------------+       |  mounts N sub-servers|
                           +----------+-----------+
                                      |
             +------------------------+------------------------+
             |                        |                        |
     +---------------+       +---------------+         +---------------+
     | fetch (:8162) |       | github (:8001)|   ...   | postgres:8011 |
     +---------------+       +---------------+         +---------------+
```

## Layers

| Layer               | Path                          | Purpose                                          |
|---------------------|-------------------------------|--------------------------------------------------|
| Registry            | `registry/servers/*.yaml`     | One manifest per server; source of truth         |
| SDK                 | `packages/mcp_common/`        | Shared server bootstrap, auth, logging, errors   |
| Servers             | `servers/<id>/`               | Per-server tool implementations                  |
| Gateway             | `gateway/`                    | Aggregation + namespacing                        |
| Scaffolding         | `scripts/create_server.py`    | Generates a server skeleton from a manifest      |
| Docker              | `docker/`, `deployment/`      | Image template + compose                         |
| Tests               | `tests/{unit,contract,...}/`  | Contract enforces registry invariants            |

## Locked decisions

| # | Decision                                                                                      |
|---|-----------------------------------------------------------------------------------------------|
| 1 | Transport: `streamable-http` in production; `--transport=stdio` for local dev                 |
| 2 | One Docker image per server, named `yourorg/mcp-<name>:<version>`                             |
| 3 | Minimal gateway stub ships in Phase 5; expanded in Phase 16                                   |
| 4 | Registry split into per-server YAML files (`registry/servers/*.yaml`)                         |
| 5 | Python 3.12+ managed with `uv`                                                                |
| 6 | Tool namespacing via FastMCP's built-in mount separator (see below)                           |

## Tool namespacing

The original plan proposed dot-notation (`github.list_issues`). FastMCP's
`mount()` uses an underscore separator, so the effective wire name is
`<server_id>_<tool_name>` (e.g. `github_list_issues`). Clients discover tools
via `list_tools()`; do not hard-code the separator.

## Ports

Deterministic assignment in `registry/index.yaml`. Gateway owns 8000, servers
occupy 8001-8171 in catalogue order. Docker compose and Kubernetes manifests
read the manifest's `port` field; do not hard-code.

## Auth taxonomy

Manifest `auth.type` values in use today:

- `none`
- `api_key`
- `basic`
- `bearer_token`
- `aws_sig`
- `gcp_sa`
- `custom`

Required env vars are declared in `auth.env`. Servers read them via
`os.environ` and raise `mcp_common.errors.ConfigError` when unset. The
scaffolding generator drops in an auth import shim per type.

## Error hierarchy

All tool errors derive from `mcp_common.errors.McpError`:

| Class              | HTTP | Meaning                                |
|--------------------|------|----------------------------------------|
| `ValidationError`  | 400  | Bad input from the caller              |
| `AuthError`        | 401  | Missing/invalid credentials            |
| `NotFoundError`    | 404  | Resource does not exist                |
| `RateLimitError`   | 429  | Upstream throttled us                  |
| `ConfigError`      | 500  | Server misconfigured (missing env etc) |
| `UpstreamError`    | 502  | Upstream 5xx or network failure        |

## Observability

`mcp_common.logging.setup_logging` wires structlog with ISO timestamps and
contextvars. Every server logs `server.init`; every tool call is wrapped by
`TimingLoggingMiddleware`, emitting `tool.start`, `tool.end`, `tool.warning`
(handled `McpError`) or `tool.exception` (unhandled).

## Health

`mcp_common.health.register_health` mounts a `health` tool that returns
`{status, server_id, version, uptime_seconds}`. The gateway registers its own
`health` at the aggregate layer.

## Deployment shape

- **Local**: `make run-fetch`, `make run-gateway`, or `docker compose up`.
- **Production**: one container per server + one for the gateway. K8s
  manifests land in `deployment/helm/` in a later phase.
