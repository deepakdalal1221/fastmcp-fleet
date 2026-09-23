from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import AuthError, ConfigError, NotFoundError, RateLimitError, UpstreamError
from mcp_common.http import is_offline, make_client
from pydantic import Field

_BASE = "https://api.cohere.com/v1"
_TIMEOUT = 30.0


def _token() -> str:
    v = os.environ.get("COHERE_API_KEY")
    if not v:
        raise ConfigError("COHERE_API_KEY is not set")
    return v


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_token()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _raise_for(r: httpx.Response) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"cohere auth failed: HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("cohere resource not found")
    if r.status_code == 429:
        raise RateLimitError("cohere rate limited")
    if r.status_code >= 400:
        raise UpstreamError(f"cohere HTTP {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def chat(
        message: Annotated[str, Field(min_length=1, description="user message")],
        model: Annotated[str, Field(description="Cohere model")] = "command-r",
        temperature: Annotated[float, Field(ge=0.0, le=5.0)] = 0.3,
    ) -> dict:
        """Chat with a Cohere command model."""
        body = {"model": model, "message": message, "temperature": temperature}
        async with make_client("cohere", timeout=60.0) as c:
            r = await c.post(f"{_BASE}/chat", headers=_headers(), json=body)
            _raise_for(r)
            data = r.json()
        return {
            "text": data.get("text", ""),
            "model": model,
            "finish_reason": data.get("finish_reason"),
            "tokens": {
                "input": ((data.get("meta") or {}).get("tokens") or {}).get("input_tokens"),
                "output": ((data.get("meta") or {}).get("tokens") or {}).get("output_tokens"),
            },
        }

    @mcp.tool
    async def embed(
        texts: Annotated[list[str], Field(description="one or more texts to embed")],
        model: Annotated[str, Field(description="embedding model")] = "embed-english-v3.0",
        input_type: Annotated[
            str, Field(description="search_document | search_query | classification | clustering")
        ] = "search_document",
    ) -> dict:
        """Generate Cohere embeddings."""
        body = {"model": model, "texts": texts, "input_type": input_type}
        async with make_client("cohere", timeout=60.0) as c:
            r = await c.post(f"{_BASE}/embed", headers=_headers(), json=body)
            _raise_for(r)
            data = r.json()
        embs = data.get("embeddings") or []
        return {"model": model, "count": len(embs), "dimensions": len(embs[0]) if embs else 0}

    @mcp.tool
    async def rerank(
        query: Annotated[str, Field(min_length=1, description="query text")],
        documents: Annotated[list[str], Field(description="candidate documents to rank")],
        top_n: Annotated[int, Field(ge=1, le=100)] = 5,
        model: Annotated[str, Field(description="rerank model")] = "rerank-english-v3.0",
    ) -> dict:
        """Rerank documents against a query."""
        body = {"model": model, "query": query, "documents": documents, "top_n": top_n}
        async with make_client("cohere", timeout=60.0) as c:
            r = await c.post(f"{_BASE}/rerank", headers=_headers(), json=body)
            _raise_for(r)
            data = r.json()
        return {
            "results": [
                {"index": rr.get("index"), "relevance_score": rr.get("relevance_score")}
                for rr in data.get("results", [])
            ]
        }
