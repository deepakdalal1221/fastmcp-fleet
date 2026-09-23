from __future__ import annotations

import argparse
import importlib
import os

from fastmcp import FastMCP

from mcp_common.config import ServerSettings
from mcp_common.errors import ConfigError
from mcp_common.health import register_health
from mcp_common.logging import get_logger, setup_logging
from mcp_common.middleware import BearerAuthMiddleware, RateLimitMiddleware, TimingLoggingMiddleware
from mcp_common.registry import load_manifest
from mcp_common.server import run

GATEWAY_ID = "gateway"
GATEWAY_VERSION = "0.1.0"


def _mount_server(gateway: FastMCP, server_id: str) -> tuple[str, int]:
    manifest = load_manifest(server_id)
    tools_mod = importlib.import_module(f"servers.{server_id}.tools")
    sub = FastMCP(name=manifest.name)
    tools_mod.register_tools(sub)

    try:
        gateway.mount(sub, namespace=server_id)
    except Exception as exc:
        raise ConfigError(f"failed to mount server '{server_id}' on gateway: {exc}") from exc
    return server_id, len(manifest.tools)


def build_gateway(server_ids: list[str]) -> tuple[FastMCP, ServerSettings, list[tuple[str, int]]]:
    cfg = ServerSettings(server_id=GATEWAY_ID)
    setup_logging(level=cfg.log_level, fmt=cfg.log_format)
    log = get_logger("gateway")
    log.info(
        "gateway.init",
        version=GATEWAY_VERSION,
        transport=cfg.transport,
        port=cfg.port,
        servers=server_ids,
    )
    gateway = FastMCP(name="MCP Gateway")
    try:
        gateway.add_middleware(TimingLoggingMiddleware(GATEWAY_ID))
        if cfg.auth_token:
            gateway.add_middleware(BearerAuthMiddleware(GATEWAY_ID, cfg.auth_token))
            log.info("gateway.auth_enabled")
        else:
            log.warning("gateway.auth_disabled", note="MCP_AUTH_TOKEN not set; gateway is unauthenticated")
        if cfg.rate_limit_enabled:
            gateway.add_middleware(
                RateLimitMiddleware(
                    GATEWAY_ID,
                    capacity=cfg.rate_limit_capacity,
                    refill_per_sec=cfg.rate_limit_refill_per_sec,
                    per_tool=cfg.rate_limit_per_tool,
                )
            )
    except AttributeError:
        log.warning("middleware.unsupported", note="FastMCP version lacks add_middleware")
    register_health(gateway, GATEWAY_ID, GATEWAY_VERSION)

    mounted: list[tuple[str, int]] = []
    for sid in server_ids:
        try:
            mounted.append(_mount_server(gateway, sid))
            log.info("gateway.mounted", server=sid)
        except Exception as exc:
            log.exception("gateway.mount_failed", server=sid, error=str(exc))
    return gateway, cfg, mounted


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="mcp-gateway")
    parser.add_argument("--transport", choices=["streamable-http", "stdio", "sse"])
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--servers", help="comma-separated server ids to mount")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    raw = args.servers or os.environ.get("GATEWAY_SERVERS", "fetch,filesystem,time")
    server_ids = [s.strip() for s in raw.split(",") if s.strip()]

    gateway, cfg, mounted = build_gateway(server_ids)

    if args.transport:
        cfg = cfg.model_copy(update={"transport": args.transport})
    if args.host:
        cfg = cfg.model_copy(update={"host": args.host})
    if args.port:
        cfg = cfg.model_copy(update={"port": args.port})

    print(f"gateway ready: {len(mounted)} servers mounted -> {mounted}")
    run(gateway, cfg)


if __name__ == "__main__":
    main()
