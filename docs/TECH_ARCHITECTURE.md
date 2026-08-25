# AS IS Closet Demo — 技术架构与主流程现状

> 本文档是对当前 demo 代码库的技术现状快照（截至 2026-08），用于补齐"先跑 demo、后补方案"所缺的技术架构说明。
> 内容全部来源于对 `app/`、`asis-agent-runtime/`、`scripts/` 现有代码的梳理，描述的是**现状（as-is）**，不是目标架构（to-be）。
> 每条主流程附一张 PlantUML（UML）图和一张 Mermaid 图，二者表达同一内容，便于在不同工具链中渲染。

---

## 0. 系统一句话概括

一个**单进程 FastAPI 应用**（`app.main:app`，默认 `:8002`）承载全部 HTTP 能力，本地文件系统（`outputs/`）承担全部持久化，按需外挂两类 sidecar：

- **OpenClaw bridge**（Node.js，`:18789`）— AI 穿搭师的 agent runtime 桥接层；
- **小红书 MCP sidecar**（Go，`:18060`）— 小红书搜索/笔记详情的只读数据源。

外部 AI 能力（VLM 衣服理解、图像编辑试穿、LLM 对话）全部走 **provider 抽象 + 本地 fallback** 的验证期架构：有 key/代理就用真实模型，没有就用本地 CV 或 mock provider 固化链路。

---

## 1. 主流程清单

| # | 主流程 | 入口端点 | 核心模块 | 用户价值 |
|---|--------|----------|----------|----------|
| F1 | 色彩测试分析 | `POST /analyze` | `analyzer.py` + `cv_pipeline.py` | 上传自拍 → 四季/十二季/二十四季色彩诊断 |
| F2 | 上衣虚拟试穿 | `POST /try-on` 系列 | `tryon.py` | 人像 + 上衣图 → AI 生成试穿结果图 |
| F3 | 小红书链接提取 | `POST /try-on/extract-xhs` | `tryon.py` | 粘贴笔记链接 → 自动提取可试穿上衣 |
| F4 | 衣橱导入与管理 | `POST /closet/import/*`、`/closet/items|outfits` | `closet.py` | 上传/链接导入 → 自动分割多品类单品入柜 |
| F5 | AI 穿搭师对话 | `POST /stylist/chat` | `stylist.py` + OpenClaw bridge + XHS MCP | 结合衣橱与小红书趋势的对话式穿搭推荐 |
| F6 | 认证与多用户隔离 | `POST /auth/phone/*` | `auth.py` + `storage.py` | 手机号验证码登录，数据按用户隔离 |

横向支撑：`ops.py`（限流/体积限制中间件、部署模式）、`storage.py`（ContextVar 用户存储上下文）、`scripts/check_runtime_readiness.py`（运行时自检）。

---

## 2. 系统总览图（所有主流程串联）

### 2.1 总览 Mermaid 图

```mermaid
flowchart TB
    subgraph Browser["浏览器（app/static 内嵌页面，移动优先）"]
        UI1["/demo · 色彩测试页"]
        UI2["/try-on/demo · 试穿页"]
        UI3["/closet/demo · 衣橱页"]
        UI4["/asis/demo · 穿搭师页"]
        UI5["/qa /mvp · QA 与验收面板"]
    end

    subgraph API["FastAPI 单进程 app.main:app（:8002）"]
        MW["request_guard_middleware<br/>ops.py：体积限制 + 滑动窗口限流"]
        subgraph Flows["六条主流程"]
            F1["F1 色彩测试<br/>POST /analyze"]
            F2["F2 虚拟试穿<br/>POST /try-on*"]
            F3["F3 小红书提取<br/>POST /try-on/extract-xhs"]
            F4["F4 衣橱入柜<br/>POST /closet/import/*"]
            F5["F5 穿搭师对话<br/>POST /stylist/chat"]
            F6["F6 认证<br/>POST /auth/phone/*"]
        end
        subgraph Providers["Provider 抽象层（tryon.py / closet.py / stylist.py）"]
            P1["衣服理解<br/>OpenAI 兼容 VLM ↔ 本地 CV fallback"]
            P2["图像编辑<br/>RunwayGoogle / OpenAI images.edit<br/>/ CodexBridge 队列 / Mock / Unavailable"]
            P3["分割抠图<br/>SegFormer(b2_clothes) + rembg 精修"]
            P4["穿搭师路由<br/>demo mock / MiniMax 直连 / OpenClaw HTTP / CLI"]
        end
        ST["storage.py<br/>ContextVar 用户上下文 + JSON manifest"]
    end

    subgraph Sidecars["本地 sidecar 进程"]
        BR["OpenClaw bridge（Node.js :18789）<br/>/api/asis/chat · /api/asis/memory"]
        MCP["小红书 MCP（Go :18060）<br/>/mcp · /api/v1/feeds/*"]
    end

    subgraph External["外部能力（可选，探测后启用）"]
        VLM["OpenAI 兼容代理<br/>127.0.0.1:8787/v1"]
        IMG["图像编辑服务<br/>images.edit / Runway Google"]
        LLM["LLM provider<br/>openai/anthropic/google/minimax..."]
        XHS["xiaohongshu.com<br/>公开 HTML / og:image"]
    end

    subgraph Disk["文件系统持久化（无数据库）"]
        D1["outputs/users/{uid}/<br/>closet · tryon · preferences"]
        D2["outputs/auth/auth_store.json"]
        D3["tests/fixtures/ + tests/results/"]
    end

    UI1 --> F1
    UI2 --> F2 & F3
    UI3 --> F4
    UI4 --> F5
    UI5 -.验收.-> API
    Browser --> MW --> Flows
    F6 --> D2
    F1 --> D3
    F2 --> P1 & P2
    F3 --> XHS
    F3 --> P1
    F4 --> P3
    F4 --> XHS
    F5 --> P4
    P1 --> VLM
    P2 --> IMG
    P4 --> LLM
    F5 <-->|HTTP /api/asis/chat| BR
    F5 -->|REST /api/v1/feeds| MCP
    BR -->|spawn openclaw CLI<br/>agent.md + skills| LLM
    BR -->|MCP 协议| MCP
    BR -->|"ASIS_TOOL_BASE_URL 回调 POST /stylist/tools 工具端点"| API
    Flows --> ST --> D1
```

