"""Assert every active server registers a superset of its manifest tools.

Impl can register MORE tools than declared, but MUST register all declared ones.
Failure here means the manifest is out of sync with implementation.
"""

from __future__ import annotations

import asyncio
import importlib
import os

import pytest
from fastmcp import FastMCP
from mcp_common.registry import load_catalogue

# Dummy env vars so _token()/_auth() paths don't blow up at import time
for var in [
    "GITHUB_TOKEN",
    "GITLAB_TOKEN",
    "GITEA_TOKEN",
    "GITEA_URL",
    "BITBUCKET_USER",
    "BITBUCKET_APP_PASSWORD",
    "AZURE_DEVOPS_ORG",
    "AZURE_DEVOPS_TOKEN",
    "SOURCEGRAPH_TOKEN",
    "CODECOV_TOKEN",
    "JIRA_URL",
    "JIRA_USER",
    "JIRA_TOKEN",
    "ASANA_TOKEN",
    "LINEAR_API_KEY",
    "NOTION_TOKEN",
    "AIRTABLE_TOKEN",
    "SLACK_BOT_TOKEN",
    "DISCORD_BOT_TOKEN",
    "SENDGRID_API_KEY",
    "TWILIO_ACCOUNT_SID",
    "TWILIO_AUTH_TOKEN",
    "MAILCHIMP_API_KEY",
    "MAILCHIMP_SERVER",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "HUGGINGFACE_TOKEN",
    "HF_TOKEN",
    "COHERE_API_KEY",
    "GROQ_API_KEY",
    "OPENROUTER_API_KEY",
    "REPLICATE_API_TOKEN",
    "MISTRAL_API_KEY",
    "TOGETHER_API_KEY",
    "MODAL_TOKEN",
    "MODAL_TOKEN_ID",
    "CLOUDFLARE_API_TOKEN",
    "CLOUDFLARE_ACCOUNT_ID",
    "DIGITALOCEAN_TOKEN",
    "VERCEL_TOKEN",
    "NETLIFY_TOKEN",
    "RENDER_TOKEN",
    "RENDER_API_KEY",
    "FLY_API_TOKEN",
    "LINODE_TOKEN",
    "HETZNER_TOKEN",
    "HEROKU_API_KEY",
    "RAILWAY_TOKEN",
    "DATADOG_API_KEY",
    "DATADOG_APP_KEY",
    "GRAFANA_URL",
    "GRAFANA_TOKEN",
    "PROMETHEUS_URL",
    "NEWRELIC_API_KEY",
    "NEWRELIC_ACCOUNT",
    "PAGERDUTY_TOKEN",
    "SENTRY_TOKEN",
    "SENTRY_ORG",
    "SUPABASE_URL",
    "SUPABASE_KEY",
    "ELASTIC_URL",
    "ELASTIC_USER",
    "ELASTIC_PASSWORD",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_REGION",
    "TFC_TOKEN",
    "CIRCLECI_TOKEN",
    "AWX_URL",
    "AWX_TOKEN",
    "TOWER_URL",
    "TOWER_TOKEN",
    "PULUMI_ACCESS_TOKEN",
    "DRONE_URL",
    "DRONE_TOKEN",
    "TEAMCITY_URL",
    "TEAMCITY_TOKEN",
    "JENKINS_URL",
    "JENKINS_USER",
    "JENKINS_TOKEN",
    "BUILDKITE_TOKEN",
    "ARGOCD_URL",
    "ARGOCD_TOKEN",
    "STRIPE_SECRET_KEY",
    "HUBSPOT_TOKEN",
    "CONFLUENCE_URL",
    "CONFLUENCE_USER",
    "CONFLUENCE_TOKEN",
    "BRAVE_API_KEY",
    "TAVILY_API_KEY",
    "OP_CONNECT_HOST",
    "OP_CONNECT_TOKEN",
    "SNYK_TOKEN",
    "SNYK_ORG",
    "AUTH0_DOMAIN",
    "AUTH0_TOKEN",
    "OKTA_URL",
    "OKTA_TOKEN",
    "VAULT_ADDR",
    "VAULT_TOKEN",
]:
    os.environ.setdefault(var, "offline")

os.environ.setdefault("MCP_OFFLINE", "1")

ACTIVE = [m for m in load_catalogue() if m.status == "active"]


@pytest.mark.contract
@pytest.mark.parametrize("manifest", ACTIVE, ids=[m.id for m in ACTIVE])
def test_registered_tools_are_superset_of_manifest(manifest):
    mod = importlib.import_module(f"servers.{manifest.id}.tools")
    mcp = FastMCP(name=manifest.id)
    mod.register_tools(mcp)
    tool_list = asyncio.run(mcp.list_tools())
    registered = {t.name for t in tool_list}
    manifest_tools = set(manifest.tools)
    missing = manifest_tools - registered
    assert not missing, (
        f"{manifest.id} manifest declares {sorted(missing)} but impl doesn't register them"
    )
