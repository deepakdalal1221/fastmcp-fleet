"""Verify MCP_RECORD_TRAJECTORY dumps tool calls to JSONL."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile

import pytest


@pytest.mark.contract
def test_trajectory_writes_jsonl_when_env_set():
    from mcp_common.trajectory import TrajectoryMiddleware, _record_dir

    with tempfile.TemporaryDirectory() as d:
        os.environ["MCP_RECORD_TRAJECTORY"] = d
        try:
            m = TrajectoryMiddleware("test-server")

            class Ctx:
                tool_name = "sample_tool"

            async def call_next(_ctx):
                return {"ok": True}

            async def run():
                return await m(Ctx(), call_next)

            asyncio.run(run())
            path = _record_dir() / "test-server.jsonl"
            assert path.exists()
            entry = json.loads(path.read_text().strip())
            assert entry["server"] == "test-server"
            assert entry["tool"] == "sample_tool"
            assert "duration_ms" in entry
            assert "error" not in entry
        finally:
            os.environ.pop("MCP_RECORD_TRAJECTORY", None)


@pytest.mark.contract
def test_trajectory_records_errors():
    from mcp_common.trajectory import TrajectoryMiddleware, _record_dir

    with tempfile.TemporaryDirectory() as d:
        os.environ["MCP_RECORD_TRAJECTORY"] = d
        try:
            m = TrajectoryMiddleware("err-server")

            class Ctx:
                tool_name = "failing_tool"

            async def call_next(_ctx):
                raise RuntimeError("boom")

            async def run():
                with pytest.raises(RuntimeError):
                    await m(Ctx(), call_next)

            asyncio.run(run())
            entry = json.loads((_record_dir() / "err-server.jsonl").read_text().strip())
            assert entry["error"].startswith("RuntimeError")
        finally:
            os.environ.pop("MCP_RECORD_TRAJECTORY", None)


@pytest.mark.contract
def test_trajectory_noop_when_env_unset():
    from mcp_common.trajectory import TrajectoryMiddleware

    os.environ.pop("MCP_RECORD_TRAJECTORY", None)
    m = TrajectoryMiddleware("noop-server")
    assert m._path is None
