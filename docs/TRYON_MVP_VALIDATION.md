# AI 上衣试穿 MVP 验证交接

这份文档用于交接当前“图片穿搭提取 + 上衣虚拟试穿”MVP。它对齐色彩测试 MVP 的验证期方式：前置处理、接口结构、测试 fixture 和 mock provider 可稳定验证；用户侧真实试穿图必须依赖 AI 图像编辑 provider，不能用本地 mock 冒充。

## 当前状态

- 产品 Demo：`http://127.0.0.1:8001/try-on/demo`
- 能力状态：`http://127.0.0.1:8001/try-on/capabilities`
- 默认验收报告：`outputs/tryon_mvp_acceptance.json`
- 生产严格验收报告：`outputs/tryon_mvp_external_acceptance.json`

当前默认验收状态为 `passed_for_validation`：

- 默认中等男模 + 上衣图可通过显式 mock provider 生成验收结果结构和测试结果图。
- 单件上衣图片可被识别并提取透明背景预览。
- 无上衣图片会被拒绝，不进入可展示结果。
- mask 尺寸与原图一致，透明区域标记上衣编辑范围。
- 前端 demo 已按 `DESIGN.md` 做成多步、浅色、图片优先体验。

## 验证期口径

验证期不依赖 Codex 内部授权实时出图，原因与色彩测试一致：当前目标是稳定验证产品链路、接口结构、质量门禁、前端体验和失败兜底，而不是证明生产模型已经可用。

默认链路：

- `GarmentAnalyzer`：优先探测 OpenAI 兼容视觉能力；不可用时回落本地 CV。
- `MockTryOnProvider`：仅由测试和验收脚本显式注入，用于验证 mask、结果图、质量校验和页面结构。
- 用户侧 `/try-on`：没有真实图片编辑 provider 时返回失败提示，不展示伪试穿图。
- `OpenAIImageEditTryOnProvider`：生产化预留 adapter，仅在本地或远程代理支持 `images.edit` 时启用。

## 核心接口

```bash
curl http://127.0.0.1:8001/try-on/capabilities

curl -X POST "http://127.0.0.1:8001/try-on/analyze-garment" \
  -F "image=@/absolute/path/to/top.jpg"

curl -X POST "http://127.0.0.1:8001/try-on" \
  -F "person_image=@/absolute/path/to/person.jpg" \
  -F "garment_image=@/absolute/path/to/top.jpg"

curl -X POST "http://127.0.0.1:8001/try-on/extract-xhs" \
  -F "url=https://www.xiaohongshu.com/explore/..."
```

## 验收命令

默认验证期验收：

```bash
python scripts/tryon_mvp_acceptance.py
```

通过标准：

- 返回 `status=passed_for_validation`。
- `summary.validation_ready=true`。
- 必要 case 全部通过：默认模特生成、单件上衣提取、无上衣拒绝。

生产真实生图严格验收：

```bash
python scripts/tryon_mvp_acceptance.py --require-external
```

通过标准：

- 本地或远程 OpenAI 兼容代理支持 `images.edit`。
- `real_openai_image_edit_generates_tryon` 通过。
- 返回真实图片编辑 provider 生成的结果图。

当前本机 `http://127.0.0.1:8787/v1` 可被发现，但不支持 `images.edit`，因此严格验收仍为 `failed`。这不影响验证期 MVP 通过，但表示生产真实生图尚未接入。

## 用户侧门禁口径

### 必须重拍

- 本人照片无人脸或多人脸。
- 本人照片明显偏糊、尺寸太小或无法稳定定位上半身。
- 无法生成有效上衣 mask。
- 衣服图没有识别到清晰上衣。

### 可继续生成

- 本人照片质量轻微风险但仍能定位单人上半身。
- 衣服图是单件上衣，或人物穿着上衣且上衣区域稳定。
- 小红书链接中能提取到公开图片并识别上衣。

## 后续替换点

- 将 `GarmentAnalyzer` 从本地 CV fallback 升级为稳定 VLM provider。
- 将 `MockTryOnProvider` 替换为支持 `images.edit` 的真实图像编辑 provider。
- 将粗略躯干 mask 替换为人体解析/服装分割模型。
- 增强质量校验：脸部一致性、背景变化、手臂/头发边界和衣服贴合度。
- 小红书链接解析后续可接登录态、队列和更稳的图片来源抽取。

## 验收底线

每次改动后至少确认：

- `pytest -q` 通过。
- `python scripts/tryon_mvp_acceptance.py` 返回 `passed_for_validation`。
- `/try-on/capabilities` 返回 `status=ready_for_validation`。
- `/try-on/demo` 在未接入图片编辑 provider 时，应明确提示需要 AI 试穿模型，不展示本地 mock 图。
- 失败样本不会返回 `generated`。
- 生产严格验收如果失败，必须明确暴露 `production_image_edit_ready=false` 和代理能力缺口。
