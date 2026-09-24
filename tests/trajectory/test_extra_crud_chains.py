"""More CRUD trajectory chains covering additional stateful workflows."""

from __future__ import annotations

import asyncio
import importlib
import os
import shutil
import tempfile

import pytest

_STATE = tempfile.mkdtemp(prefix="crud_traj_ext_")


@pytest.fixture(autouse=True, scope="module")
def _env():
    os.environ["MCP_OFFLINE"] = "1"
    os.environ["MCP_STATE_DIR"] = _STATE
    for v in [
        "GITHUB_TOKEN",
        "STRIPE_SECRET_KEY",
        "SLACK_BOT_TOKEN",
        "DISCORD_BOT_TOKEN",
        "JIRA_URL",
        "JIRA_USER",
        "JIRA_TOKEN",
        "NOTION_TOKEN",
        "AIRTABLE_TOKEN",
        "TRELLO_KEY",
        "TRELLO_TOKEN",
        "HUBSPOT_TOKEN",
        "VAULT_ADDR",
        "VAULT_TOKEN",
        "LINEAR_API_KEY",
        "ASANA_TOKEN",
        "PAGERDUTY_TOKEN",
        "TWILIO_ACCOUNT_SID",
        "TWILIO_AUTH_TOKEN",
    ]:
        os.environ.setdefault(v, "offline")
    os.environ["VAULT_ADDR"] = "http://localhost:8200"
    yield
    shutil.rmtree(_STATE, ignore_errors=True)


async def _fns(sid):
    from mcp_common import local_store

    await local_store.reset(sid)
    mod = importlib.import_module(f"servers.{sid}.tools")
    from fastmcp import FastMCP

    m = FastMCP(name=sid)
    mod.register_tools(m)
    return {t.name: t.fn for t in await m.list_tools()}


@pytest.mark.asyncio
@pytest.mark.trajectory
async def test_linear_full_cycle():
    f = await _fns("linear")
    await f["create_issue"](team_id="T1", title="A")
    await f["create_issue"](team_id="T1", title="B")
    r = await f["list_issues"](team_id="T1")
    assert len(r["issues"]) == 2


@pytest.mark.asyncio
@pytest.mark.trajectory
async def test_asana_full_cycle():
    f = await _fns("asana")
    await f["create_task"](project_id="P1", name="One")
    await f["create_task"](project_id="P1", name="Two")
    r = await f["list_tasks"](project_id="P1")
    assert len(r["tasks"]) == 2


@pytest.mark.asyncio
@pytest.mark.trajectory
async def test_pagerduty_incident_lifecycle():
    f = await _fns("pagerduty")
    await f["create_incident"](service_id="S1", title="Alert 1")
    await f["create_incident"](service_id="S1", title="Alert 2")
    r = await f["list_incidents"](service_id="S1")
    assert len(r["incidents"]) == 2


@pytest.mark.asyncio
@pytest.mark.trajectory
async def test_twilio_sms_and_redact():
    f = await _fns("twilio")
    sent = await f["send_sms"](to="+1", from_="+2", body="hi")
    sid_ = sent["sid"]
    listed = await f["list_messages"](to="+1")
    assert len(listed["messages"]) == 1
    if "delete_message" in f:
        d = await f["delete_message"](message_sid=sid_)
        assert d["deleted"]


@pytest.mark.asyncio
@pytest.mark.trajectory
async def test_multi_server_incident_response():
    """Realistic: PD incident → GitHub issue → Slack notification, all read back."""
    pd = await _fns("pagerduty")
    gh = await _fns("github")
    sl = await _fns("slack")
    inc = await pd["create_incident"](service_id="prod", title="DB CPU spike")
    gh_issue = await gh["create_issue"](owner="acme", repo="ops", title=f"Investigate {inc['id']}")
    await sl["post_message"](channel="#oncall", text=f"See {inc['id']} + {gh_issue['html_url']}")
    assert len((await pd["list_incidents"](service_id="prod"))["incidents"]) == 1
    assert len((await gh["list_issues"](owner="acme", repo="ops"))["issues"]) == 1
    assert len((await sl["get_conversation"](channel="#oncall"))["messages"]) == 1


@pytest.mark.asyncio
@pytest.mark.trajectory
async def test_stripe_subscription_lifecycle():
    f = await _fns("stripe")
    intent = await f["create_payment_intent"](amount=999, currency="usd", customer="cus_a")
    charge_id = intent["charge_id"]
    charges = await f["list_charges"](customer="cus_a")
    assert len(charges["data"]) == 1
    if "refund_charge" in f:
        refund = await f["refund_charge"](charge_id=charge_id, amount=999)
        assert refund["status"] == "succeeded"
