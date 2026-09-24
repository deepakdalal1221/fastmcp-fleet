"""Fleet dashboard: single-pane-of-glass UI for the fastmcp-fleet gateway.

Serves an HTML page at http://localhost:8080/ showing all servers grouped by
prefix, with inline tool discovery and invoke via the all-in-one gateway (:9000).
"""

from __future__ import annotations

import json
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
        raise HTTPException(502, "gateway did not return mcp-session-id")
    # Consume + ack init
    await client.post(
        GATEWAY_URL,
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        headers={
            "Accept": "application/json, text/event-stream",
            "mcp-session-id": session_id,
        },
    )
    return session_id


def _parse_sse(text: str) -> dict:
    for line in text.splitlines():
        if line.startswith("data:"):
            return json.loads(line[5:].strip())
    return {}


async def _mcp_call(client: httpx.AsyncClient, session_id: str, method: str, params: dict) -> dict:
    body = {"jsonrpc": "2.0", "id": str(uuid.uuid4()), "method": method}
    if params is not None:
        body["params"] = params
    r = await client.post(
        GATEWAY_URL,
        json=body,
        headers={
            "Accept": "application/json, text/event-stream",
            "mcp-session-id": session_id,
        },
    )
    return _parse_sse(r.text)


async def api_servers(request: Request):
    return JSONResponse(_load_manifests())


async def api_tools(request: Request):
    async with httpx.AsyncClient(timeout=30.0) as c:
        sid = await _mcp_init(c)
        resp = await _mcp_call(c, sid, "tools/list", {})
        tools = resp.get("result", {}).get("tools", [])
    # Group by server prefix (before first _)
    grouped: dict[str, list[dict]] = {}
    for t in tools:
        name = t["name"]
        prefix = name.split("_", 1)[0]
        grouped.setdefault(prefix, []).append(t)
    return JSONResponse({"total": len(tools), "grouped": grouped})


async def api_invoke(request: Request):
    body = await request.json()
    tool_name = body.get("tool_name")
    arguments = body.get("arguments", {})
    async with httpx.AsyncClient(timeout=60.0) as c:
        sid = await _mcp_init(c)
        resp = await _mcp_call(
            c,
            sid,
            "tools/call",
            {"name": tool_name, "arguments": arguments},
        )
        if "error" in resp:
            raise HTTPException(400, str(resp["error"]))
        return JSONResponse(resp.get("result", {}))


