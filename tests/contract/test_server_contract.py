from __future__ import annotations

import importlib

import pytest
from mcp_common import create_server
from mcp_common.testing import call_tool


@pytest.mark.asyncio
@pytest.mark.parametrize("server_id", ["fetch", "filesystem", "time", "github", "postgres"])
async def test_server_boots_and_registers_manifest_tools(server_id: str):
    mcp, manifest, _ = create_server(server_id)
    mod = importlib.import_module(f"servers.{server_id}.tools")
    mod.register_tools(mcp)

    registered = await mcp.list_tools()
    names = {t.name for t in registered}

    for tool_name in manifest.tools:
        assert tool_name in names, f"{server_id}: tool {tool_name} from manifest not registered"

    assert "health" in names, f"{server_id}: health tool missing"


@pytest.mark.asyncio
async def test_health_tool_returns_expected_payload():
    mcp, _, _ = create_server("fetch")
    result = await call_tool(mcp, "health")
    assert result["status"] == "ok"
    assert result["server_id"] == "fetch"
    assert "uptime_seconds" in result
    assert "version" in result


@pytest.mark.asyncio
async def test_time_now_utc_shape():
    mcp, _, _ = create_server("time")
    mod = importlib.import_module("servers.time.tools")
    mod.register_tools(mcp)
    result = await call_tool(mcp, "now", tz="UTC")
    assert "iso" in result
    assert "epoch" in result
    assert result["timezone"] == "UTC"
