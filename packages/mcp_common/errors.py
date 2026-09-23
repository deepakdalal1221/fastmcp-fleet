from __future__ import annotations


class McpError(Exception):
    code: str = "internal_error"
    http_status: int = 500

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_payload(self) -> dict:
        return {"code": self.code, "message": self.message, "details": self.details}


class ConfigError(McpError):
    code = "config_error"
    http_status = 500


class AuthError(McpError):
    code = "unauthorized"
    http_status = 401


class ValidationError(McpError):
    code = "invalid_argument"
    http_status = 400


class NotFoundError(McpError):
    code = "not_found"
    http_status = 404


class RateLimitError(McpError):
    code = "rate_limited"
    http_status = 429


class UpstreamError(McpError):
    code = "upstream_error"
    http_status = 502
