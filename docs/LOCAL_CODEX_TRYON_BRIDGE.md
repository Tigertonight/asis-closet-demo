# 本地 Codex 试穿桥接

本地调试启用 `TRYON_LOCAL_CODEX_BRIDGE=1` 后，没有可复用结果的试穿会调用
已登录的 Codex CLI 原生图片工具，生成完成后自动回填原试穿任务与记录。
当前本机 `.env` 已启用此设置；生成消耗当前 Codex 账号的可用额度。

## 调用顺序与范围

1. 现有预生成示例、匹配的历史结果优先复用。
2. 需要新生成时，在本地环境优先使用 `LocalCodexImageGenTryOnProvider`。
3. 继续沿用项目的服装／配饰分步、单品穿法、叠穿顺序、遮挡与质量检查。
4. 后台任务等待图片完成，页面通过现有任务轮询取得结果；失败或超时返回可重试错误。

每一步传入三张图：当前人物图、该步骤的参考拼图、可编辑区域指引。
第一步使用原模特图，后续步骤使用上一步结果。参考拼图由原穿搭照片与该步骤单品构成。
原蒙版使用 alpha 表示可编辑区域；传入 Codex 前将 alpha 转为不透明黑白图，
黑色可编辑、白色保留、灰色为边缘，避免透明蒙版显示为全白。

现有构图与人物保护检查继续执行。逐件语义复核服务不可用时，结果仍会标记为
“建议复核”，不会把未核实的单品一致性当成通过。

## 配置

```dotenv
TRYON_LOCAL_CODEX_BRIDGE=1
TRYON_CODEX_TIMEOUT_SECONDS=900
SELFIT_CODEX_IMAGE_MODEL=
```

`SELFIT_CODEX_BIN` 可指定 CLI 路径，默认从 PATH 或 macOS Codex 应用寻找。
不设置 `SELFIT_CODEX_IMAGE_MODEL` 时使用 CLI 默认模型；该选项控制图片任务的编排模型。
每步超时默认 900 秒，限制在 60–1200 秒之间。先运行 `codex login status` 确认登录。
更改 `.env` 后需重启本地服务。

仅 `local/dev/development/test` 且非公开演示环境允许启用。
`demo/staging/production/prod` 或 `SELFIT_PUBLIC_DEMO=1` 均不会使用本地桥接。
设为 `0` 后恢复原图片服务选择顺序。`TRYON_ENABLE_PI_AGENT_CODE_WORKER`
是旧实验 worker 开关，与本桥接不同，不需要启用。

CLI 在独立临时目录运行，禁用 shell、应用、插件、子 agent 等工具，不加载项目指令；
通过原生图片工具生成后校验返回路径、时间、图片格式与大小，再复制到试穿目录。
每一步在 `stage_*/codex_bridge/<调用 ID>/` 留存输入哈希、原蒙版引用、CLI 事件、
生成原图、尺寸归一化结果与耗时。所有图片和运行证据位于 Git 忽略的 `outputs/` 下。

## 2026-09-09 验证

通过本地 `8784` 的真实 HTTP 接口提交“高腰干练”通勤套装，使用 `female_medium_1`
模特和全部 8 件单品。此套装无预生成示例，服装和配饰两步均调用
`local_codex_imagegen`，分别耗时 59.84、62.53 秒；任务状态为 `completed`，
结果为 1024 × 1536，记录包含全部 8 件单品且无跳过项。
质量检查为 `warn`：构图检查通过，逐件语义复核服务未配置。

测试产物：`outputs/codex-tryon-bridge-20260909/e2e-result.png`、
`e2e-request.json`、`e2e-result.json`。使用独立访客账号测试。
自动测试会默认关闭真实图片调用，通过模拟 CLI 覆盖环境限制、超时、错误结果、
临时图片归档、蒙版转换，并回归预生成结果与缓存复用。

CLI 能力依据：[非交互运行](https://learn.chatgpt.com/docs/non-interactive-mode)、
[原生图片生成](https://learn.chatgpt.com/docs/image-generation)。
