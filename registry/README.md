# Server Registry

Each server has its own manifest under `registry/servers/<id>.yaml`. This is the **single source of truth** for the platform: the scaffolder, gateway, compose generator, and Helm chart all read from here.

Split-file format was chosen deliberately to avoid merge conflicts at 171 entries.

## Schema

```yaml
id: string                # unique lowercase identifier (matches file name and dir under servers/)
name: string              # human-readable name
category: string          # one of: development, database, cloud, devops, communication,
                          #   project-management, productivity, storage, search, browser,
                          #   monitoring, security, ai-ml, data-platform, business, utility
description: string       # one-line purpose
auth:
  type: string            # none | api_key | bearer_token | oauth2 | basic | aws_sig | gcp_sa | custom
  env: string | list      # environment variable(s) providing credentials (empty if type=none)
transport: string         # streamable-http (default) | stdio (local-only)
port: int                 # HTTP port assignment (unique across catalogue for compose)
image: string             # container image reference (without tag)
version: string           # semver of the server
tools: list[string]       # planned tool names (namespaced as <id>.<tool> at gateway)
docs: string              # upstream reference URL
maintainers: list[string] # owner tag(s)
status: string            # planned | pilot | active | deprecated
```

## Load the catalogue programmatically

```python
from mcp_common.registry import load_catalogue

catalogue = load_catalogue()  # list[ServerManifest]
```