### 2.2 总览 PlantUML 图

```plantuml
@startuml asis_overview
skinparam componentStyle rectangle
skinparam linetype ortho

package "浏览器（app/static 内嵌页面）" as UI {
  [色彩测试页 /demo] as ui1
  [试穿页 /try-on/demo] as ui2
  [衣橱页 /closet/demo] as ui3
  [穿搭师页 /asis/demo] as ui4
  [QA 面板 /qa /mvp] as ui5
}

package "FastAPI 单进程 :8002（app.main:app）" as API {
  [request_guard_middleware\n限流 + 体积限制] as mw
  [F1 色彩测试 /analyze] as f1
  [F2 虚拟试穿 /try-on*] as f2
  [F3 小红书提取 /try-on/extract-xhs] as f3
  [F4 衣橱入柜 /closet/import/*] as f4
  [F5 穿搭师对话 /stylist/chat] as f5
  [F6 认证 /auth/phone/*] as f6
  [Provider 抽象层\nVLM / 图像编辑 / 分割 / 穿搭师路由] as providers
  [storage.py\nContextVar + JSON manifest] as storage
}

package "本地 sidecar" as SC {
  [OpenClaw bridge :18789\n(Node.js)] as bridge
  [小红书 MCP :18060\n(Go)] as mcp
}

package "外部能力（可选）" as EXT {
  [OpenAI 兼容代理 :8787] as vlm
  [图像编辑服务] as img
  [LLM providers] as llm
  [xiaohongshu.com] as xhs
}

database "文件系统（无数据库）" as FS {
  [outputs/users/{uid}/] as d1
  [auth_store.json] as d2
  [tests/fixtures + results] as d3
}

ui1 --> f1
ui2 --> f2
ui2 --> f3
ui3 --> f4
ui4 --> f5
UI ..> mw : 全部请求
mw --> f1
mw --> f2
f1 --> d3
f2 --> providers
f3 --> xhs
f4 --> providers
f5 --> providers
f5 <--> bridge : HTTP /api/asis/chat
f5 --> mcp : REST /api/v1/feeds
bridge --> llm : spawn openclaw CLI
bridge --> mcp : MCP 协议
bridge --> API : 工具回调 /stylist/tools/{name}
providers --> vlm
providers --> img
providers --> llm
f6 --> d2
API --> storage
storage --> d1
@enduml
```

### 2.3 总览说明

1. **单进程 + 文件系统**是当前架构的最大特征：没有数据库、没有消息队列、没有独立 worker；所有用户数据（衣橱、试穿、会话、认证）都落在 `outputs/` 目录的 JSON manifest + 图片文件中。
2. **六条主流程共享同一套基础设施**：`ops.py` 的限流中间件拦在所有请求之前；`auth.py` 颁发的 Bearer Token 解出 `user_id` 后，由 `storage.py` 的 `ContextVar` 在整个请求周期内决定数据读写目录。
3. **流程之间通过数据串联而非直接调用**：F4 入柜的单品是 F2/F5 的输入（试穿用 garment、穿搭师上下文）；F3 提取的上衣既可进 F2 试穿，也可进 F4 入柜；F1 的色彩结论是 F5 穿搭建议的推理依据之一（`color-match` skill）。
4. **外部 AI 能力全部可插拔**：provider 探测失败时自动降级（本地 CV / mock / demo 回复），保证 demo 在零外部依赖下也能跑通全链路——这是"验证期"架构的核心设计。
5. **穿搭师是唯一多进程流程**：FastAPI → OpenClaw bridge（HTTP）→ openclaw CLI（子进程）→ LLM；agent 再反向回调 FastAPI 的 `/stylist/tools/{name}` 读取衣橱/发起试穿，并可经 MCP 协议使用小红书 sidecar。

---

## 3. F1 色彩测试分析流程（`POST /analyze`）

### 3.1 UML 活动图（PlantUML）

```plantuml
@startuml f1_analyze_activity
title F1 色彩测试分析活动图（analyzer.analyze_image_bytes）
start
:接收上传图片 bytes;
:校验大小(<=12MB)/格式(JPEG,PNG,WEBP)\nPIL 解码 + 缩放到最长边 1800;
partition "Stage 1 input_quality" {
  :分辨率/宽高比/曝光/清晰度检查\n(PIL FIND_EDGES + ImageStat);
}
partition "预处理" {
  if (脸过小或比例越界?) then (是)
    :_auto_crop_for_small_face()\n以脸为中心裁剪并放大;
  else (否)
  endif
}
partition "Stage 2 face_cv（cv_pipeline.run_face_cv）" {
  :MediaPipe Face Detector 主检测\nHaar Cascade 兜底 + IoU 去重;
  if (无人脸/多脸/遮挡/强模糊?) then (fail)
    #Tomato:标记硬阻断 issue;
  else (pass/warn)
  endif
}
partition "Stage 3 color_card_cv" {
  :HybridColorCardDetector\ncolour-checker-detection 主 + OpenCV 兜底;
  note right: 色卡非必需\n缺失/伪卡/反光均为 warn
}
partition "Stage 4 vl_review" {
  if (fixture 用例?) then (是)
    :MockVisionReviewer 回放\nexpected.json 预标注;
  else (真实上传)
    :run_local_visual_risk_review()\n本地 CV 检测妆容/滤镜/美颜;
  endif
}
partition "Stage 5 color_correction" {
  if (色卡可用于校正?) then (是)
    :采样 24 色块, lstsq 求 3x4 校正矩阵\ncolour-science 输出 DeltaE2000;
  else (否)
    :correction.no_card_fallback\n原图继续推理;
  endif
}
partition "Stage 6 skin_tone" {
  :MediaPipe Face Landmarker 定位\n额头/双颊/下颌区域;
  :HSV+YCrCb+RGB 肤色 mask 自适应采样\n输出 RGB/Lab/HSV + 冷暖/明度/彩度;
}
partition "Stage 7 feature_contrast" {
  :发际/眼部区域非肤色暗像素采样\n计算五官对比度;
}
partition "Stage 8 seasonal_result" {
  :三段诊断(冷暖/深浅/净柔)\n+ 12 季虚拟色布排序(softmax);
  :_apply_consumer_confidence_policy()\n按风险码压置信度上限(<=0.76);
}
:_build_decision() 聚合各 stage issues;
if (任一 stage = fail?) then (是)
  #Tomato:status = needs_retake\n只返回重拍建议;
elseif (存在链路异常?) then (是)
  #Tomato:status = failed;
else (否)
  #LightGreen:status = analyzed\n_build_result_summary() 生成 C 端摘要\n(四层口径/Top 候选/推荐色/下一步);
endif
:保存上传图并返回统一 JSON;
stop
@enduml
```

