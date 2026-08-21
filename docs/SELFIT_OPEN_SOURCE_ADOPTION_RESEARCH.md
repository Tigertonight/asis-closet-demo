# selfit 开源方案采用调研

## 结论

优先把下一阶段拆成三条可落地链路：

1. **衣物分割 / 抠图**：先接 `mattmdjaga/segformer_b2_clothes` 或 FASHN Human Parser 做多品类 semantic mask，再用 `rembg` 或 BiRefNet 做边缘透明化精修。
2. **AI 穿搭师 Agent**：继续使用独立 `selfit-agent-runtime` + 最新 OpenClaw fork 的 sidecar 方案，不把 Agent runtime 直接耦合进 FastAPI。
3. **小红书搜索 / 图文依据**：主服务只保留 provider interface。真实搜索优先接 MCP / Playwright sidecar，避免把登录态、反检测和抓取风险放进产品主进程。

## 衣物分割与抠图

### 推荐采用顺序

| 优先级 | 方案 | 用途 | 采用方式 |
|---|---|---|---|
| P0 | `mattmdjaga/segformer_b2_clothes` | 上衣、裤子、裙子、鞋包等衣物类别 mask | 直接接入当前 `SegFormerClothesAdapter` |
| P0 | FASHN Human Parser | 更贴近 fashion / virtual try-on 的人体解析 | 作为 SegFormer B2 的替换 provider |
| P1 | `rembg` | 快速背景移除和透明 PNG | 作为边缘精修 fallback |
| P1 | BiRefNet / BiRefNet_HR-matting | 高分辨率前景抠图与透明边缘 | 作为高质量 cutout provider |
| P2 | SCHP | 传统人体解析 baseline | 作为兼容备用，不做首选 |

### 采用判断

- `mattmdjaga/segformer_b2_clothes` 和 SCHP 都基于 ATR/LIP 类标签体系，天然覆盖上衣、裙子、裤子、鞋、包、帽子、围巾等类别。
- FASHN Human Parser 是更近的 fashion / VTON 方向模型，适合作为后续主 provider 候选。
- `rembg` 胜在接入简单，支持 CLI、Python library、HTTP server、Docker，适合先补透明 PNG 能力。
- BiRefNet 更适合作为“边缘干净”的高质量 provider，尤其是白色/浅色衣服、半透明边缘、复杂背景。

### 下一步实现建议

- 在 `app/closet.py` 中补 `ClothesSegmentationProvider` 抽象：
  - `SegFormerB2Provider`
  - `FashnHumanParserProvider`
  - `RembgMattingProvider`
  - `BiRefNetMattingProvider`
- pipeline 顺序：
  - semantic segmentation 得到类别 mask。
  - mask 合并 / bbox 裁剪。
  - matting provider 精修 alpha。
  - 输出 `cutout_path`、`mask_path`、`preview_path`、`subcategory/slot`。
- 如果模型不可用，继续返回 `partial_top_fallback`，但在 UI 明确提示“当前只稳定识别上衣”。

## 试穿模型

### 可采用方案

| 方案 | 优点 | 风险 |
|---|---|---|
| CatVTON | 结构简单、推理相对轻，官方称 1024x768 <8GB VRAM | 仍需要 GPU 和预处理稳定性 |
| IDM-VTON | 质量高，社区成熟，纹理保持较好 | CC BY-NC-SA，商业化需谨慎 |
| VITON-HD / StableVITON | 经典 baseline，资料多 | 工程老、预处理复杂 |

### 采用判断

- 当前 selfit 试穿先保持上衣链路和 mock 组合试穿。
- 下一阶段如果要本地开源试穿，优先试 CatVTON；如果只是验证效果，可并行试 IDM-VTON，但注意许可证。
- 试穿模型建议继续 provider 化，不与衣橱/Agent 强耦合。

## AI 穿搭师 Agent

### 推荐方案

继续使用 `selfit-agent-runtime` 独立 sidecar，并基于最新版 OpenClaw fork 落地：

- OpenClaw 负责 session、memory、skills、tools、multi-agent routing。
- FastAPI 只暴露 selfit tools：
  - `selfit_closet_search`
  - `selfit_get_item`
  - `selfit_compose_outfit`
  - `selfit_save_outfit`
  - `selfit_tryon_from_outfit`
  - `selfit_xhs_search`
  - `selfit_xhs_fetch_note`
  - `selfit_style_kb_search`
- FastAPI 不 import OpenClaw 内部代码。
- 模型 key 失效必须返回 `ai_unavailable`，不走假兜底。

### 备选

- LangGraph：适合 Python 内部自建 Agent，memory/persistence/human-in-loop 强，但会把 Agent runtime 拉回主项目。
- OpenAI Agents SDK：轻量、好接，但 skills/memory/多渠道不如 OpenClaw 贴近你的诉求。

### 采用判断

