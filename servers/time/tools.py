from __future__ import annotations

from datetime import datetime
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastmcp import FastMCP
from pydantic import Field

from mcp_common.errors import ValidationError


def _zone(tz: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz)
    except ZoneInfoNotFoundError as exc:
        raise ValidationError(f"unknown timezone: {tz}") from exc


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def now(
        tz: Annotated[str, Field(description="IANA timezone name (e.g. UTC, America/Los_Angeles)")] = "UTC",
    ) -> dict:
        """Return the current time in the given IANA timezone as ISO-8601."""
        dt = datetime.now(tz=_zone(tz))
        return {"iso": dt.isoformat(), "epoch": dt.timestamp(), "timezone": tz}

    @mcp.tool
    async def convert_timezone(
        iso: Annotated[str, Field(description="ISO-8601 datetime; naive values are treated as being in from_tz")],
        from_tz: Annotated[str, Field(description="Source IANA timezone")],
        to_tz: Annotated[str, Field(description="Target IANA timezone")],
    ) -> dict:
        """Convert an ISO-8601 datetime from one IANA timezone to another."""
        try:
            dt = datetime.fromisoformat(iso)
        except ValueError as exc:
            raise ValidationError(f"invalid ISO-8601 datetime: {iso}") from exc
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_zone(from_tz))
        return {"iso": dt.astimezone(_zone(to_tz)).isoformat(), "timezone": to_tz}

    @mcp.tool
    async def format(
        iso: Annotated[str, Field(description="ISO-8601 datetime to format")],
        fmt: Annotated[str, Field(description="strftime format string, e.g. %Y-%m-%d %H:%M:%S")],
    ) -> dict:
        """Format an ISO-8601 datetime using a strftime pattern."""
        try:
            dt = datetime.fromisoformat(iso)
        except ValueError as exc:
            raise ValidationError(f"invalid ISO-8601 datetime: {iso}") from exc
        return {"formatted": dt.strftime(fmt)}

    @mcp.tool
    async def parse(
        text: Annotated[str, Field(description="Datetime string to parse")],
        fmt: Annotated[str, Field(description="strptime format string matching the input")],
        tz: Annotated[str, Field(description="IANA timezone to attach if the parsed value is naive")] = "UTC",
    ) -> dict:
        """Parse a datetime string with strptime and return it as ISO-8601 in the given timezone."""
        try:
            dt = datetime.strptime(text, fmt)
        except ValueError as exc:
            raise ValidationError(f"parse failed: {exc}") from exc
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_zone(tz))
        return {"iso": dt.isoformat()}
