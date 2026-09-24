from __future__ import annotations

import os
from typing import Annotated

from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import AuthError, ConfigError, NotFoundError, UpstreamError
from mcp_common.http import is_offline, make_client
from pydantic import Field

_TIMEOUT = 30.0


def _account() -> str:
    v = os.environ.get("AZURE_STORAGE_ACCOUNT")
    if not v:
        raise ConfigError("AZURE_STORAGE_ACCOUNT is not set")
    return v


def _key() -> str:
    v = os.environ.get("AZURE_STORAGE_KEY")
    if not v:
        raise ConfigError("AZURE_STORAGE_KEY is not set")
    return v


def _base() -> str:
    return f"https://{_account()}.blob.core.windows.net"


def _headers() -> dict[str, str]:
    return {"x-ms-version": "2023-11-03", "Authorization": f"SharedKey {_account()}:{_key()}"}


def _raise_for(r) -> None:
    if r.status_code in (401, 403):
        raise AuthError(f"azure-blob HTTP {r.status_code}")
    if r.status_code == 404:
        raise NotFoundError("azure-blob resource not found")
    if r.status_code >= 400:
        raise UpstreamError(f"azure-blob HTTP {r.status_code}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_containers() -> dict:
        """List Azure Blob storage containers. Offline: reads local_store."""
        if is_offline():
            cs = local_store.list_all("azure-blob", "containers")
            return {"containers": cs, "count": len(cs)}
        async with make_client("azure-blob", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_base()}/?comp=list", headers=_headers())
            _raise_for(r)
        return {"raw_xml": r.text[:2000]}

    @mcp.tool
    async def list_blobs(
        container: Annotated[str, Field(min_length=1)],
    ) -> dict:
        """List blobs in a container. Offline: reads local_store."""
        if is_offline():
            blobs = local_store.list_all("azure-blob", f"blobs:{container}")
            return {"container": container, "blobs": blobs, "count": len(blobs)}
        async with make_client("azure-blob", timeout=_TIMEOUT) as c:
            r = await c.get(
                f"{_base()}/{container}?restype=container&comp=list", headers=_headers()
            )
            _raise_for(r)
        return {"container": container, "raw_xml": r.text[:2000]}

    @mcp.tool
    async def get_blob(
        container: Annotated[str, Field(min_length=1)],
        blob: Annotated[str, Field(min_length=1)],
    ) -> dict:
        """Fetch a blob's metadata + content preview. Offline: local_store lookup."""
        if is_offline():
            rec = local_store.get("azure-blob", f"blobs:{container}", blob)
            if not rec:
                raise NotFoundError(f"blob {blob} in {container} not in offline store")
            return rec
        async with make_client("azure-blob", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_base()}/{container}/{blob}", headers=_headers())
            _raise_for(r)
        return {
            "container": container,
            "blob": blob,
            "size": len(r.content),
            "content_preview": r.text[:400] if isinstance(r.text, str) else "",
        }

    @mcp.tool
    async def upload_blob(
        container: Annotated[str, Field(min_length=1)],
        blob: Annotated[str, Field(min_length=1)],
        content: Annotated[str, Field(description="UTF-8 text content")],
    ) -> dict:
        """Upload text content as a blob. Offline: writes to local_store."""
        if is_offline():
            rec = {"container": container, "blob": blob, "size": len(content), "content": content}
            local_store.put("azure-blob", f"blobs:{container}", blob, rec)
            return {"uploaded": {"container": container, "blob": blob, "size": len(content)}}
        headers = {**_headers(), "x-ms-blob-type": "BlockBlob"}
        async with make_client("azure-blob", timeout=_TIMEOUT) as c:
            r = await c.put(
                f"{_base()}/{container}/{blob}", headers=headers, content=content.encode("utf-8")
            )
            _raise_for(r)
        return {"container": container, "blob": blob, "status": r.status_code}
