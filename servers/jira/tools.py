from __future__ import annotations

import base64
import os
import re
from typing import Annotated, Any

import httpx
from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import (
    AuthError,
    ConfigError,
    NotFoundError,
    RateLimitError,
    UpstreamError,
    ValidationError,
)
from mcp_common.http import is_offline, make_client
from pydantic import Field

_MAX_RESULTS = 100


def _base_url() -> str:
    url = os.environ.get("JIRA_BASE_URL", "").strip().rstrip("/")
    if not url:
        raise ConfigError("JIRA_BASE_URL is not set (e.g. https://acme.atlassian.net)")
    if not url.startswith(("http://", "https://")):
        raise ConfigError("JIRA_BASE_URL must start with http:// or https://")
    return url


def _auth_header() -> str:
    email = os.environ.get("JIRA_EMAIL", "").strip()
    token = os.environ.get("JIRA_API_TOKEN", "").strip()
    if not email or not token:
        raise ConfigError("JIRA_EMAIL and JIRA_API_TOKEN must be set")
    credentials = f"{email}:{token}".encode()
    return "Basic " + base64.b64encode(credentials).decode()


def _headers() -> dict[str, str]:
    return {
        "Authorization": _auth_header(),
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "fastmcp-platform/jira",
    }


def _clamp(n: int, lo: int = 1, hi: int = _MAX_RESULTS) -> int:
    return max(lo, min(hi, n))


def _raise_for_status(response: httpx.Response) -> None:
    if response.status_code == 401:
        raise AuthError("Jira authentication failed")
    if response.status_code == 403:
        raise AuthError("Jira permission denied")
    if response.status_code == 404:
        raise NotFoundError("Jira resource not found")
    if response.status_code == 429:
        raise RateLimitError("Jira rate limit exceeded")
    if response.status_code >= 500:
        raise UpstreamError(f"Jira upstream error: HTTP {response.status_code}")
    if response.status_code >= 400:
        raise UpstreamError(f"Jira HTTP {response.status_code}: {response.text[:200]}")


async def _request(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
) -> Any:
    url = f"{_base_url()}/rest/api/3{path}"
    try:
        response = await client.request(method, url, params=params, json=body, headers=_headers())
    except httpx.RequestError as exc:
        raise UpstreamError(f"Jira request failed: {exc}") from exc
    _raise_for_status(response)
    if response.status_code == 204 or not response.content:
        return {}
    return response.json()


def _issue_slim(issue: dict[str, Any]) -> dict[str, Any]:
    fields = issue.get("fields") or {}
    status = (fields.get("status") or {}).get("name")
    issuetype = (fields.get("issuetype") or {}).get("name")
    assignee = fields.get("assignee") or {}
    reporter = fields.get("reporter") or {}
    priority = fields.get("priority") or {}
    return {
        "id": issue.get("id"),
        "key": issue.get("key"),
        "summary": fields.get("summary"),
        "status": status,
        "type": issuetype,
        "priority": priority.get("name"),
        "assignee": assignee.get("displayName"),
        "reporter": reporter.get("displayName"),
        "created": fields.get("created"),
        "updated": fields.get("updated"),
    }


