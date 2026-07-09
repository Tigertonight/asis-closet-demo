# 色彩测试 MVP POC

这是一个用于验证“AI 色彩测试 MVP 是否可行”的本地 POC。当前阶段不做生产部署，目标是跑通：

1. 用户上传自拍图片；可以带标准色卡，也可以无色卡先测。
2. 本地规则先做硬性质量门禁。
3. `face_cv`、`color_card_cv`、`color_correction` 使用本地 OpenCV 真实计算。
4. `skin_tone`、`feature_contrast`、`seasonal_result` 使用本地启发式规则实时计算，不再返回写死季节型。
5. 硬阻断问题要求重拍；软风险继续分析并在阶段结果里标记 `warn`。
6. 通过可回归测试集验证整体通过率。

## 启动

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

完整用户试用还需要安装 AI 能力依赖，并复制 `.env.example` 后填入你的模型 key / sidecar 地址：

```bash
. .venv/bin/activate
pip install -r requirements-ai.txt
cp .env.example .env
```

如果 `.env` 已经存在，可以只补 asis 的非敏感运行默认项，不覆盖已有 key：

```bash
python scripts/sync_asis_env.py
```

配置完成后检查真实能力是否齐全：

```bash
python scripts/check_runtime_readiness.py
```

严格检查会在任一关键依赖缺失时返回非 0：

```bash
python scripts/check_runtime_readiness.py --strict
```

本地完整试用可以一键启动 FastAPI、asis OpenClaw bridge 和小红书 MCP：

```bash
./scripts/start_asis_full_stack.sh
```

默认地址：

- asis 页面：`http://127.0.0.1:8002/asis/demo`
- 运行检查：`http://127.0.0.1:8002/asis/runtime-readiness`
- OpenClaw bridge：`http://127.0.0.1:18789/api/asis/chat`
- 小红书 MCP：`http://127.0.0.1:18060/mcp`

启动后可运行轻量运行态检查：

```bash
python scripts/asis_runtime_smoke.py http://127.0.0.1:8002
```

## 内测上线 Demo

给外部同学体验时，不要直接使用本地开发默认值。推荐使用 Docker/Compose 或服务器守护进程运行 `scripts/deploy_demo.sh`：

```bash
cp .env.demo.example .env.demo
# 填写 .env.demo 中的 ASIS_AUTH_SECRET、模型 key 和 sidecar 配置
docker compose -f docker-compose.demo.yml up --build -d
```

非 Docker 服务器也可以在配置好 `.env` / 环境变量后运行：

```bash
ASIS_ENV=demo ASIS_PUBLIC_DEMO=1 ./scripts/deploy_demo.sh
```

公开 demo 必须满足：

- `ASIS_AUTH_SECRET` 为强随机值，不能使用默认值。
- `ASIS_AUTH_RETURN_DEV_CODE=0`，避免把验证码返回给前端。
- `ASIS_AUTH_ALLOW_MOCK_CODES=0`，避免公网接受固定验证码。
- `ASIS_MAX_REQUEST_BODY_MB`、`ASIS_UPLOAD_RATE_LIMIT`、`ASIS_AI_RATE_LIMIT` 已设置。
- `scripts/cleanup_user_outputs.py` 定期清理 `outputs/users` 下的过期体验数据。
- `scripts/wait_for_demo_readiness.py --require-sidecars` 通过后再放量。

部署后检查：

```bash
curl http://127.0.0.1:8002/health
curl http://127.0.0.1:8002/health/dependencies
python scripts/check_runtime_readiness.py --strict
```

也可以让脚本自动拉起全栈并验收，结束后自动清理进程：

```bash
python scripts/asis_full_stack_acceptance.py
```

当 `.env` 已经配置好模型 key，并希望严格要求所有真实能力就绪时：

```bash
python scripts/asis_full_stack_acceptance.py --strict
```

严格模式会实际调用一次 `/stylist/chat`，因此模型 key 无效、额度不足、provider 不通都会让验收失败，而不是只检查变量是否存在。

