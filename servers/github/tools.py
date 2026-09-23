from __future__ import annotations

from mcp_common import local_store
from mcp_common.http import is_offline, make_client

import os
from typing import Annotated, Any

import httpx
from fastmcp import FastMCP
from pydantic import Field

from mcp_common.errors import (
    AuthError,
    ConfigError,
    NotFoundError,
    RateLimitError,
    UpstreamError,
    ValidationError,
)

_API_BASE = "https://api.github.com"
_DEFAULT_PER_PAGE = 30
_MAX_PER_PAGE = 100


def _token() -> str:
    tok = os.environ.get("GITHUB_TOKEN", "").strip()
    if not tok:
        raise ConfigError("GITHUB_TOKEN is not set")
    return tok


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_token()}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "fastmcp-platform/0.1.0",
    }


def _clamp_per_page(n: int) -> int:
    if n < 1:
        return 1
    if n > _MAX_PER_PAGE:
        return _MAX_PER_PAGE
    return n


async def _get(client: httpx.AsyncClient, path: str, params: dict[str, Any] | None = None) -> Any:
    try:
        r = await client.get(f"{_API_BASE}{path}", params=params, headers=_headers())
    except httpx.RequestError as exc:
        raise UpstreamError(f"github request failed: {exc}") from exc
    if r.status_code == 401:
        raise AuthError("github token rejected")
    if r.status_code == 403 and r.headers.get("X-RateLimit-Remaining") == "0":
        raise RateLimitError("github rate limit exceeded")
    if r.status_code == 404:
        raise NotFoundError(f"github resource not found: {path}")
    if r.status_code >= 500:
        raise UpstreamError(f"github {r.status_code}: {r.text[:200]}")
    if r.status_code >= 400:
        raise UpstreamError(f"github {r.status_code}: {r.text[:200]}")
    return r.json()


async def _post(client: httpx.AsyncClient, path: str, body: dict[str, Any]) -> Any:
    try:
        r = await client.post(f"{_API_BASE}{path}", json=body, headers=_headers())
    except httpx.RequestError as exc:
        raise UpstreamError(f"github request failed: {exc}") from exc
    if r.status_code == 401:
        raise AuthError("github token rejected")
    if r.status_code == 403:
        raise UpstreamError("github forbidden (check token scopes)")
    if r.status_code == 404:
        raise NotFoundError(f"github resource not found: {path}")
    if r.status_code >= 400:
        raise UpstreamError(f"github {r.status_code}: {r.text[:200]}")
    return r.json()


def _repo_slim(repo: dict[str, Any]) -> dict[str, Any]:
    return {
        "full_name": repo.get("full_name"),
        "name": repo.get("name"),
        "private": repo.get("private"),
        "description": repo.get("description"),
        "default_branch": repo.get("default_branch"),
        "stars": repo.get("stargazers_count"),
        "forks": repo.get("forks_count"),
        "open_issues": repo.get("open_issues_count"),
        "language": repo.get("language"),
        "html_url": repo.get("html_url"),
    }


def _issue_slim(issue: dict[str, Any]) -> dict[str, Any]:
    return {
        "number": issue.get("number"),
        "title": issue.get("title"),
        "state": issue.get("state"),
        "author": (issue.get("user") or {}).get("login"),
        "labels": [lab.get("name") for lab in issue.get("labels") or []],
        "html_url": issue.get("html_url"),
    }


def _pr_slim(pr: dict[str, Any]) -> dict[str, Any]:
    return {
        "number": pr.get("number"),
        "title": pr.get("title"),
        "state": pr.get("state"),
        "draft": pr.get("draft"),
        "author": (pr.get("user") or {}).get("login"),
        "base": (pr.get("base") or {}).get("ref"),
        "head": (pr.get("head") or {}).get("ref"),
        "html_url": pr.get("html_url"),
    }


