#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME_DIR="$ROOT_DIR/outputs/runtime"
mkdir -p "$RUNTIME_DIR"

# shellcheck source=selfit_env_compat.sh
source "$ROOT_DIR/scripts/selfit_env_compat.sh"
promote_legacy_selfit_env

export SELFIT_ENV="${SELFIT_ENV:-demo}"
export SELFIT_PUBLIC_DEMO="${SELFIT_PUBLIC_DEMO:-1}"
export SELFIT_AUTH_RETURN_DEV_CODE="${SELFIT_AUTH_RETURN_DEV_CODE:-0}"
export SELFIT_AUTH_ALLOW_MOCK_CODES="${SELFIT_AUTH_ALLOW_MOCK_CODES:-0}"
export SELFIT_MAX_REQUEST_BODY_MB="${SELFIT_MAX_REQUEST_BODY_MB:-36}"
export SELFIT_UPLOAD_RATE_LIMIT="${SELFIT_UPLOAD_RATE_LIMIT:-60}"
export SELFIT_AI_RATE_LIMIT="${SELFIT_AI_RATE_LIMIT:-30}"
export SELFIT_AUTH_RATE_LIMIT="${SELFIT_AUTH_RATE_LIMIT:-20}"

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
APP_HOST="${APP_HOST:-0.0.0.0}"
APP_PORT="${APP_PORT:-8002}"
SELFIT_CLEANUP_DAYS="${SELFIT_CLEANUP_DAYS:-7}"
SELFIT_CLEANUP_INTERVAL_SECONDS="${SELFIT_CLEANUP_INTERVAL_SECONDS:-21600}"
REQUIRE_SIDECARS="${REQUIRE_SIDECARS:-1}"

if [ -z "${SELFIT_AUTH_SECRET:-}" ] || [ "$SELFIT_AUTH_SECRET" = "selfit-local-auth-secret" ]; then
  echo "SELFIT_AUTH_SECRET must be set to a strong non-default value before running the public demo." >&2
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
    "$PYTHON_BIN" "$ROOT_DIR/scripts/cleanup_user_outputs.py" --days "$SELFIT_CLEANUP_DAYS" >>"$RUNTIME_DIR/cleanup.log" 2>&1 || true
    sleep "$SELFIT_CLEANUP_INTERVAL_SECONDS"
  done
) &
PIDS+=("$!")

WAIT_ARGS=("--timeout" "120")
if [ "$REQUIRE_SIDECARS" = "1" ]; then
  WAIT_ARGS+=("--require-sidecars")
fi

APP_HOST="$APP_HOST" APP_PORT="$APP_PORT" "$ROOT_DIR/scripts/start_selfit_full_stack.sh" &
PIDS+=("$!")

"$PYTHON_BIN" "$ROOT_DIR/scripts/wait_for_demo_readiness.py" "${WAIT_ARGS[@]}"

echo "Demo is ready at http://${APP_HOST}:${APP_PORT}/selfit/demo"
wait
