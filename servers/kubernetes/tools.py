from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import NotFoundError
from mcp_common.http import is_offline
from pydantic import Field


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def get_pods(
        namespace: Annotated[str, Field(min_length=1, max_length=500)] = "default",
    ) -> dict:
        """get_pods for kubernetes. Offline: local_store."""
        if is_offline():
            items = local_store.list_all("kubernetes", "pods:" + namespace)
            return {"items": items, "count": len(items)}
        return {"note": "live mode not implemented in offline fleet"}

    @mcp.tool
    async def get_services(
        namespace: Annotated[str, Field(min_length=1, max_length=500)] = "default",
    ) -> dict:
        """get_services for kubernetes. Offline: local_store."""
        if is_offline():
            items = local_store.list_all("kubernetes", "services:" + namespace)
            return {"items": items, "count": len(items)}
        return {"note": "live mode not implemented in offline fleet"}

    @mcp.tool
    async def get_deployments(
        namespace: Annotated[str, Field(min_length=1, max_length=500)] = "default",
    ) -> dict:
        """get_deployments for kubernetes. Offline: local_store."""
        if is_offline():
            items = local_store.list_all("kubernetes", "deployments:" + namespace)
            return {"items": items, "count": len(items)}
        return {"note": "live mode not implemented in offline fleet"}

    @mcp.tool
    async def describe_pod(
        namespace: Annotated[str, Field(min_length=1, max_length=500)],
        name: Annotated[str, Field(min_length=1, max_length=500)],
    ) -> dict:
        """describe_pod for kubernetes. Offline: local_store."""
        if is_offline():
            rec = local_store.get("kubernetes", "pods:" + namespace, str(namespace))
            if not rec:
                raise NotFoundError(f"kubernetes record {namespace} not found")
            return rec
        return {"note": "live mode not implemented in offline fleet"}

    @mcp.tool
    async def logs(
        namespace: Annotated[str, Field(min_length=1, max_length=500)],
        pod: Annotated[str, Field(min_length=1, max_length=500)],
    ) -> dict:
        """logs for kubernetes. Offline: local_store."""
        if is_offline():
            rec = local_store.get("kubernetes", "logs:" + namespace, str(namespace))
            if not rec:
                raise NotFoundError(f"kubernetes record {namespace} not found")
            return rec
        return {"note": "live mode not implemented in offline fleet"}