如果使用非 OpenAI 的穿搭师模型 key，请同时设置 `STYLIST_OPENCLAW_MODEL`，并确保 provider 前缀和 key 匹配。例如 `GOOGLE_API_KEY` 对应 `STYLIST_OPENCLAW_MODEL=google/gemini-2.5-flash`，`ANTHROPIC_API_KEY` 对应 `STYLIST_OPENCLAW_MODEL=anthropic/claude-sonnet-4-6`，MiniMax API key 对应 `STYLIST_OPENCLAW_MODEL=minimax/MiniMax-M3` + `MINIMAX_API_KEY`，MiniMax Coding Plan/OAuth 对应 `STYLIST_OPENCLAW_MODEL=minimax-portal/MiniMax-M3` + `MINIMAX_OAUTH_TOKEN`。未设置时默认按 `openai/gpt-5.5` 路由。

完整用户试用能力对应关系：

- 多品类自动入柜：`requirements-ai.txt` 中的 `torch`、`transformers`，默认模型为 `mattmdjaga/segformer_b2_clothes`。
- 透明 PNG 边缘精修：`requirements-ai.txt` 中的 `rembg`、`onnxruntime`，可用 `ASIS_REMBG_ENABLED=0` 关闭。
- 真实试穿图生成：配置 `TRYON_OPENAI_BASE_URL` + `TRYON_OPENAI_API_KEY`，或配置 `TRYON_RUNWAY_GOOGLE_URL` + `TRYON_RUNWAY_GOOGLE_API_KEY`。
- AI 穿搭师：启动独立 OpenClaw / asis sidecar，并配置 `STYLIST_OPENCLAW_CHAT_URL`、`STYLIST_OPENCLAW_MEMORY_URL`。
- 小红书搜索依据：启动小红书 MCP sidecar，并配置 `ASIS_XHS_MCP_URL`。

## 上传分析

```bash
curl -X POST "http://127.0.0.1:8000/analyze" \
  -F "image=@/absolute/path/to/face-with-card.jpg"
```

验证期说明：任意外部图片不会直接调用 Codex 内部 VL 能力；测试 fixture 会读取 `tests/fixtures/expected.json` 中的 Codex 辅助标注，真实 `/analyze` 上传会先用本地 CV 做妆容/滤镜/美颜风险初筛。其他核心分析阶段会真实计算：人脸/色卡/校正/肤色/对比度/季节型均来自当前图片。

单样本完整链路：

```bash
curl http://127.0.0.1:8000/fixtures/season_spring_bright/analyze
curl http://127.0.0.1:8000/fixtures/card_missing/analyze
curl http://127.0.0.1:8000/fixtures/season_summer_light/explain
```

测试集清单：

```bash
curl http://127.0.0.1:8000/fixtures
```

## 自测

重建测试集：

```bash
python scripts/build_mvp_fixtures.py
```

启动服务后查看结果：

```bash
curl http://127.0.0.1:8000/self-test/results
```

查看前端联调契约：

```bash
curl http://127.0.0.1:8000/analyze/contract
```

查看当前 MVP 验收状态：

```bash
curl http://127.0.0.1:8000/mvp/status
```

查看当前用户侧门禁规则：

```bash
curl http://127.0.0.1:8000/mvp/rules
```

运行正式回归测试：

```bash
pytest -q
```

启动服务后运行轻量验收：

```bash
python scripts/smoke_mvp.py
```

运行后会写入：

```text
tests/results/smoke_mvp_results.json
http://127.0.0.1:8000/qa-artifacts/smoke_mvp_results.json
```

刷新 QA 物料（自测 JSON、HTML 报告、contact sheet、采样区域图）：

```bash
python scripts/generate_qa_artifacts.py
```

浏览器页面：

```text
http://127.0.0.1:8000/mvp
http://127.0.0.1:8000/qa
http://127.0.0.1:8000/self-test
```

交接文档：

```text
docs/MVP_VALIDATION.md
http://127.0.0.1:8000/mvp/handoff
docs/ALGORITHM_EXPLAINER.md
http://127.0.0.1:8000/mvp/algorithm
http://127.0.0.1:8000/mvp/algorithm/contract
http://127.0.0.1:8000/mvp/seasonal-evaluation
docs/OPEN_SOURCE_TECH_SELECTION.md
http://127.0.0.1:8000/mvp/open-source-tech
```

## 上衣虚拟试穿 MVP

