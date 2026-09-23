from __future__ import annotations

from mcp_common.http import is_offline

from mcp_common import local_store

import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from pydantic import Field

from mcp_common.errors import AuthError, ConfigError, NotFoundError, RateLimitError, UpstreamError

_BASE = "https://api.stripe.com/v1"
_TIMEOUT = 30.0


def _key() -> str:
    v = os.environ.get("STRIPE_SECRET_KEY")
    if not v:
        raise ConfigError("STRIPE_SECRET_KEY is not set")
    return v


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_key()}"}


def _raise_for(r: httpx.Response) -> None:
    if r.status_code < 400:
        return
    if r.status_code in (401, 403):
        raise AuthError(f"stripe auth failed: {r.text[:200]}")
    if r.status_code == 404:
        raise NotFoundError(f"stripe not found: {r.text[:200]}")
    if r.status_code == 429:
        raise RateLimitError(f"stripe rate-limited: {r.text[:200]}")
    raise UpstreamError(f"stripe {r.status_code}: {r.text[:200]}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_customers(
        limit: Annotated[int, Field(description="Max customers to return", ge=1, le=100)] = 20,
    ) -> dict:
        """List Stripe customers."""
        async with make_client("stripe", timeout=_TIMEOUT) as client:
            r = await client.get(f"{_BASE}/customers", headers=_headers(), params={"limit": limit})
        _raise_for(r)
        return {
            "customers": [
                {"id": c.get("id"), "email": c.get("email"), "name": c.get("name"), "created": c.get("created")}
                for c in r.json().get("data", [])
            ]
        }

    @mcp.tool
    async def list_charges(
        limit: Annotated[int, Field(ge=1, le=100)] = 10,
        customer: Annotated[str | None, Field(description="filter by customer id")] = None,
    ) -> dict:
        """List Stripe charges. Offline mode returns locally-created charges."""
        if is_offline():
            stored = await local_store.list_all("stripe", "charges")
            charges = [row["value"] for row in stored]
            if customer:
                charges = [c for c in charges if c.get("customer") == customer]
            return {"data": charges[:limit], "has_more": False}
        params = {"limit": limit}
        if customer:
            params["customer"] = customer
        async with make_client("stripe", timeout=_TIMEOUT) as c:
            r = await c.get(f"{_BASE}/v1/charges", headers=_headers(), params=params)
            _raise_for(r)
            j = r.json()
        return {"data": [{"id": ch["id"], "amount": ch["amount"], "currency": ch["currency"], "status": ch.get("status"), "customer": ch.get("customer")} for ch in j.get("data", [])], "has_more": j.get("has_more", False)}

    @mcp.tool
    async def list_subscriptions(
        limit: Annotated[int, Field(description="Max subscriptions to return", ge=1, le=100)] = 20,
    ) -> dict:
        """List Stripe subscriptions."""
        async with make_client("stripe", timeout=_TIMEOUT) as client:
            r = await client.get(f"{_BASE}/subscriptions", headers=_headers(), params={"limit": limit})
        _raise_for(r)
        return {
            "subscriptions": [
                {
                    "id": s.get("id"),
                    "status": s.get("status"),
                    "customer": s.get("customer"),
                    "current_period_end": s.get("current_period_end"),
                }
                for s in r.json().get("data", [])
            ]
        }

    @mcp.tool
    async def create_payment_intent(
        amount: Annotated[int, Field(ge=1, description="amount in cents")],
        currency: Annotated[str, Field(min_length=3, max_length=3, description="ISO currency code")] = "usd",
        customer: Annotated[str | None, Field(description="stripe customer id")] = None,
    ) -> dict:
        """Create a Stripe PaymentIntent. Offline mode persists as a charge in local state."""
        if is_offline():
            col = "charges"
            n = local_store.next_id("stripe", col)
            pi_id = f"pi_offline_{n}"
            ch_id = f"ch_offline_{n}"
            charge = {"id": ch_id, "amount": amount, "currency": currency, "customer": customer, "status": "succeeded", "payment_intent": pi_id}
            await local_store.put("stripe", col, ch_id, charge)
            return {"id": pi_id, "amount": amount, "currency": currency, "customer": customer, "status": "succeeded", "charge_id": ch_id}
        data = {"amount": str(amount), "currency": currency}
        if customer:
            data["customer"] = customer
        async with make_client("stripe", timeout=_TIMEOUT) as c:
            r = await c.post(f"{_BASE}/v1/payment_intents", headers=_headers(), data=data)
            _raise_for(r)
            j = r.json()
        return {"id": j.get("id"), "amount": j.get("amount"), "currency": j.get("currency"), "customer": j.get("customer"), "status": j.get("status")}

