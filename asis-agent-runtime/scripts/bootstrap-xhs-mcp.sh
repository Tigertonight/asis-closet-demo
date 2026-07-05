#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENDOR_DIR="$ROOT_DIR/vendor"
XHS_DIR="$VENDOR_DIR/xiaohongshu-mcp"
UPSTREAM_URL="${XHS_MCP_UPSTREAM_URL:-https://github.com/xpzouying/xiaohongshu-mcp.git}"

mkdir -p "$VENDOR_DIR"

if [ -d "$XHS_DIR/.git" ]; then
  git -C "$XHS_DIR" fetch --depth 1 origin main
  git -C "$XHS_DIR" checkout FETCH_HEAD
else
  git clone --depth 1 "$UPSTREAM_URL" "$XHS_DIR"
fi

COMMIT="$(git -C "$XHS_DIR" rev-parse HEAD)"
DATE="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
cat > "$ROOT_DIR/xiaohongshu-mcp.lock.json" <<JSON
{
  "upstream": "$UPSTREAM_URL",
  "resolved_commit": "$COMMIT",
  "resolved_at": "$DATE",
  "notes": "Locked by scripts/bootstrap-xhs-mcp.sh. Run with Go from vendor/xiaohongshu-mcp when Go is installed."
}
JSON

echo "Xiaohongshu MCP upstream locked at $COMMIT"
if command -v go >/dev/null 2>&1; then
  echo "Go is available. Start with: cd $XHS_DIR && go run . -headless=true"
else
  echo "Go is not available on PATH. Install Go before starting xpzouying/xiaohongshu-mcp, or use a Node RedNote MCP sidecar."
fi