你的产品诉求包含记忆管理、技能调用、小红书搜索、多轮穿搭师会话。相比直接在 FastAPI 里自研，OpenClaw sidecar 更符合“独立、可升级、可回滚、不耦合”的边界。

## 小红书搜索与图文获取

### 2026-07-04 可用 MCP 调研结论

当前小红书 / RedNote 方向已有多种开源 MCP server，可以直接作为 selfit 穿搭师的搜索依据来源接入：

- `xpzouying/xiaohongshu-mcp`：优先候选。面向中国站 `xiaohongshu.com`，文档提供 HTTP MCP endpoint，推荐配置为 `http://localhost:18060/mcp` + `streamableHttp`。项目文档也说明 OpenClaw 当前不原生直连 MCP，推荐通过 MCPorter 桥接。
- `iFurySt/RedNote-MCP`：Node/npm 方案，支持登录初始化、Cookie 持久化、关键词搜索、URL 读取，适合作为轻量备选；主要以 stdio MCP client 配置为主。
- `MilesCool/rednote-mcp`：TypeScript + Playwright，偏“搜索并提取内容”的 MCP server，数据结构包含标题、正文、作者、互动数据、图片和标签，适合做趋势与证据摘要。
- `zhjiang22/openclaw-xhs`：面向 OpenClaw 的小红书技能包/工具包，基于 `xiaohongshu-mcp` 和 XHS-Downloader，提供搜索、趋势跟踪和个人记忆库导出思路，可作为 selfit-agent-runtime skill 设计参考。

因此本项目不需要从 0 写小红书搜索。V1 采用 `xpzouying/xiaohongshu-mcp` 作为首选 sidecar，同时保留 RedNote MCP 的 stdio/Node 备选；FastAPI 继续只做能力状态和业务工具边界。

### 可采用方案

| 方案 | 用途 | 采用建议 |
|---|---|---|
| `xpzouying/xiaohongshu-mcp` | 中国站 `xiaohongshu.com` 的 MCP 服务，支持搜索、笔记详情、发布等 | selfit 优先接入候选；以 HTTP MCP sidecar 方式运行 |
| `@sykuang/rednote-mcp` | Node/TypeScript + Playwright，偏海外 `rednote.com`，支持 npx、HTTP、MCP Streamable HTTP | 可作为跨平台快速验证方案，但目标站点与中国站不同 |
| `iFurySt/RedNote-MCP` | npm 安装，登录 cookie 管理，搜索 notes、URL 内容读取 | 可作为轻量验证备选 |
| MediaCrawler | 多平台公开信息采集，含小红书 | 适合研究，不建议直接嵌主服务 |
| XHS-Downloader | 小红书链接提取、作品采集、媒体下载 | 可作为素材下载参考，注意许可证 |
| xiaohongshu-crawler / RedNote MCP | MCP 化搜索、笔记详情、评论 | 最贴近 Agent 工具调用 |
| Spider_XHS | Cookie 登录后的 PC 端接口采集 | 风险高，只适合内部验证 |

### 采用判断

- 主项目现在已有公开链接提取能力，适合继续保留。
- 关键词搜索不要写进 FastAPI 主进程，应做成 `selfit_xhs_search` provider，并由 selfit Agent runtime 通过 MCP 调用。
- 如果要接 Agent，优先选 MCP/HTTP sidecar：OpenClaw 调 MCP，FastAPI 只看结构化结果。
- 需要在产品文案上明确：不承诺绕过登录、反爬或私域内容。

### 推荐接入路径

V1 推荐接 `xpzouying/xiaohongshu-mcp`，因为它明确针对中国站 `xiaohongshu.com`，并提供 HTTP MCP endpoint：

```bash
# 从源码启动，默认 headless
go run .

# 或非 headless，用于首次登录/调试
go run . -headless=false
```

服务默认暴露：

```text
http://localhost:18060/mcp
```

可用 MCP Inspector 验证：

```bash
npx @modelcontextprotocol/inspector
```

Inspector 里连接：

```text
http://localhost:18060/mcp
```

Claude Code / MCP client 的 HTTP 配置形态：

```bash
claude mcp add --transport http xiaohongshu-mcp http://localhost:18060/mcp
```

如果使用海外 `rednote.com` 或需要 Node/npx 快速验证，可用 `@sykuang/rednote-mcp`：

```bash
# stdio 模式
npx -y @sykuang/rednote-mcp --stdio

# HTTP 模式
npx -y @sykuang/rednote-mcp --port :18060
```

其 HTTP 模式也暴露 MCP Streamable HTTP：

```text
http://localhost:18060/mcp
```

如果 OpenClaw fork 暂时不能直接作为 MCP client，按 `xiaohongshu-mcp` 官方说明增加 MCPorter 桥接层：