第一版只验证“上衣替换”链路：上传本人照片和目标上衣图，服务会提取衣服要素、生成上衣区域 mask，并调用图像编辑 provider 输出试穿结果。

本地 demo：

```text
http://127.0.0.1:8000/try-on/demo
```

Demo 默认选择 `male_medium_1.png` 中等男模；页面内可切换男/女、胖/中/瘦共 18 张测试模特，也可以上传本人照片覆盖当前模特。

衣服要素提取：

```bash
curl -X POST "http://127.0.0.1:8000/try-on/analyze-garment" \
  -F "image=@/absolute/path/to/top.jpg"
```

完整试穿链路：

```bash
curl -X POST "http://127.0.0.1:8000/try-on" \
  -F "person_image=@/absolute/path/to/person.jpg" \
  -F "garment_image=@/absolute/path/to/top.jpg"
```

小红书链接图片提取与上衣识别：

```bash
curl -X POST "http://127.0.0.1:8000/try-on/extract-xhs" \
  -F "url=https://www.xiaohongshu.com/explore/..."
```

该接口会：

1. 抓取公开页面 HTML 和元数据中的图片链接。
2. 下载候选图片到 `outputs/tryon/xhs/`。
3. 对每张图片判断是否有可试穿上衣。
4. 对有人穿上衣的图片生成上半身区域预览；对单件上衣图按衣服区域提取透明背景 PNG。

说明：小红书页面如果需要登录或触发反爬，服务可能只能提取到公开元数据中的封面图。第一版偏保守，只展示能稳定识别到上衣的图片。

衣服理解 provider：

- 默认会优先探测本地 Codex/OpenAI 兼容代理 `http://127.0.0.1:8787/v1`，也可以通过 `TRYON_OPENAI_BASE_URL`、`OPENAI_BASE_URL` 或 `LOCAL_OPENAI_BASE_URL` 指定代理地址。
- 如果配置了 `TRYON_OPENAI_API_KEY` 或 `OPENAI_API_KEY`，会随请求传给兼容服务；本地代理无 key 时会使用占位授权值。
- 对齐色彩测试 MVP 的验证期做法：默认验收不依赖 Codex 内部授权实时调用大模型，而是用本地 CV、fixture/mock provider 固化链路；代理可用时，衣服要素识别会优先通过视觉模型输出结构化结果；不可用或调用失败时，使用本地 CV fallback 跑通 MVP 链路。返回结构中的 `pipeline.garment_analysis.evidence.provider` 会明确标记当前 provider。

代理可用且支持 `images.edit` 图片编辑接口时，会通过 OpenAI 兼容图像编辑 provider 调用真实生图。未检测到图片编辑能力或 key 时，用户接口不会展示伪试穿图；验收脚本会显式注入本地 mock provider，用于验证接口、mask、页面和质量校验链路。输出文件保存在：

```text
outputs/tryon/
```

能力状态接口：

```bash
curl http://127.0.0.1:8000/try-on/capabilities
```

该接口会返回当前本地代理地址、衣服理解是否走 VLM、真实图片编辑是否可用，以及用户生成链路是否需要接入 AI 图片编辑模型。

试穿 MVP 验收：

```bash
python scripts/tryon_mvp_acceptance.py
```

本地无可用图片编辑代理或 key 时，脚本会用显式 mock provider 验收默认模特生成、单件上衣提取、无上衣拒绝，并输出 `passed_for_validation`。这与色彩测试 MVP 的 fixture 验证模式一致：验证期前置链路通过，但用户侧真实试穿图仍必须等待严格验收。

本地 Codex/OpenAI 兼容代理支持 `images.edit` 后运行严格验收：

```bash
python scripts/tryon_mvp_acceptance.py --require-external
```

严格模式只有在真实图像编辑返回 `generated` 且有结果图时才会通过。默认验收报告分别写入：

```text
outputs/tryon_mvp_acceptance.json
outputs/tryon_mvp_external_acceptance.json
```

试穿结果结构：

