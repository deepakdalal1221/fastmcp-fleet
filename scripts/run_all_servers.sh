#!/bin/bash
set -euo pipefail

REGISTRY_DIR="${REGISTRY_DIR:-registry/servers}"
export MCP_HOST="${MCP_HOST:-0.0.0.0}"
export MCP_TRANSPORT="${MCP_TRANSPORT:-streamable-http}"
export MCP_OFFLINE="${MCP_OFFLINE:-1}"

pids=()
cleanup() {
    kill -TERM "${pids[@]}" 2>/dev/null || true
    wait
    exit 0
}
trap cleanup SIGTERM SIGINT

launched=0
skipped=0
for yaml in "$REGISTRY_DIR"/*.yaml; do
    sid=$(basename "$yaml" .yaml)
    status=$(awk '/^status:/ {print $2; exit}' "$yaml")
    port=$(awk '/^port:/ {print $2; exit}' "$yaml")
    case "$status" in
        active|pilot) ;;
        *) skipped=$((skipped+1)); continue ;;
    esac
    if [ ! -f "servers/$sid/tools.py" ]; then
        skipped=$((skipped+1))
        continue
    fi
    if grep -q "NotImplementedError" "servers/$sid/tools.py" 2>/dev/null; then
        skipped=$((skipped+1))
        continue
    fi
    mod=$(echo "$sid" | tr '-' '_')
    python -m "servers.$mod.main" --port "$port" &
    pids+=($!)
    launched=$((launched+1))
done

echo "[supervisor] launched=$launched skipped=$skipped total_children=${#pids[@]}"
echo "[supervisor] waiting on all children (SIGTERM/SIGINT triggers cleanup)..."
wait