```bash
npm i -g mcporter
npx mcporter config add xiaohongshu-mcp http://localhost:18060/mcp
npx mcporter list xiaohongshu-mcp
```

OpenClaw agent 侧仍只看 `selfit_xhs_search` / `selfit_xhs_fetch_note` 两类语义工具，底层到底是 MCPorter、streamable HTTP，还是 stdio bridge，由 `selfit-agent-runtime` 的工具适配层处理。

### selfit 集成设计

在 selfit 中不要让 FastAPI 直接依赖 MCP SDK。推荐链路：

```text
selfit Web
  -> FastAPI /stylist/chat
  -> selfit-agent-runtime / OpenClaw
  -> xiaohongshu-mcp sidecar
  -> search_feeds / get_feed_detail
  -> Agent 汇总趋势与图文依据
  -> FastAPI 返回结构化推荐
```

FastAPI 当前的 `selfit_xhs_search` 保持 provider interface：

- 如果 `SELFIT_XHS_MCP_URL` 和 `STYLIST_XHS_SEARCH_URL` 都未配置，返回 `not_configured`。
- 如果 `SELFIT_XHS_MCP_URL` 已配置，`/stylist/capabilities` 和 `selfit_xhs_search` 会显示 `mcp_sidecar_configured`，但真实搜索仍由 Agent runtime 直接调 MCP，不经过 FastAPI。
- 如果要把 MCP 结果回传 FastAPI，可让 Agent 只提交结构化字段：`title`、`url`、`cover_url`、`image_urls`、`summary`、`style_tags`、`engagement`。

建议新增环境变量：

```bash
SELFIT_XHS_MCP_URL=http://127.0.0.1:18060/mcp
SELFIT_XHS_MCP_MODE=streamable-http
SELFIT_XHS_ALLOWED_TOOLS=search_feeds,get_feed_detail
```

只允许 read-only 工具进入穿搭师链路：

- `check_login_status`
- `search_feeds`
- `get_feed_detail`
- 可选：`list_feeds`

不建议 V1 开放：

- `post_comment_to_feed`
- `reply_comment_in_feed`
- `like_feed`
- `favorite_feed`
- `publish_content`
- `publish_with_video`

原因：selfit 当前诉求是“给穿搭建议提供依据”，不是自动运营账号。写操作会引入账号安全、内容合规和误操作风险。

### 安全与合规边界

- MCP sidecar 独立运行，cookie 文件不进入 FastAPI 项目目录。
- 首次登录必须由用户主动扫码/登录。
- 不承诺绕过登录、反爬或私域内容。
- 对外只展示“来自小红书公开内容的穿搭灵感摘要”，不全文搬运笔记。
- 引用图片只作为搜索依据，不自动入柜；用户明确选择后再进入导入链路。
- Agent 输出必须带 `evidence_sources`，标明来自 `xhs_search` 或 `xhs_note`。

## 推荐落地顺序

1. 接入 `SegFormerB2Provider`，让多品类自动入柜真实可用。
2. 接入 `rembg`，先把透明 PNG 边缘体验做稳。
3. 评估 FASHN Human Parser 和 BiRefNet，作为更高质量 provider。
4. 启动最新 OpenClaw fork，跑通 `selfit-stylist` 的 HTTP chat。
5. 把 memory 真实接入 OpenClaw namespace。
6. 接 `xiaohongshu-mcp` / RedNote MCP provider，不进入 FastAPI 主进程。
7. 试 CatVTON 本地试穿 sidecar，仍只作为 provider。

## Sources

- `mattmdjaga/segformer_b2_clothes`: https://huggingface.co/mattmdjaga/segformer_b2_clothes
- Training repo: https://github.com/mattmdjaga/segformer_b2_clothes
- SCHP: https://github.com/GoGoDuck912/Self-Correction-Human-Parsing
- FASHN Human Parser: https://github.com/fashn-AI/fashn-human-parser
- `rembg`: https://github.com/danielgatis/rembg
- BiRefNet: https://github.com/ZhengPeng7/BiRefNet
- OpenClaw Docs: https://docs.openclaw.ai/
- OpenClaw tools / skills / plugins: https://docs.openclaw.ai/tools
- LangGraph memory: https://docs.langchain.com/oss/python/langgraph/add-memory
- CatVTON: https://github.com/Zheng-Chong/CatVTON
- IDM-VTON: https://github.com/yisol/IDM-VTON
- MediaCrawler: https://github.com/NanmiCoder/MediaCrawler
- XHS-Downloader: https://github.com/JoeanAmier/XHS-Downloader
- xiaohongshu-crawler MCP: https://github.com/yangsijie666/xiaohongshu-crawler
- xiaohongshu-mcp: https://github.com/xpzouying/xiaohongshu-mcp
- rednote-mcp Node port: https://github.com/sykuang/rednote-mcp
- RedNote-MCP: https://github.com/iFurySt/RedNote-MCP
