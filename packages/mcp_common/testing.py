from __future__ import annotations

from contextlib import contextmanager
from typing import Any


@contextmanager
def env(**overrides: str) -> Any:
    import os

    old = {k: os.environ.get(k) for k in overrides}
    os.environ.update(overrides)
    try:
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


async def call_tool(mcp: Any, name: str, **kwargs: Any) -> Any:
    tool = None
    if hasattr(mcp, "get_tool"):
        tool = await mcp.get_tool(name)
    elif hasattr(mcp, "tools"):
        tool = mcp.tools.get(name)
    if tool is None:
        raise LookupError(f"tool not registered: {name}")
    fn = getattr(tool, "fn", None) or getattr(tool, "func", None) or tool
    result = fn(**kwargs)
    if hasattr(result, "__await__"):
        result = await result
    return result
