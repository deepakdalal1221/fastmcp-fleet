"""Offline trajectory tests: create -> list state consistency for stateful servers.

Runs each stateful server through a create-write + list-read cycle and asserts
the written entity appears in the read result. Requires MCP_OFFLINE=1.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Offline env setup applied to every test in this module
# ---------------------------------------------------------------------------

_STATE_DIR = tempfile.mkdtemp(prefix="mcp_trajectory_")


@pytest.fixture(autouse=True, scope="module")
def _offline_env():
    os.environ["MCP_OFFLINE"] = "1"
    os.environ["MCP_STATE_DIR"] = _STATE_DIR
    # Dummy env vars so _token()/_auth() paths in each server dont raise
    for var in (
        "GITHUB_TOKEN",
        "JIRA_URL",
        "JIRA_USER",
        "JIRA_TOKEN",
        "ASANA_TOKEN",
        "LINEAR_API_KEY",
        "SLACK_BOT_TOKEN",
        "STRIPE_SECRET_KEY",
        "TWILIO_ACCOUNT_SID",
        "TWILIO_AUTH_TOKEN",
        "PAGERDUTY_TOKEN",
        "PAGERDUTY_FROM",
        "NOTION_TOKEN",
    ):
        os.environ.setdefault(var, "offline-dummy")
    yield
    shutil.rmtree(_STATE_DIR, ignore_errors=True)


async def _register(server_id: str):
    """Load a server's tools and return {tool_name: callable}."""
    from mcp_common import local_store

    await local_store.reset(server_id)
    import importlib

    mod = importlib.import_module(f"servers.{server_id}.tools")
    from fastmcp import FastMCP

    m = FastMCP(name=server_id)
    mod.register_tools(m)
    tool_list = await m.list_tools()
    return {t.name: t.fn for t in tool_list}


# ---------------------------------------------------------------------------
# Roundtrip tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.trajectory
async def test_github_roundtrip():
    fns = await _register("github")
    await fns["create_issue"](owner="acme", repo="app", title="Bug A")
    r = await fns["list_issues"](owner="acme", repo="app")
    assert len(r["issues"]) == 1
    assert r["issues"][0]["title"] == "Bug A"


@pytest.mark.asyncio
@pytest.mark.trajectory
async def test_jira_roundtrip():
    fns = await _register("jira")
    await fns["create_issue"](project_key="TRAJ", summary="Bug B")
    r = await fns["search_issues"](jql="project = TRAJ")
    assert len(r["issues"]) == 1
    assert r["issues"][0]["summary"] == "Bug B"


@pytest.mark.asyncio
@pytest.mark.trajectory
async def test_asana_roundtrip():
    fns = await _register("asana")
    await fns["create_task"](project_id="P1", name="Do the thing")
    r = await fns["list_tasks"](project_id="P1")
    assert len(r["tasks"]) == 1
    assert r["tasks"][0]["name"] == "Do the thing"


@pytest.mark.asyncio
@pytest.mark.trajectory
async def test_linear_roundtrip():
    fns = await _register("linear")
    await fns["create_issue"](team_id="TEAM", title="Linear thing")
    r = await fns["list_issues"](team_id="TEAM")
    assert len(r["issues"]) == 1
    assert r["issues"][0]["title"] == "Linear thing"


@pytest.mark.asyncio
@pytest.mark.trajectory
async def test_slack_roundtrip():
    fns = await _register("slack")
    await fns["post_message"](channel="C1", text="hello")
    r = await fns["get_conversation"](channel="C1")
    assert len(r["messages"]) == 1
    assert r["messages"][0]["text"] == "hello"


@pytest.mark.asyncio
@pytest.mark.trajectory
async def test_stripe_roundtrip():
    fns = await _register("stripe")
    await fns["create_payment_intent"](amount=750, currency="usd", customer="cus_x")
    r = await fns["list_charges"](customer="cus_x")
    assert len(r["data"]) == 1
    assert r["data"][0]["amount"] == 750


@pytest.mark.asyncio
@pytest.mark.trajectory
async def test_twilio_roundtrip():
    fns = await _register("twilio")
    await fns["send_sms"](to="+15550001111", from_="+15550009999", body="hi")
    r = await fns["list_messages"](to="+15550001111")
    assert len(r["messages"]) == 1
    assert r["messages"][0]["body"] == "hi"