### 3.2 Mermaid 流程图

```mermaid
flowchart TD
    A[上传图片 bytes] --> B[校验 12MB / JPEG·PNG·WEBP<br/>PIL 解码 + 缩放至 1800px]
    B --> C{{Stage1 input_quality<br/>分辨率/曝光/清晰度}}
    C --> D{脸过小或比例越界?}
    D -- 是 --> E[_auto_crop_for_small_face<br/>以脸为中心裁剪放大]
    D -- 否 --> F
    E --> F{{Stage2 face_cv<br/>MediaPipe 主 / Haar 兜底}}
    F --> G{无人脸/多脸/遮挡/强模糊?}
    G -- fail --> Z1[硬阻断 issue]
    G -- pass/warn --> H{{Stage3 color_card_cv<br/>colour-checker-detection + OpenCV}}
    H --> I{{Stage4 vl_review}}
    I --> I1{fixture 用例?}
    I1 -- 是 --> I2[MockVisionReviewer<br/>回放 expected.json]
    I1 -- 否 --> I3[run_local_visual_risk_review<br/>本地 CV 妆容/滤镜/美颜]
    I2 --> J
    I3 --> J{{Stage5 color_correction}}
    J --> K{色卡可校正?}
    K -- 是 --> K1[lstsq 求 3×4 矩阵<br/>DeltaE2000 验证改善]
    K -- 否 --> K2[no_card_fallback 原图推理]
    K1 --> L{{Stage6 skin_tone<br/>Landmarker 区域 + 肤色 mask}}
    K2 --> L
    L --> M{{Stage7 feature_contrast<br/>非肤色暗像素采样}}
    M --> N{{Stage8 seasonal_result<br/>三段诊断 + 虚拟色布排序}}
    N --> O[_apply_consumer_confidence_policy<br/>置信度上限 ≤0.76]
    O --> P[_build_decision 聚合 issues]
    P --> Q{存在 fail?}
    Q -- 是 --> R1[needs_retake<br/>只给重拍建议]
    Q -- 全部 pass/warn --> R2[analyzed<br/>result_summary 四层口径]
    Q -- 异常 --> R3[failed]
    R1 --> S[返回统一 JSON]
    R2 --> S
    R3 --> S
    Z1 --> P
```

### 3.3 流程说明

- **编排入口**：`app/analyzer.py: analyze_image_bytes()`，8 个 stage 顺序执行，每个 stage 输出统一结构 `{status: pass|warn|fail|unknown, confidence, evidence, issues, suggestions}`。
- **双链路设计**：fixture 链路（`GET /fixtures/{case_id}/analyze`）回放 `tests/fixtures/expected.json` 中的 Codex 辅助标注保证回归稳定（当前 53/53 通过）；真实上传链路（`POST /analyze`）的 `vl_review` 改走本地 CV 初筛（口红/腮红/偏色/磨皮），未来生产化时替换 `OpenAIVisionReviewer`。
- **硬阻断 vs 软风险**：分辨率过低、严重过曝、非人像、多人脸、严重遮挡等判 `fail` → 整体 `needs_retake`；无色卡、轻微美颜、自动裁剪等判 `warn` → 仍可 `analyzed`，但进入 `_build_result_summary()` 的四层口径分流：`standard` / `light_note` / `low_confidence` / `retake`。
- **置信度上限保护**：验证期规则推理不允许包装成"高置信绝对判断"，`seasonal_result` 的置信度按命中的风险码取上限最小值（验证期全局 ≤0.76，浓妆/滤镜 ≤0.62，无色卡 ≤0.70）。
- **本地模型**：`app/models/` 下只有两个 MediaPipe 模型文件（人脸检测 + 478 点 Landmarker），首次调用时懒加载，无 GPU 依赖。
- **降级主线**：色卡检测失败 → 不用色卡；校正矩阵求解失败 → 原图推理；Landmarker 失败 → 人脸框比例区域。整条链路的设计原则是"能出结果就不阻断，但必须在 `decision.warnings` 和 `capture.risk_labels` 里如实标记"。

---

## 4. F2 上衣虚拟试穿流程（`POST /try-on` 系列）

### 4.1 UML 活动图（PlantUML）

```plantuml
@startuml f2_tryon_activity
title F2 虚拟试穿活动图（tryon.run_try_on，7 阶段）
start
:接收 person_image + garment_image\n(或 outfit / inspiration / outfit_plan 变体);
partition "Stage1 input_quality" {
  :人像 >=640x640 / 衣服 >=360x360\n格式与 12MB 校验;
}
partition "Stage2 person_detection" {
  :MediaPipe + Haar 检测人脸\n校验单人/正脸/无遮挡/清晰度;
  if (人像不合格?) then (fail)
    #Tomato:needs_retake;
    stop
  endif
}
partition "Stage3 garment_analysis" {
  if (OpenAI 兼容代理可用?) then (是)
    :OpenAIGarmentAnalysisProvider\nVLM 输出结构化衣服要素;
  else (否)
    :LocalGarmentAnalysisProvider\n本地 CV 颜色/纹理/bbox;
  endif
  note right: 输出 category/colors/material\n/fit/sleeve/neckline/pattern
}
partition "Stage4 upper_body_mask" {
  :基于人脸定位躯干可编辑区域\n生成 RGBA mask(黑=可编辑,白=保护);
}
partition "Stage5 edit_contract" {
  :定义编辑约束:保留人脸/发型/肤色\n/体型/姿势/背景,仅改衣服区域;
}
partition "Stage6 image_edit" {
  if (Runway Google 已配置?) then (是)
    :RunwayGoogleTryOnProvider;
  elseif (代理支持 images.edit?) then (是)
    :OpenAIImageEditTryOnProvider;
  elseif (启用 Codex 桥接队列?) then (是)
    :CodexImageGenBridgeTryOnProvider\n异步任务队列 outputs/.../codex_bridge;
  elseif (验收注入 mock?) then (是)
    :MockTryOnProvider\n本地拼接验证链路;
  else (否)
    #Tomato:UnavailableTryOnProvider\n不展示伪试穿图;
  endif
}
partition "Stage7 quality_review" {
  :复核人脸保留度/保护区差异\n/mask 比例/整体质量;
}
if (生成了结果图?) then (是)
  #LightGreen:status = generated\n写入 outputs/users/{uid}/tryon/{tryon_id}/\nresult.png + upper_body_mask.png;
else (否)
  #Tomato:status = failed / needs_retake;
endif
:返回 tryon 结果 JSON\n(pipeline 全阶段证据 + result 路径);
stop
@enduml
```

