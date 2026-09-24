"""Contract: every server fixture file must be valid JSON. If a schema.json exists it is enforced."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from mcp_common.registry import ROOT_DIR

FIXTURE_DIRS = [
    d for d in (ROOT_DIR / "servers").iterdir() if d.is_dir() and (d / "fixtures").is_dir()
]


@pytest.mark.contract
@pytest.mark.parametrize("server_dir", FIXTURE_DIRS, ids=[d.name for d in FIXTURE_DIRS])
def test_fixture_files_are_valid_json(server_dir):
    for fx in (server_dir / "fixtures").glob("*.json"):
        try:
            json.loads(fx.read_text())
        except json.JSONDecodeError as e:
            pytest.fail(f"{server_dir.name}/{fx.name} is invalid JSON: {e}")


@pytest.mark.contract
@pytest.mark.parametrize("server_dir", FIXTURE_DIRS, ids=[d.name for d in FIXTURE_DIRS])
def test_fixtures_validate_against_schema_if_present(server_dir):
    schema_path = server_dir / "fixtures" / "schema.json"
    if not schema_path.exists():
        pytest.skip("no schema.json")
    import jsonschema

    schema = json.loads(schema_path.read_text())
    for fx in (server_dir / "fixtures").glob("*.json"):
        if fx.name == "schema.json":
            continue
        data = json.loads(fx.read_text())
        try:
            jsonschema.validate(data, schema)
        except jsonschema.ValidationError as e:
            pytest.fail(f"{server_dir.name}/{fx.name} violates schema: {e.message}")
