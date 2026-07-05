#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME_DIR="$ROOT_DIR/outputs/runtime"
mkdir -p "$RUNTIME_DIR"

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
UVICORN_BIN="${UVICORN_BIN:-$ROOT_DIR/.venv/bin/uvicorn}"
NODE_BIN="${NODE_BIN:-/Users/yuanzexiang/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node}"

load_dotenv() {
  local env_file="$ROOT_DIR/.env"
  if [ ! -f "$env_file" ]; then
    return
  fi
  if [ ! -x "$PYTHON_BIN" ]; then
    echo "Cannot load .env because PYTHON_BIN is not executable: $PYTHON_BIN" >&2
    exit 1
  fi
  while IFS= read -r -d '' assignment; do
    export "$assignment"
  done < <("$PYTHON_BIN" - "$env_file" <<'PY'
from pathlib import Path
import sys
from dotenv import dotenv_values

env_file = Path(sys.argv[1])
for key, value in dotenv_values(env_file).items():
    if key and value is not None:
        print(f"{key}={value}", end="\0")
PY
  )
}

load_dotenv

APP_HOST="${APP_HOST:-127.0.0.1}"
APP_PORT="${APP_PORT:-8002}"
ASIS_XHS_HEADLESS="${ASIS_XHS_HEADLESS:-true}"

export STYLIST_OPENCLAW_CHAT_URL="${STYLIST_OPENCLAW_CHAT_URL:-http://127.0.0.1:18789/api/asis/chat}"
export STYLIST_OPENCLAW_MEMORY_URL="${STYLIST_OPENCLAW_MEMORY_URL:-http://127.0.0.1:18789/api/asis/memory}"
export STYLIST_ASIS_TOOL_BASE_URL="${STYLIST_ASIS_TOOL_BASE_URL:-http://${APP_HOST}:${APP_PORT}}"
export ASIS_TOOL_BASE_URL="${ASIS_TOOL_BASE_URL:-http://${APP_HOST}:${APP_PORT}}"
export ASIS_XHS_MCP_URL="${ASIS_XHS_MCP_URL:-http://127.0.0.1:18060/mcp}"
export ASIS_XHS_MCP_MODE="${ASIS_XHS_MCP_MODE:-streamable-http}"
export ASIS_XHS_ALLOWED_TOOLS="${ASIS_XHS_ALLOWED_TOOLS:-check_login_status,search_feeds,get_feed_detail,list_feeds}"
export ASIS_OPENCLAW_BRIDGE_HOST="${ASIS_OPENCLAW_BRIDGE_HOST:-127.0.0.1}"
export ASIS_OPENCLAW_BRIDGE_PORT="${ASIS_OPENCLAW_BRIDGE_PORT:-18789}"
export OPENCLAW_HOME="${OPENCLAW_HOME:-$ROOT_DIR/asis-agent-runtime/.openclaw-home}"
export OPENCLAW_STATE_DIR="${OPENCLAW_STATE_DIR:-$ROOT_DIR/asis-agent-runtime/.openclaw}"
export OPENCLAW_CONFIG_PATH="${OPENCLAW_CONFIG_PATH:-$ROOT_DIR/asis-agent-runtime/config/openclaw.local.json}"

PIDS=()

cleanup() {
  for pid in "${PIDS[@]:-}"; do
    if kill -0 "$pid" >/dev/null 2>&1; then
      kill "$pid" >/dev/null 2>&1 || true
    fi
  done
}
trap cleanup EXIT INT TERM

require_file() {
  if [ ! -e "$1" ]; then
    echo "Missing required file: $1" >&2
    exit 1
  fi
}

require_file "$PYTHON_BIN"
require_file "$UVICORN_BIN"
require_file "$ROOT_DIR/asis-agent-runtime/scripts/start-asis-openclaw-bridge.sh"
require_file "$ROOT_DIR/asis-agent-runtime/scripts/start-xhs-mcp-go.sh"

echo "Starting asis OpenClaw bridge..."
(
  cd "$ROOT_DIR"
  NODE_BIN="$NODE_BIN" ./asis-agent-runtime/scripts/start-asis-openclaw-bridge.sh
) >"$RUNTIME_DIR/openclaw-bridge.log" 2>&1 &
PIDS+=("$!")

echo "Starting Xiaohongshu MCP sidecar..."
(
  cd "$ROOT_DIR"
  ./asis-agent-runtime/scripts/start-xhs-mcp-go.sh -headless="$ASIS_XHS_HEADLESS"
) >"$RUNTIME_DIR/xiaohongshu-mcp.log" 2>&1 &
PIDS+=("$!")

echo "Starting FastAPI app..."
(
  cd "$ROOT_DIR"
  "$UVICORN_BIN" app.main:app --host "$APP_HOST" --port "$APP_PORT"
) >"$RUNTIME_DIR/fastapi.log" 2>&1 &
PIDS+=("$!")

echo "Logs:"
echo "  $RUNTIME_DIR/openclaw-bridge.log"
echo "  $RUNTIME_DIR/xiaohongshu-mcp.log"
echo "  $RUNTIME_DIR/fastapi.log"
echo
echo "asis app: http://${APP_HOST}:${APP_PORT}/asis/demo"
echo "readiness: http://${APP_HOST}:${APP_PORT}/asis/runtime-readiness"
echo
echo "Waiting for services. Press Ctrl+C to stop all."

sleep 3
"$PYTHON_BIN" "$ROOT_DIR/scripts/check_runtime_readiness.py" || true

wait
