#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
XHS_DIR="$ROOT_DIR/vendor/xiaohongshu-mcp"
VENDORED_GO="$ROOT_DIR/vendor/toolchains/go/bin/go"
GO_BIN="${GO_BIN:-}"

if [ -z "$GO_BIN" ]; then
  if command -v go >/dev/null 2>&1; then
    GO_BIN="$(command -v go)"
  elif [ -x "$VENDORED_GO" ]; then
    GO_BIN="$VENDORED_GO"
  else
    echo "Go is not available. Run python scripts/bootstrap-go-runtime.py first, or install Go." >&2
    exit 1
  fi
fi

if [ ! -d "$XHS_DIR" ]; then
  echo "xiaohongshu-mcp source is missing. Run ./scripts/bootstrap-xhs-mcp.sh first." >&2
  exit 1
fi

cd "$XHS_DIR"
exec "$GO_BIN" run . "$@"
