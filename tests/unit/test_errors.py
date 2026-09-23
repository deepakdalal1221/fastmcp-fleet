from __future__ import annotations

import pytest
from mcp_common.errors import (
    AuthError,
    ConfigError,
    NotFoundError,
    RateLimitError,
    UpstreamError,
    ValidationError,
)


@pytest.mark.parametrize(
    "cls,expected_status,expected_code",
    [
        (ConfigError, 500, "config_error"),
        (AuthError, 401, "unauthorized"),
        (ValidationError, 400, "invalid_argument"),
        (NotFoundError, 404, "not_found"),
        (RateLimitError, 429, "rate_limited"),
        (UpstreamError, 502, "upstream_error"),
    ],
)
def test_error_shapes(cls, expected_status, expected_code):
    err = cls("boom")
    payload = err.to_payload()
    assert err.http_status == expected_status
    assert payload["code"] == expected_code
    assert payload["message"] == "boom"