def _project_slim(project: dict[str, Any]) -> dict[str, Any]:
    lead = project.get("lead") or {}
    return {
        "id": project.get("id"),
        "key": project.get("key"),
        "name": project.get("name"),
        "type": project.get("projectTypeKey"),
        "style": project.get("style"),
        "lead": lead.get("displayName"),
    }


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def search_issues(
        jql: Annotated[str, Field(description="JQL query, e.g. project = DEMO")] = "",
        max_results: Annotated[int, Field(ge=1, le=100)] = 20,
    ) -> dict:
        """Search Jira issues by JQL. Offline mode reads local state by project key in JQL."""
        if is_offline():
            m = re.search(r"project\s*=\s*['\"]?([A-Z][A-Z0-9_]+)", jql or "")
            issues = []
            if m:
                stored = await local_store.list_all("jira", f"issues:{m.group(1)}")
                issues = [row["value"] for row in stored][:max_results]
            return {
                "issues": [
                    {
                        "key": i["key"],
                        "summary": i["fields"]["summary"],
                        "status": i["fields"]["status"]["name"],
                    }
                    for i in issues
                ]
            }
        async with make_client("jira", timeout=_TIMEOUT) as c:
            r = await c.get(
                f"{_base()}/rest/api/3/search",
                auth=_auth(),
                params={"jql": jql, "maxResults": max_results},
            )
            _raise_for(r)
            data = r.json()
        return {
            "issues": [
                {
                    "key": i["key"],
                    "summary": i["fields"].get("summary"),
                    "status": (i["fields"].get("status") or {}).get("name"),
                }
                for i in data.get("issues", [])
            ]
        }

    @mcp.tool
    async def get_issue(
        key: Annotated[str, Field(description="Issue key, e.g. ENG-123")],
    ) -> dict:
        """Get a single Jira issue by key."""
        if not key.strip():
            raise ValidationError("key must not be empty")
        async with make_client("jira", timeout=30.0) as client:
            data = await _request(client, "GET", f"/issue/{key}")
        return _issue_slim(data)

    @mcp.tool
    async def create_issue(
        project_key: Annotated[str, Field(min_length=1, description="Jira project key like DEMO")],
        summary: Annotated[str, Field(min_length=1, description="issue summary")],
        description: Annotated[str | None, Field(description="issue description")] = None,
        issue_type: Annotated[str, Field(description="issue type name")] = "Task",
    ) -> dict:
        """Create a Jira issue. Offline mode persists to local state."""
        if is_offline():
            col = f"issues:{project_key}"
            n = local_store.next_id("jira", col)
            key = f"{project_key}-{n}"
            issue = {
                "key": key,
                "id": str(1000 + n),
                "fields": {
                    "summary": summary,
                    "description": description,
                    "issuetype": {"name": issue_type},
                    "status": {"name": "To Do"},
                    "project": {"key": project_key},
                },
            }
            await local_store.put("jira", col, key, issue)
            return {"key": key, "id": issue["id"], "summary": summary, "status": "To Do"}
        payload = {
            "fields": {
                "project": {"key": project_key},
                "summary": summary,
                "issuetype": {"name": issue_type},
            }
        }
        if description is not None:
            payload["fields"]["description"] = description
        async with make_client("jira", timeout=_TIMEOUT) as c:
            r = await c.post(f"{_base()}/rest/api/3/issue", auth=_auth(), json=payload)
            _raise_for(r)
            j = r.json()
        return {"key": j.get("key"), "id": j.get("id"), "summary": summary}

    @mcp.tool
    async def update_issue(
        key: Annotated[str, Field(description="Issue key, e.g. ENG-123")],
        summary: Annotated[str | None, Field(description="New summary (optional)")] = None,
        description: Annotated[
            str | None, Field(description="New description text (optional)")
        ] = None,
    ) -> dict:
        """Update summary and/or description on a Jira issue."""
        if not key.strip():
            raise ValidationError("key must not be empty")
        fields: dict[str, Any] = {}
        if summary is not None:
            if not summary.strip():
                raise ValidationError("summary must not be empty when provided")
            fields["summary"] = summary
        if description is not None:
            fields["description"] = {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": description}],
                    }
                ],
            }
        if not fields:
            raise ValidationError("provide at least one of: summary, description")
        async with make_client("jira", timeout=30.0) as client:
            await _request(client, "PUT", f"/issue/{key}", body={"fields": fields})
        return {"key": key, "updated_fields": list(fields.keys())}

    @mcp.tool
    async def list_projects(
        max_results: Annotated[int, Field(description="Max projects to return (1-100)")] = 50,
    ) -> dict:
        """List Jira projects visible to the caller."""
        params = {"maxResults": _clamp(max_results)}
        async with make_client("jira", timeout=30.0) as client:
            data = await _request(client, "GET", "/project/search", params=params)
        projects = [_project_slim(p) for p in (data.get("values") or [])]
        return {
            "projects": projects,
            "total": data.get("total", len(projects)),
            "count": len(projects),
        }
