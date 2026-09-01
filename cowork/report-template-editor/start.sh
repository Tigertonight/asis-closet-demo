#!/usr/bin/env bash
# start.sh — 由 Guard 拉起业务主进程；末行必须 exec
set -eo pipefail
cd "$(dirname "$0")"

# Pod 镜像预置 /opt/venv/bin 在 PATH 最前，python3 直接解析到 /opt/venv/bin/python3。
# 禁止在工程内建 .venv（verify_no_venv_creation.sh 会卡；详见 subapp-spec §4.1）。
export APP_PORT="${APP_PORT:-3000}"
exec python3 -m uvicorn app:app --host 0.0.0.0 --port "${APP_PORT}" 2>&1
