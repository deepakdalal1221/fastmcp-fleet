# Contributing to fastmcp-fleet

Thanks for your interest. Contributions welcome for new MCP servers, better fixtures, Local Store wiring for more mutating tools, and platform hardening.

## Setup

```bash
git clone https://github.com/deepakdalal1221/fastmcp-fleet.git
cd fastmcp-fleet
uv sync --extra all --extra dev
```

## Run the test suite

```bash
uv run python -m pytest tests/ -q
```

All 200 tests should pass.

## Add a new MCP server

1. Add an `Entry(...)` to the CATALOGUE list in `scripts/build_registry.py` (append at the end — port assignment is index-based).
2. Regenerate manifests: `uv run python scripts/build_registry.py`
3. Scaffold the server: `uv run mcp-create <id>`
4. Implement `servers/<id>/tools.py` following the canonical pattern in `servers/github/tools.py` or `servers/cloudflare/tools.py`:
   - `from mcp_common.http import is_offline, make_client`
   - `from mcp_common import local_store` (only if the server has mutating tools)
   - Every network call uses `make_client("<id>", timeout=_TIMEOUT)` so offline mode intercepts it
   - Every `_token()`/`_key()` helper raises `ConfigError` when its env var is missing
   - `_raise_for(r)` maps 401/403 → `AuthError`, 404 → `NotFoundError`, 429 → `RateLimitError`, else → `UpstreamError`
5. If a tool mutates state, wire it to `local_store` so subsequent read tools return locally-created entities. See `servers/github/tools.py::create_issue` for reference.
6. Add fixtures: `servers/<id>/fixtures/default.json` at minimum. For a specific tool, name the file after `{method}_{path-slug}.json`.
7. Promote the server: change `status: planned` to `status: active` in `registry/servers/<id>.yaml`.
8. Register it in the gateway: append its id to `GATEWAY_SERVERS` in `deployment/compose/docker-compose.yml`.
9. Add a trajectory test in `tests/trajectory/test_offline_chains.py` if the server has a create → read cycle.

## Commit conventions

Conventional commits: `feat(<scope>):`, `fix(<scope>):`, `chore:`, `docs:`, `test:`, `ci:`

## Code style

Ruff + mypy strict. Run `uv run ruff check .` and `uv run mypy .` before pushing.
