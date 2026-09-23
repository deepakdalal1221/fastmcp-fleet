from __future__ import annotations

import hmac

from mcp_common.errors import AuthError


def verify_bearer(presented: str | None, expected: str) -> None:
    if not expected:
        return
    if not presented:
        raise AuthError("missing bearer token")
    scheme, _, token = presented.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AuthError("malformed bearer token")
    if not hmac.compare_digest(token, expected):
        raise AuthError("invalid bearer token")