def _commit_slim(commit: dict[str, Any]) -> dict[str, Any]:
    c = commit.get("commit") or {}
    author = c.get("author") or {}
    return {
        "sha": commit.get("sha"),
        "message": (c.get("message") or "").splitlines()[0][:200],
        "author": author.get("name"),
        "date": author.get("date"),
        "html_url": commit.get("html_url"),
    }


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_repos(
        owner: Annotated[str, Field(description="User or organization login")],
        per_page: Annotated[int, Field(description="Page size (1-100)")] = _DEFAULT_PER_PAGE,
    ) -> dict:
        """List repositories owned by a user or organization."""
        params = {"per_page": _clamp_per_page(per_page), "type": "all"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            data = await _get(client, f"/users/{owner}/repos", params=params)
        return {"owner": owner, "repos": [_repo_slim(r) for r in data]}

    @mcp.tool
    async def get_repo(
        owner: Annotated[str, Field(description="Repo owner login")],
        repo: Annotated[str, Field(description="Repo name")],
    ) -> dict:
        """Get metadata for a single repository."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            data = await _get(client, f"/repos/{owner}/{repo}")
        return _repo_slim(data)

    @mcp.tool
    async def list_issues(
        owner: Annotated[str, Field(min_length=1, description="repo owner")],
        repo: Annotated[str, Field(min_length=1, description="repo name")],
        state: Annotated[str, Field(description="open | closed | all")] = "open",
        per_page: Annotated[int, Field(ge=1, le=100)] = 30,
    ) -> dict:
        """List GitHub issues. In offline mode, returns locally-created issues from the store."""
        if is_offline():
            col = f"issues:{owner}/{repo}"
            stored = await local_store.list_all("github", col)
            issues = [row["value"] for row in stored]
            if state != "all":
                issues = [i for i in issues if i.get("state") == state]
            return {"issues": issues[:per_page]}
        async with make_client("github", timeout=_TIMEOUT) as c:
            r = await c.get(
                f"{_BASE}/repos/{owner}/{repo}/issues",
                headers=_headers(),
                params={"state": state, "per_page": per_page},
            )
            _raise_for(r)
            data = r.json()
        return {
            "issues": [
                {
                    "number": i["number"],
                    "title": i["title"],
                    "state": i.get("state"),
                    "user": (i.get("user") or {}).get("login"),
                    "html_url": i.get("html_url"),
                }
                for i in data
            ]
        }

    @mcp.tool
    async def create_issue(
        owner: Annotated[str, Field(min_length=1, description="repo owner")],
        repo: Annotated[str, Field(min_length=1, description="repo name")],
        title: Annotated[str, Field(min_length=1, description="issue title")],
        body: Annotated[str | None, Field(description="markdown body")] = None,
    ) -> dict:
        """Create a GitHub issue. In offline mode, persists to local state for later reads."""
        if is_offline():
            col = f"issues:{owner}/{repo}"
            n = local_store.next_id("github", col)
            issue = {
                "number": n,
                "title": title,
                "body": body,
                "state": "open",
                "html_url": f"https://github.com/{owner}/{repo}/issues/{n}",
                "user": {"login": "offline-user"},
            }
            await local_store.put("github", col, str(n), issue)
            return issue
        payload = {"title": title}
        if body is not None:
            payload["body"] = body
        async with make_client("github", timeout=_TIMEOUT) as c:
            r = await c.post(
                f"{_BASE}/repos/{owner}/{repo}/issues",
                headers=_headers(),
                json=payload,
            )
            _raise_for(r)
            i = r.json()
        return {
            "number": i["number"],
            "title": i["title"],
            "state": i.get("state"),
            "html_url": i.get("html_url"),
        }

    @mcp.tool
    async def list_pulls(
        owner: Annotated[str, Field(description="Repo owner login")],
        repo: Annotated[str, Field(description="Repo name")],
        state: Annotated[str, Field(description="open, closed, or all")] = "open",
        per_page: Annotated[int, Field(description="Page size (1-100)")] = _DEFAULT_PER_PAGE,
    ) -> dict:
        """List pull requests on a repository."""
        if state not in {"open", "closed", "all"}:
            raise ValidationError(f"state must be one of open/closed/all: {state!r}")
        params = {"state": state, "per_page": _clamp_per_page(per_page)}
        async with httpx.AsyncClient(timeout=30.0) as client:
            data = await _get(client, f"/repos/{owner}/{repo}/pulls", params=params)
        return {"repo": f"{owner}/{repo}", "state": state, "pulls": [_pr_slim(p) for p in data]}

    @mcp.tool
    async def get_pr(
        owner: Annotated[str, Field(description="Repo owner login")],
        repo: Annotated[str, Field(description="Repo name")],
        number: Annotated[int, Field(description="Pull request number")],
    ) -> dict:
        """Get a single pull request by number."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            data = await _get(client, f"/repos/{owner}/{repo}/pulls/{number}")
        slim = _pr_slim(data)
        slim.update(
            {
                "merged": data.get("merged"),
                "mergeable": data.get("mergeable"),
                "additions": data.get("additions"),
                "deletions": data.get("deletions"),
                "changed_files": data.get("changed_files"),
            }
        )
        return slim

    @mcp.tool
    async def list_commits(
        owner: Annotated[str, Field(description="Repo owner login")],
        repo: Annotated[str, Field(description="Repo name")],
        per_page: Annotated[int, Field(description="Page size (1-100)")] = _DEFAULT_PER_PAGE,
    ) -> dict:
        """List commits on the default branch of a repository."""
        params = {"per_page": _clamp_per_page(per_page)}
        async with httpx.AsyncClient(timeout=30.0) as client:
            data = await _get(client, f"/repos/{owner}/{repo}/commits", params=params)
        return {"repo": f"{owner}/{repo}", "commits": [_commit_slim(c) for c in data]}


