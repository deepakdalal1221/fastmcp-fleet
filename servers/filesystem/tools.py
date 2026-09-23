from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field

from mcp_common.errors import ConfigError, NotFoundError, ValidationError

_MAX_READ_BYTES = 1_000_000
_MAX_WRITE_BYTES = 1_000_000
_MAX_LIST_ENTRIES = 5_000
_MAX_SEARCH_RESULTS = 500


def _root() -> Path:
    raw = os.environ.get("FS_ROOT")
    if not raw:
        raise ConfigError("FS_ROOT is not set")
    root = Path(raw).expanduser().resolve()
    if not root.is_dir():
        raise ConfigError(f"FS_ROOT is not a directory: {root}")
    return root


def _resolve_inside(root: Path, relative: str) -> Path:
    if not relative or relative.startswith("/") or ".." in Path(relative).parts:
        raise ValidationError(f"path must be relative and inside FS_ROOT: {relative!r}")
    target = (root / relative).resolve()
    if not target.is_relative_to(root):
        raise ValidationError(f"path escapes FS_ROOT: {relative!r}")
    return target


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def read_file(
        path: Annotated[str, Field(description="Path relative to FS_ROOT")],
    ) -> dict:
        """Read a UTF-8 text file inside FS_ROOT and return its contents."""
        target = _resolve_inside(_root(), path)
        if not target.exists():
            raise NotFoundError(f"file not found: {path}")
        if not target.is_file():
            raise ValidationError(f"not a regular file: {path}")
        data = target.read_bytes()
        if len(data) > _MAX_READ_BYTES:
            raise ValidationError(f"file too large: {len(data)} bytes (max {_MAX_READ_BYTES})")
        return {"path": path, "size": len(data), "text": data.decode("utf-8", errors="replace")}

    @mcp.tool
    async def write_file(
        path: Annotated[str, Field(description="Path relative to FS_ROOT")],
        content: Annotated[str, Field(description="UTF-8 text content to write")],
        overwrite: Annotated[bool, Field(description="Allow overwriting an existing file")] = False,
    ) -> dict:
        """Write a UTF-8 text file inside FS_ROOT and return the bytes written."""
        encoded = content.encode("utf-8")
        if len(encoded) > _MAX_WRITE_BYTES:
            raise ValidationError(f"content too large: {len(encoded)} bytes (max {_MAX_WRITE_BYTES})")
        target = _resolve_inside(_root(), path)
        if target.exists() and not overwrite:
            raise ValidationError(f"file exists (overwrite=false): {path}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(encoded)
        return {"path": path, "size": len(encoded)}

    @mcp.tool
    async def list_dir(
        path: Annotated[str, Field(description="Directory relative to FS_ROOT; use '.' for the root")] = ".",
    ) -> dict:
        """List directory entries relative to FS_ROOT (files, dirs, symlinks)."""
        target = _resolve_inside(_root(), path)
        if not target.is_dir():
            raise NotFoundError(f"not a directory: {path}")
        entries: list[dict] = []
        for i, child in enumerate(sorted(target.iterdir())):
            if i >= _MAX_LIST_ENTRIES:
                break
            entries.append(
                {
                    "name": child.name,
                    "type": "dir" if child.is_dir() else "file" if child.is_file() else "other",
                    "size": child.stat().st_size if child.is_file() else None,
                }
            )
        return {"path": path, "entries": entries, "truncated": len(entries) >= _MAX_LIST_ENTRIES}

    @mcp.tool
    async def stat(
        path: Annotated[str, Field(description="Path relative to FS_ROOT")],
    ) -> dict:
        """Return file/directory metadata (size, mtime, type) for a path inside FS_ROOT."""
        target = _resolve_inside(_root(), path)
        if not target.exists():
            raise NotFoundError(f"path not found: {path}")
        st = target.stat()
        return {
            "path": path,
            "type": "dir" if target.is_dir() else "file" if target.is_file() else "other",
            "size": st.st_size,
            "mtime": st.st_mtime,
        }

    @mcp.tool
    async def search(
        pattern: Annotated[str, Field(description="Glob pattern (e.g. **/*.py)")],
        path: Annotated[str, Field(description="Directory relative to FS_ROOT to search from")] = ".",
    ) -> dict:
        """Search for paths matching a glob pattern within a directory inside FS_ROOT."""
        target = _resolve_inside(_root(), path)
        if not target.is_dir():
            raise NotFoundError(f"not a directory: {path}")
        results: list[str] = []
        for match in target.glob(pattern):
            if not match.resolve().is_relative_to(_root()):
                continue
            results.append(str(match.relative_to(_root())))
            if len(results) >= _MAX_SEARCH_RESULTS:
                break
        return {"pattern": pattern, "path": path, "matches": results, "truncated": len(results) >= _MAX_SEARCH_RESULTS}
