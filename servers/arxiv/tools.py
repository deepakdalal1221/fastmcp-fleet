from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import NotFoundError, UpstreamError
from mcp_common.http import is_offline, make_client
from pydantic import Field

_BASE = "http://export.arxiv.org/api/query"
_TIMEOUT = 30.0


def _raise_for(r) -> None:
    if r.status_code == 404:
        raise NotFoundError("arxiv paper not found")
    if r.status_code >= 400:
        raise UpstreamError(f"arxiv HTTP {r.status_code}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def search(
        query: Annotated[str, Field(min_length=1, max_length=200)],
        limit: Annotated[int, Field(ge=1, le=50)] = 10,
    ) -> dict:
        """Search arXiv papers by keyword. Offline: reads local_store."""
        if is_offline():
            hits = [
                p
                for p in local_store.list_all("arxiv", "papers")
                if query.lower() in p.get("title", "").lower()
            ]
            return {"query": query, "results": hits[:limit], "count": len(hits)}
        async with make_client("arxiv", timeout=_TIMEOUT) as c:
            r = await c.get(_BASE, params={"search_query": f"all:{query}", "max_results": limit})
            _raise_for(r)
        return {"query": query, "raw_atom": r.text[:2000]}

    @mcp.tool
    async def get_paper(
        paper_id: Annotated[str, Field(min_length=1, max_length=64)],
    ) -> dict:
        """Fetch metadata for an arXiv paper by id (e.g. 2401.12345). Offline: local_store lookup."""
        if is_offline():
            rec = local_store.get("arxiv", "papers", paper_id)
            if not rec:
                raise NotFoundError(f"arxiv paper {paper_id} not in offline store")
            return rec
        async with make_client("arxiv", timeout=_TIMEOUT) as c:
            r = await c.get(_BASE, params={"id_list": paper_id})
            _raise_for(r)
        return {"paper_id": paper_id, "raw_atom": r.text[:2000]}
