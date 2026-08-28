# Selfit 生产部署手册（香港/海外免备案 · 当天上线）

本手册用于把 selfit demo 部署到 `selfit.com.cn`（阿里云购买的域名）+ 海外服务器，全程免 ICP 备案。

---

## 0. 前置条件清单

| 项目 | 要求 | 状态 |
|---|---|---|
| 域名实名认证 | 阿里云域名控制台 → 实名认证（不通过则域名无法解析） | ☐ |
| 服务器 | 阿里云香港 ECS（或任意海外 VPS） | ☐ |
| 试穿 API Key | **必须是公网可达的 Gemini key**（见下方警告） | ☐ |

### ⚠️ 关键警告：试穿 API 不能用公司内网网关

`.env.demo.example` 里的 `TRYON_RUNWAY_GOOGLE_URL=https://runway.devops.rednote.life/...` 解析到**小红书内网 IP（10.x）**，海外服务器无法访问，上线必须替换为公网端点：

```bash
# .env.demo 中替换为（Google AI Studio 申请 key: https://aistudio.google.com/apikey）
TRYON_RUNWAY_GOOGLE_URL=https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent
TRYON_RUNWAY_GOOGLE_API_KEY=<你的公网 Gemini API key>
```

代码已适配官方 Gemini 认证（`x-goog-api-key` header），payload 本身就是标准 `generateContent` 格式，无需其他改动。香港服务器访问 `googleapis.com` 无障碍。

---

## 1. 购买香港服务器

**推荐：阿里云「轻量应用服务器」**（比标准 ECS 便宜很多，demo 阶段完全够用）：

- **地域**：中国香港
- **套餐**：2C2G 30Mbps（约 34-60 元/月，slim 档可跑，见下方内存说明）或 2C4G（更稳）
- **镜像**：Ubuntu 22.04 / 24.04
- **流量**：套餐自带（一般 1TB/月），试穿是图片密集型，超出部分按量计费也不贵

> **2C2G 内存账本**（实测）：系统+Caddy ~400MB，FastAPI 空载 ~400MB，单次试穿峰值 ~200MB，rembg 抠图 ~500-700MB。
> 单用户串行完全没问题；风险是「多用户并发试穿 + 同时触发衣柜抠图」叠加触顶被 OOM killer 杀进程。
> setup 脚本已在 ≤2G 内存机器上自动创建 2G swap 兜底（慢但不崩）；再加一道保险可在 `.env.demo` 设 `SELFIT_REMBG_ENABLED=0`（省 ~600MB，衣柜抠图退化为语义 mask）。
> 第一波用户超过 ~20 人或想省心，直接 2C4G。

如果选标准 **ECS**（弹性扩容、可绑 GPU、按量付费更灵活）：

- **规格**：slim 档 `ecs.c7.large`（2C4G）即可；full 档（含 torch 衣柜分割 + sidecar）建议 `ecs.c7.xlarge`（4C8G）
- **带宽**：按使用流量计费，峰值 30~50Mbps
- **登录方式**：SSH 密钥对（推荐）

> **部署档位**（`setup_server.sh` 的 `SELFIT_PROFILE` 环境变量）：
> - `slim`（默认）：只装基础依赖 + rembg，不装 torch、不启 sidecar。试穿主流程完整可用，**2C2G 可跑**
> - `full`：加 torch/transformers（衣柜自动分割）+ OpenClaw + 小红书 MCP。建议 4C8G
>
> 第一波用户验证主流程建议 slim；后续升级只需重跑 `SELFIT_PROFILE=full sudo bash deploy/setup_server.sh`。

记下**公网 IP**（假设为 `1.2.3.4`）。

## 2. 域名 DNS 解析

阿里云 → 云解析 DNS → `selfit.com.cn` → 添加记录：

| 记录类型 | 主机记录 | 记录值 |
|---|---|---|
| A | `@` | `1.2.3.4` |
| A | `www` | `1.2.3.4` |

> 前提：域名已完成实名认证，否则解析记录会被暂停。

## 3. 安全组

ECS 安全组入方向只放行：

| 端口 | 源 | 用途 |
|---|---|---|
| 22 | 你的 IP / 公司出口 | SSH |
| 80 | 0.0.0.0/0 | HTTP（Caddy 证书签发 + 跳转） |
| 443 | 0.0.0.0/0 | HTTPS |

**不要**放行 8002（应用只监听 127.0.0.1，由 Caddy 反代）。

## 4. 上传代码到服务器

代码在 GitHub 私有仓库，两种方式任选：

**方式 A：本机 rsync（推荐，无需处理 git 凭证）**

```bash
ssh root@1.2.3.4 "mkdir -p /opt/selfit"
rsync -av --delete \
  --exclude .git --exclude .venv --exclude __pycache__ \
  --exclude uploads --exclude outputs --exclude .pytest_cache \
  --exclude 'selfit-agent-runtime/vendor' \
  --exclude 'selfit-agent-runtime/.openclaw*' \
  --exclude '*.log' --exclude .DS_Store \
  ./ root@1.2.3.4:/opt/selfit/asis-closet-demo/
```

