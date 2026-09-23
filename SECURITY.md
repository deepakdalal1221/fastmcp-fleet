# Security Policy

## Supported versions

The `main` branch is the only supported version. Security patches are applied there.

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.

Report privately via one of these:

- GitHub Security Advisories: <https://github.com/deepakdalal1221/fastmcp-fleet/security/advisories/new>
- Email: `deepakdalal1221@users.noreply.github.com`

Include as much detail as possible: reproduction steps, affected version/SHA, and impact.

## Scope

This project runs mock MCP servers locally with fixture data and a per-server SQLite store. It is not intended for production API access. Vulnerabilities of interest include:

- Path traversal in the filesystem server or fixture lookup
- SQL injection into the Local Store
- Unauthorized network egress in "offline" mode
- Auth bypass in the gateway bearer-token middleware
- Container escape via docker-compose configuration

Third-party API keys should never leave the caller's environment. If you find code that accidentally logs or forwards credentials, please report it.
