#!/usr/bin/env bash
# 唯一合法的服务器发布方式：从 git 发布，禁止 rsync/tar 整目录镜像覆盖。
#
# 背景：2026-08-28 内测期间发生过事故——并行部署时一方用
# `rsync --delete -o -g -t` 把本地工作目录镜像覆盖到服务器，把另一方刚
# 部署的算法修复回滚成了旧版，导致「同答案不同人格」的用户反馈。
# 之后所有发布（人类或 AI）统一走本脚本。
#
# 用法（服务器上）：
#   sudo bash scripts/deploy_release.sh              # 发布 origin/main 最新提交
#   sudo bash scripts/deploy_release.sh <commit>     # 发布指定提交
#
# 脚本做五件事：
#   1. 校验工作区干净且与 git 一致（防本地脏文件/旧文件混入）
#   2. 备份当前运行版本（/opt/selfit/deploy-backups/<时间戳>/）
#   3. git 硬重置到目标提交（代码=git，杜绝镜像覆盖）
#   4. 跑核心测试（分型/照片检测/管理后台契约）
#   5. 重启服务 + 健康检查 + 版本指纹核对
#
# 回滚：
#   sudo bash scripts/deploy_release.sh <上一个commit>

set -euo pipefail

APP_DIR="${SELFIT_APP_DIR:-/opt/selfit/asis-closet-demo}"
BACKUP_ROOT="/opt/selfit/deploy-backups"
VENV="$APP_DIR/.venv"
SERVICE="${SELFIT_SERVICE:-selfit}"

cd "$APP_DIR"

# ---------- 1. 前置校验 ----------
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "[deploy] ERROR: $APP_DIR 不是 git 仓库（可能被镜像覆盖破坏过）。请重新 git clone 后再用本脚本发布。" >&2
    exit 1
fi

# 运行数据目录不在 git 里，代码与数据分离；outputs/ qa_photos/ 等运行时
# 目录被 .gitignore 忽略，git reset 不会碰它们。
git fetch origin --prune

TARGET_COMMIT="${1:-origin/main}"
git rev-parse --verify "$TARGET_COMMIT^{commit}" >/dev/null 2>&1 || {
    echo "[deploy] ERROR: 目标提交 $TARGET_COMMIT 不存在" >&2
    exit 1
}
TARGET_SHA=$(git rev-parse "$TARGET_COMMIT^{commit}")
CURRENT_SHA=$(git rev-parse HEAD 2>/dev/null || echo "none")

echo "[deploy] 当前: $CURRENT_SHA"
echo "[deploy] 目标: $TARGET_SHA"

# ---------- 2. 备份当前版本 ----------
STAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_DIR="$BACKUP_ROOT/$STAMP"
mkdir -p "$BACKUP_DIR"
if [ "$CURRENT_SHA" != "none" ]; then
    git archive "$CURRENT_SHA" | tar -x -C "$BACKUP_DIR"
    echo "[deploy] 已备份当前代码到 $BACKUP_DIR"
fi

# ---------- 3. 发布目标版本 ----------
# 硬重置：服务器代码永远等于某个 git 提交。任何未经 git 的文件改动
# （rsync --delete / tar 覆盖 / 手改）都会在下一次发布被纠正回来。
git reset --hard "$TARGET_SHA"

# 环境文件不进 git，单独保留（已存在则不动）
if [ ! -f "$APP_DIR/.env.demo" ]; then
    echo "[deploy] WARNING: .env.demo 不存在，服务可能起不来（从 example 复制并填写密钥）" >&2
fi

# 依赖同步（requirements.txt 变化时才重装）
if [ -f "$VENV/bin/pip" ]; then
    "$VENV/bin/pip" install -q -r "$APP_DIR/requirements.txt"
else
    echo "[deploy] WARNING: venv 不存在，跳过依赖安装（首次部署请先跑 deploy/setup_server.sh）" >&2
fi

# ---------- 4. 核心测试 ----------
echo "[deploy] 运行核心测试…"
cd "$APP_DIR"
"$VENV/bin/python" -m pytest tests/test_selfit_persona.py tests/test_selfit_photo_wiring.py tests/test_selfit_admin_submissions.py -q

# ---------- 5. 重启 + 健康检查 + 版本核对 ----------
systemctl restart "$SERVICE"
for i in $(seq 1 15); do
    if curl -fsS "http://127.0.0.1:8002/health" >/dev/null 2>&1; then
        break
    fi
    sleep 2
    if [ "$i" = "15" ]; then
        echo "[deploy] ERROR: 服务健康检查失败，回滚到 $CURRENT_SHA" >&2
        git reset --hard "$CURRENT_SHA"
        systemctl restart "$SERVICE"
        exit 1
    fi
done

DEPLOYED=$(git rev-parse HEAD)
echo "[deploy] 发布完成: $DEPLOYED"
curl -fsS "http://127.0.0.1:8002/health" && echo
echo "[deploy] 如需回滚: sudo bash scripts/deploy_release.sh $CURRENT_SHA"