HTML = """
<!doctype html>
<html><head><meta charset="utf-8"><title>fastmcp-fleet dashboard</title>
<script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.14.0/dist/cdn.min.js"></script>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font: 14px system-ui, -apple-system, sans-serif; background: #0f172a; color: #e2e8f0; padding: 20px; }
  h1 { font-size: 24px; margin-bottom: 4px; color: #f8fafc; }
  .sub { color: #94a3b8; margin-bottom: 20px; font-size: 13px; }
  .search { width: 100%; padding: 10px 14px; background: #1e293b; border: 1px solid #334155; border-radius: 6px; color: #e2e8f0; font-size: 14px; margin-bottom: 16px; }
  .search:focus { outline: none; border-color: #6366f1; }
  .stats { display: flex; gap: 16px; margin-bottom: 20px; }
  .stat { background: #1e293b; border-radius: 6px; padding: 12px 18px; }
  .stat b { font-size: 22px; color: #a5b4fc; display: block; }
  .stat span { color: #94a3b8; font-size: 12px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 10px; }
  .card { background: #1e293b; border: 1px solid #334155; border-radius: 6px; padding: 12px 14px; cursor: pointer; transition: all 0.15s; }
  .card:hover { border-color: #6366f1; background: #24314a; }
  .card.selected { border-color: #a5b4fc; background: #2a3554; }
  .card h3 { font-size: 15px; color: #f1f5f9; margin-bottom: 4px; }
  .card .meta { color: #94a3b8; font-size: 11px; }
  .card .badge { display: inline-block; padding: 2px 6px; background: #334155; border-radius: 3px; font-size: 10px; margin-right: 4px; color: #cbd5e1; }
  .card .badge.active { background: #16a34a; color: white; }
  .card .badge.pilot { background: #d97706; color: white; }
  .panel { margin-top: 20px; background: #1e293b; border: 1px solid #334155; border-radius: 6px; padding: 20px; }
  .panel h2 { color: #f8fafc; margin-bottom: 12px; }
  .tool { padding: 10px 14px; background: #0f172a; border-radius: 4px; margin-bottom: 8px; cursor: pointer; }
  .tool:hover { background: #172033; }
  .tool code { color: #a5b4fc; font-weight: 600; }
  .tool .desc { color: #94a3b8; font-size: 12px; margin-top: 3px; }
  .form-row { display: flex; flex-direction: column; gap: 6px; margin-bottom: 10px; }
  .form-row label { color: #cbd5e1; font-size: 12px; font-weight: 500; }
  .form-row input, .form-row textarea { background: #0f172a; border: 1px solid #334155; border-radius: 4px; padding: 8px 10px; color: #e2e8f0; font-family: monospace; font-size: 13px; }
  .form-row input:focus, .form-row textarea:focus { outline: none; border-color: #6366f1; }
  button { background: #6366f1; color: white; border: 0; padding: 10px 20px; border-radius: 4px; cursor: pointer; font-size: 14px; font-weight: 500; }
  button:hover { background: #4f46e5; }
  button:disabled { background: #4b5563; cursor: not-allowed; }
  .response { margin-top: 16px; background: #0f172a; border-radius: 4px; padding: 14px; overflow-x: auto; }
  .response pre { color: #a7f3d0; font-family: monospace; font-size: 12px; white-space: pre-wrap; word-break: break-word; }
  .response.error pre { color: #fca5a5; }
  .loading { color: #94a3b8; font-style: italic; }
</style>
</head><body x-data="dashboard()">
  <h1>fastmcp-fleet dashboard</h1>
  <p class="sub">175 servers · 539 tools · offline-first · <a href="https://github.com/deepakdalal1221/fastmcp-fleet" style="color:#a5b4fc">github</a></p>

  <div class="stats">
    <div class="stat"><b x-text="servers.length"></b><span>servers</span></div>
    <div class="stat"><b x-text="totalTools"></b><span>tools</span></div>
    <div class="stat"><b x-text="activeCount"></b><span>active</span></div>
    <div class="stat"><b x-text="pilotCount"></b><span>pilot</span></div>
  </div>

  <input class="search" placeholder="Filter servers…" x-model="filter">

  <div class="grid">
    <template x-for="srv in filteredServers" :key="srv.id">
      <div class="card" :class="{selected: selected && selected.id === srv.id}" @click="selectServer(srv)">
        <h3 x-text="srv.name"></h3>
        <div class="meta">
          <span class="badge" :class="srv.status" x-text="srv.status"></span>
          <span x-text="'port ' + srv.port"></span>
        </div>
        <div class="meta" style="margin-top:6px" x-text="srv.tools.length + ' tools · ' + srv.category"></div>
      </div>
    </template>
  </div>

  <div class="panel" x-show="selected" x-cloak>
    <h2 x-text="selected ? selected.name + ' (' + selected.id + ')' : ''"></h2>
    <template x-for="tool in selectedTools" :key="tool.name">
      <div class="tool" @click="pickTool(tool)">
        <code x-text="tool.name"></code>
        <div class="desc" x-text="tool.description || ''"></div>
      </div>
    </template>
    <div x-show="selectedTools.length === 0" class="loading" x-text="loading ? 'Loading tools from gateway…' : 'No tools yet — start make dev first'"></div>
  </div>

  <div class="panel" x-show="activeTool" x-cloak>
    <h2 x-text="activeTool ? activeTool.name : ''"></h2>
    <p class="sub" x-text="activeTool ? (activeTool.description || '') : ''"></p>
    <template x-for="(schema, key) in toolInputs" :key="key">
      <div class="form-row">
        <label x-text="key + (schema.required ? ' *' : '')"></label>
        <input :placeholder="schema.type || 'string'" x-model="formValues[key]">
      </div>
    </template>
    <button @click="invoke()" :disabled="invoking" x-text="invoking ? 'Running…' : 'Invoke'"></button>
    <div class="response" :class="{error: response && response.isError}" x-show="response" x-cloak>
      <pre x-text="responseText"></pre>
    </div>
  </div>

  <script>
    function dashboard() {
      return {
        servers: [], grouped: {}, totalTools: 0,
        filter: '', selected: null, selectedTools: [], loading: false,
        activeTool: null, toolInputs: {}, formValues: {}, invoking: false, response: null,
        get activeCount() { return this.servers.filter(s => s.status === 'active').length; },
        get pilotCount() { return this.servers.filter(s => s.status === 'pilot').length; },
        get filteredServers() {
          const f = this.filter.toLowerCase();
          return this.servers.filter(s => !f || s.id.includes(f) || s.name.toLowerCase().includes(f) || s.category.includes(f));
        },
        get responseText() { return this.response ? JSON.stringify(this.response, null, 2) : ''; },
        async init() {
          const [srvs, tls] = await Promise.all([
            fetch('/api/servers').then(r => r.json()),
            fetch('/api/tools').then(r => r.json()).catch(() => ({total: 0, grouped: {}})),
          ]);
          this.servers = srvs;
          this.grouped = tls.grouped;
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
          this.response = null;
        },
        async invoke() {
          this.invoking = true; this.response = null;
          const args = {};
          for (const [k, v] of Object.entries(this.formValues)) {
            if (v === '') continue;
            const t = this.toolInputs[k].type;
            if (t === 'integer' || t === 'number') args[k] = Number(v);
            else if (t === 'boolean') args[k] = v === 'true';
            else if (t === 'array' || t === 'object') { try { args[k] = JSON.parse(v); } catch { args[k] = v; } }
            else args[k] = v;
          }
          try {
            const r = await fetch('/api/invoke', {
              method: 'POST', headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({tool_name: this.activeTool.name, arguments: args}),
            });
            const data = await r.json();
            this.response = r.ok ? data : {isError: true, detail: data.detail};
          } catch (e) {
            this.response = {isError: true, error: e.message};
          } finally { this.invoking = false; }
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
    ]
)


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    main()
