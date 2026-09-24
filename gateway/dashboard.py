"""Fleet dashboard: sandbox UI for the fastmcp-fleet gateway.

Advanced features: command palette (⌘K), state inspector, metrics dashboard,
favorites, plus everything from v3 (fill demo, schema panels, copy snippets,
keyboard shortcuts).
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
import yaml
from mcp_common import local_store
from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY = REPO_ROOT / "registry" / "servers"
STATE_DIR = Path(os.environ.get("MCP_STATE_DIR", REPO_ROOT / "state"))
GATEWAY_URL = "http://localhost:9000/mcp"


def _load_manifests() -> list[dict[str, Any]]:
    out = []
    for f in sorted(REGISTRY.glob("*.yaml")):
        try:
            m = yaml.safe_load(f.read_text())
            out.append(
                {
                    "id": m.get("id", f.stem),
                    "name": m.get("name", f.stem),
                    "category": m.get("category", "misc"),
                    "port": m.get("port"),
                    "status": m.get("status", "unknown"),
                    "tools": m.get("tools", []),
                    "description": m.get("description", ""),
                }
            )
        except Exception:
            continue
    return out


async def _mcp_init(client: httpx.AsyncClient) -> str:
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "dashboard", "version": "1"},
        },
    }
    r = await client.post(
        GATEWAY_URL, json=body, headers={"Accept": "application/json, text/event-stream"}
    )
    session_id = r.headers.get("mcp-session-id")
    if not session_id:
        raise HTTPException(502, "gateway not reachable — is `make dev` running on :9000?")
    await client.post(
        GATEWAY_URL,
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        headers={"Accept": "application/json, text/event-stream", "mcp-session-id": session_id},
    )
    return session_id


def _parse_sse(text: str) -> dict:
    for line in text.splitlines():
        if line.startswith("data:"):
            return json.loads(line[5:].strip())
    return {}


async def _mcp_call(client: httpx.AsyncClient, session_id: str, method: str, params: dict) -> dict:
    body = {"jsonrpc": "2.0", "id": str(uuid.uuid4()), "method": method, "params": params}
    r = await client.post(
        GATEWAY_URL,
        json=body,
        headers={"Accept": "application/json, text/event-stream", "mcp-session-id": session_id},
    )
    return _parse_sse(r.text)


async def api_servers(request: Request):
    return JSONResponse(_load_manifests())


async def api_tools(request: Request):
    try:
        async with httpx.AsyncClient(timeout=30.0) as c:
            sid = await _mcp_init(c)
            resp = await _mcp_call(c, sid, "tools/list", {})
            tools = resp.get("result", {}).get("tools", [])
    except HTTPException:
        return JSONResponse({"total": 0, "tools": [], "grouped": {}, "error": "gateway offline"})
    grouped: dict[str, list[dict]] = {}
    for t in tools:
        name = t["name"]
        prefix = name.split("_", 1)[0]
        grouped.setdefault(prefix, []).append(t)
    return JSONResponse({"total": len(tools), "tools": tools, "grouped": grouped})


async def api_invoke(request: Request):
    body = await request.json()
    tool_name = body.get("tool_name")
    arguments = body.get("arguments", {})
    t0 = time.perf_counter()
    async with httpx.AsyncClient(timeout=60.0) as c:
        sid = await _mcp_init(c)
        resp = await _mcp_call(c, sid, "tools/call", {"name": tool_name, "arguments": arguments})
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    if "error" in resp:
        return JSONResponse({"error": resp["error"], "elapsed_ms": elapsed_ms}, status_code=400)
    result = resp.get("result", {})
    result["_elapsed_ms"] = elapsed_ms
    return JSONResponse(result)


def _find_state_db(sid: str) -> Path | None:
    for p in (STATE_DIR / f"{sid}.db", REPO_ROOT / "servers" / sid / "state.db"):
        if p.exists():
            return p
    return None


async def api_state(request: Request):
    sid = request.path_params["sid"]
    p = _find_state_db(sid)
    if not p:
        return JSONResponse(
            {"sid": sid, "exists": False, "buckets": [], "message": "No state.db (no writes yet)"}
        )
    try:
        con = sqlite3.connect(str(p))
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        # store schema (from mcp_common.store): PK (collection, key), value TEXT JSON
        cur.execute(
            "SELECT collection, COUNT(*) as n FROM store GROUP BY collection ORDER BY collection"
        )
        buckets = [{"name": r["collection"], "count": r["n"]} for r in cur.fetchall()]
        # If a specific bucket requested, return rows
        bucket = request.query_params.get("bucket")
        rows = []
        if bucket:
            cur.execute("SELECT key, value FROM store WHERE collection=? ORDER BY key", (bucket,))
            for r in cur.fetchall():
                try:
                    parsed = json.loads(r["value"])
                except Exception:
                    parsed = r["value"]
                rows.append({"key": r["key"], "value": parsed})
        con.close()
        return JSONResponse(
            {
                "sid": sid,
                "exists": True,
                "path": str(p),
                "buckets": buckets,
                "rows": rows,
                "bucket": bucket,
            }
        )
    except sqlite3.DatabaseError as e:
        return JSONResponse(
            {"sid": sid, "exists": True, "error": str(e), "buckets": [], "rows": []}
        )


async def api_reset(request: Request):
    sid = request.path_params["sid"]
    removed = []
    for p in (STATE_DIR / f"{sid}.db", REPO_ROOT / "servers" / sid / "state.db"):
        if p.exists():
            p.unlink()
            removed.append(str(p))
    seeded = await local_store.seed(sid)
    return JSONResponse({"removed": removed, "sid": sid, "seeded": seeded})


async def api_reset_all(request: Request):
    removed = []
    if STATE_DIR.exists():
        for f in STATE_DIR.glob("*.db"):
            f.unlink()
            removed.append(str(f))
    for sd in (REPO_ROOT / "servers").glob("*/state.db"):
        sd.unlink()
        removed.append(str(sd))
    seeded_total = 0
    for seed_file in (REPO_ROOT / "servers").glob("*/seed.json"):
        seeded_total += await local_store.seed(seed_file.parent.name)
    return JSONResponse({"removed": removed, "count": len(removed), "seeded": seeded_total})


HTML = r"""
<!doctype html>
<html><head><meta charset="utf-8"><title>fastmcp-fleet sandbox</title>
<script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.14.0/dist/cdn.min.js"></script>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font: 14px system-ui,-apple-system,sans-serif; background: #0b1220; color: #e2e8f0; padding: 20px; min-height: 100vh; }
  h1 { font-size: 22px; color: #f8fafc; }
  h2 { font-size: 17px; color: #f8fafc; margin-bottom: 4px; }
  h3 { font-size: 13px; color: #cbd5e1; margin-bottom: 10px; text-transform: uppercase; letter-spacing: 0.5px; }
  .sub { color: #94a3b8; margin-bottom: 12px; font-size: 12px; }
  a { color: #a5b4fc; text-decoration: none; } a:hover { text-decoration: underline; }
  input, textarea, button { font-family: inherit; }
  .header { display: flex; justify-content: space-between; align-items: center; gap: 20px; margin-bottom: 16px; }
  .header .kbds { color: #94a3b8; font-size: 11px; }
  .kbd { display: inline-block; background: #0b1220; border: 1px solid #334155; border-bottom-width: 2px; border-radius: 3px; padding: 1px 5px; font-size: 10px; color: #94a3b8; font-family: monospace; }
  .tabs { display: flex; gap: 4px; margin-bottom: 14px; border-bottom: 1px solid #1e293b; }
  .tab { padding: 8px 16px; cursor: pointer; color: #94a3b8; border-bottom: 2px solid transparent; font-size: 13px; font-weight: 500; }
  .tab.on { color: #a5b4fc; border-color: #6366f1; }
  .tab:hover:not(.on) { color: #cbd5e1; }
  .layout { display: grid; grid-template-columns: 1fr 300px; gap: 18px; }
  @media (max-width: 900px) { .layout { grid-template-columns: 1fr; } }
  .search { width: 100%; padding: 10px 14px; background: #1e293b; border: 1px solid #334155; border-radius: 6px; color: #e2e8f0; font-size: 14px; margin-bottom: 8px; }
  .search:focus { outline: none; border-color: #6366f1; }
  .chips { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 16px; }
  .chip { padding: 4px 10px; background: #1e293b; border: 1px solid #334155; border-radius: 12px; font-size: 12px; cursor: pointer; color: #cbd5e1; user-select: none; }
  .chip.on { background: #6366f1; border-color: #6366f1; color: white; }
  .chip:hover:not(.on) { background: #2a3554; }
  .stats { display: flex; gap: 10px; margin-bottom: 16px; flex-wrap: wrap; }
  .stat { background: #1e293b; border-radius: 6px; padding: 8px 12px; min-width: 80px; }
  .stat b { font-size: 18px; color: #a5b4fc; display: block; }
  .stat span { color: #94a3b8; font-size: 11px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 8px; }
  .card { background: #1e293b; border: 1px solid #334155; border-radius: 6px; padding: 10px 12px; cursor: pointer; transition: all 0.15s; position: relative; }
  .card:hover { border-color: #6366f1; background: #24314a; }
  .card.selected { border-color: #a5b4fc; background: #2a3554; }
  .card h3 { font-size: 14px; color: #f1f5f9; margin-bottom: 3px; text-transform: none; letter-spacing: 0; }
  .card .meta { color: #94a3b8; font-size: 11px; margin-top: 2px; }
  .card .badge { display: inline-block; padding: 1px 5px; background: #334155; border-radius: 3px; font-size: 10px; margin-right: 3px; color: #cbd5e1; }
  .card .badge.active { background: #16a34a; color: white; }
  .card .badge.pilot { background: #d97706; color: white; }
  .card .actions-row { position: absolute; top: 4px; right: 4px; display: flex; gap: 2px; opacity: 0; transition: opacity 0.15s; }
  .card:hover .actions-row, .card .actions-row.on { opacity: 1; }
  .card .icon-btn { padding: 2px 6px; font-size: 11px; background: transparent; border: 1px solid #334155; border-radius: 3px; color: #94a3b8; cursor: pointer; }
  .card .icon-btn:hover { background: #334155; color: #f1f5f9; }
  .card .icon-btn.star { color: #fbbf24; border-color: #fbbf24; }
  .panel { margin-top: 16px; background: #1e293b; border: 1px solid #334155; border-radius: 6px; padding: 18px; }
  .tool { padding: 9px 12px; background: #0f172a; border-radius: 4px; margin-bottom: 5px; cursor: pointer; border: 1px solid transparent; }
  .tool:hover { background: #172033; border-color: #334155; }
  .tool code { color: #a5b4fc; font-weight: 600; font-family: monospace; font-size: 13px; }
  .tool .desc { color: #94a3b8; font-size: 12px; margin-top: 2px; }
  .form-row { display: flex; flex-direction: column; gap: 3px; margin-bottom: 10px; }
  .form-row label { color: #cbd5e1; font-size: 12px; font-weight: 500; }
  .form-row .hint { color: #64748b; font-size: 10px; }
  .form-row input, .form-row textarea { background: #0b1220; border: 1px solid #334155; border-radius: 4px; padding: 7px 10px; color: #e2e8f0; font-family: monospace; font-size: 12px; }
  .form-row input:focus, .form-row textarea:focus { outline: none; border-color: #6366f1; }
  .actions { display: flex; gap: 8px; align-items: center; margin-top: 8px; flex-wrap: wrap; }
  button.primary { background: #6366f1; color: white; border: 0; padding: 8px 18px; border-radius: 4px; cursor: pointer; font-size: 13px; font-weight: 500; }
  button.primary:hover { background: #4f46e5; }
  button.primary:disabled { background: #4b5563; cursor: not-allowed; }
  button.ghost { background: transparent; border: 1px solid #334155; color: #cbd5e1; padding: 7px 12px; border-radius: 4px; cursor: pointer; font-size: 12px; }
  button.ghost:hover { border-color: #6366f1; color: #a5b4fc; }
  .elapsed { color: #94a3b8; font-size: 11px; margin-left: auto; }
  .details { margin-top: 12px; display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  @media (max-width: 700px) { .details { grid-template-columns: 1fr; } }
  .sec { background: #0f172a; border-radius: 4px; padding: 10px 12px; border: 1px solid #1e293b; }
  .sec h4 { font-size: 11px; color: #94a3b8; margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.5px; display: flex; justify-content: space-between; align-items: center; }
  .sec h4 .clip { cursor: pointer; color: #64748b; text-transform: none; font-weight: normal; letter-spacing: normal; }
  .sec h4 .clip:hover { color: #a5b4fc; }
  .sec pre { color: #cbd5e1; font-family: monospace; font-size: 11px; white-space: pre-wrap; word-break: break-word; max-height: 200px; overflow-y: auto; }
  .sec.response pre { color: #a7f3d0; }
  .sec.error pre { color: #fca5a5; }
  .sec.empty pre { color: #475569; font-style: italic; }
  .history { background: #1e293b; border: 1px solid #334155; border-radius: 6px; padding: 14px; }
  .hist-item { padding: 6px 8px; margin-bottom: 4px; background: #0f172a; border-radius: 3px; cursor: pointer; font-size: 12px; display: flex; justify-content: space-between; align-items: center; }
  .hist-item:hover { background: #172033; }
  .hist-item .n { color: #a5b4fc; font-family: monospace; font-size: 11px; }
  .hist-item .t { color: #94a3b8; font-size: 10px; }
  .hist-item.err .n { color: #fca5a5; }
  .empty-state { color: #64748b; font-size: 12px; text-align: center; padding: 16px 0; }
  /* Command palette */
  .cmdk-backdrop { position: fixed; inset: 0; background: rgba(0,0,0,0.6); backdrop-filter: blur(4px); z-index: 100; display: flex; align-items: flex-start; justify-content: center; padding-top: 12vh; }
  .cmdk { width: min(680px, 90vw); background: #1e293b; border: 1px solid #6366f1; border-radius: 8px; overflow: hidden; box-shadow: 0 20px 60px rgba(0,0,0,0.5); }
  .cmdk input { width: 100%; background: transparent; border: 0; border-bottom: 1px solid #334155; padding: 14px 18px; color: #e2e8f0; font-size: 16px; font-family: inherit; }
  .cmdk input:focus { outline: none; }
  .cmdk .list { max-height: 55vh; overflow-y: auto; }
  .cmdk .row { padding: 10px 18px; cursor: pointer; border-bottom: 1px solid #24314a; display: flex; align-items: center; gap: 10px; }
  .cmdk .row.sel { background: #334155; }
  .cmdk .row .type { background: #0f172a; color: #a5b4fc; padding: 2px 8px; border-radius: 3px; font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; }
  .cmdk .row .name { color: #f1f5f9; font-family: monospace; }
  .cmdk .row .desc { color: #94a3b8; font-size: 11px; margin-left: auto; }
  .cmdk .hint { padding: 8px 18px; color: #64748b; font-size: 11px; text-align: right; border-top: 1px solid #24314a; background: #0f172a; }
  /* Metrics */
  .metrics-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 12px; }
  .metric-card { background: #1e293b; padding: 14px 16px; border-radius: 6px; border: 1px solid #334155; }
  .metric-card b { color: #f1f5f9; font-size: 20px; display: block; }
  .metric-card small { color: #94a3b8; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; }
  .metric-table { width: 100%; margin-top: 10px; border-collapse: collapse; font-size: 12px; }
  .metric-table th { text-align: left; color: #94a3b8; padding: 6px 8px; border-bottom: 1px solid #334155; font-weight: 500; }
  .metric-table td { color: #cbd5e1; padding: 6px 8px; border-bottom: 1px solid #1e293b; }
  .metric-table td.n { color: #a5b4fc; font-family: monospace; }
  /* State inspector */
  .state-buckets { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 12px; }
  .state-bucket { padding: 5px 10px; background: #0f172a; border: 1px solid #334155; border-radius: 4px; font-size: 12px; cursor: pointer; font-family: monospace; }
  .state-bucket.on { background: #6366f1; border-color: #6366f1; color: white; }
  .state-row { background: #0f172a; padding: 8px 10px; border-radius: 4px; margin-bottom: 4px; font-family: monospace; font-size: 11px; }
  .state-row .k { color: #a5b4fc; }
  .state-row pre { color: #cbd5e1; margin-top: 4px; white-space: pre-wrap; word-break: break-word; }
</style>
</head><body x-data="dashboard()" x-init="init()" @keydown.window="handleKey($event)">
  <div class="header">
    <div>
      <h1>fastmcp-fleet sandbox</h1>
      <p class="sub">175 servers · <span x-text="totalTools"></span> tools · offline-first · <a href="https://github.com/deepakdalal1221/fastmcp-fleet">github</a></p>
    </div>
    <div class="kbds">
      <span class="kbd">⌘K</span> palette · <span class="kbd">/</span> search · <span class="kbd">⌘⏎</span> invoke · <span class="kbd">esc</span> back
    </div>
  </div>

  <div class="tabs">
    <div class="tab" :class="{on: view === 'grid'}" @click="view='grid'">Servers</div>
    <div class="tab" :class="{on: view === 'metrics'}" @click="view='metrics'">Metrics</div>
    <div class="tab" :class="{on: view === 'state'}" @click="view='state'">State inspector</div>
  </div>

  <!-- SERVERS VIEW -->
  <div x-show="view === 'grid'">
    <div class="stats">
      <div class="stat"><b x-text="servers.length"></b><span>servers</span></div>
      <div class="stat"><b x-text="totalTools"></b><span>tools</span></div>
      <div class="stat"><b x-text="activeCount"></b><span>active</span></div>
      <div class="stat"><b x-text="favorites.length"></b><span>starred</span></div>
      <div class="stat"><b x-text="filteredServers.length"></b><span>filtered</span></div>
      <div class="stat"><b x-text="history.length"></b><span>calls made</span></div>
    </div>

    <div class="layout">
      <div>
        <input class="search" placeholder="Filter servers or search 539 tools… (/ to focus, ⌘K for palette)" x-model="filter" x-ref="searchInput">
        <div class="chips">
          <div class="chip" :class="{on: !catFilter}" @click="catFilter=''">all</div>
          <div class="chip" :class="{on: catFilter==='__fav'}" @click="catFilter = catFilter==='__fav' ? '' : '__fav'">★ favorites</div>
          <template x-for="cat in categories" :key="cat">
            <div class="chip" :class="{on: catFilter===cat}" @click="catFilter = catFilter===cat ? '' : cat" x-text="cat"></div>
          </template>
        </div>

        <div x-show="toolMatches.length > 0" class="panel" x-cloak>
          <h2 x-text="'Matching tools: ' + toolMatches.length"></h2>
          <template x-for="t in toolMatches.slice(0, 12)" :key="t.name">
            <div class="tool" @click="pickToolByName(t)">
              <code x-text="t.name"></code>
              <div class="desc" x-text="t.description || ''"></div>
            </div>
          </template>
        </div>

        <div class="grid" x-show="!activeTool" x-cloak>
          <template x-for="srv in filteredServers" :key="srv.id">
            <div class="card" :class="{selected: selected && selected.id === srv.id}" @click="selectServer(srv)">
              <div class="actions-row" :class="{on: isFav(srv.id)}">
                <button class="icon-btn star" @click.stop="toggleFav(srv.id)" x-text="isFav(srv.id) ? '★' : '☆'"></button>
                <button class="icon-btn" @click.stop="inspectState(srv)">◱</button>
                <button class="icon-btn" @click.stop="resetServer(srv)">✕</button>
              </div>
              <h3 x-text="srv.name"></h3>
              <div class="meta">
                <span class="badge" :class="srv.status" x-text="srv.status"></span>
                <span x-text="'port ' + srv.port"></span>
              </div>
              <div class="meta" x-text="srv.tools.length + ' tools · ' + srv.category"></div>
            </div>
          </template>
        </div>

        <div class="panel" x-show="selected && !activeTool" x-cloak>
          <h2 x-text="selected ? selected.name + ' · ' + selected.id : ''"></h2>
          <p class="sub" x-text="selected ? (selected.description || (selectedTools.length + ' tools registered on gateway')) : ''"></p>
          <template x-for="tool in selectedTools" :key="tool.name">
            <div class="tool" @click="pickTool(tool)">
              <code x-text="tool.name"></code>
              <div class="desc" x-text="tool.description || ''"></div>
            </div>
          </template>
          <div x-show="selectedTools.length === 0" class="empty-state">no tools registered on live gateway (start <code style="background:#0f172a;padding:2px 6px;border-radius:3px">make dev</code> in a separate terminal)</div>
        </div>

        <div class="panel" x-show="activeTool" x-cloak>
          <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:4px;">
            <div style="flex:1">
              <h2 x-text="activeTool ? activeTool.name : ''"></h2>
              <p class="sub" x-text="activeTool ? (activeTool.description || '') : ''"></p>
            </div>
            <button class="ghost" @click="activeTool = null; response = null">← back</button>
          </div>
          <div class="empty-state" x-show="Object.keys(toolInputs).length === 0">this tool takes no arguments</div>
          <template x-for="(schema, key) in toolInputs" :key="key">
            <div class="form-row">
              <label>
                <span x-text="key"></span>
                <span x-show="schema.required" style="color:#f87171">*</span>
                <span class="hint" x-text="' — ' + (schema.type || 'string') + (schema.description ? ' · ' + schema.description : '')"></span>
              </label>
              <template x-if="schema.type === 'array' || schema.type === 'object'">
                <textarea rows="3" :placeholder="'JSON ' + schema.type" x-model="formValues[key]"></textarea>
              </template>
              <template x-if="schema.type !== 'array' && schema.type !== 'object'">
                <input :placeholder="schema.type || 'string'" x-model="formValues[key]" @keydown.meta.enter="invoke()" @keydown.ctrl.enter="invoke()">
              </template>
            </div>
          </template>
          <div class="actions">
            <button class="primary" @click="invoke()" :disabled="invoking" x-text="invoking ? 'Running…' : 'Invoke'"></button>
            <button class="ghost" @click="fillDemo()" x-show="Object.keys(toolInputs).length > 0">Fill demo</button>
            <button class="ghost" @click="copyCurl()" x-text="copiedCurl ? 'copied ✓' : 'Copy curl'"></button>
            <button class="ghost" @click="copyPython()" x-text="copiedPy ? 'copied ✓' : 'Copy Python'"></button>
            <span class="elapsed" x-show="lastElapsed" x-text="lastElapsed + ' ms'"></span>
          </div>
          <div class="details">
            <div class="sec">
              <h4>Input schema <span class="clip" @click="copy(JSON.stringify(activeTool.inputSchema, null, 2), 'schema')" x-text="copiedSchema ? '✓' : 'copy'"></span></h4>
              <pre x-text="prettySchema(activeTool.inputSchema)"></pre>
            </div>
            <div class="sec" :class="response ? (response.isError ? 'error' : 'response') : (samplePreview ? '' : 'empty')">
              <h4>
                <span x-text="response ? (response.isError ? 'Error' : 'Response') : (samplePreview ? 'Last response for this tool' : 'What to expect')"></span>
                <span class="clip" x-show="response || samplePreview" @click="copy(responseText, 'resp')" x-text="copiedResp ? '✓' : 'copy'"></span>
              </h4>
              <pre x-text="responseText || samplePreview || 'Invoke the tool to see a response here.'"></pre>
            </div>
          </div>
        </div>
      </div>

      <div>
        <div class="history">
          <h3>Recent invocations</h3>
          <div class="empty-state" x-show="history.length === 0">no calls yet · click a tool to try one</div>
          <template x-for="h in history" :key="h.at">
            <div class="hist-item" :class="{err: h.error}" @click="replay(h)">
              <div>
                <div class="n" x-text="h.tool_name"></div>
                <div class="t" x-text="h.error ? 'error' : (h.elapsed_ms + ' ms')"></div>
              </div>
              <div class="t" x-text="h.timeText"></div>
            </div>
          </template>
        </div>
      </div>
    </div>
  </div>

  <!-- METRICS VIEW -->
  <div x-show="view === 'metrics'" x-cloak>
    <div class="metrics-grid">
      <div class="metric-card"><b x-text="metrics.total"></b><small>total calls</small></div>
      <div class="metric-card"><b x-text="metrics.uniqueTools"></b><small>unique tools</small></div>
      <div class="metric-card"><b x-text="metrics.avgMs + ' ms'"></b><small>avg latency</small></div>
      <div class="metric-card"><b x-text="metrics.p95Ms + ' ms'"></b><small>p95 latency</small></div>
      <div class="metric-card"><b x-text="metrics.errorRate + '%'"></b><small>error rate</small></div>
      <div class="metric-card"><b x-text="metrics.starred"></b><small>servers starred</small></div>
    </div>
    <div class="panel" x-show="metrics.perTool.length > 0" x-cloak>
      <h3>Top invoked tools</h3>
      <table class="metric-table">
        <thead><tr><th>Tool</th><th>Calls</th><th>Avg ms</th><th>Errors</th></tr></thead>
        <tbody>
          <template x-for="row in metrics.perTool.slice(0, 20)" :key="row.name">
            <tr>
              <td><code x-text="row.name" style="color:#a5b4fc"></code></td>
              <td class="n" x-text="row.count"></td>
              <td class="n" x-text="row.avg"></td>
              <td x-text="row.errors" :style="row.errors > 0 ? 'color:#fca5a5' : ''"></td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>
    <div class="empty-state" x-show="metrics.total === 0">No calls yet. Switch to Servers tab and try a tool.</div>
  </div>

  <!-- STATE INSPECTOR VIEW -->
  <div x-show="view === 'state'" x-cloak>
    <div style="margin-bottom: 12px;">
      <select class="search" x-model="stateSid" @change="loadState()">
        <option value="">Select a server…</option>
        <template x-for="s in servers" :key="s.id"><option :value="s.id" x-text="s.name + ' · ' + s.id"></option></template>
      </select>
    </div>
    <div class="panel" x-show="stateSid" x-cloak>
      <h2 x-text="stateSid ? 'State of ' + stateSid : ''"></h2>
      <p class="sub" x-text="stateData ? (stateData.exists ? stateData.path : (stateData.message || 'No state.db yet')) : 'Loading…'"></p>
      <div class="state-buckets" x-show="stateData && stateData.buckets && stateData.buckets.length > 0">
        <template x-for="b in (stateData.buckets || [])" :key="b.name">
          <div class="state-bucket" :class="{on: stateBucket === b.name}" @click="stateBucket = b.name; loadState()">
            <span x-text="b.name"></span> · <span x-text="b.count"></span>
          </div>
        </template>
      </div>
      <template x-for="row in (stateData.rows || [])" :key="row.key">
        <div class="state-row">
          <span class="k" x-text="row.key"></span>
          <pre x-text="JSON.stringify(row.value, null, 2)"></pre>
        </div>
      </template>
      <div class="empty-state" x-show="stateData && stateData.buckets && stateData.buckets.length === 0" x-text="stateData.message || 'No writes yet'"></div>
    </div>
  </div>

  <!-- COMMAND PALETTE -->
  <div class="cmdk-backdrop" x-show="cmdkOpen" x-cloak @click.self="cmdkOpen = false">
    <div class="cmdk">
      <input placeholder="Search tools, servers, actions… (⌘K to toggle)" x-model="cmdkQuery" x-ref="cmdkInput" @keydown="cmdkKey($event)">
      <div class="list">
        <template x-for="(item, idx) in cmdkItems" :key="idx">
          <div class="row" :class="{sel: cmdkIdx === idx}" @click="cmdkRun(item)">
            <span class="type" x-text="item.type"></span>
            <span class="name" x-text="item.name"></span>
            <span class="desc" x-text="item.desc || ''"></span>
          </div>
        </template>
      </div>
      <div class="hint"><span class="kbd">↑↓</span> nav · <span class="kbd">↵</span> select · <span class="kbd">esc</span> close</div>
    </div>
  </div>

  <script>
    const DEMO_MAP = {
      owner:'acme', repo:'app', project_id:'demo-1', project_key:'DEMO', workspace_slug:'acme',
      title:'Demo item from dashboard', name:'Demo item', subject:'Demo subject', item_name:'Demo row',
      body:'Created via fastmcp-fleet dashboard', description:'Created via dashboard', notes:'From dashboard',
      email:'demo@example.com', email_address:'demo@example.com', firstname:'Alice', lastname:'Adams',
      channel:'C_DEMO', channel_id:'C_DEMO', team_id:'T_DEMO', list_id:'L_DEMO', board_id:'B_DEMO',
      folder_id:'folder_demo', dataset_id:'ds_demo', bucket:'demo-bucket', key:'demo-key',
      url:'https://example.com', q:'hello world', query:'hello world', text:'hello world', message:'hello world',
      sql:'SELECT 1', cmd:'echo hello', path:'/tmp/demo.txt', to:'+15550001111', from_:'+15550002222',
      status:'opened', state:'open', per_page:'20', limit:'20',
    };
    function demoValue(paramName, type) {
      if (DEMO_MAP[paramName] !== undefined) return DEMO_MAP[paramName];
      const lc = paramName.toLowerCase();
      if (lc.endsWith('_id') || lc === 'id') return 'demo-1';
      if (lc.includes('email')) return 'demo@example.com';
      if (lc.includes('url')) return 'https://example.com';
      if (lc.includes('name') || lc.includes('title')) return 'Demo item';
      if (type === 'integer' || type === 'number') return '1';
      if (type === 'boolean') return 'true';
      if (type === 'array') return '[]';
      if (type === 'object') return '{}';
      return '';
    }

    function dashboard() {
      return {
        view: 'grid',
        servers: [], allTools: [], grouped: {}, totalTools: 0,
        filter: '', catFilter: '',
        selected: null, selectedTools: [],
        activeTool: null, toolInputs: {}, formValues: {}, invoking: false, response: null, lastElapsed: 0,
        copiedResp: false, copiedSchema: false, copiedCurl: false, copiedPy: false,
        history: JSON.parse(localStorage.getItem('fleet_history') || '[]'),
        favorites: JSON.parse(localStorage.getItem('fleet_favorites') || '[]'),
        cmdkOpen: false, cmdkQuery: '', cmdkIdx: 0,
        stateSid: '', stateBucket: '', stateData: null,
        get categories() { return [...new Set(this.servers.map(s => s.category))].sort(); },
        get activeCount() { return this.servers.filter(s => s.status === 'active').length; },
        get filteredServers() {
          const f = this.filter.toLowerCase();
          return this.servers.filter(s => {
            if (this.catFilter === '__fav') { if (!this.isFav(s.id)) return false; }
            else if (this.catFilter && s.category !== this.catFilter) return false;
            if (!f) return true;
            return s.id.includes(f) || s.name.toLowerCase().includes(f) || s.category.includes(f);
          });
        },
        get toolMatches() {
          const f = this.filter.toLowerCase();
          if (!f || f.length < 2) return [];
          return this.allTools.filter(t => t.name.toLowerCase().includes(f) || (t.description || '').toLowerCase().includes(f)).slice(0, 50);
        },
        get responseText() {
          if (!this.response) return '';
          if (this.response.error && !this.response.structuredContent) return JSON.stringify(this.response.error, null, 2);
          if (this.response.structuredContent) return JSON.stringify(this.response.structuredContent, null, 2);
          if (this.response.content) return this.response.content.map(c => c.text || JSON.stringify(c)).join('\n');
          return JSON.stringify(this.response, null, 2);
        },
        get samplePreview() {
          if (!this.activeTool) return '';
          const prev = this.history.find(h => h.tool_name === this.activeTool.name && !h.error && h.response);
          if (prev) return '// Sample from your previous call\n' + JSON.stringify(prev.response, null, 2);
          if (this.activeTool.outputSchema) return '// Expected shape (outputSchema)\n' + JSON.stringify(this.activeTool.outputSchema, null, 2);
          return '';
        },
        get metrics() {
          const hist = this.history;
          const total = hist.length;
          if (!total) return { total:0, uniqueTools:0, avgMs:0, p95Ms:0, errorRate:0, starred: this.favorites.length, perTool:[] };
          const byTool = {};
          hist.forEach(h => {
            byTool[h.tool_name] = byTool[h.tool_name] || { name:h.tool_name, count:0, sumMs:0, errors:0 };
            byTool[h.tool_name].count++;
            byTool[h.tool_name].sumMs += (h.elapsed_ms || 0);
            if (h.error) byTool[h.tool_name].errors++;
          });
          const perTool = Object.values(byTool).map(r => ({ ...r, avg: Math.round(r.sumMs / r.count) })).sort((a,b) => b.count - a.count);
          const sorted = hist.map(h => h.elapsed_ms || 0).sort((a,b) => a-b);
          const p95 = sorted[Math.floor(sorted.length * 0.95)] || 0;
          const avg = Math.round(sorted.reduce((a,b) => a+b, 0) / sorted.length);
          const errors = hist.filter(h => h.error).length;
          return { total, uniqueTools: perTool.length, avgMs: avg, p95Ms: p95, errorRate: Math.round(errors/total*100), starred: this.favorites.length, perTool };
        },
        get cmdkItems() {
          const q = this.cmdkQuery.toLowerCase();
          const items = [];
          if (this.cmdkQuery === '') {
            items.push({type:'view', name:'Metrics', desc:'call counts + latency', run: () => this.view = 'metrics'});
            items.push({type:'view', name:'State inspector', desc:'browse SQLite state', run: () => this.view = 'state'});
            items.push({type:'action', name:'Reset all state', desc:'clear every state.db & reseed', run: () => this.resetAll()});
          }
          this.allTools.forEach(t => {
            if (!q || t.name.toLowerCase().includes(q)) items.push({type:'tool', name:t.name, desc:t.description || '', run:() => this.pickToolByName(t)});
          });
          this.servers.forEach(s => {
            if (q && (s.id.includes(q) || s.name.toLowerCase().includes(q))) items.push({type:'server', name:s.id, desc:s.name + ' · ' + s.category, run:() => { this.view='grid'; this.selectServer(s); }});
          });
          return items.slice(0, 40);
        },
        async init() {
          const [srvs, tls] = await Promise.all([
            fetch('/api/servers').then(r => r.json()),
            fetch('/api/tools').then(r => r.json()).catch(() => ({total:0, tools:[], grouped:{}})),
          ]);
          this.servers = srvs;
          this.grouped = tls.grouped;
          this.allTools = tls.tools || [];
          this.totalTools = tls.total;
        },
        isFav(sid) { return this.favorites.includes(sid); },
        toggleFav(sid) {
          const i = this.favorites.indexOf(sid);
          if (i >= 0) this.favorites.splice(i, 1); else this.favorites.push(sid);
          localStorage.setItem('fleet_favorites', JSON.stringify(this.favorites));
        },
        selectServer(srv) {
          this.selected = srv;
          this.activeTool = null; this.response = null;
          const prefix = srv.id.replace(/-/g, '_');
          this.selectedTools = this.grouped[prefix] || [];
        },
        pickTool(t) {
          this.activeTool = t;
          this.toolInputs = (t.inputSchema && t.inputSchema.properties) || {};
          const req = (t.inputSchema && t.inputSchema.required) || [];
          this.formValues = {};
          for (const k of Object.keys(this.toolInputs)) {
            this.formValues[k] = '';
            this.toolInputs[k].required = req.includes(k);
          }
          this.response = null; this.lastElapsed = 0;
        },
        pickToolByName(t) {
          const prefix = t.name.split('_')[0];
          const srv = this.servers.find(s => s.id.replace(/-/g, '_') === prefix);
          if (srv) this.selected = srv;
          this.pickTool(t);
          this.view = 'grid';
        },
        fillDemo() {
          for (const k of Object.keys(this.toolInputs)) this.formValues[k] = demoValue(k, this.toolInputs[k].type);
        },
        argsPayload() {
          const args = {};
          for (const [k, v] of Object.entries(this.formValues)) {
            if (v === '') continue;
            const t = this.toolInputs[k].type;
            if (t === 'integer' || t === 'number') args[k] = Number(v);
            else if (t === 'boolean') args[k] = v === 'true';
            else if (t === 'array' || t === 'object') { try { args[k] = JSON.parse(v); } catch { args[k] = v; } }
            else args[k] = v;
          }
          return args;
        },
        async invoke() {
          if (!this.activeTool) return;
          this.invoking = true; this.response = null;
          const args = this.argsPayload();
          const started = Date.now();
          try {
            const r = await fetch('/api/invoke', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({tool_name:this.activeTool.name, arguments:args}) });
            const data = await r.json();
            this.response = r.ok ? data : {isError:true, ...data};
            this.lastElapsed = data._elapsed_ms || (Date.now() - started);
          } catch (e) {
            this.response = {isError:true, error:e.message};
            this.lastElapsed = Date.now() - started;
          } finally { this.invoking = false; }
          const now = new Date();
          this.history.unshift({
            tool_name:this.activeTool.name, args, at:Date.now(),
            timeText: now.toLocaleTimeString(), elapsed_ms:this.lastElapsed,
            error: !!(this.response && this.response.isError), response:this.response,
          });
          this.history = this.history.slice(0, 30);
          localStorage.setItem('fleet_history', JSON.stringify(this.history));
        },
        replay(h) {
          const tool = this.allTools.find(t => t.name === h.tool_name);
          if (!tool) return;
          this.pickToolByName(tool);
          this.formValues = {};
          for (const [k, v] of Object.entries(h.args || {})) this.formValues[k] = typeof v === 'object' ? JSON.stringify(v) : String(v);
        },
        copy(text, tag) {
          navigator.clipboard.writeText(text);
          if (tag === 'resp') this.copiedResp = true;
          else if (tag === 'schema') this.copiedSchema = true;
          setTimeout(() => { this.copiedResp = false; this.copiedSchema = false; }, 1500);
        },
        copyCurl() {
          if (!this.activeTool) return;
          const body = {tool_name:this.activeTool.name, arguments:this.argsPayload()};
          navigator.clipboard.writeText(`curl -X POST http://localhost:8080/api/invoke \\\n  -H 'Content-Type: application/json' \\\n  -d '${JSON.stringify(body)}'`);
          this.copiedCurl = true; setTimeout(() => this.copiedCurl = false, 1500);
        },
        copyPython() {
          if (!this.activeTool) return;
          const args = this.argsPayload();
          navigator.clipboard.writeText(`import asyncio\nfrom fastmcp import Client\n\nasync def main():\n    async with Client("http://localhost:9000/mcp") as c:\n        r = await c.call_tool("${this.activeTool.name}", ${JSON.stringify(args)})\n        print(r.data)\n\nasyncio.run(main())`);
          this.copiedPy = true; setTimeout(() => this.copiedPy = false, 1500);
        },
        prettySchema(s) { return s ? JSON.stringify(s, null, 2) : '(no inputSchema)'; },
        async resetServer(srv) {
          if (!confirm(`Reset state for ${srv.id}? (Restores seed.json if present)`)) return;
          const r = await fetch('/api/reset/' + srv.id, {method:'POST'}).then(r => r.json());
          const parts = [];
          if (r.removed && r.removed.length) parts.push(`Removed: ${r.removed.length} db(s)`);
          if (r.seeded) parts.push(`Seeded: ${r.seeded} rows`);
          alert(parts.length ? parts.join(' • ') : `No state for ${srv.id}`);
        },
        async resetAll() {
          if (!confirm('Reset ALL server state? Restores seed.json baselines for stateful servers.')) return;
          const r = await fetch('/api/reset-all', {method:'POST'}).then(r => r.json());
          alert(`Removed ${r.count} state DBs • Seeded ${r.seeded || 0} rows`);
        },
        async inspectState(srv) {
          this.view = 'state'; this.stateSid = srv.id; this.stateBucket = '';
          await this.loadState();
        },
        async loadState() {
          if (!this.stateSid) { this.stateData = null; return; }
          const url = '/api/state/' + this.stateSid + (this.stateBucket ? '?bucket=' + encodeURIComponent(this.stateBucket) : '');
          this.stateData = await fetch(url).then(r => r.json());
        },
        handleKey(e) {
          if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
            e.preventDefault(); this.cmdkOpen = true; this.cmdkQuery = ''; this.cmdkIdx = 0;
            this.$nextTick(() => this.$refs.cmdkInput.focus());
            return;
          }
          if (this.cmdkOpen) return;
          if (e.key === '/' && e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA') {
            e.preventDefault(); this.$refs.searchInput.focus();
          } else if (e.key === 'Escape' && this.activeTool) {
            this.activeTool = null; this.response = null;
          } else if ((e.metaKey || e.ctrlKey) && e.key === 'Enter' && this.activeTool) {
            e.preventDefault(); this.invoke();
          }
        },
        cmdkKey(e) {
          if (e.key === 'Escape') { this.cmdkOpen = false; return; }
          if (e.key === 'ArrowDown') { this.cmdkIdx = Math.min(this.cmdkIdx + 1, this.cmdkItems.length - 1); e.preventDefault(); }
          else if (e.key === 'ArrowUp') { this.cmdkIdx = Math.max(this.cmdkIdx - 1, 0); e.preventDefault(); }
          else if (e.key === 'Enter') { const item = this.cmdkItems[this.cmdkIdx]; if (item) this.cmdkRun(item); }
        },
        cmdkRun(item) { this.cmdkOpen = false; item.run(); },
      };
    }
  </script>
</body></html>
"""


async def index(request: Request):
    return HTMLResponse(HTML)


app = Starlette(
    routes=[
        Route("/", index),
        Route("/api/servers", api_servers),
        Route("/api/tools", api_tools),
        Route("/api/invoke", api_invoke, methods=["POST"]),
        Route("/api/state/{sid}", api_state),
        Route("/api/reset/{sid}", api_reset, methods=["POST"]),
        Route("/api/reset-all", api_reset_all, methods=["POST"]),
    ]
)


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    main()
