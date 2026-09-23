from __future__ import annotations

from mcp_common.http import is_offline, make_client

from mcp_common import local_store

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from pydantic import Field

from mcp_common.errors import AuthError, ConfigError, NotFoundError, RateLimitError, UpstreamError

_BASE = "https://api.pagerduty.com"
_TIMEOUT = 30.0


def _token() -> str:
    v = os.environ.get("PAGERDUTY_TOKEN")
    if not v:
        raise ConfigError("PAGERDUTY_TOKEN is not set")
    return v


def _headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    h = {
        "Authorization": f"Token token={_token()}",
        "Accept": "application/vnd.pagerduty+json;version=2",
        "Content-Type": "application/json",
    }
    if extra:
        h.update(extra)
    return h


def _raise_for(r: httpx.Response) -> None:
    if r.status_code < 400:
        return
    if r.status_code in (401, 403):
        raise AuthError(f"pagerduty auth failed: {r.text[:200]}")
    if r.status_code == 404:
        raise NotFoundError(f"pagerduty not found: {r.text[:200]}")
    if r.status_code == 429:
        raise RateLimitError(f"pagerduty rate-limited: {r.text[:200]}")
    raise UpstreamError(f"pagerduty {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_incidents(
        service_id: Annotated[str | None, Field(description="filter by service id")] = None,
        status: Annotated[str, Field(description="triggered | acknowledged | resolved | all")] = "triggered",
        limit: Annotated[int, Field(ge=1, le=100)] = 20,
    ) -> dict:
        """List PagerDuty incidents. Offline mode returns locally-created incidents."""
        if is_offline():
            if service_id:
                stored = await local_store.list_all("pagerduty", f"incidents:{service_id}")
            else:
                stored = []
            incidents = [row["value"] for row in stored]
            if status != "all":
                incidents = [i for i in incidents if i.get("status") == status]
            incidents = incidents[:limit]
            return {"incidents": [{"id": i["id"], "title": i["title"], "urgency": i["urgency"], "status": i["status"]} for i in incidents]}
        params = {"limit": limit, "statuses[]": status if status != "all" else None}
        if service_id:
            params["service_ids[]"] = service_id
        params = {k: v for k, v in params.items() if v is not None}
        async with make_client("pagerduty", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/incidents", headers=_headers(), params=params)
            _raise_for(r)
            j = r.json()
        return {"incidents": [{"id": i.get("id"), "title": i.get("title"), "urgency": i.get("urgency"), "status": i.get("status")} for i in j.get("incidents", [])]}

    @mcp.tool
    async def create_incident(
        service_id: Annotated[str, Field(min_length=1, description="PagerDuty service id")],
        title: Annotated[str, Field(min_length=1, description="incident title")],
        urgency: Annotated[str, Field(description="high | low")] = "high",
        details: Annotated[str | None, Field(description="incident details")] = None,
    ) -> dict:
        """Create a PagerDuty incident. Offline mode persists to local state."""
        if is_offline():
            col = f"incidents:{service_id}"
            n = local_store.next_id("pagerduty", col)
            iid = f"PDOFF{n:04d}"
            inc = {"id": iid, "title": title, "urgency": urgency, "status": "triggered", "service": {"id": service_id}, "description": details}
            await local_store.put("pagerduty", col, iid, inc)
            return {"id": iid, "title": title, "urgency": urgency, "status": "triggered"}
        payload = {"incident": {"type": "incident", "title": title, "service": {"id": service_id, "type": "service_reference"}, "urgency": urgency}}
        if details is not None:
            payload["incident"]["body"] = {"type": "incident_body", "details": details}
        async with make_client("pagerduty", timeout=_TIMEOUT) as c:
            r = await c.post(f"{_BASE}/incidents", headers={**_headers(), "From": os.environ.get("PAGERDUTY_FROM", "offline@mcp")}, json=payload)
            _raise_for(r)
            j = r.json()
        i = j.get("incident", {})
        return {"id": i.get("id"), "title": i.get("title"), "urgency": i.get("urgency"), "status": i.get("status")}

    @mcp.tool
    async def list_services(
        limit: Annotated[int, Field(description="Max services to return", ge=1, le=100)] = 25,
    ) -> dict:
        """List PagerDuty services."""
        async with make_client("pagerduty", timeout=_TIMEOUT) as client:
            r = await client.get(f"{_BASE}/services", headers=_headers(), params={"limit": limit})
        _raise_for(r)
        return {
            "services": [
                {
                    "id": s.get("id"),
                    "name": s.get("name"),
                    "status": s.get("status"),
                    "description": s.get("description"),
                }
                for s in r.json().get("services", [])
            ]
        }
