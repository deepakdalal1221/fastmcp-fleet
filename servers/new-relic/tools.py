from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from mcp_common.errors import AuthError, ConfigError, NotFoundError, RateLimitError, UpstreamError
from mcp_common.http import make_client
from pydantic import Field

_BASE = "https://api.newrelic.com/graphql"
_TIMEOUT = 30.0


def _api_key() -> str:
    v = os.environ.get("NEWRELIC_API_KEY")
    if not v:
        raise ConfigError("NEWRELIC_API_KEY is not set")
    return v


def _account() -> int:
    v = os.environ.get("NEWRELIC_ACCOUNT")
    if not v:
        raise ConfigError("NEWRELIC_ACCOUNT is not set")
    try:
        return int(v)
    except ValueError as e:
        raise ConfigError(f"NEWRELIC_ACCOUNT must be an integer: {v!r}") from e


def _headers() -> dict[str, str]:
    return {"API-Key": _api_key(), "Content-Type": "application/json"}


def _raise_for(r: httpx.Response) -> None:
    if r.status_code < 400:
        return
    if r.status_code in (401, 403):
        raise AuthError(f"new-relic auth failed: {r.text[:200]}")
    if r.status_code == 404:
        raise NotFoundError(f"new-relic not found: {r.text[:200]}")
    if r.status_code == 429:
        raise RateLimitError(f"new-relic rate-limited: {r.text[:200]}")
    raise UpstreamError(f"new-relic {r.status_code}: {r.text[:200]}")


async def _post_graphql(gql: str) -> dict:
    async with make_client("new-relic", timeout=_TIMEOUT) as client:
        r = await client.post(_BASE, headers=_headers(), json={"query": gql})
    _raise_for(r)
    body = r.json()
    if "errors" in body and body["errors"]:
        raise UpstreamError(f"new-relic graphql errors: {body['errors']}"[:400])
    return body.get("data", {})


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def nrql(
        query: Annotated[str, Field(description="NRQL query string")],
    ) -> dict:
        """Run an NRQL query against the configured New Relic account."""
        escaped = query.replace("\\", "\\\\").replace('"', '\\"')
        gql = (
            "{ actor { account(id: "
            + str(_account())
            + ') { nrql(query: "'
            + escaped
            + '") { results } } } }'
        )
        data = await _post_graphql(gql)
        results = data.get("actor", {}).get("account", {}).get("nrql", {}).get("results", [])
        return {"results": results[:500]}

    @mcp.tool
    async def list_alerts() -> dict:
        """List New Relic alert policies for the account."""
        gql = (
            "{ actor { account(id: "
            + str(_account())
            + ") { alerts { policiesSearch { policies { id name incidentPreference } } } } } }"
        )
        data = await _post_graphql(gql)
        policies = (
            data.get("actor", {})
            .get("account", {})
            .get("alerts", {})
            .get("policiesSearch", {})
            .get("policies", [])
        )
        return {"policies": policies}
