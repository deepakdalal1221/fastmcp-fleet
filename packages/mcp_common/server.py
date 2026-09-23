from __future__ import annotations

import argparse
from typing import Any

from fastmcp import FastMCP

from mcp_common.config import ServerSettings
from mcp_common.health import register_health
from mcp_common.logging import get_logger, setup_logging
from mcp_common.middleware import RateLimitMiddleware, TimingLoggingMiddleware
from mcp_common.registry import ServerManifest, load_manifest


def create_server(
    server_id: str, *, settings: ServerSettings | None = None
) -> tuple[FastMCP, ServerManifest, ServerSettings]:
    manifest = load_manifest(server_id)
    cfg = settings or ServerSettings(server_id=server_id, port=manifest.port)
    setup_logging(level=cfg.log_level, fmt=cfg.log_format)
    log = get_logger("mcp_common.server")
    log.info(
        "server.init",
        server=server_id,
        version=manifest.version,
        transport=cfg.transport,
        port=cfg.port,
    )
    mcp = FastMCP(name=manifest.name)
    try:
        mcp.add_middleware(TimingLoggingMiddleware(server_id))
        if cfg.rate_limit_enabled:
            mcp.add_middleware(
                RateLimitMiddleware(
                    server_id,
                    capacity=cfg.rate_limit_capacity,
                    refill_per_sec=cfg.rate_limit_refill_per_sec,
                    per_tool=cfg.rate_limit_per_tool,
                )
            )
    except AttributeError:
        log.warning("middleware.unsupported", note="FastMCP version lacks add_middleware")
    register_health(mcp, server_id, manifest.version)
    return mcp, manifest, cfg


def parse_runtime_args(default_port: int) -> ServerSettings:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=["streamable-http", "stdio", "sse"])
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--log-level")
    parser.add_argument("--log-format", choices=["json", "text"])
    args, _ = parser.parse_known_args()

    overrides: dict[str, Any] = {}
    if args.transport:
        overrides["transport"] = args.transport
    if args.host:
        overrides["host"] = args.host
    if args.port is not None:
        overrides["port"] = args.port
    if args.log_level:
        overrides["log_level"] = args.log_level
    if args.log_format:
        overrides["log_format"] = args.log_format

    base = ServerSettings()
    if base.port == 8000:
        base = base.model_copy(update={"port": default_port})
    if overrides:
        base = base.model_copy(update=overrides)
    return base


def run(mcp: FastMCP, cfg: ServerSettings) -> None:
    if cfg.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(transport=cfg.transport, host=cfg.host, port=cfg.port)
