"""Fleet dashboard: sandbox UI for the fastmcp-fleet gateway.

Serves an HTML page at http://localhost:8080/ with 175-server grid,
global tool search, category filter, recent invocations, auto-fill demo values,
schema preview, sample response, copy-as-curl/python snippets, keyboard shortcuts.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
import yaml
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
        GATEWAY_URL,
        json=body,
        headers={"Accept": "application/json, text/event-stream"},
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


async def api_reset(request: Request):
    sid = request.path_params["sid"]
    db = STATE_DIR / f"{sid}.db"
    legacy = REPO_ROOT / "servers" / sid / "state.db"
    removed = []
    for p in (db, legacy):
        if p.exists():
            p.unlink()
            removed.append(str(p))
    return JSONResponse({"removed": removed, "sid": sid})


async def api_reset_all(request: Request):
    removed = []
    if STATE_DIR.exists():
        for f in STATE_DIR.glob("*.db"):
            f.unlink()
            removed.append(str(f))
    for sd in (REPO_ROOT / "servers").glob("*/state.db"):
        sd.unlink()
        removed.append(str(sd))
    return JSONResponse({"removed": removed, "count": len(removed)})


HTML = r"""
<!doctype html>
<html><head><meta charset="utf-8"><title>fastmcp-fleet sandbox</title>
<script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.14.0/dist/cdn.min.js"></script>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font: 14px system-ui, -apple-system, sans-serif; background: #0b1220; color: #e2e8f0; padding: 20px; min-height: 100vh; }
  h1 { font-size: 22px; color: #f8fafc; }
  .sub { color: #94a3b8; margin-bottom: 16px; font-size: 12px; }
  a { color: #a5b4fc; text-decoration: none; } a:hover { text-decoration: underline; }
  input, textarea, button { font-family: inherit; }
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
  .card h3 { font-size: 14px; color: #f1f5f9; margin-bottom: 3px; }
  .card .meta { color: #94a3b8; font-size: 11px; margin-top: 2px; }
  .card .badge { display: inline-block; padding: 1px 5px; background: #334155; border-radius: 3px; font-size: 10px; margin-right: 3px; color: #cbd5e1; }
  .card .badge.active { background: #16a34a; color: white; }
  .card .badge.pilot { background: #d97706; color: white; }
  .card .reset-btn { position: absolute; top: 5px; right: 5px; padding: 2px 6px; font-size: 10px; background: transparent; border: 1px solid #334155; border-radius: 3px; color: #94a3b8; cursor: pointer; opacity: 0; transition: opacity 0.15s; }
  .card:hover .reset-btn { opacity: 1; }
  .card .reset-btn:hover { background: #b91c1c; color: white; border-color: #b91c1c; }
  .panel { margin-top: 16px; background: #1e293b; border: 1px solid #334155; border-radius: 6px; padding: 18px; }
  .panel h2 { color: #f8fafc; margin-bottom: 4px; font-size: 17px; }
  .panel .h-sub { color: #94a3b8; font-size: 12px; margin-bottom: 12px; }
  .tool { padding: 9px 12px; background: #0f172a; border-radius: 4px; margin-bottom: 5px; cursor: pointer; border: 1px solid transparent; }
  .tool:hover { background: #172033; border-color: #334155; }
  .tool.active { border-color: #6366f1; background: #24314a; }
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
  .sec h4 { font-size: 11px; color: #94a3b8; margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.5px; display: flex; justify-content: space-between; }
  .sec h4 .clip { cursor: pointer; color: #64748b; text-transform: none; font-weight: normal; letter-spacing: normal; }
  .sec h4 .clip:hover { color: #a5b4fc; }
  .sec pre { color: #cbd5e1; font-family: monospace; font-size: 11px; white-space: pre-wrap; word-break: break-word; max-height: 180px; overflow-y: auto; }
  .sec.response pre { color: #a7f3d0; }
  .sec.error pre { color: #fca5a5; }
  .sec.empty pre { color: #475569; font-style: italic; }
  .history { background: #1e293b; border: 1px solid #334155; border-radius: 6px; padding: 14px; }
  .history h3 { font-size: 13px; color: #cbd5e1; margin-bottom: 10px; text-transform: uppercase; letter-spacing: 0.5px; }
  .hist-item { padding: 6px 8px; margin-bottom: 4px; background: #0f172a; border-radius: 3px; cursor: pointer; font-size: 12px; display: flex; justify-content: space-between; align-items: center; }
  .hist-item:hover { background: #172033; }
  .hist-item .n { color: #a5b4fc; font-family: monospace; font-size: 11px; }
  .hist-item .t { color: #94a3b8; font-size: 10px; }
  .hist-item.err .n { color: #fca5a5; }
  .empty-state { color: #64748b; font-size: 12px; text-align: center; padding: 16px 0; }
  .kbd { display: inline-block; background: #0b1220; border: 1px solid #334155; border-bottom-width: 2px; border-radius: 3px; padding: 1px 5px; font-size: 10px; color: #94a3b8; font-family: monospace; }
</style>
</head><body x-data="dashboard()" x-init="init()" @keydown.window="handleKey($event)">
  <div style="display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 4px;">
    <div>
      <h1>fastmcp-fleet sandbox</h1>
      <p class="sub">175 servers · <span x-text="totalTools"></span> tools · offline-first · <a href="https://github.com/deepakdalal1221/fastmcp-fleet">github</a> · <a href="#" @click.prevent="resetAll()">reset all state</a></p>
    </div>
    <div class="sub" style="text-align: right;">
      <span class="kbd">/</span> focus · <span class="kbd">⌘⏎</span> invoke · <span class="kbd">esc</span> back
    </div>
  </div>

  <div class="stats">
    <div class="stat"><b x-text="servers.length"></b><span>servers</span></div>
    <div class="stat"><b x-text="totalTools"></b><span>tools</span></div>
    <div class="stat"><b x-text="activeCount"></b><span>active</span></div>
    <div class="stat"><b x-text="filteredServers.length"></b><span>filtered</span></div>
    <div class="stat"><b x-text="history.length"></b><span>calls made</span></div>
  </div>

  <div class="layout">
    <div>
      <input class="search" placeholder="Filter servers or search 539 tools… (/ to focus)" x-model="filter" x-ref="searchInput">
      <div class="chips">
        <div class="chip" :class="{on: !catFilter}" @click="catFilter=''">all</div>
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
            <button class="reset-btn" @click.stop="resetServer(srv)">reset</button>
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
        <p class="h-sub" x-text="selected ? (selected.description || (selectedTools.length + ' tools registered on gateway')) : ''"></p>
        <template x-for="tool in selectedTools" :key="tool.name">
          <div class="tool" @click="pickTool(tool)">
            <code x-text="tool.name"></code>
            <div class="desc" x-text="tool.description || ''"></div>
          </div>
        </template>
        <div x-show="selectedTools.length === 0" class="empty-state">no tools registered on live gateway (start <code style="background:#0f172a;padding:2px 6px;border-radius:3px">make dev</code> in a separate terminal)</div>
      </div>

      <div class="panel" x-show="activeTool" x-cloak>
        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 4px;">
          <div style="flex: 1">
            <h2 x-text="activeTool ? activeTool.name : ''"></h2>
            <p class="h-sub" x-text="activeTool ? (activeTool.description || '') : ''"></p>
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
          <div class="sec" :class="response ? (response.isError ? 'error response' : 'response') : (samplePreview ? '' : 'empty')">
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

  <script>
    // Heuristic demo values for common param names / types
    const DEMO_MAP = {
      owner: 'acme', repo: 'app', project_id: 'demo-1', project_key: 'DEMO', workspace_slug: 'acme',
      title: 'Demo item from dashboard', name: 'Demo item', subject: 'Demo subject', item_name: 'Demo row',
      body: 'Created via fastmcp-fleet dashboard', description: 'Created via dashboard', notes: 'From dashboard',
      email: 'demo@example.com', email_address: 'demo@example.com', firstname: 'Alice', lastname: 'Adams',
      channel: 'C_DEMO', channel_id: 'C_DEMO', team_id: 'T_DEMO', list_id: 'L_DEMO', board_id: 'B_DEMO',
      folder_id: 'folder_demo', dataset_id: 'ds_demo', bucket: 'demo-bucket', key: 'demo-key',
      url: 'https://example.com', q: 'hello world', query: 'hello world', text: 'hello world', message: 'hello world',
      sql: 'SELECT 1', cmd: 'echo hello', path: '/tmp/demo.txt', to: '+15550001111', from_: '+15550002222',
      status: 'opened', state: 'open', per_page: '20', limit: '20',
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
        servers: [], allTools: [], grouped: {}, totalTools: 0,
        filter: '', catFilter: '',
        selected: null, selectedTools: [],
        activeTool: null, toolInputs: {}, formValues: {}, invoking: false, response: null, lastElapsed: 0,
        copiedResp: false, copiedSchema: false, copiedCurl: false, copiedPy: false,
        history: JSON.parse(localStorage.getItem('fleet_history') || '[]'),
        get categories() { return [...new Set(this.servers.map(s => s.category))].sort(); },
        get activeCount() { return this.servers.filter(s => s.status === 'active').length; },
        get filteredServers() {
          const f = this.filter.toLowerCase();
          return this.servers.filter(s => {
            if (this.catFilter && s.category !== this.catFilter) return false;
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
          // Look for last successful call to this tool in history
          const prev = this.history.find(h => h.tool_name === this.activeTool.name && !h.error && h.response);
          if (prev) return '// Sample from your previous call\n' + JSON.stringify(prev.response, null, 2);
          // Fall back to outputSchema if present
          if (this.activeTool.outputSchema) return '// Expected shape (outputSchema)\n' + JSON.stringify(this.activeTool.outputSchema, null, 2);
          return '';
        },
        prettySchema(s) { return s ? JSON.stringify(s, null, 2) : '(no inputSchema)'; },
        async init() {
          const [srvs, tls] = await Promise.all([
            fetch('/api/servers').then(r => r.json()),
            fetch('/api/tools').then(r => r.json()).catch(() => ({total: 0, tools: [], grouped: {}})),
          ]);
          this.servers = srvs;
          this.grouped = tls.grouped;
          this.allTools = tls.tools || [];
          this.totalTools = tls.total;
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
        },
        fillDemo() {
          for (const k of Object.keys(this.toolInputs)) {
            const t = this.toolInputs[k].type;
            this.formValues[k] = demoValue(k, t);
          }
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
            const r = await fetch('/api/invoke', {
              method: 'POST', headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({tool_name: this.activeTool.name, arguments: args}),
            });
            const data = await r.json();
            this.response = r.ok ? data : {isError: true, ...data};
            this.lastElapsed = data._elapsed_ms || (Date.now() - started);
          } catch (e) {
            this.response = {isError: true, error: e.message};
            this.lastElapsed = Date.now() - started;
          } finally { this.invoking = false; }
          const now = new Date();
          this.history.unshift({
            tool_name: this.activeTool.name, args, at: Date.now(),
            timeText: now.toLocaleTimeString(),
            elapsed_ms: this.lastElapsed, error: !!(this.response && this.response.isError),
            response: this.response,
          });
          this.history = this.history.slice(0, 20);
          localStorage.setItem('fleet_history', JSON.stringify(this.history));
        },
        replay(h) {
          const tool = this.allTools.find(t => t.name === h.tool_name);
          if (!tool) return;
          this.pickToolByName(tool);
          this.formValues = {};
          for (const [k, v] of Object.entries(h.args || {})) {
            this.formValues[k] = typeof v === 'object' ? JSON.stringify(v) : String(v);
          }
        },
        copy(text, tag) {
          navigator.clipboard.writeText(text);
          if (tag === 'resp') this.copiedResp = true;
          else if (tag === 'schema') this.copiedSchema = true;
          setTimeout(() => { this.copiedResp = false; this.copiedSchema = false; }, 1500);
        },
        copyCurl() {
          if (!this.activeTool) return;
          const args = this.argsPayload();
          const body = {tool_name: this.activeTool.name, arguments: args};
          const cmd = `curl -X POST http://localhost:8080/api/invoke \\\n  -H 'Content-Type: application/json' \\\n  -d '${JSON.stringify(body)}'`;
          navigator.clipboard.writeText(cmd);
          this.copiedCurl = true; setTimeout(() => this.copiedCurl = false, 1500);
        },
        copyPython() {
          if (!this.activeTool) return;
          const args = this.argsPayload();
          const code = `import asyncio\nfrom fastmcp import Client\n\nasync def main():\n    async with Client("http://localhost:9000/mcp") as c:\n        r = await c.call_tool("${this.activeTool.name}", ${JSON.stringify(args)})\n        print(r.data)\n\nasyncio.run(main())`;
          navigator.clipboard.writeText(code);
          this.copiedPy = true; setTimeout(() => this.copiedPy = false, 1500);
        },
        async resetServer(srv) {
          if (!confirm(`Reset state for ${srv.id}?`)) return;
          const r = await fetch('/api/reset/' + srv.id, {method: 'POST'}).then(r => r.json());
          alert(r.removed.length ? `Removed: ${r.removed.join(', ')}` : `No state for ${srv.id}`);
        },
        async resetAll() {
          if (!confirm('Reset ALL server state? This deletes every state.db.')) return;
          const r = await fetch('/api/reset-all', {method: 'POST'}).then(r => r.json());
          alert(`Removed ${r.count} state DBs`);
        },
        handleKey(e) {
          if (e.key === '/' && e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA') {
            e.preventDefault(); this.$refs.searchInput.focus();
          } else if (e.key === 'Escape' && this.activeTool) {
            this.activeTool = null; this.response = null;
          } else if ((e.metaKey || e.ctrlKey) && e.key === 'Enter' && this.activeTool) {
            e.preventDefault(); this.invoke();
          }
        }
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
        Route("/api/reset/{sid}", api_reset, methods=["POST"]),
        Route("/api/reset-all", api_reset_all, methods=["POST"]),
    ]
)


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    main()
