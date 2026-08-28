#!/usr/bin/env bash
# Selfit 一键服务器初始化脚本（Ubuntu 22.04 / 24.04，免备案海外服务器）
# 用法：先把代码放到 /opt/selfit/asis-closet-demo，然后以 root 运行：
#   sudo bash deploy/setup_server.sh
# 幂等：重复运行安全，已安装的组件会跳过。

set -euo pipefail

APP_DIR="${SELFIT_APP_DIR:-/opt/selfit/asis-closet-demo}"
DOMAIN="${SELFIT_DOMAIN:-selfit.com.cn}"
LOG_TAG="[selfit-setup]"

log() { echo "$LOG_TAG $*"; }
die() { echo "$LOG_TAG ERROR: $*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "请用 root / sudo 运行本脚本"
[[ -f "$APP_DIR/scripts/deploy_demo.sh" ]] || die "未找到 $APP_DIR，请先上传代码（见 deploy/README.md）"

# ---------- 1. 系统依赖 ----------
log "安装系统依赖..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y --no-install-recommends \
    git curl ca-certificates gnupg build-essential software-properties-common \
    libglib2.0-0 libgl1 libgomp1 libjpeg-dev zlib1g-dev \
    libgles2 libegl1 \
    chromium-browser 2>/dev/null || \
    apt-get install -y --no-install-recommends chromium 2>/dev/null || \
    log "chromium 安装跳过（小红书 MCP sidecar 可能需要它，可稍后手动安装）"
# libgles2/libegl1：无头服务器上 mediapipe C 绑定库动态链接必需，
# 缺失会导致 pose/face landmarker 静默初始化失败（selfit 照片检测全挂）。

# Python 3.11（与 Dockerfile 保持一致）
if ! command -v python3.11 >/dev/null 2>&1; then
    log "安装 Python 3.11 (deadsnakes PPA)..."
    add-apt-repository -y ppa:deadsnakes/ppa
    apt-get update -y
    apt-get install -y python3.11 python3.11-venv python3.11-dev
fi

# Node.js 20 LTS（OpenClaw bridge 需要）
if ! command -v node >/dev/null 2>&1 || [[ "$(node -v | cut -c2- | cut -d. -f1)" -lt 18 ]]; then
    log "安装 Node.js 20 (NodeSource)..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt-get install -y nodejs
fi
log "node $(node -v)"

# Caddy（自动 HTTPS）
if ! command -v caddy >/dev/null 2>&1; then
    log "安装 Caddy..."
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
    apt-get update -y
    apt-get install -y caddy
fi

# ---------- 2. Python 虚拟环境 ----------
# SELFIT_PROFILE:
#   slim  (默认) 只装 requirements.txt + rembg/onnxruntime —— 2C2G/2C4G 可跑试穿主流程
#   full          额外装 torch/transformers（衣柜自动分割）—— 建议 4C8G
PROFILE="${SELFIT_PROFILE:-slim}"
log "部署档位: $PROFILE"

cd "$APP_DIR"
if [[ ! -x .venv/bin/python ]]; then
    log "创建 venv 并安装 Python 依赖..."
    python3.11 -m venv .venv
fi
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
if [[ "$PROFILE" == "full" ]]; then
    .venv/bin/pip install -r requirements-ai.txt
else
    # 轻量抠图（onnxruntime + u2net，远轻于 torch）
    .venv/bin/pip install "rembg>=2.0.59" "onnxruntime>=1.18.0"
fi

# ---------- 3. Bootstrap sidecars（仅 full 档；slim 档 REQUIRE_SIDECARS=0 跳过） ----------
if [[ "$PROFILE" == "full" ]]; then
    log "Bootstrap OpenClaw bridge（clone + pnpm build）..."
    bash selfit-agent-runtime/scripts/bootstrap-openclaw.sh || log "WARN: openclaw bootstrap 失败，AI 搭配师 sidecar 将不可用（可在 .env.demo 设 REQUIRE_SIDECARS=0 先上线主流程）"
    if [[ -f selfit-agent-runtime/scripts/build-openclaw.sh ]]; then
        npm install -g pnpm@9 >/dev/null 2>&1 || true
        bash selfit-agent-runtime/scripts/build-openclaw.sh || log "WARN: openclaw build 失败"
    fi

    log "Bootstrap Xiaohongshu MCP（clone + Go 工具链）..."
    bash selfit-agent-runtime/scripts/bootstrap-xhs-mcp.sh || log "WARN: xiaohongshu-mcp bootstrap 失败，小红书链接提取 sidecar 将不可用"
    .venv/bin/python selfit-agent-runtime/scripts/bootstrap-go-runtime.py || log "WARN: Go 工具链下载失败"
else
    log "slim 档：跳过 sidecar bootstrap（AI 搭配师 / 小红书链接提取不可用）"
fi

# ---------- 4. 运行目录 ----------
mkdir -p outputs/runtime outputs/users uploads/users \
    selfit-agent-runtime/.openclaw selfit-agent-runtime/.openclaw-home

# ---------- 5. .env.demo ----------
if [[ ! -f .env.demo ]]; then
    log "生成 .env.demo..."
    cp .env.demo.example .env.demo
    SECRET="$(openssl rand -hex 32)"
    sed -i.bak "s|^SELFIT_AUTH_SECRET=$|SELFIT_AUTH_SECRET=$SECRET|" .env.demo && rm -f .env.demo.bak
    if [[ "$PROFILE" == "slim" ]]; then
        sed -i.bak "s|^REQUIRE_SIDECARS=1|REQUIRE_SIDECARS=0|" .env.demo && rm -f .env.demo.bak
        sed -i.bak "s|^REQUIRE_TRYON=1|REQUIRE_TRYON=0|" .env.demo && rm -f .env.demo.bak
        log "slim 档：已设 REQUIRE_SIDECARS=0 / REQUIRE_TRYON=0"
    fi
    log "已生成随机 SELFIT_AUTH_SECRET"
    log "重要：请编辑 $APP_DIR/.env.demo 填写 TRYON_RUNWAY_GOOGLE_URL / TRYON_RUNWAY_GOOGLE_API_KEY（见 deploy/README.md）"
fi

# ---------- 6. systemd 服务 ----------
log "安装 systemd 服务 selfit.service..."
install -m 0644 deploy/selfit.service /etc/systemd/system/selfit.service
sed -i.bak "s|/opt/selfit/asis-closet-demo|$APP_DIR|g" /etc/systemd/system/selfit.service && rm -f /etc/systemd/system/selfit.service.bak
systemctl daemon-reload
systemctl enable selfit

# ---------- 7. Caddy 反代 ----------
log "配置 Caddy（$DOMAIN -> 127.0.0.1:8002）..."
install -m 0644 deploy/Caddyfile /etc/caddy/Caddyfile
sed -i.bak "s|selfit.com.cn|$DOMAIN|g" /etc/caddy/Caddyfile && rm -f /etc/caddy/Caddyfile.bak
systemctl enable caddy

# ---------- 8. Swap（小内存机器的 OOM 保险） ----------
TOTAL_MEM_MB=$(grep MemTotal /proc/meminfo | awk '{print int($2/1024)}')
if [[ $TOTAL_MEM_MB -le 2048 ]] && ! swapon --show | grep -q .; then
    if [[ -f /swapfile ]]; then
        log "发现旧 /swapfile 但未启用，重新启用..."
        swapon /swapfile || log "WARN: swap 启用失败"
    else
        log "内存 ${TOTAL_MEM_MB}MB <= 2G 且无 swap，创建 2G /swapfile..."
        dd if=/dev/zero of=/swapfile bs=1M count=2048 status=progress
        chmod 600 /swapfile
        mkswap /swapfile
        swapon /swapfile
        echo '/swapfile none swap sw 0 0' >> /etc/fstab
        # 低 swappiness：尽量用内存，swap 只做 OOM 兜底
        sysctl -w vm.swappiness=10 >/dev/null
        echo 'vm.swappiness=10' > /etc/sysctl.d/99-selfit-swap.conf
        log "swap 已启用（2G，swappiness=10）"
    fi
fi

# ---------- 9. 防火墙 ----------
if command -v ufw >/dev/null 2>&1 && ufw status | grep -q "Status: active"; then
    ufw allow 80/tcp || true
    ufw allow 443/tcp || true
    log "ufw 已放行 80/443"
fi

cat <<'DONE'

==================== 初始化完成 ====================
接下来：
1. 编辑 .env.demo 填写密钥：
     vim /opt/selfit/asis-closet-demo/.env.demo
2. 启动服务：
     systemctl restart selfit caddy
3. 查看状态/日志：
     systemctl status selfit
     journalctl -u selfit -f
     journalctl -u caddy -f
4. 健康检查：
     curl -s http://127.0.0.1:8002/health
     curl -s https://DOMAIN/health   （DNS 生效 + Caddy 签发证书后）

务必确认域名 DNS 已解析到本机公网 IP（A 记录 @ 和 www）。
====================================================
DONE