```json
{
  "status": "generated | needs_retake | failed",
  "tryon_id": "...",
  "input": {
    "person_image_id": "...",
    "garment_image_id": "..."
  },
  "garment": {
    "category": "top",
    "colors": [],
    "material": [],
    "fit": "",
    "details": [],
    "style_tags": []
  },
  "pipeline": {
    "input_quality": {},
    "person_detection": {},
    "garment_analysis": {},
    "upper_body_mask": {},
    "image_edit": {},
    "quality_review": {}
  },
  "result": {
    "image_path": "...",
    "mask_path": "...",
    "user_message": ""
  }
}
```

当前验证集：

- 53 个正式用例
- 6 组场景：基础质量异常、真实上传自动裁剪、人像异常、色卡异常、妆容/滤镜风险、合格季节型样本
- 8 个合格色彩结构样本
- 当前结果：`53/53` 通过，`100%`
- `face_cv`、`color_card_cv`、`color_correction`、`skin_tone`、`feature_contrast`、`seasonal_result` 均为真实计算阶段
- 可分析样本包含无色卡、色卡异常 fallback、脸小/截图自动裁剪、复杂海报墙、室内暖光/屏幕冷光、眼镜反光、刘海/帽檐、手托脸、美颜/滤镜/妆容等软风险继续分析样本
- 季节型结构完整率：`100%`
- `/qa` 页面支持选择单个样本并运行完整分析链路
- 已验证合格样本输出 `analyzed`，并返回真实计算的肤色 RGB/Lab/HSV、冷暖/明度/彩度/对比度、4季/12季/24季候选
- 已验证硬阻断样本输出 `needs_retake` 和用户可理解重拍建议
- 已验证软风险样本输出 `analyzed`，并在 `decision.warnings` 和对应阶段里保留问题码
- 已验证前端友好 `result_summary`：成功样本返回中文季节型、维度、判断原因、推荐色/避雷色；重拍样本不返回误导性结果
- 已验证四层用户结果口径：标准可用 `9` 张、可用但轻提示 `24` 张、低可信初步 `8` 张、建议重拍 `12` 张；当前季节型仍处于规则验证期，高质量样本可进入标准结果，但置信度仍会被上限保护，避免包装成高置信绝对判断
- `/qa` 页面支持按标准可用、轻提示、低可信、全部初步、建议重拍筛选，并展示中文影响因素

主要产物：

```text
tests/fixtures/images/
tests/fixtures/expected.json
tests/results/self_test_results.json
tests/results/self_test_report.html
tests/results/contact_sheet.jpg
tests/results/region_overlay_sheet.jpg
tests/results/overlays/
```

## 出参结构

`/analyze` 返回统一阶段结构；稳定字段也可以通过 `/analyze/contract` 查看：

```json
{
  "status": "needs_retake | analyzed | failed",
  "decision": {
    "retake_required": false,
    "blocking_errors": [],
    "warnings": [],
    "confidence_factors": [],
    "user_message": ""
  },
  "result_summary": {
    "available": true,
    "title": "明亮春型",
    "season": {
      "season_4": "spring",
      "season_4_name": "春季型",
      "season_12": "bright_spring",
      "season_12_name": "明亮春型",
      "season_24": "bright_spring_light_bright_high",
      "season_24_name": "明亮春型 · 明亮 / 鲜明 / 强对比",
      "top_candidates": [
        {
          "rank": 1,
          "season_12_name": "明亮春型",
          "confidence_percent": 76,
          "reason": "当前照片中肤色冷暖、明度、彩度和五官对比最接近这一类。"
        },
        {
          "rank": 2,
          "season_12_name": "浅夏型",
          "confidence_percent": 71,
          "reason": "这是相邻候选，适合用自然光或带色卡照片复核。"
        }
      ]
    },
    "dimensions": {
      "temperature": "warm",
      "temperature_name": "偏暖",
      "brightness": "light",
      "brightness_name": "明亮",
      "chroma": "bright",
      "chroma_name": "鲜明",
      "contrast": "high",
      "contrast_name": "强"
    },
    "confidence": 0.76,
    "confidence_percent": 76,
    "capture": {
      "quality_level": "standard",
      "quality_label": "标准结果",
      "result_tier": "standard",
      "result_tier_label": "标准可用",
      "used_color_card": true,
      "color_card_state": "used",
      "auto_cropped": false,
      "reference_only": false,
      "guidance_label": "照片条件较好，可以直接参考本次结果。",
      "risk_codes": [],
      "risk_labels": []
    },
    "next_actions": [
      {
        "code": "use_result",
        "label": "查看搭配建议",
        "priority": "primary",
        "reason": "照片条件较好，可以继续使用本次结果。"
      },
      {
        "code": "copy_summary",
        "label": "复制诊断摘要",
        "priority": "secondary",
        "reason": "方便保存或分享本次诊断。"
      }
    ],
    "why": [],
    "suitable_colors": [
      {"code": "ivory", "name": "象牙白", "hex": "#fff1d6"}
    ],
    "avoid_colors": [
      {"code": "muddy_gray", "name": "浑浊灰", "hex": "#77736c"}
    ],
    "confidence_notes": ["检测到可用标准色卡，肤色校正更稳定。"],
    "retake_message": ""
  },
  "pipeline": {
    "input_quality": {},
    "face_cv": {},
    "color_card_cv": {},
    "vl_review": {},
    "color_correction": {},
    "skin_tone": {},
    "feature_contrast": {},
    "seasonal_result": {}
  }
}
```