### 4.2 Mermaid 流程图

```mermaid
flowchart TD
    A[person_image + garment_image] --> B{{S1 input_quality<br/>分辨率/格式/大小}}
    B --> C{{S2 person_detection<br/>MediaPipe + Haar}}
    C -->|fail| Z[needs_retake]
    C -->|pass| D{{S3 garment_analysis}}
    D --> D1{VLM 代理可用?}
    D1 -- 是 --> D2[OpenAIGarmentAnalysisProvider<br/>VLM 结构化要素]
    D1 -- 否 --> D3[LocalGarmentAnalysisProvider<br/>本地 CV fallback]
    D2 --> E{{S4 upper_body_mask<br/>躯干可编辑区域 RGBA mask}}
    D3 --> E
    E --> F{{S5 edit_contract<br/>保留人脸/肤色/背景 仅改衣区}}
    F --> G{{S6 image_edit}}
    G --> H{Provider 优先级}
    H --> H1[RunwayGoogleTryOnProvider]
    H --> H2[OpenAIImageEditTryOnProvider]
    H --> H3[CodexImageGenBridgeTryOnProvider<br/>异步队列]
    H --> H4[MockTryOnProvider 验收用]
    H --> H5[UnavailableTryOnProvider<br/>不展示伪图]
    H1 & H2 & H3 & H4 --> I{{S7 quality_review<br/>人脸保留/保护区差异/质量}}
    H5 --> Z2[failed]
    I -->|有结果图| J[generated<br/>写 outputs/users/uid/tryon/tryon_id/]
    I -->|无结果| Z2
    J --> K[返回统一 JSON<br/>pipeline 证据 + result 路径]
    Z --> K
    Z2 --> K
```

### 4.3 流程说明

- **编排入口**：`app/tryon.py: run_try_on()`，7 个 stage 定义在 `TRYON_PIPELINE_STAGES`。HTTP 层有 5 个变体入口（`/try-on`、`/from-inspiration`、`/from-outfit`、`/from-outfit-plan`、`/asis/try-on/from-outfit`），最终都汇入同一 pipeline，差别只在 garment 素材的来源（直接上传 / 灵感图 / 衣橱搭配）。
- **双层 provider 抽象**：
  - 衣服理解层 `_default_garment_analysis_provider()`：探测 `TRYON_OPENAI_BASE_URL` / 本地 `127.0.0.1:8787/v1` 代理，可用则走 VLM，否则本地 CV。返回结构中的 `pipeline.garment_analysis.evidence.provider` 会如实标记当前 provider。
  - 图像编辑层 `_default_provider()`：按 RunwayGoogle → OpenAI images.edit → CodexBridge（异步任务队列，供外部 agent 取任务回传结果）→ Mock → Unavailable 优先级选择。
- **诚实降级原则**：没有真实图像编辑能力时，用户接口**不展示伪试穿图**（`UnavailableTryOnProvider`），mock 只在验收脚本 `scripts/tryon_mvp_acceptance.py` 中显式注入，用于固化 mask、接口和页面链路。
- **能力自描述**：`GET /try-on/capabilities` 返回当前代理地址、衣服理解是否走 VLM、真实图片编辑是否可用，前端据此决定 UI 展示口径。
- **产出落盘**：每次试穿一个工作目录 `outputs/users/{uid}/tryon/{tryon_id}/`，含 `result.png`、`upper_body_mask.png` 等；AS IS 模式下还会写入试穿记录 manifest（见 F4）。

---

## 5. F3 小红书链接提取流程（`POST /try-on/extract-xhs`）

### 5.1 UML 时序图（PlantUML）

```plantuml
@startuml f3_xhs_sequence
title F3 小红书链接提取时序图（tryon.extract_xhs_link）
actor 用户
participant "前端 /try-on/demo" as FE
participant "FastAPI main.py" as API
participant "tryon.py" as TRYON
participant "GarmentAnalyzer\n(VLM 或本地CV)" as GA
database "outputs/users/{uid}/tryon/xhs/" as CACHE

用户 -> FE : 粘贴笔记链接
FE -> API : POST /try-on/extract-xhs (url)
API -> TRYON : extract_xhs_link(url)
TRYON -> TRYON : 标准化 URL
TRYON -> TRYON : _fetch_xhs_html()\n抓取公开页面 HTML
note right of TRYON
  若触发登录墙/反爬,
  只能拿到 og 元数据封面图
end note
TRYON -> TRYON : 解析 __INITIAL_STATE__ JSON\n+ meta og:image 标签
TRYON -> TRYON : 合并候选图 URL(最多 12 张)
loop 每张候选图
  TRYON -> CACHE : 下载并缓存图片
  TRYON -> GA : 判断是否含可试穿上衣
  GA --> TRYON : category/bbox/质量分
  alt 模特穿着上衣 person_wearing_top
    TRYON -> TRYON : 生成上半身区域预览
  else 单件上衣 single_garment
    TRYON -> TRYON : 按衣服区域提取透明 PNG
  else 无可试穿上衣
    TRYON -> TRYON : 丢弃(保守策略)
  end
end
TRYON --> API : fashion_items + style_context\n+ reference_sheet
API --> FE : 候选上衣列表
FE --> 用户 : 展示可试穿上衣, 点击进入 F2 试穿
@enduml
```

