#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME_DIR="$ROOT_DIR/outputs/runtime"
mkdir -p "$RUNTIME_DIR"

export ASIS_ENV="${ASIS_ENV:-demo}"
export ASIS_PUBLIC_DEMO="${ASIS_PUBLIC_DEMO:-1}"
export ASIS_AUTH_RETURN_DEV_CODE="${ASIS_AUTH_RETURN_DEV_CODE:-0}"
export ASIS_AUTH_ALLOW_MOCK_CODES="${ASIS_AUTH_ALLOW_MOCK_CODES:-0}"
export ASIS_MAX_REQUEST_BODY_MB="${ASIS_MAX_REQUEST_BODY_MB:-36}"
export ASIS_UPLOAD_RATE_LIMIT="${ASIS_UPLOAD_RATE_LIMIT:-60}"
export ASIS_AI_RATE_LIMIT="${ASIS_AI_RATE_LIMIT:-30}"
export ASIS_AUTH_RATE_LIMIT="${ASIS_AUTH_RATE_LIMIT:-20}"

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
APP_HOST="${APP_HOST:-0.0.0.0}"
APP_PORT="${APP_PORT:-8002}"
ASIS_CLEANUP_DAYS="${ASIS_CLEANUP_DAYS:-7}"
ASIS_CLEANUP_INTERVAL_SECONDS="${ASIS_CLEANUP_INTERVAL_SECONDS:-21600}"
REQUIRE_SIDECARS="${REQUIRE_SIDECARS:-1}"

if [ -z "${ASIS_AUTH_SECRET:-}" ] || [ "$ASIS_AUTH_SECRET" = "asis-local-auth-secret" ]; then
  echo "ASIS_AUTH_SECRET must be set to a strong non-default value before running the public demo." >&2
  exit 1
fi

PIDS=()
cleanup() {
  for pid in "${PIDS[@]:-}"; do
    if kill -0 "$pid" >/dev/null 2>&1; then
      kill "$pid" >/dev/null 2>&1 || true
    fi
  done
}
trap cleanup EXIT INT TERM

(
  while true; do
    "$PYTHON_BIN" "$ROOT_DIR/scripts/cleanup_user_outputs.py" --days "$ASIS_CLEANUP_DAYS" >>"$RUNTIME_DIR/cleanup.log" 2>&1 || true
    sleep "$ASIS_CLEANUP_INTERVAL_SECONDS"
  done
) &
PIDS+=("$!")

WAIT_ARGS=("--timeout" "120")
if [ "$REQUIRE_SIDECARS" = "1" ]; then
  WAIT_ARGS+=("--require-sidecars")
fi

APP_HOST="$APP_HOST" APP_PORT="$APP_PORT" "$ROOT_DIR/scripts/start_asis_full_stack.sh" &
PIDS+=("$!")

"$PYTHON_BIN" "$ROOT_DIR/scripts/wait_for_demo_readiness.py" "${WAIT_ARGS[@]}"

echo "Demo is ready at http://${APP_HOST}:${APP_PORT}/asis/demo"
wait