`result_summary` 是给 C 端前端直接消费的稳定摘要层；`pipeline` 保留给调试、QA 和模型迭代使用。若最终状态是 `needs_retake`，`result_summary.available=false`，不会返回季节型、推荐色或避雷色，只返回 `retake_message`。

前端优先消费：

- `capture.quality_level`：`standard` 表示标准结果，`reference_only` 表示初步结果，`retake` 表示建议重拍。
- `capture.result_tier`：更细的用户侧四层口径：`standard` 标准可用、`light_note` 可用但轻提示、`low_confidence` 低可信初步、`retake` 建议重拍。
- `capture.result_tier_label`：`result_tier` 的中文展示文案，结果页优先展示它。
- `season.top_candidates`：Top-2 季型候选，结果页可展示“主倾向 + 备选倾向”，避免把验证期规则推理包装成唯一确定答案。
- `capture.risk_labels`：中文影响因素，例如“未检测到色卡”“未使用色卡校正”“可能有轻微美颜”；前端可直接展示。
- `capture.used_color_card` / `capture.color_card_state`：用于判断是否引导用户补拍带色卡照片。
- `capture.guidance_label`：结果页顶部的人话提示。
- `next_actions`：结果页按钮或后续链路入口，例如 `use_result`、`retake_with_card`、`retake_photo`、`copy_summary`。

`/self-test/cached-results` 额外提供以下 QA 指标，供验收面板或后续监控使用：

- `result_tier_summary`：四层结果分布，包含标准可用、可用但轻提示、低可信初步、建议重拍。
- `group_summary`：按测试场景组聚合结果，除兼容旧的标准/初步/重拍外，也包含 `light_note` 和 `low_confidence`，用于判断某一类场景是否过度低可信。
- `acceptance_gates`：机器可读验收门槛，当前覆盖回归通过、色卡缺失/不可用仍可测、自动裁剪可继续分析、轻风险不被误拦、严重异常必须阻断、可分析覆盖充足。
- `product_metrics.seasonal_accuracy`：基于 `seasonal_gold` 金标样本计算 Top-1 / Top-2 季节型命中率；当前 Top-1 / Top-2 均为 `100%`，已达到 Top-1 `>=70%`、Top-2 `>=85%` 的 MVP 回归门槛。
- `product_metrics.reference_reason_summary`：所有初步结果的中文原因聚合。
- `product_metrics.tier_reason_summary.light_note`：可用但轻提示样本的原因聚合，适合检查轻微美颜、轻微姿态、自动裁剪是否被正确放行。
- `product_metrics.tier_reason_summary.low_confidence`：低可信初步样本的原因聚合，适合优先复核强滤镜、浓妆、粉底、明显模糊、伪色卡、大角度侧脸等会直接影响肤色判断的场景。无色卡或色卡轻微不可用默认归入轻提示，不再单独视为低可信。

`/mvp` 是给非技术同学看的 MVP 状态页：汇总是否可演示、四层结果分布、用户侧门禁规则、验收门槛和 QA 入口，并提供 12 个代表样本入口；点击样本会打开 `/demo?case=...` 并自动跑对应产品结果。当前代表样本覆盖标准可用、无色卡轻提示、伪色卡低可信、遮挡需重拍，以及 App 截图、彩色背景、海报墙、室内暖光、屏幕冷光、普通眼镜、刘海遮额、手托脸等真实用户灰区。

