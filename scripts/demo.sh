#!/bin/bash
# Scripted MCP demo: start fleet, run a multi-server agent trajectory via curl.
set -euo pipefail

echo "▸ Starting fastmcp-fleet on :9000..."
MCP_OFFLINE=1 MCP_STATE_DIR=./.demo_state uv run python -m gateway.all_in_one --port 9000 > /tmp/demo.log 2>&1 &
PID=$!
for i in {1..15}; do sleep 1; grep -q "Uvicorn running" /tmp/demo.log 2>/dev/null && break; done
sleep 1

echo "▸ Handshake..."
H=$(curl -s -N -D /tmp/dh.txt -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -X POST http://localhost:9000/mcp -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{"tools":{}},"clientInfo":{"name":"demo","version":"1"}}}')
SID=$(grep -i "mcp-session-id" /tmp/dh.txt | awk '{print $2}' | tr -d '\r\n')
echo "  session: $SID"

echo "▸ Count tools..."
N=$(curl -s -N -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -H "mcp-session-id: $SID" -X POST http://localhost:9000/mcp -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' | grep -oE '"name":"[^"]+"' | wc -l | tr -d ' ')
echo "  $N tools available"

call() {
  local name=$1
  local args=$2
  curl -s -N -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -H "mcp-session-id: $SID" -X POST http://localhost:9000/mcp -d "{\"jsonrpc\":\"2.0\",\"id\":99,\"method\":\"tools/call\",\"params\":{\"name\":\"$name\",\"arguments\":$args}}" | grep -oE '"[a-z_]+":"[^"]+"' | head -3
}

echo ""
echo "▸ Cross-server trajectory: github → jira → slack"
echo "  1. github_create_issue(owner=acme, repo=demo, title=Demo bug)"
call github_create_issue '{"owner":"acme","repo":"demo","title":"Demo bug"}'
echo ""
echo "  2. jira_create_issue(project_key=DEMO, summary=Track bug)"
call jira_create_issue '{"project_key":"DEMO","summary":"Track bug"}'
echo ""
echo "  3. slack_post_message(channel=C-demo, text=Bug tracked)"
call slack_post_message '{"channel":"C-demo","text":"Bug tracked"}'
echo ""
echo "▸ Read back everything:"
echo "  github_list_issues:"
call github_list_issues '{"owner":"acme","repo":"demo"}'
echo ""
echo "  jira search_issues:"
call jira_search_issues '{"jql":"project = DEMO"}'
echo ""
echo "  slack get_conversation:"
call slack_get_conversation '{"channel":"C-demo"}'
echo ""
echo "▸ Cleanup"
kill $PID 2>/dev/null || true
wait $PID 2>/dev/null || true
rm -rf ./.demo_state
echo "▸ Done."
