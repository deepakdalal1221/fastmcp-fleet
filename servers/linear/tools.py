from __future__ import annotations

import os
from typing import Annotated, Any

import httpx
from fastmcp import FastMCP
from mcp_common import local_store
from mcp_common.errors import (
    AuthError,
    ConfigError,
    RateLimitError,
    UpstreamError,
    ValidationError,
)
from mcp_common.http import is_offline, make_client
from pydantic import Field

_ENDPOINT = "https://api.linear.app/graphql"
_MAX_FIRST = 100


def _api_key() -> str:
    key = os.environ.get("LINEAR_API_KEY", "").strip()
    if not key:
        raise ConfigError("LINEAR_API_KEY is not set")
    return key


def _headers() -> dict[str, str]:
    return {
        "Authorization": _api_key(),
        "Content-Type": "application/json",
        "User-Agent": "fastmcp-platform/linear",
    }


def _clamp(n: int, lo: int = 1, hi: int = _MAX_FIRST) -> int:
    return max(lo, min(hi, n))


def _raise_for_status(response: httpx.Response) -> None:
    if response.status_code == 401:
        raise AuthError("Linear authentication failed")
    if response.status_code == 403:
        raise AuthError("Linear permission denied")
    if response.status_code == 429:
        raise RateLimitError("Linear rate limit exceeded")
    if response.status_code >= 500:
        raise UpstreamError(f"Linear upstream error: HTTP {response.status_code}")
    if response.status_code >= 400:
        raise UpstreamError(f"Linear HTTP {response.status_code}: {response.text[:200]}")


async def _graphql(
    client: httpx.AsyncClient, query: str, variables: dict[str, Any] | None = None
) -> dict[str, Any]:
    try:
        response = await client.post(
            _ENDPOINT,
            json={"query": query, "variables": variables or {}},
            headers=_headers(),
        )
    except httpx.RequestError as exc:
        raise UpstreamError(f"Linear request failed: {exc}") from exc
    _raise_for_status(response)
    payload = response.json()
    if "errors" in payload and payload["errors"]:
        first = payload["errors"][0]
        message = str(first.get("message", "unknown Linear GraphQL error"))
        ext = first.get("extensions") or {}
        code = str(ext.get("code", "")).lower()
        if code in {"authentication_error", "unauthenticated"}:
            raise AuthError(f"Linear GraphQL auth error: {message}")
        if code == "ratelimited":
            raise RateLimitError(f"Linear GraphQL rate limited: {message}")
        raise UpstreamError(f"Linear GraphQL error: {message}")
    return payload.get("data") or {}


_ISSUES_QUERY = """
query Issues($first: Int!, $filter: IssueFilter) {
  issues(first: $first, filter: $filter) {
    nodes {
      id identifier title priority estimate url createdAt updatedAt
      state { id name type }
      team { id key name }
      assignee { id name email }
    }
  }
}
"""

_CREATE_ISSUE_MUTATION = """
mutation IssueCreate($input: IssueCreateInput!) {
  issueCreate(input: $input) {
    success
    issue { id identifier title url }
  }
}
"""

_TEAMS_QUERY = """
query Teams($first: Int!) {
  teams(first: $first) {
    nodes { id key name description }
  }
}
"""

_PROJECTS_QUERY = """
query Projects($first: Int!) {
  projects(first: $first) {
    nodes { id name state startDate targetDate url description }
  }
}
"""


