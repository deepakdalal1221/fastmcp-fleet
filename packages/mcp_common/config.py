from __future__ import annotations

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

Transport = Literal["streamable-http", "stdio", "sse"]
LogFormat = Literal["json", "text"]


class ServerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MCP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    server_id: str = Field(default="unknown")
    env: Literal["dev", "staging", "prod"] = "dev"
    transport: Transport = "streamable-http"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"
    log_format: LogFormat = "json"
    auth_token: str = ""
    request_timeout_seconds: float = 30.0
    max_concurrent_requests: int = 100
    rate_limit_enabled: bool = True
    rate_limit_capacity: float = 60.0
    rate_limit_refill_per_sec: float = 1.0
    rate_limit_per_tool: bool = True
    seed: int = 42
    offline: bool = False
    fixture_dir: str = ""
