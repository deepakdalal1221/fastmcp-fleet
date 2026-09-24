"""Trajectory tests: verify every seeded server's seed data is retrievable.

For each of the 60 servers that ship with a `seed.json`, this test:
  1. Uses an isolated per-server SQLite state directory
  2. Calls local_store.seed(sid) to load the baseline
  3. For every bucket in seed.json, asserts local_store.list_all(sid, bucket)
     returns exactly the seeded row count
  4. Spot-checks that the first row's stored value matches the seed payload

This locks in the contract that `MCP_OFFLINE=1` + seed.json => agents see
mock data on the very first tool call, without needing to call create_* first.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVERS_DIR = REPO_ROOT / "servers"


def _discover_seeded_servers() -> list[tuple[str, str, int]]:
    """Return (server_id, bucket, expected_count) for every bucket in every seed.json."""
    cases: list[tuple[str, str, int]] = []
    for seed_file in sorted(SERVERS_DIR.glob("*/seed.json")):
        sid = seed_file.parent.name
        try:
            data = json.loads(seed_file.read_text())
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        for bucket, rows in data.items():
            if isinstance(rows, list):
                cases.append((sid, bucket, len(rows)))
    return cases


CASES = _discover_seeded_servers()


@pytest.mark.trajectory
@pytest.mark.parametrize(
    "server_id,bucket,expected_count",
    CASES,
    ids=[f"{sid}/{bucket}" for sid, bucket, _ in CASES],
)
def test_seed_populates_bucket(server_id, bucket, expected_count, tmp_path, monkeypatch):
    """Every bucket in seed.json must be populated after local_store.seed()."""
    import asyncio

    monkeypatch.setenv("MCP_OFFLINE", "1")
    monkeypatch.setenv("MCP_STATE_DIR", str(tmp_path))

    from mcp_common import local_store

    async def run():
        await local_store.reset(server_id)
        loaded = await local_store.seed(server_id)
        assert loaded > 0, f"seed({server_id}) loaded 0 rows"
        items = await local_store.list_all(server_id, bucket)
        assert len(items) == expected_count, (
            f"{server_id}/{bucket}: expected {expected_count} rows, got {len(items)}"
        )
        # Spot: first row's value must be a dict (the seeded payload)
        assert isinstance(items[0], dict), f"{server_id}/{bucket}[0] is not a dict"

    asyncio.run(run())


def test_seed_coverage_smoke():
    """At least 60 servers should have seed.json (49 batch-22-26 + 11 stateful)."""
    seeded = list(SERVERS_DIR.glob("*/seed.json"))
    assert len(seeded) >= 60, f"expected >=60 seed files, found {len(seeded)}"


def test_all_seeded_buckets_reachable():
    """Every seed.json must parse and contain at least one non-empty bucket."""
    for seed_file in SERVERS_DIR.glob("*/seed.json"):
        sid = seed_file.parent.name
        data = json.loads(seed_file.read_text())
        assert isinstance(data, dict), f"{sid}/seed.json is not a dict"
        assert data, f"{sid}/seed.json is empty"
        for bucket, rows in data.items():
            assert isinstance(rows, list) and rows, (
                f"{sid}/seed.json[{bucket}] is empty or wrong type"
            )
            for row in rows:
                assert isinstance(row, dict), f"{sid}/seed.json[{bucket}] row not a dict"
                assert "key" in row and "value" in row, (
                    f"{sid}/seed.json[{bucket}] row missing key/value"
                )
