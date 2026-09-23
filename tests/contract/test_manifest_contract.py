from __future__ import annotations

import pytest

from mcp_common.registry import ServerManifest, load_catalogue, load_manifest

VALID_AUTH_TYPES = {
    "none",
    "api_key",
    "basic",
    "bearer",
    "bearer_token",
    "token",
    "oauth",
    "connection_string",
    "iam",
    "aws_sig",
    "gcp_sa",
    "custom",
}
VALID_TRANSPORTS = {"streamable-http", "stdio", "sse"}
VALID_STATUS = {"pilot", "planned", "active", "deprecated"}


def test_catalogue_has_expected_size():
    catalogue = load_catalogue()
    assert len(catalogue) >= 160, f"expected 160+ servers, got {len(catalogue)}"


def test_catalogue_ids_are_unique():
    catalogue = load_catalogue()
    ids = [m.id for m in catalogue]
    assert len(ids) == len(set(ids)), "duplicate server ids in catalogue"


def test_catalogue_ports_are_unique_and_disjoint_from_gateway():
    catalogue = load_catalogue()
    ports = [m.port for m in catalogue]
    assert 8000 not in ports, "server ports must not collide with gateway 8000"
    assert len(ports) == len(set(ports)), "duplicate ports in catalogue"


@pytest.mark.parametrize("server_id", [m.id for m in load_catalogue()])
def test_manifest_shape(server_id: str):
    m = load_manifest(server_id)
    assert isinstance(m, ServerManifest)
    assert m.id == server_id
    assert m.name and isinstance(m.name, str)
    assert m.category and isinstance(m.category, str)
    assert m.auth.type in VALID_AUTH_TYPES, f"{server_id}: unknown auth type {m.auth.type}"
    assert m.transport in VALID_TRANSPORTS
    assert 1024 <= m.port <= 65535
    assert m.image.startswith("yourorg/mcp-")
    assert m.version
    assert m.tools, f"{server_id}: manifest.tools must not be empty"
    assert m.status in VALID_STATUS


def test_pilot_servers_are_marked_pilot(pilot_ids):
    for sid in pilot_ids:
        m = load_manifest(sid)
        assert m.status == "pilot", f"{sid} should be status=pilot, got {m.status}"
