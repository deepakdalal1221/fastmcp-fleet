"""LLM-judge trajectory scoring — skipped unless LLM_API_KEY set."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("LLM_API_KEY"), reason="LLM_API_KEY not set")

SCENARIOS_DIR = Path(__file__).parent / "scenarios"


@pytest.mark.parametrize(
    "scenario_file", sorted(SCENARIOS_DIR.glob("*.json")), ids=lambda p: p.stem
)
def test_scenario_loads(scenario_file):
    """At minimum, every scenario file is valid JSON with the required fields."""
    data = json.loads(scenario_file.read_text())
    assert "goal" in data and "expected_tools" in data and "rubric" in data


@pytest.mark.eval
def test_llm_judge_placeholder():
    """Placeholder: real implementation would run an agent, capture trajectory, ask LLM to score against rubric."""
    pytest.skip("real LLM judge implementation deferred")