@pytest.mark.asyncio
@pytest.mark.trajectory
async def test_pagerduty_roundtrip():
    fns = await _register("pagerduty")
    await fns["create_incident"](service_id="SVC", title="Prod alarm")
    r = await fns["list_incidents"](service_id="SVC")
    assert len(r["incidents"]) == 1
    assert r["incidents"][0]["title"] == "Prod alarm"


@pytest.mark.asyncio
@pytest.mark.trajectory
async def test_notion_roundtrip():
    fns = await _register("notion")
    await fns["create_page"](parent_id="DB1", title="Trajectory Note")
    r = await fns["search"](parent_id="DB1", query="Trajectory")
    assert len(r["results"]) == 1
    assert r["results"][0]["title"] == "Trajectory Note"


# ---------------------------------------------------------------------------
# Cross-server chain: github issue -> jira issue -> slack message
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.trajectory
async def test_chain_github_jira_slack():
    gh = await _register("github")
    jr = await _register("jira")
    sl = await _register("slack")

    # 1. Create GH issue
    g = await gh["create_issue"](owner="acme", repo="chain", title="Chain test")
    assert g["title"] == "Chain test"

    # 2. Create Jira issue that references GH
    j = await jr["create_issue"](
        project_key="CHAIN", summary=f"Track {g['title']} (GH #{g['number']})"
    )
    assert "CHAIN-" in j["key"]

    # 3. Post Slack message linking both
    await sl["post_message"](channel="C-chain", text=f"Opened {g['html_url']} and {j['key']}")

    # 4. Verify all three read paths return the created entities
    gh_list = await gh["list_issues"](owner="acme", repo="chain")
    jr_list = await jr["search_issues"](jql="project = CHAIN")
    sl_list = await sl["get_conversation"](channel="C-chain")

    assert len(gh_list["issues"]) == 1
    assert len(jr_list["issues"]) == 1
    assert len(sl_list["messages"]) == 1
    assert j["key"] in sl_list["messages"][0]["text"]


@pytest.mark.asyncio
@pytest.mark.trajectory
async def test_hubspot_roundtrip():
    os.environ.setdefault("HUBSPOT_TOKEN", "offline-dummy")
    fns = await _register("hubspot")
    await fns["create_contact"](email="alice@example.com", firstname="Alice")
    r = await fns["list_contacts"]()
    assert r["count"] >= 1


@pytest.mark.asyncio
@pytest.mark.trajectory
async def test_freshdesk_roundtrip():
    for v in ("FRESHDESK_DOMAIN", "FRESHDESK_API_KEY"):
        os.environ.setdefault(v, "offline-dummy")
    fns = await _register("freshdesk")
    await fns["create_ticket"](subject="Bug X", description="from test", email="a@b.com")
    r = await fns["list_tickets"]()
    assert r["count"] >= 1


@pytest.mark.asyncio
@pytest.mark.trajectory
async def test_monday_roundtrip():
    os.environ.setdefault("MONDAY_TOKEN", "offline-dummy")
    fns = await _register("monday")
    await fns["create_item"](board_id="B1", name="Row 1")
    r = await fns["list_items"](board_id="B1")
    assert r["count"] >= 1


@pytest.mark.asyncio
@pytest.mark.trajectory
async def test_clickup_roundtrip():
    os.environ.setdefault("CLICKUP_TOKEN", "offline-dummy")
    fns = await _register("clickup")
    await fns["create_task"](list_id="L1", name="Task 1")
    r = await fns["list_tasks"](list_id="L1")
    assert r["count"] >= 1


@pytest.mark.asyncio
@pytest.mark.trajectory
async def test_plane_roundtrip():
    for v in ("PLANE_URL", "PLANE_TOKEN"):
        os.environ.setdefault(v, "offline-dummy")
    fns = await _register("plane")
    await fns["create_issue"](workspace_slug="w1", project_id="p1", name="Issue 1")
    r = await fns["list_issues"](workspace_slug="w1", project_id="p1")
    assert r["count"] >= 1


@pytest.mark.asyncio
@pytest.mark.trajectory
async def test_wrike_roundtrip():
    os.environ.setdefault("WRIKE_TOKEN", "offline-dummy")
    fns = await _register("wrike")
    await fns["create_task"](title="Wrike task 1")
    r = await fns["list_tasks"]()
    assert r["count"] >= 1


@pytest.mark.asyncio
@pytest.mark.trajectory
async def test_shortcut_roundtrip():
    os.environ.setdefault("SHORTCUT_TOKEN", "offline-dummy")
    fns = await _register("shortcut")
    await fns["create_story"](name="Story 1")
    r = await fns["list_stories"]()
    assert r["count"] >= 1
