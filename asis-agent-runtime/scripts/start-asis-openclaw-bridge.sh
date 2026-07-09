#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
NODE_BIN="${NODE_BIN:-node}"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/../.venv/bin/python}"

load_dotenv() {
  local env_file="$ROOT_DIR/../.env"
  if [ ! -f "$env_file" ]; then
    return
  fi
  if [ ! -x "$PYTHON_BIN" ]; then
    return
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

if ! command -v "$NODE_BIN" >/dev/null 2>&1; then
  echo "node is not available. Set NODE_BIN to a node executable path." >&2
  exit 1
fi

if [ ! -f "$ROOT_DIR/vendor/openclaw/dist/entry.mjs" ] && [ ! -f "$ROOT_DIR/vendor/openclaw/dist/entry.js" ]; then
  echo "OpenClaw is not built. Run ./scripts/build-openclaw.sh first." >&2
  exit 1
fi

export ASIS_OPENCLAW_BRIDGE_HOST="${ASIS_OPENCLAW_BRIDGE_HOST:-127.0.0.1}"
export ASIS_OPENCLAW_BRIDGE_PORT="${ASIS_OPENCLAW_BRIDGE_PORT:-18789}"
export ASIS_TOOL_BASE_URL="${ASIS_TOOL_BASE_URL:-http://127.0.0.1:8002}"
export OPENCLAW_HOME="${OPENCLAW_HOME:-$ROOT_DIR/.openclaw-home}"
export OPENCLAW_STATE_DIR="${OPENCLAW_STATE_DIR:-$ROOT_DIR/.openclaw}"
export OPENCLAW_CONFIG_PATH="${OPENCLAW_CONFIG_PATH:-$ROOT_DIR/config/openclaw.local.json}"

mkdir -p "$OPENCLAW_HOME" "$OPENCLAW_STATE_DIR"

exec "$NODE_BIN" "$ROOT_DIR/scripts/asis-openclaw-bridge.mjs"
