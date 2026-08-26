# selfit（适我）

selfit 是一个面向个人风格认知、色彩分析和穿搭决策的 MVP。当前仓库已包含消费者 onboarding、线下智能镜拍照、本地色彩分析、电子衣橱、AI 单品抠图、虚拟试穿和穿搭师 Agent Runtime。

> 个人风格 DNA = `suit` 你适合的 × `like` 你喜欢的 × `vibe` 你表达的

本项目仍处于验证期：用户流程和本地 CV 链路可直接运行；真实生图、AI 穿搭师和小红书搜索需要额外的模型凭证或 sidecar。

## 主要能力

| 能力 | 当前实现 | 入口 |
|---|---|---|
| selfit onboarding | 还原 Figma 的 `suit / like / vibe` 完整流程，默认使用浏览器内 mock adapter | `/selfit` |
| 线下智能镜 | 摄像头授权、3/2/1 秒倒计时、拍照、重拍/确认、处理进度、报告二维码和自动复位 | `/selfit/mirror` |
| 个人色彩分析 | 人脸、色卡、颜色校正、肤色、五官对比度和 4/12/24 季候选 | `/demo`、`POST /analyze` |
| 电子衣橱 | 登录后的单品入柜、链接导入、分类、编辑、搭配组合和试穿记录 | `/closet/demo` |
| AI 单品抠图 | 图片编辑模型优先，SegFormer / rembg / 本地 CV 分层兜底 | `/closet/capabilities` |
| 虚拟试穿 | 人像与服装理解、上半身 mask、图片编辑 provider 和质量检查 | `/try-on/demo` |
| AI 穿搭师 | 会话、记忆、衣橱工具、搭配 skill 和小红书灵感检索 | `selfit-agent-runtime/` |
| QA / 验收 | 回归样本、解释页、产品门禁、稳定性和全栈验收 | `/mvp`、`/qa` |

## 体验边界

- `/selfit` 默认使用 `live` 模式，请求项目内的 `/api/v1/selfit` 报告链路并按后端 `typeId` 加载 16 人格模板。需要纯前端演示时可临时使用 `?apiMode=mock`。
- `/selfit/mirror` 已可使用真实摄像头；未授权或设备不支持时会进入演示模式。默认展示示例报告，正式分析端点可通过 `window.__SELFIT_MIRROR_CONFIG__` 接入。
- `/demo` 和 `POST /analyze` 运行仓库中的真实本地 CV / 规则链路，不依赖 Codex 内部看图能力。
- 试穿的 fixture / mock provider 只用于验证接口和管线；正式生成结果必须通过外部图片编辑 provider。

## 快速启动

推荐 Python 3.11。

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

启动后可直接访问：

- onboarding：<http://127.0.0.1:8000/selfit>
- 智能镜：<http://127.0.0.1:8000/selfit/mirror>
- 色彩测试：<http://127.0.0.1:8000/demo>
- 电子衣橱：<http://127.0.0.1:8000/closet/demo>
- 虚拟试穿：<http://127.0.0.1:8000/try-on/demo>
- MVP 状态：<http://127.0.0.1:8000/mvp>
- QA：<http://127.0.0.1:8000/qa>
- OpenAPI：<http://127.0.0.1:8000/docs>

摄像头 API 要求 HTTPS 或浏览器认可的 localhost 安全上下文。

### 本地登录

衣橱和穿搭师 API 使用手机验证码会话。本地非公开模式默认允许开发验证码 `0000`；请勿在公网环境使用该默认值。

## 完整 AI 能力

基础色彩分析只需 `requirements.txt`。多品类衣物分割、透明边缘精修和完整用户试用需要：

```bash
. .venv/bin/activate
pip install -r requirements-ai.txt
cp .env.example .env
python scripts/sync_selfit_env.py
python scripts/check_runtime_readiness.py
```

`sync_selfit_env.py` 只补充 selfit 的非敏感默认项，不覆盖现有 key。

### 模型与 sidecar

| 用途 | 主要配置 |
|---|---|
| AI 单品抠图 / 试穿 | `TRYON_OPENAI_BASE_URL`、`TRYON_OPENAI_API_KEY`、`TRYON_IMAGE_MODEL` |
| Runway / Google 试穿 | `TRYON_RUNWAY_GOOGLE_URL`、`TRYON_RUNWAY_GOOGLE_API_KEY` |
| 穿搭师模型 | `STYLIST_OPENCLAW_MODEL` 及对应 provider key |
| OpenClaw bridge | `STYLIST_OPENCLAW_CHAT_URL`、`STYLIST_OPENCLAW_MEMORY_URL` |
| 小红书 MCP | `SELFIT_XHS_MCP_URL`、`SELFIT_XHS_ALLOWED_TOOLS` |
| 本地衣物分割 | `SELFIT_SEGFORMER_MODEL`、`SELFIT_SEGFORMER_DEVICE` |
| 透明边缘精修 | `SELFIT_REMBG_ENABLED`、`SELFIT_BIREFNET_ENDPOINT` |

完整配置项和安全默认值请查看 `.env.example` 与 `.env.demo.example`。

新 clone 的仓库如果需要本地 OpenClaw 和小红书 MCP，先准备 runtime：