**方式 B：服务器 git clone（需配置 SSH deploy key）**

```bash
ssh root@1.2.3.4
mkdir -p /opt/selfit && cd /opt/selfit
# 把本机 ~/.ssh/id_ed25519.pub 内容加入 GitHub 仓库 Deploy keys（只读）
git clone git@github.com:Tigertonight/asis-closet-demo.git
```

## 5. 一键初始化

在服务器上：

```bash
cd /opt/selfit/asis-closet-demo
sudo bash deploy/setup_server.sh
```

脚本完成：python3.11 + venv、Node 20、pnpm、Caddy、`SELFIT_PROFILE` 对应的依赖（slim 档跳过 torch 和 sidecar bootstrap）、随机生成 `SELFIT_AUTH_SECRET`、安装 systemd 服务和 Caddy 反代。幂等可重复跑。

full 档运行方式：

```bash
SELFIT_PROFILE=full sudo bash deploy/setup_server.sh
```

## 6. 填密钥并启动

```bash
vim /opt/selfit/asis-closet-demo/.env.demo   # 必填项见下表
systemctl restart selfit caddy
```

`.env.demo` 必填 / 关注项：

| 变量 | 说明 |
|---|---|
| `TRYON_RUNWAY_GOOGLE_URL` | 公网 Gemini 端点（见第 0 节，**必填**） |
| `TRYON_RUNWAY_GOOGLE_API_KEY` | 公网 Gemini key（**必填**） |
| `SELFIT_AUTH_SECRET` | setup 脚本已自动生成 |
| `MINIMAX_API_KEY` | AI 搭配师（OpenClaw）用；没有可留空 |
| `REQUIRE_SIDECARS` | `1` 要求两个 sidecar 就绪才放行；sidecar 没配好先改 `0` 保底上线主流程 |
| `REQUIRE_TRYON` | `1` 要求试穿 provider key 已配置才放行；暂无 Gemini key 先跑 onboarding/报告流程时改 `0`（拿到 key 填入后试穿即恢复可用） |
| `SELFIT_CLEANUP_DAYS` | 用户产物清理天数，默认 7 |

## 7. 上线验收清单

```bash
# 服务器本机
curl -s http://127.0.0.1:8002/health
systemctl status selfit caddy
journalctl -u selfit -f          # 看 "Demo is ready"

# 公网（DNS 生效后，Caddy 首次会自动签发 Let's Encrypt 证书）
curl -sI https://selfit.com.cn/health
```

浏览器打开 `https://selfit.com.cn/selfit/demo`，走一遍完整主流程：
上传用户照 → 选/传衣服 → 生成试穿图。DNS 生效后 `https://selfit.com.cn/health` 返回 200 即上线完成。

## 8. 降级策略（时间不够时）

- **slim 档本身就是降级形态**：`.env.demo` 设 `REQUIRE_SIDECARS=0`，AI 搭配师和小红书链接提取不可用，但**模特试穿主流程完全可用**（代码内置优雅降级：torch 缺失 → 衣柜自动分割返回空；`SELFIT_REMBG_ENABLED=0` → 抠图退化为语义 mask）。
- **小红书 MCP 首次运行需要登录态**：`journalctl -u selfit` 观察 `xiaohongshu-mcp.log`；短期可先不启用该功能。
- **内存吃紧（2C2G）**：确认 `.env.demo` 里 `SELFIT_REMBG_ENABLED=1` 时观察峰值；rembg 首次会下载 ~170MB 的 u2net 模型。

## 9. 日常运维

```bash
# 更新代码后重新部署（本机执行 rsync 后，服务器上）
systemctl restart selfit

# 日志
journalctl -u selfit -n 200
tail -f /opt/selfit/asis-closet-demo/outputs/runtime/fastapi.log

# 磁盘（用户图片占用）
du -sh /opt/selfit/asis-closet-demo/outputs /opt/selfit/asis-closet-demo/uploads
```

## 10. 常见问题

| 现象 | 排查 |
|---|---|
| Caddy 证书签发失败 | DNS 未生效 / 80 端口未放行；`journalctl -u caddy -f` |
| `systemctl status selfit` 反复重启 | `journalctl -u selfit -n 100`；多半是 readiness 超时（sidecar 或 tryon key 未配好） |
| 试穿报 provider_error | `.env.demo` 的 Gemini URL/key 配错；服务器上 `curl -s -o /dev/null -w "%{http_code}" https://generativelanguage.googleapis.com` 应返回 404（网络通） |
| 上传 413 | Caddy `request_body max_size 48MB` 已覆盖应用 36MB，若仍报错检查客户端 |

---

**后续（非紧急）**：提交 ICP 备案迁回大陆 ECS（延迟更低）；OSS 外置图片存储（`.env.demo` 的 `SELFIT_ASSET_STORE=oss`）；服务器用户隔离与 fail2ban。
