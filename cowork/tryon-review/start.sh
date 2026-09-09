#!/usr/bin/env bash
# start.sh - 由 Guard 应用拉起业务主进程；末行必须 exec
# 由 guard-transform 模板渲染生成
set -eo pipefail
cd "$(dirname "$0")"

# Linux 上用 .venv 绝对路径调用 python，避免 exec 替换 shell 后 PATH 失效
if [ "$(uname)" = "Linux" ] && [ -f ".venv/bin/python" ]; then
  PYTHON=".venv/bin/python"
else
  PYTHON="python3"
fi

export APP_PORT="${APP_PORT:-3000}"
exec $PYTHON -m uvicorn app:app --host 0.0.0.0 --port ${APP_PORT} 2>&1