def _issue_slim(issue: dict[str, Any]) -> dict[str, Any]:
    state = issue.get("state") or {}
    team = issue.get("team") or {}
    assignee = issue.get("assignee") or {}
    return {
        "id": issue.get("id"),
        "identifier": issue.get("identifier"),
        "title": issue.get("title"),
        "priority": issue.get("priority"),
        "estimate": issue.get("estimate"),
        "url": issue.get("url"),
        "state": state.get("name"),
        "state_type": state.get("type"),
        "team": team.get("key") or team.get("name"),
        "assignee": assignee.get("name"),
        "created_at": issue.get("createdAt"),
        "updated_at": issue.get("updatedAt"),
    }


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_issues(
        team_id: Annotated[str, Field(description="Linear team id")] = "",
        limit: Annotated[int, Field(ge=1, le=100)] = 20,
    ) -> dict:
        """List Linear issues. Offline mode returns locally-created issues for the team."""
        if is_offline():
            if not team_id:
                return {"issues": []}
            stored = await local_store.list_all("linear", f"issues:{team_id}")
            issues = [row["value"] for row in stored][:limit]
            return {
                "issues": [
                    {
                        "identifier": i["identifier"],
                        "title": i["title"],
                        "state": i["state"]["name"],
                    }
                    for i in issues
                ]
            }
        query = "query Issues($first:Int){issues(first:$first){nodes{id identifier title state{name} team{id}}}}"
        async with make_client("linear", timeout=_TIMEOUT) as c:
            r = await c.post(
                _BASE, headers=_headers(), json={"query": query, "variables": {"first": limit}}
            )
            _raise_for(r)
            j = r.json()
        nodes = (((j.get("data") or {}).get("issues") or {}).get("nodes")) or []
        return {
            "issues": [
                {
                    "identifier": n["identifier"],
                    "title": n["title"],
                    "state": (n.get("state") or {}).get("name"),
                }
                for n in nodes
            ]
        }

    @mcp.tool
    async def create_issue(
        team_id: Annotated[str, Field(min_length=1, description="Linear team id")],
        title: Annotated[str, Field(min_length=1, description="issue title")],
        description: Annotated[str | None, Field(description="issue body")] = None,
    ) -> dict:
        """Create a Linear issue. Offline mode persists to local state."""
        if is_offline():
            col = f"issues:{team_id}"
            n = local_store.next_id("linear", col)
            iid = f"OFF-{n:03d}"
            issue = {
                "id": iid,
                "identifier": iid,
                "title": title,
                "description": description,
                "state": {"name": "Todo"},
                "team": {"id": team_id},
            }
            await local_store.put("linear", col, iid, issue)
            return {
                "id": iid,
                "identifier": iid,
                "title": title,
                "url": f"https://linear.app/offline/issue/{iid}",
            }
        query = "mutation IssueCreate($input: IssueCreateInput!){issueCreate(input:$input){issue{id identifier title url state{name}}}}"
        variables = {"input": {"teamId": team_id, "title": title, "description": description}}
        async with make_client("linear", timeout=_TIMEOUT) as c:
            r = await c.post(
                _BASE, headers=_headers(), json={"query": query, "variables": variables}
            )
            _raise_for(r)
            j = r.json()
        i = (((j.get("data") or {}).get("issueCreate") or {}).get("issue")) or {}
        return {
            "id": i.get("id"),
            "identifier": i.get("identifier"),
            "title": i.get("title"),
            "url": i.get("url"),
        }

    @mcp.tool
    async def list_teams(
        first: Annotated[int, Field(description="Max teams to return (1-100)")] = 50,
    ) -> dict:
        """List Linear teams."""
        async with make_client("linear", timeout=30.0) as client:
            data = await _graphql(client, _TEAMS_QUERY, {"first": _clamp(first)})
        nodes = ((data.get("teams") or {}).get("nodes")) or []
        teams = [
            {
                "id": n.get("id"),
                "key": n.get("key"),
                "name": n.get("name"),
                "description": n.get("description"),
            }
            for n in nodes
        ]
        return {"teams": teams, "count": len(teams)}

    @mcp.tool
    async def list_projects(
        first: Annotated[int, Field(description="Max projects to return (1-100)")] = 50,
    ) -> dict:
        """List Linear projects."""
        async with make_client("linear", timeout=30.0) as client:
            data = await _graphql(client, _PROJECTS_QUERY, {"first": _clamp(first)})
        nodes = ((data.get("projects") or {}).get("nodes")) or []
        projects = [
            {
                "id": n.get("id"),
                "name": n.get("name"),
                "state": n.get("state"),
                "start_date": n.get("startDate"),
                "target_date": n.get("targetDate"),
                "url": n.get("url"),
                "description": n.get("description"),
            }
            for n in nodes
        ]
        return {"projects": projects, "count": len(projects)}
