## Frontend Design

前端实现必须优先读取项目根目录的 `DESIGN.md`。

本项目当前采用“信任分享与审美试穿产品”的浅色消费级设计方向：

- 产品关键词：信任、审美、试穿、分享、轻修图、素材浏览
- 参考气质：Airbnb 的可信赖结构、美图/Wink 的轻量修图感、小红书/花瓣的图片浏览与灵感选择感
- 主体验必须优先服务“用户判断衣服是否适合自己”，而不是展示技术链路

### Visual Direction

- 使用 `DESIGN.md` 中定义的浅色、温暖、图片优先的视觉系统。
- 主背景使用暖白 / 淡粉灰，不使用大面积深色沉浸背景。
- 主 CTA 使用柔和玫红 `#ff4f86`，只用于核心行动和选中态。
- 照片、衣服图、试穿结果是视觉中心；UI 应该退后。
- 深色界面只适合内部 QA、调试、mask 检查或开发工具页，不适合作为用户主流程。

### Component Rules

- Buttons: pill shape, 999px radius, bold friendly label, no uppercase letter-spacing.
- Primary CTA: rose accent, white text, large tappable height.
- Secondary actions: white surface with rose border/text.
- Cards: white / translucent white, 16-24px radius, soft warm shadow.
- Upload areas: dashed rose border, warm white background, immediate image preview.
- Image frames: stable aspect ratio; result image must be larger than controls.
- Image system: follow `DESIGN.md` ratios and fit rules; generated try-on result is always the visual hero.
- Tokens: prefer the shared spacing, radius, and shadow tokens from `DESIGN.md` before adding one-off values.
- Model selector: default only shows selected model; alternatives live in a dedicated selection screen or drawer.
- Bottom navigation: light translucent background; active tab uses soft rose fill.
- Debug data such as JSON, mask, provider, pipeline stages should not dominate the user-facing page.
- Component states should feel complete: upload, link extraction, generation, success, retake, and failure states need user-facing copy.

### Layout Rules

- Main try-on flow should be mobile-first and multi-step:
  1. Start / overview
  2. Model selection or self-photo upload
  3. Garment upload or Xiaohongshu link extraction
  4. Result and sharing/inspection
- Desktop may center a mobile app shell; do not turn the consumer flow into a dashboard unless explicitly requested.
- Avoid marketing-only landing pages. The first screen should lead directly into the usable try-on experience.
- Avoid one-screen clutter. Use progressive disclosure and page/state transitions.

### Copy Rules

- Use user-facing language: “上传上衣图”, “选择模特”, “生成试穿图”.
- Avoid technical wording in primary UI: “mask”, “pipeline”, “provider”, “JSON”, “confidence”.
- If technical output is useful, hide it behind debug/inspection sections.
- Failure and retake copy should explain the next best action instead of exposing implementation errors.

### Verification Rules

Before finishing frontend work:

- Use browser tools to inspect the rendered page.
- Check mobile width around 390-430px and desktop centered shell.
- Confirm no horizontal overflow.
- Confirm no text overlap or clipped buttons.
- Confirm console has no broken resource errors.
- Confirm the main action path is visually obvious without reading technical details.
- Run the `DESIGN.md` MVP Self-Test Checklist before considering the UI finished.
