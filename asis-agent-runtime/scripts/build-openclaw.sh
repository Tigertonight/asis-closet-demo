#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OPENCLAW_DIR="$ROOT_DIR/vendor/openclaw"
PNPM_BIN="${PNPM_BIN:-pnpm}"
NODE_BIN="${NODE_BIN:-node}"

if [ ! -d "$OPENCLAW_DIR" ]; then
  echo "OpenClaw source is missing. Run ./scripts/bootstrap-openclaw.sh first." >&2
  exit 1
fi

if ! command -v "$PNPM_BIN" >/dev/null 2>&1; then
  echo "pnpm is not available. Set PNPM_BIN to a pnpm executable path." >&2
  exit 1
fi
if command -v "$NODE_BIN" >/dev/null 2>&1; then
  NODE_DIR="$(dirname "$(command -v "$NODE_BIN")")"
  export PATH="$NODE_DIR:$PATH"
else
  echo "node is not available. Set NODE_BIN to a node executable path." >&2
  exit 1
fi

cd "$OPENCLAW_DIR"
"$PNPM_BIN" install --frozen-lockfile
"$PNPM_BIN" build

if [ ! -f "$OPENCLAW_DIR/dist/entry.mjs" ] && [ ! -f "$OPENCLAW_DIR/dist/entry.js" ]; then
  echo "OpenClaw build finished but dist/entry.(m)js is missing." >&2
  exit 1
fi

echo "OpenClaw build is ready."
