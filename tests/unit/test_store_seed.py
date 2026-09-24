from __future__ import annotations

import asyncio
import json

import pytest
from mcp_common import local_store
from mcp_common.store import _db_path, _seed_path


@pytest.mark.unit
def test_seed_loads_json_into_store(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_STATE_DIR", str(tmp_path))
    sid = "github"

    seed_data = json.loads(_seed_path(sid).read_text())
    total_rows = sum(len(v) for v in seed_data.values() if isinstance(v, list))

    loaded = asyncio.run(local_store.seed(sid))
    assert loaded == total_rows

    for collection in seed_data:
        items = asyncio.run(local_store.list_all(sid, collection))
        assert len(items) == len(seed_data[collection])


@pytest.mark.unit
def test_seed_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_STATE_DIR", str(tmp_path))
    sid = "github"

    first = asyncio.run(local_store.seed(sid))
    second = asyncio.run(local_store.seed(sid))
    assert first == second

    seed_data = json.loads(_seed_path(sid).read_text())
    for collection in seed_data:
        items = asyncio.run(local_store.list_all(sid, collection))
        assert len(items) == len(seed_data[collection])


@pytest.mark.unit
def test_seed_missing_file_returns_zero(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_STATE_DIR", str(tmp_path))
    fake_sid = "server-with-no-seed-file-xyz"
    assert not _seed_path(fake_sid).exists()

    loaded = asyncio.run(local_store.seed(fake_sid))
    assert loaded == 0


@pytest.mark.unit
def test_reset_then_seed_restores_baseline(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_STATE_DIR", str(tmp_path))
    sid = "jira"

    baseline = asyncio.run(local_store.seed(sid))
    assert baseline > 0

    asyncio.run(
        local_store.put(sid, "issues:USER/PROJ", "999", {"key": "USER-999", "title": "extra"})
    )

    db = _db_path(sid)
    assert db.exists()
    db.unlink()

    restored = asyncio.run(local_store.seed(sid))
    assert restored == baseline
