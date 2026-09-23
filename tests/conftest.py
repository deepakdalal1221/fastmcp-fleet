from __future__ import annotations

import pytest
from mcp_common.registry import load_catalogue


@pytest.fixture(scope="session")
def catalogue():
    return load_catalogue()


@pytest.fixture(scope="session")
def pilot_ids() -> list[str]:
    return ["fetch", "filesystem", "time", "github", "postgres"]