### 5.2 Mermaid 流程图

```mermaid
flowchart TD
    A[用户粘贴小红书链接] --> B[标准化 URL]
    B --> C[_fetch_xhs_html<br/>抓取公开页面 HTML]
    C --> D{反爬/登录墙?}
    D -- 是 --> D1[仅保留 og 元数据封面图]
    D -- 否 --> D2[解析 __INITIAL_STATE__<br/>+ meta 标签图片]
    D1 --> E[合并候选图 URL ≤12 张]
    D2 --> E
    E --> F{遍历候选图}
    F --> G[下载缓存到 outputs/.../xhs/]
    G --> H[GarmentAnalyzer 识别上衣<br/>VLM 或本地 CV]
    H --> I{含可试穿上衣?}
    I -- 模特穿着 --> J1[生成上半身区域预览]
    I -- 单件上衣 --> J2[按 bbox 提取透明 PNG]
    I -- 无 --> J3[丢弃 保守策略]
    J1 & J2 --> K[聚合 fashion_items]
    J3 --> F
    K --> L[输出 fashion_items<br/>+ style_context + reference_sheet]
    L --> M[前端选择上衣 → 进入 F2 试穿链路]
```

### 5.3 流程说明

- **职责**：把"刷到喜欢的穿搭"转化为"可试穿的素材"，是内容平台到试穿链路的桥。
- **抓取策略**：纯服务端 httpx 抓公开 HTML，解析 `__INITIAL_STATE__` 内嵌 JSON 与 `og:image` 元数据，最多取 12 张候选图下载缓存到 `outputs/users/{uid}/tryon/xhs/`。
- **识别策略偏保守**：复用 F2 的 `GarmentAnalyzer` 判断每张图是否有可试穿上衣，区分"模特穿着"（生成上半身区域预览）与"单件平铺"（按 bbox 提取透明背景 PNG）两种素材形态；识别不稳的图片直接丢弃，第一版只展示能稳定识别的结果。
- **已知限制**：小红书若要求登录或触发反爬，只能拿到封面图；该限制以 `warnings` 形式返回给前端，而不是包装成失败。
- **出口**：提取出的 `fashion_items` 可直接作为 F2 的 garment 输入，也可经 F4 的 `/closet/import/link` 入柜（F4 复用同一抓取/下载能力）。

---

## 6. F4 衣橱导入与管理流程（`/closet/*`）

### 6.1 UML 活动图（PlantUML）

```plantuml
@startuml f4_closet_activity
title F4 衣橱导入与自动入柜活动图（closet._import_sources）
start
if (导入方式?) then (上传图片)
  :POST /closet/import/upload\n保存原图到 closet/sources/;
elseif (链接导入) then (小红书/网页链接)
  :POST /closet/import/link\n复用 F3 抓取并下载图片;
endif
while (还有未处理源图?) is (是)
  if (torch+transformers 可用?) then (是)
    :SegFormerClothesAdapter\nmattmdjaga/segformer_b2_clothes 语义分割;
    :按品类分组 label(top/bottom/skirt\n/dress/shoes/bag/accessory);
    while (还有未处理品类?) is (是)
      :生成 binary mask + bbox;
      if (rembg 可用?) then (是)
        :RembgMattingProvider\nrembg 精修 + 高斯边缘柔化;
      else (否)
        :直接使用语义 mask alpha;
      endif
      :产出 cutout.png / mask.png / preview.png;
      :构建 closet item\n(属性/质量分/pipeline 证据);
    endwhile (否)
  else (否)
    :top fallback: 仅按上衣区域提取;
  endif
endwhile (否)
:按 item_id 去重合并;
:写入 closet_manifest.json;
partition "后续管理（CRUD）" {
  :GET/PATCH/DELETE /closet/items/{id}\nPOST /{id}/reprocess 重跑分割;
  :/closet/outfits 搭配 CRUD\n生成 flatlay 封面;
  :/closet/tryon-records 试穿记录\n(由 F2 AS IS 模式写入);
}
stop
@enduml
```

### 6.2 Mermaid 流程图

```mermaid
flowchart TD
    A1[上传图片<br/>/closet/import/upload] --> B[保存原图到 closet/sources/]
    A2[链接导入<br/>/closet/import/link] --> B2[复用 F3 抓取下载]
    B --> C{遍历源图}
    B2 --> C
    C --> D{torch + transformers 可用?}
    D -- 是 --> E[SegFormerClothesAdapter<br/>segformer_b2_clothes 语义分割]
    D -- 否 --> F[top fallback 仅提取上衣]
    E --> G[按品类分组<br/>top/bottom/skirt/dress/shoes/bag/accessory]
    G --> H{遍历品类}
    H --> I[binary mask + bbox 裁剪]
    I --> J{rembg 可用?}
    J -- 是 --> K1[RembgMattingProvider<br/>精修 + 边缘柔化]
    J -- 否 --> K2[直接用语义 mask alpha]
    K1 & K2 --> L[产出 cutout/mask/preview.png<br/>构建 item + 质量分]
    L --> H
    F --> M[合并]
    L --> M[按 item_id 去重合并]
    M --> N[写 closet_manifest.json]
    N --> O[管理接口<br/>items/outfits/tryon-records CRUD<br/>preferences 偏好]
    O -.供给.-> P[F2 试穿 garment 来源<br/>F5 穿搭师衣橱上下文]
```

### 6.3 流程说明

- **核心能力**：`closet.py` 把"一张图"自动拆成"多件带透明背景的品类单品"。分割走 `SegFormerClothesAdapter`（HuggingFace `mattmdjaga/segformer_b2_clothes`，懒加载），边缘精修走 `RembgMattingProvider`（rembg + onnxruntime），两者都可用环境变量关闭或降级。
- **品类覆盖**：top / bottom / skirt / dress / shoes / bag / accessory 七类，通过 `SEGFORMER_LABEL_CATEGORY_HINTS` 把分割 label 映射到业务品类。
- **重模型可选**：未安装 `requirements-ai.txt`（torch/transformers/rembg）时服务照常启动，入柜降级为"仅上衣提取"的 fallback，`GET /closet/capabilities` 如实上报能力状态。
- **数据结构**：item 携带 `source`（来源图与 crop_box）、`assets`（cutout/mask/preview 路径）、`attributes`（颜色/材质/版型/风格标签）、`quality`（usable/review/rejected + 分数）、`pipeline`（分割与抠图 provider 证据），全部 JSON 落盘。
- **三个清单**：`closet_manifest.json`（单品）、`outfits_manifest.json`（搭配，含 flatlay 封面与 scene_tags）、`tryon_records_manifest.json`（试穿记录，由 F2 的 AS IS 模式写入）。这三个清单正是 F5 穿搭师的全部"衣橱事实来源"。