`/demo?case=<case_id>` 可作为分享/演示链接直接打开并自动运行样本；如果 `case_id` 不存在，页面会停在上传页并给出友好提示，避免把无效链接包装成上传失败。

`/fixtures/{case_id}/explain` 聚合单张 fixture 的核心解释信息：结果层级、肤色/五官采样来源、维度分数、季节候选、色卡状态、问题码和采样图链接，适合排查某个样本为什么被判成某一季型。

`/mvp/handoff` 暴露 `docs/MVP_VALIDATION.md` 的交接文档，包含启动、演示路径、用户侧门禁、接口、后续替换点和验收底线。

`/mvp/algorithm` 暴露 `docs/ALGORITHM_EXPLAINER.md` 的算法说明，解释当前真实模型、色彩维度、三段诊断、12/24 季候选排序、色卡策略、置信度口径和 QA 验证方式。

`/mvp/algorithm/contract` 是机器可读算法 contract，结构化返回模型、阈值、季节映射、色卡策略和 QA 门槛，方便前端、QA 脚本或后续评估服务消费。

`/mvp/seasonal-evaluation` 聚合季节型金标样本的期望、预测、Top 候选、维度证据、采样图和 explain 链接，适合排查“为什么这张样本判成某个季节型”。

`/mvp/status` 是更轻量的机器可读状态入口：汇总当前通过数、四层结果分布、季节型 Top-1/Top-2 命中、验收门槛和 QA 物料链接。`status=ready` 表示当前回归与关键验收门槛都通过，可用于验证期演示。

`/mvp/rules` 固化当前用户侧门禁规则：`hard_retake` 只覆盖非人像、多人脸、严重遮挡、严重画质异常等无法判断的场景；`light_note` 覆盖无色卡、普通色卡不可用、自动裁剪、轻微姿态/妆容风险；`low_confidence` 覆盖明显滤镜、浓妆、粉底、明显模糊、伪色卡、大角度侧脸等会直接影响肤色判断的场景。

`/analyze/contract` 额外提供 `examples.standard`、`examples.light_note`、`examples.low_confidence`、`examples.retake` 等最小样例，前端可以直接用它们覆盖标准结果、轻提示、低可信初步和重拍分支。旧的 `examples.reference_only` 保留作兼容。

每个阶段统一包含：

```json
{
  "status": "pass | warn | fail | unknown",
  "confidence": 0.0,
  "evidence": {},
  "issues": [],
  "suggestions": []
}
```

## 硬阻断与软风险

MVP 阶段不把所有异常都当成重拍。当前规则按“是否会破坏肤色校正/稳定提取”区分：

- 硬阻断：低分辨率、严重过曝/欠曝、强模糊、非人像、多人脸、半张脸、无法自动裁剪的脸太小、口罩/墨镜等明显遮挡，以及会让脸部稳定区域不可用的严重异常。
- 软风险：未检测到色卡、色卡裁切/太远/反光/伪卡/遮挡导致不能参与校正、脸部偏小但可自动裁剪、脸部细节略软但仍可采样、截图/长图可自动裁剪、头部姿态偏侧或轻微倾斜、口红、妆容/粉底/腮红/彩瞳、美颜磨皮、滤镜偏色，以及验证集中被 Codex VL/fixture 判断为可继续分析的轻微 CV 风险。
- 软风险处理：最终状态仍为 `analyzed`，但对应阶段返回 `warn`，`confidence` 会降低，并在 `decision.warnings` 中给出建议。
- 无色卡处理：`color_card_cv` 返回 `card.missing`，`color_correction` 返回 `correction.no_card_fallback`，继续输出季节型结果；后续可用这些标记引导用户补拍带色卡照片。
- 脸小处理：如果本地 CV 能定位到单人脸，会自动裁剪到更适合分析的范围，返回 `face.auto_cropped`；只有完全检测不到脸、多人脸或裁剪后仍不可用时才要求重拍。
- 色卡处理：色卡不是必需品；色卡不可用、疑似误检或校正失败时都会改用原图推理，并通过 `card.*` / `correction.*` 标记为轻提示。只要照片本身可分析，不因为色卡问题要求用户重拍；完整可用但轻微倾斜的色卡仍视为已使用，只做轻提示。
- 美颜磨皮和妆容：默认继续分析并降低可信度；如果叠加强曝光、强滤镜、脸部严重失真或遮挡，则由输入质量/遮挡规则转为硬阻断。

