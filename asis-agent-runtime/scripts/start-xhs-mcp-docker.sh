#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE_DIR="$ROOT_DIR/vendor/xiaohongshu-mcp/docker"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is not available. Install Docker Desktop, or install Go and run vendor/xiaohongshu-mcp with go run ." >&2
  exit 1
fi

if [ ! -f "$COMPOSE_DIR/docker-compose.yml" ]; then
  echo "xiaohongshu-mcp docker compose file is missing. Run ./scripts/bootstrap-xhs-mcp.sh first." >&2
  exit 1
fi

mkdir -p "$COMPOSE_DIR/data" "$COMPOSE_DIR/images"
cd "$COMPOSE_DIR"
docker compose up -d
echo "Xiaohongshu MCP should be available at http://127.0.0.1:18060/mcp"