---

## 7. F5 AI 穿搭师对话流程（`POST /stylist/chat`）

### 7.1 UML 时序图（PlantUML）

```plantuml
@startuml f5_stylist_sequence
title F5 AI 穿搭师对话时序图（跨 3 进程）
actor 用户
participant "前端 /asis/demo" as FE
participant "FastAPI :8002\nmain.py / stylist.py" as API
participant "stylist_sessions.py" as SS
participant "OpenClaw bridge :18789\n(Node.js)" as BR
participant "openclaw CLI\n(agent.md + skills)" as CLI
participant "小红书 MCP :18060\n(Go)" as MCP
participant "LLM provider" as LLM

用户 -> FE : 输入"周五聚餐穿什么"
FE -> API : POST /stylist/chat\n{message, session_id, context}
API -> SS : ensure_stylist_session()\n+ recent_conversation(8 条)
API -> API : _attach_closet_context()\n读衣橱清单, 按相关性+品类均衡选品
alt 需要小红书灵感 (inspiration_tab)
  API -> MCP : GET /api/v1/login/status
  API -> MCP : GET /api/v1/feeds/search?keyword=...
  MCP --> API : 笔记列表(过滤+排序)
  note right of API: 失败时降级 Bing 公开搜索\nsite:xiaohongshu.com
end
API -> API : append_stylist_message("user")
alt demo 模式
  API -> API : _demo_chat_response() 本地 mock
else MiniMax 直连(轻量路径)
  API -> LLM : _run_light_closet_ai()
else OpenClaw HTTP(完整 agent 路径)
  API -> BR : POST /api/asis/chat\n(消息+衣橱上下文+xhs笔记+历史)
  BR -> BR : buildAgentMessage() 组装完整 prompt
  BR -> CLI : spawn openclaw agent --local\n--agent asis-stylist --model $MODEL
  loop agent 思考循环
    CLI -> LLM : 对话推理
    CLI -> API : 回调 POST /stylist/tools/{name}\n(closet_search/get_item/compose_outfit\n/save_outfit/tryon_from_outfit/xhs_search...)
    API --> CLI : 工具结果(衣橱事实)
    opt 需要趋势证据
      CLI -> MCP : MCP 协议 search_feeds/get_feed_detail
      MCP --> CLI : 笔记数据
    end
  end
  CLI --> BR : asis_stylist_recommendation_v1 JSON
  BR --> API : 标准化 agent 结果
end
API -> SS : append_stylist_message("assistant")\n+ update_stylist_session()
API --> FE : 回复 + tool_steps + xhs_notes\n+ recommended_outfits
FE --> 用户 : 打字机展示 + 笔记卡片 + 推荐搭配
@enduml
```

### 7.2 Mermaid 时序图

```mermaid
sequenceDiagram
    autonumber
    actor U as 用户
    participant FE as 前端 /asis/demo
    participant API as FastAPI :8002
    participant SS as stylist_sessions
    participant BR as OpenClaw bridge :18789
    participant CLI as openclaw CLI<br/>(agent.md + 7 skills)
    participant MCP as 小红书 MCP :18060
    participant LLM as LLM provider

    U->>FE: 输入穿搭问题
    FE->>API: POST /stylist/chat
    API->>SS: ensure_session + 取最近8条历史
    API->>API: _attach_closet_context<br/>衣橱选品(相关性+品类均衡)
    opt 需要小红书灵感
        API->>MCP: /api/v1/login/status + feeds/search
        MCP-->>API: 笔记(过滤排序, 失败降级 Bing)
    end
    API->>SS: 持久化 user 消息
    alt demo 模式
        API->>API: _demo_chat_response
    else MiniMax 轻量直连
        API->>LLM: _run_light_closet_ai
    else OpenClaw 完整 agent
        API->>BR: POST /api/asis/chat
        BR->>CLI: spawn openclaw --agent asis-stylist
        loop agent 循环
            CLI->>LLM: 推理
            CLI->>API: 回调 /stylist/tools/{name}
            API-->>CLI: 衣橱事实/试穿发起
            CLI->>MCP: search_feeds / get_feed_detail
            MCP-->>CLI: 趋势证据
        end
        CLI-->>BR: recommendation_v1 JSON
        BR-->>API: 标准化结果
    end
    API->>SS: 持久化 assistant 回复
    API-->>FE: 回复 + tool_steps + xhs_notes + outfits
    FE-->>U: 展示推荐与证据
```

### 7.3 流程说明

- **三进程拓扑**：FastAPI（业务与工具事实源）↔ OpenClaw bridge（`:18789`，Node.js HTTP 桥，`asis-agent-runtime/scripts/asis-openclaw-bridge.mjs`）→ spawn `openclaw` CLI 子进程加载 `agents/asis-stylist/agent.md` 与 7 个 skills；小红书 MCP（`:18060`，Go）对两侧分别提供 REST（FastAPI 灵感搜索）与 MCP 协议（agent 工具）两种接入。
- **四级路由**：`run_stylist_chat()` 按配置依次选择：demo mock（零依赖演示）→ MiniMax 直连轻量路径 → OpenClaw HTTP（完整 agent）→ OpenClaw CLI；全不可用时返回 503 `ai_unavailable` 而非伪造回答。模型经 `STYLIST_OPENCLAW_MODEL`（如 `openai/gpt-5.5`、`google/gemini-2.5-flash`、`minimax/MiniMax-M3`）路由，provider 前缀与 API key 不匹配时直接报不可用。
- **数据边界铁律**（写在 agent.md 硬性规则里）：agent 只能通过 asis tools（`POST /stylist/tools/{name}`，8 个工具）获取衣橱/搭配/试穿/小红书数据，不允许直接读 manifest、不允许捏造单品与证据；所有写操作（保存搭配、发起试穿）也以工具形式回调 FastAPI 完成。
- **7 个场景技能**：color-match、ootd-breakdown、capsule-wardrobe、travel-outfit、wedding-guest-outfit、interview-outfit、xhs-trend-research，由 OpenClaw 按用户意图自动匹配，前端也可通过 `context.requested_skills` 显式指定。
- **会话与记忆**：会话以 JSON 文件存于用户目录下（`stylist_sessions/`，原子写入），每轮带入最近 8 条历史；跨会话长期记忆由 bridge 的 `/api/asis/memory/{user_id}` 维护，FastAPI 侧 `/stylist/memory` 仅做代理。
- **证据链透传**：小红书笔记、工具步骤（`tool_steps`）、证据来源（`evidence_sources`）随响应返回前端，用于"推荐理由有据可查"的产品表达。

