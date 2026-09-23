from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from pydantic import Field

from mcp_common.errors import AuthError, ConfigError, NotFoundError, RateLimitError, UpstreamError
from mcp_common.http import is_offline, make_client
from mcp_common import local_store

_BASE = "https://sourcegraph.com/.api"
_TIMEOUT = 30.0


def _token() -> str:
    v = os.environ.get("SOURCEGRAPH_TOKEN")
    if not v:
        raise ConfigError("SOURCEGRAPH_TOKEN is not set")
    return v


def _headers() -> dict[str, str]:
    return {"Authorization": f"token {_token()}", "Content-Type": "application/json", "Accept": "application/json"}


def _raise_for(r: httpx.Response) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"sourcegraph auth failed: HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("sourcegraph resource not found")
    if r.status_code == 429:
        raise RateLimitError("sourcegraph rate limited")
    if r.status_code >= 400:
        raise UpstreamError(f"sourcegraph HTTP {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def search(
        query: Annotated[str, Field(min_length=1, description="Sourcegraph search query, e.g. 'repo:^github.com/foo/bar$ func Foo'")],
    ) -> dict:
        """Run a Sourcegraph search via GraphQL and return top file hits."""
        gql = {
            "query": "query($q:String!){search(query:$q,version:V3){results{matchCount,results{__typename,...on FileMatch{repository{name},file{path,url}}}}}}",
            "variables": {"q": query},
        }
        async with make_client("sourcegraph", timeout=_TIMEOUT) as c:
            r = await c.post(f"{_BASE}/graphql", headers=_headers(), json=gql)
            _raise_for(r)
            data = r.json()
        s = ((data.get("data") or {}).get("search") or {}).get("results") or {}
        hits = []
        for h in (s.get("results") or [])[:20]:
            if h.get("__typename") == "FileMatch":
                hits.append({"repo": (h.get("repository") or {}).get("name"), "path": (h.get("file") or {}).get("path"), "url": (h.get("file") or {}).get("url")})
        return {"match_count": s.get("matchCount"), "hits": hits}

    @mcp.tool
    async def get_file(
        repo: Annotated[str, Field(min_length=1, description="repo name like github.com/foo/bar")],
        path: Annotated[str, Field(min_length=1, description="file path")],
    ) -> dict:
        """Read a file from a Sourcegraph-indexed repo."""
        gql = {
            "query": "query($r:String!,$p:String!){repository(name:$r){defaultBranch{target{commit{blob(path:$p){content}}}}}}",
            "variables": {"r": repo, "p": path},
        }
        async with make_client("sourcegraph", timeout=_TIMEOUT) as c:
            r = await c.post(f"{_BASE}/graphql", headers=_headers(), json=gql)
            _raise_for(r)
            data = r.json()
        content = (((((data.get("data") or {}).get("repository") or {}).get("defaultBranch") or {}).get("target") or {}).get("commit") or {}).get("blob") or {}
        text = content.get("content") or ""
        return {"repo": repo, "path": path, "size": len(text), "content_preview": text[:400]}

    @mcp.tool
    async def search_symbols(
        query: Annotated[str, Field(min_length=1, description="symbol query, prefixed by type:symbol in Sourcegraph")],
    ) -> dict:
        """Search for symbols with type:symbol filter."""
        return {"query": query, "note": "use search() with query 'type:symbol <name>' — Sourcegraph merges symbol results into search()"}