```bash
cd selfit-agent-runtime
./scripts/bootstrap-openclaw.sh
./scripts/bootstrap-xhs-mcp.sh
python3 scripts/bootstrap-go-runtime.py   # 本机没有 Go 时
PNPM_BIN="$(command -v pnpm)" NODE_BIN="$(command -v node)" ./scripts/build-openclaw.sh
cd ..
```

然后启动 FastAPI、OpenClaw bridge 和小红书 MCP：

```bash
NODE_BIN="$(command -v node)" ./scripts/start_selfit_full_stack.sh
```

完整栈默认使用端口：

- selfit FastAPI：`8002`
- OpenClaw bridge：`18789`
- 小红书 MCP：`18060`

更详细的 Agent Runtime 部署、搜索和 skill 说明见 `selfit-agent-runtime/README.md`。

## 常用 API

### 色彩分析

```bash
curl -X POST "http://127.0.0.1:8000/analyze" \
  -F "image=@/absolute/path/to/portrait.jpg"
```

成功响应会在 `result_summary` 中返回用户可消费的结果，在 `pipeline` 中保留 QA 和调试证据。照片不可用时返回 `needs_retake`，不会伪造季节型结果。稳定字段可查看：

```bash
curl http://127.0.0.1:8000/analyze/contract
```

### 试穿

```bash
curl -X POST "http://127.0.0.1:8000/try-on" \
  -F "person_image=@/absolute/path/to/person.jpg" \
  -F "garment_image=@/absolute/path/to/garment.jpg"
```

查看当前 provider 能力：

```bash
curl http://127.0.0.1:8000/try-on/capabilities
```

衣橱和穿搭师的能力接口分别为 `/closet/capabilities` 和 `/stylist/capabilities`，访问时需要登录会话。除健康检查、演示页和部分能力接口外，衣橱、穿搭师与用户资产接口均需要登录。完整路由以运行中的 OpenAPI 页 `/docs` 为准。

## 测试与验收

运行全部自动化测试：

```bash
.venv/bin/pytest -q
```

仓库当前可收集 235 个测试，覆盖鉴权、色彩分析、onboarding、衣橱、试穿、穿搭师与运行态。

常用专项检查：

```bash
python scripts/smoke_mvp.py
python scripts/tryon_mvp_acceptance.py
python scripts/evaluate_color_stability.py
python scripts/run_ai_cutout_evaluation.py --base-url http://127.0.0.1:8000
python scripts/selfit_full_stack_acceptance.py
```

严格模式要求真实 provider 和 sidecar 就绪：

```bash
python scripts/check_runtime_readiness.py --strict
python scripts/tryon_mvp_acceptance.py --require-external
python scripts/selfit_full_stack_acceptance.py --strict
```

QA 和调试结果会写入 `tests/results/` 或 `outputs/`，这些运行产物不应提交到 Git。

## 部署 Demo

公开 Demo 必须使用强密钥，关闭开发验证码，并开启请求限流与用户数据清理。

```bash
cp .env.demo.example .env.demo
# 填写 SELFIT_AUTH_SECRET、模型 key 和 sidecar 地址
docker compose -f docker-compose.demo.yml up --build -d
```

默认对外端口为 `8002`。部署后检查：

```bash
curl http://127.0.0.1:8002/health
curl http://127.0.0.1:8002/health/dependencies
python scripts/check_runtime_readiness.py --strict
```

非 Docker 环境可在配置好 `.env` 后运行：

```bash
SELFIT_ENV=demo SELFIT_PUBLIC_DEMO=1 ./scripts/deploy_demo.sh
```

## 目录结构

```text
app/
  main.py                    FastAPI 路由与服务入口
  analyzer.py                色彩分析、MVP 与 QA 页
  closet.py                  电子衣橱、单品抠图和搭配
  tryon.py                   试穿 provider 与图片管线
  stylist.py                 穿搭师编排与工具调用
  static/selfit/             onboarding 与智能镜前端
selfit-agent-runtime/        OpenClaw bridge、agent、skills 和 MCP 配置
scripts/                     启动、部署、验收和数据生成脚本
tests/                       自动化测试与 fixture
docs/                        算法、产品、集成和验收文档
outputs/                     本地生成结果与运行状态（不提交）
uploads/                     本地用户上传（不提交）
```

## 核心文档

- 视觉与前端真值源：`DESIGN.md`
- onboarding 前后端契约：`docs/SELFIT_BACKEND_INTEGRATION.md`
- 报告数据契约：`docs/SELFIT_REPORT_DATA_CONTRACT.md`
- 智能镜实现说明：`docs/SELFIT_MIRROR_FRONTEND.md`
- 色彩算法说明：`docs/ALGORITHM_EXPLAINER.md`
- MVP 验证交接：`docs/MVP_VALIDATION.md`
- 试穿验证交接：`docs/TRYON_MVP_VALIDATION.md`
- Agent Runtime：`selfit-agent-runtime/README.md`

## 开发约定

- 消费者主流程必须遵循 `DESIGN.md` 和 Figma Ready for Dev 稿。
- 不在用户主界面暴露 `mask`、`pipeline`、`provider`、JSON 或调试信息。
- 真实 AI 不可用时必须返回可理解的失败或重试状态，不得伪造生成结果。
- `.env`、用户上传、运行日志、本地 Agent 状态和部署包不得提交。