---

## 8. F6 认证与多用户数据隔离流程（`/auth/*` + storage）

### 8.1 UML 时序图（PlantUML）

```plantuml
@startuml f6_auth_sequence
title F6 手机号验证码登录与请求级用户隔离
actor 用户
participant "前端" as FE
participant "FastAPI /auth/*" as API
participant "auth.py" as AUTH
participant "auth_store.json" as DB
participant "storage.py\n(ContextVar)" as ST

用户 -> FE : 输入手机号
FE -> API : POST /auth/phone/start
API -> AUTH : start_phone_login(phone)
AUTH -> AUTH : 归一化 E.164\n生成验证码(开发默认 0000)
AUTH -> DB : 存 code_hash(HMAC-SHA256)\n10 分钟过期
AUTH --> FE : dev 模式返回 dev_code
用户 -> FE : 输入验证码
FE -> API : POST /auth/phone/verify
API -> AUTH : verify_phone_login(phone, code)
AUTH -> DB : 校验最新未消费验证码\n(过期/尝试>5/不匹配 → 拒绝)
AUTH -> DB : _find_or_create_user()
AUTH -> ST : hydrate_user_from_demo_data()\n新用户复制 demo 数据
AUTH -> DB : 存 session(token_hash, 24h)
AUTH --> FE : access_token + user
note over FE,ST : 之后的每个请求
FE -> API : 任意业务请求\nAuthorization: Bearer <token>
API -> AUTH : get_current_user (Depends)
AUTH -> DB : resolve_token 校验
AUTH --> API : user dict
API -> ST : user_storage(user_id)\n设置 ContextVar
ST -> ST : storage_context()\n→ outputs/users/{user_id}/
API -> API : 业务处理(读写均落在该用户目录)
@enduml
```

### 8.2 Mermaid 时序图

```mermaid
sequenceDiagram
    autonumber
    actor U as 用户
    participant FE as 前端
    participant API as FastAPI /auth/*
    participant AUTH as auth.py
    participant DB as auth_store.json
    participant ST as storage.py(ContextVar)

    U->>FE: 输入手机号
    FE->>API: POST /auth/phone/start
    API->>AUTH: 归一化 E.164 + 生成验证码
    AUTH->>DB: 存 code_hash(HMAC, 10min 过期)
    AUTH-->>FE: dev 模式回显 dev_code
    U->>FE: 输入验证码
    FE->>API: POST /auth/phone/verify
    API->>AUTH: 校验(过期/次数/匹配)
    AUTH->>DB: find_or_create_user
    AUTH->>ST: hydrate_user_from_demo_data
    AUTH->>DB: 写 session(token_hash, 24h)
    AUTH-->>FE: access_token + user
    Note over FE,ST: 之后每个业务请求
    FE->>API: Bearer token 请求
    API->>AUTH: get_current_user 校验
    API->>ST: user_storage(user_id) 设 ContextVar
    ST-->>API: 所有读写 → outputs/users/{user_id}/
    API-->>FE: 业务响应
```

### 8.3 流程说明

- **认证方式**：手机号 + 验证码 + Bearer Token，无密码。验证码与 token 均只存 HMAC-SHA256 哈希；单文件 `outputs/auth/auth_store.json` 承载 users / codes / sessions 三张"表"。
- **隔离机制**：`storage.py` 用 `ContextVar` 保存当前请求的 `user_id`，`StorageContext`（frozen dataclass，14 个路径字段）把该用户的所有目录计算集中在一处；业务代码不感知路径拼接，天然避免越权读写其他用户目录。未登录场景回落到 `local_user`。
- **演示友好**：新用户首次登录时从 demo 数据水合（`hydrate_user_from_demo_data`），立即可体验完整产品；`ASIS_AUTH_DEV_CODE` / `ASIS_AUTH_RETURN_DEV_CODE` / `ASIS_AUTH_ALLOW_MOCK_CODES` 三个开关在公网 demo（`ASIS_PUBLIC_DEMO=1`）下必须关闭。
- **配套防护**：`ops.py` 中间件对 `/auth/phone/*` 限 20 次/小时、上传类 60 次/小时、AI 类 30 次/小时，请求体上限 36MB；`scripts/cleanup_user_outputs.py` 定期清理过期体验数据。

---

## 9. 存储与文件布局（现状）

```
app/
├── main.py              # 全部路由（未用 APIRouter），静态页与静态目录挂载
├── analyzer.py          # F1 编排：8 stage、决策、result_summary、fixture 回放
├── cv_pipeline.py       # F1 本地 CV：人脸/色卡/校正/肤色/对比度/季节型
├── tryon.py             # F2/F3：试穿 pipeline、provider 抽象、小红书抓取
├── closet.py            # F4：SegFormer 入柜、rembg 精修、清单 CRUD、内嵌 demo 页
├── stylist.py           # F5：对话路由、衣橱/小红书上下文注入、工具分发
├── stylist_sessions.py  # F5：JSON 会话存储（原子写）
├── auth.py              # F6：验证码/token，单 JSON 文件
├── storage.py           # ContextVar 用户上下文 + StorageContext
├── ops.py               # 限流中间件、部署模式、门禁报告
├── models/              # MediaPipe tflite / face_landmarker.task（仅本地模型文件）
└── static/              # 各 demo 页面前端

outputs/                 # 运行时数据（gitignore）
├── users/{user_id}/
│   ├── closet/          # sources / items / outfits / *_manifest.json / stylist_sessions/
│   ├── tryon/           # {tryon_id}/ 工作目录 + codex_bridge/ 异步队列 + xhs/ 缓存
│   └── preferences.json
├── auth/auth_store.json
└── runtime/             # sidecar 日志

tests/
├── fixtures/            # 53 个色彩用例 + expected.json + tryon_models 模特图
└── results/             # 自测 JSON、HTML 报告、contact sheet
```