## 验证期 AI 架构

- `MockVisionReviewer`：服务自测时读取 fixture 中的 Codex 辅助标注，保证回归稳定。
- `CodexAssistedReviewer`：标记当前人工/Agent 辅助看图标注流程，不作为服务运行时依赖。
- `OpenAIVisionReviewer`：生产化预留适配器，当前不启用。

当前 POC 的核心分析阶段已替换为真实本地 CV/规则逻辑：

- `face_cv`：MediaPipe Face Detector 优先、OpenCV Haar Cascade 兜底，检测正脸、人数、脸部占比、裁切、遮挡和脸部清晰度；轻微贴边或轻度模糊默认继续分析并降低可信度。
- `face_landmarks`：本地 MediaPipe Face Landmarker 模型驱动肤色和五官采样区域，优先用真实关键点定位额头、脸颊、下颌、眼睛和发际候选区；模型失败时回退到人脸框比例区域。
- `color_card_cv`：`colour-checker-detection` segmentation + OpenCV 回退检测 24 色 ColorChecker 候选；官方库候选会先经过位置/形态校验，不够像标准色卡时回落为无色卡，避免把衣服/背景/UI 彩色块误报成色卡异常。
- `color_correction`：基于检测到的 24 个色块近似采样，计算线性 RGB 校正矩阵，并用 `colour-science` 输出 CIE 2000 DeltaE、RGB 距离、`correction_quality` 和 `matrix_rgb_3x4`；矩阵求解失败时降级为原图推理。
- `skin_tone`：优先基于 MediaPipe 关键点生成额头、双颊、下颌候选区域，再用 HSV/YCrCb/RGB 肤色 mask 和自适应小窗口提取稳定肤色；有可用色卡矩阵时会对肤色 RGB 做保守校正混合，并同时输出 `region_source`、`raw_rgb`、`full_corrected_rgb`、最终 `rgb`、`correction_strength` 和 `sample_quality`。
- `feature_contrast`：优先基于 MediaPipe 关键点生成眼部和发际候选区域，再做自适应暗色特征采样；采样优先使用非肤色暗像素，避免少量背景或边缘暗点把浅色类型误判成高对比；输出各区域 `source`、`selection_method`、`dark_pixel_ratio` 和 `sample_quality`。
- `vl_review`：测试 fixture 继续读取 Codex 辅助标注；真实上传先使用本地 CV 做妆容/滤镜/美颜风险初筛，能标记明显口红、腮红、整体偏色和过度平滑等软风险。
- `seasonal_result`：基于肤色冷暖、深浅、净柔三段诊断和虚拟色布排序输出 4 季、12 季和派生 24 季候选；无色卡样本会继续推理，但通过 warning 降低可信度。

`vl_review` 的本地 CV 初筛不等同于完整语义理解；生产化时应替换或叠加正式 VL API。

开源算法选型见 `docs/OPEN_SOURCE_TECH_SELECTION.md`。当前路线是不直接依赖某个个人色彩开源项目做最终分类，而是优先替换底层模块：已用 MediaPipe Face Landmarker 接入真实关键点采样，已用 `colour-checker-detection` 接入混合色卡检测，已用 `colour-science` 输出标准 CIE 2000 DeltaE 校正指标，已把 `skin_tone` 升级为自适应肤色 mask 采样，并把 `feature_contrast` 升级为非肤色暗像素自适应采样；后续继续评估 skin parsing，并用自研标注集升级 `seasonal_result`。

## 下一步

1. 用更强的人脸关键点模型替换 Haar Cascade，补齐姿态、眼睛、嘴唇、脸颊区域定位。
2. 将 `vl_review` 接入正式 OpenAI Vision API 或其他 VL 模型。
3. 用专业标注实拍样本校准肤色、对比度和季节型规则阈值。
4. 完善有色卡时的颜色校正矩阵，降低环境光偏差。
