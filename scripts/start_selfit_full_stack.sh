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
import os
import sys
from dotenv import dotenv_values

env_file = Path(sys.argv[1])
for key, value in dotenv_values(env_file).items():
    if key and value is not None and key not in os.environ:
        print(f"{key}={value}", end="\0")
PY
  )
}

load_dotenv

# shellcheck source=selfit_env_compat.sh
source "$ROOT_DIR/scripts/selfit_env_compat.sh"
promote_legacy_selfit_env

APP_HOST="${APP_HOST:-127.0.0.1}"
APP_PORT="${APP_PORT:-8002}"
SELFIT_XHS_HEADLESS="${SELFIT_XHS_HEADLESS:-true}"
SELFIT_OPENCLAW_BRIDGE_HOST="${SELFIT_OPENCLAW_BRIDGE_HOST:-127.0.0.1}"
SELFIT_OPENCLAW_BRIDGE_PORT="${SELFIT_OPENCLAW_BRIDGE_PORT:-18789}"

export STYLIST_OPENCLAW_CHAT_URL="${STYLIST_OPENCLAW_CHAT_URL:-http://127.0.0.1:18789/api/selfit/chat}"
export STYLIST_OPENCLAW_MEMORY_URL="${STYLIST_OPENCLAW_MEMORY_URL:-http://127.0.0.1:18789/api/selfit/memory}"
export STYLIST_SELFIT_TOOL_BASE_URL="${STYLIST_SELFIT_TOOL_BASE_URL:-http://${APP_HOST}:${APP_PORT}}"
export SELFIT_TOOL_BASE_URL="${SELFIT_TOOL_BASE_URL:-http://${APP_HOST}:${APP_PORT}}"
export SELFIT_XHS_MCP_URL="${SELFIT_XHS_MCP_URL:-http://127.0.0.1:18060/mcp}"
export SELFIT_XHS_MCP_MODE="${SELFIT_XHS_MCP_MODE:-streamable-http}"
export SELFIT_XHS_ALLOWED_TOOLS="${SELFIT_XHS_ALLOWED_TOOLS:-check_login_status,search_feeds,get_feed_detail,list_feeds}"
export SELFIT_OPENCLAW_BRIDGE_HOST
export SELFIT_OPENCLAW_BRIDGE_PORT
export OPENCLAW_HOME="${OPENCLAW_HOME:-$ROOT_DIR/selfit-agent-runtime/.openclaw-home}"
export OPENCLAW_STATE_DIR="${OPENCLAW_STATE_DIR:-$ROOT_DIR/selfit-agent-runtime/.openclaw}"
export OPENCLAW_CONFIG_PATH="${OPENCLAW_CONFIG_PATH:-$ROOT_DIR/selfit-agent-runtime/config/openclaw.local.json}"

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
require_file "$ROOT_DIR/selfit-agent-runtime/scripts/start-selfit-openclaw-bridge.sh"
require_file "$ROOT_DIR/selfit-agent-runtime/scripts/start-xhs-mcp-go.sh"

kill_listener_on_port() {
  local port="$1"
  local pids
  pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN -n -P 2>/dev/null || true)"
  if [ -n "$pids" ]; then
    echo "Stopping stale listener(s) on port $port: $pids"
    # shellcheck disable=SC2086
    kill $pids >/dev/null 2>&1 || true
    sleep 1
    pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN -n -P 2>/dev/null || true)"
    if [ -n "$pids" ]; then
      # shellcheck disable=SC2086
      kill -9 $pids >/dev/null 2>&1 || true
    fi
  fi
}

if [ "${SELFIT_SKIP_PORT_CLEANUP:-false}" != "true" ]; then
  kill_listener_on_port "$APP_PORT"
  kill_listener_on_port "$SELFIT_OPENCLAW_BRIDGE_PORT"
  kill_listener_on_port "18060"
fi

echo "Starting selfit OpenClaw bridge..."
(
  cd "$ROOT_DIR"
  NODE_BIN="$NODE_BIN" ./selfit-agent-runtime/scripts/start-selfit-openclaw-bridge.sh
) >"$RUNTIME_DIR/openclaw-bridge.log" 2>&1 &
PIDS+=("$!")

echo "Starting Xiaohongshu MCP sidecar..."
(
  cd "$ROOT_DIR"
  ./selfit-agent-runtime/scripts/start-xhs-mcp-go.sh -headless="$SELFIT_XHS_HEADLESS"
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
echo "selfit app: http://${APP_HOST}:${APP_PORT}/selfit/demo"
echo "readiness: http://${APP_HOST}:${APP_PORT}/selfit/runtime-readiness"
echo
echo "Waiting for services. Press Ctrl+C to stop all."

sleep 3
"$PYTHON_BIN" "$ROOT_DIR/scripts/check_runtime_readiness.py" || true

wait