关键事实：**无数据库、无 Pydantic 模型**（全部 plain dict + JSON manifest），`app/models/` 只放 CV 模型权重。

---

## 10. 部署拓扑（现状）

| 模式 | 命令 | 说明 |
|------|------|------|
| 本地最小（仅色彩 MVP） | `uvicorn app.main:app --port 8000` | 只装 `requirements.txt`，无 AI 依赖 |
| 本地全栈 | `./scripts/start_asis_full_stack.sh` | 并行拉起 FastAPI:8002 + OpenClaw bridge:18789 + XHS MCP:18060，结束后自动清理 |
| 公开 demo（Docker） | `docker compose -f docker-compose.demo.yml up -d` | 需 `.env.demo`：强随机 `ASIS_AUTH_SECRET`、关闭 dev code、配置限流 |
| 公开 demo（裸机） | `ASIS_ENV=demo ASIS_PUBLIC_DEMO=1 ./scripts/deploy_demo.sh` | 守护进程方式 |

自检链路：`/health` → `/health/dependencies` → `scripts/check_runtime_readiness.py [--strict]` → `scripts/wait_for_demo_readiness.py --require-sidecars`（放量前）。严格模式会真实调一次 `/stylist/chat` 验证模型 key 有效。

---

## 11. Provider 选择矩阵与降级策略（验证期架构核心）

| 能力 | 优先 | 次选 | 兜底 | 能力上报端点 |
|------|------|------|------|--------------|
| 衣服要素理解 | OpenAI 兼容 VLM（`:8787/v1` 或 `TRYON_OPENAI_BASE_URL`） | — | 本地 CV（颜色/纹理/bbox） | `/try-on/capabilities` |
| 试穿图像编辑 | RunwayGoogle → OpenAI `images.edit` → CodexBridge 异步队列 | — | Mock（仅验收注入）/ Unavailable（不展示伪图） | `/try-on/capabilities` |
| 入柜分割 | SegFormer b2_clothes + rembg 精修 | 语义 mask 无精修 | 仅上衣 fallback | `/closet/capabilities` |
| 穿搭师对话 | OpenClaw HTTP（agent + skills） | MiniMax 直连 / OpenClaw CLI | demo mock / 503 | `/stylist/capabilities` |
| vl_review（色彩） | MockVisionReviewer（fixture 回归） | 本地 CV 风险初筛（真实上传） | OpenAIVisionReviewer（预留未启用） | — |
| 小红书数据 | MCP sidecar 登录态搜索 | og 元数据封面 | Bing 公开搜索降级 | `/asis/runtime-readiness` |

统一原则：**能探测就探测，探测失败如实降级并在 evidence.provider / capabilities 里标记，绝不伪造能力**。

---

## 12. 现状限制与后续演进方向

**现状限制（as-is）**

1. 单进程 + 文件系统：并发能力受单机限制，JSON manifest 无事务、无索引，用户量上去后需引入数据库（manifest → 表结构）与对象存储（图片 → OSS）。
2. 重 AI 依赖（torch/transformers/rembg）与应用同进程，首次请求懒加载导致冷启动慢；试穿图像编辑为同步 HTTP 调用，长耗时占用连接（CodexBridge 队列是异步化的雏形）。
3. 认证为单文件 JSON，验证码无真实短信通道（开发固定码）；限流为单机内存滑动窗口，多实例部署即失效。
4. 色彩诊断与试穿均为"验证期规则/外链模型"，置信度被人为上限保护；`vl_review` 的本地 CV 初筛不等于完整语义理解。
5. 小红书抓取依赖公开 HTML 结构，易受反爬/改版影响。

**README 已规划的下一步**

1. 更强人脸关键点模型替换 Haar 兜底，补齐姿态/眼/唇/脸颊定位；
2. `vl_review` 接入正式 VL API；
3. 专业标注实拍样本校准肤色/对比度/季节型阈值；
4. 完善色卡校正矩阵，降低环境光偏差。

**架构层面建议的演进（to-be 候选）**

- 存储：manifest → SQLite/Postgres；图片 → 对象存储 + CDN；`outputs/users/{uid}` 的目录语义可直接映射为表 + bucket 前缀。
- 任务化：试穿生成、入柜分割改为队列 + worker（CodexBridge 的 job 文件机制可直接平移到 Redis/Stream）。
- 服务拆分：AI 推理（分割/编辑/VLM）与 Web 层分离，按 GPU/CPU 资源独立伸缩；sidecar 拓扑已具备雏形。
- 观测：把 `/mvp/status`、`acceptance_gates`、capabilities 系列端点接入正式监控告警。

---

## 附：文档与代码索引

| 主题 | 文档 | 代码 |
|------|------|------|
| 色彩 MVP 验证 | `docs/MVP_VALIDATION.md`（`/mvp/handoff`） | `app/analyzer.py`、`app/cv_pipeline.py` |
| 算法说明 | `docs/ALGORITHM_EXPLAINER.md`（`/mvp/algorithm`） | 同上 |
| 开源选型 | `docs/OPEN_SOURCE_TECH_SELECTION.md` | `app/models/` |
| 试穿验证 | `docs/TRYON_MVP_VALIDATION.md` | `app/tryon.py` |
| 交互计划 | `docs/AS_IS_INTERACTION_PLAN.md` | `app/closet.py`、`app/stylist.py` |
| 数据 Schema | `docs/ASIS_DATA_SCHEMA.md` | `app/storage.py` |
| Agent runtime | `asis-agent-runtime/README.md`、`agents/asis-stylist/agent.md` | `asis-agent-runtime/` |
| 启动/验收脚本 | `README.md` | `scripts/start_asis_full_stack.sh`、`scripts/*acceptance*.py` |
