#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENDOR_DIR="$ROOT_DIR/vendor"
OPENCLAW_DIR="$VENDOR_DIR/openclaw"
UPSTREAM_URL="${OPENCLAW_UPSTREAM_URL:-https://github.com/openclaw/openclaw.git}"

mkdir -p "$VENDOR_DIR"

if [ -d "$OPENCLAW_DIR/.git" ]; then
  git -C "$OPENCLAW_DIR" fetch --depth 1 origin main
  git -C "$OPENCLAW_DIR" checkout FETCH_HEAD
else
  git clone --depth 1 "$UPSTREAM_URL" "$OPENCLAW_DIR"
fi

COMMIT="$(git -C "$OPENCLAW_DIR" rev-parse HEAD)"
python3 - "$ROOT_DIR/openclaw.lock.json" "$UPSTREAM_URL" "$COMMIT" <<'PY'
import json
import sys
from datetime import datetime, timezone

path, upstream, commit = sys.argv[1:4]
data = {
    "upstream": upstream,
    "resolved_commit": commit,
    "resolved_at": datetime.now(timezone.utc).isoformat(),
    "notes": "Locked by scripts/bootstrap-openclaw.sh. selfit layer remains outside vendor/openclaw.",
}
with open(path, "w", encoding="utf-8") as handle:
    json.dump(data, handle, ensure_ascii=False, indent=2)
    handle.write("\n")
PY

echo "OpenClaw upstream locked at $COMMIT"
