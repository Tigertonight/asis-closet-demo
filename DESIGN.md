# AS IS Design System

Chinese product name: `适我`.

## 1. Product Positioning

AS IS is a trust, taste, and sharing experience for color-aware outfit recommendation and AI-assisted try-on. Use `AS IS` as the product name in English contexts and `适我` wherever a Chinese name is needed. The interface must help users feel:

- The person in the image is still themselves.
- Clothing color, fit, and style can be judged clearly.
- The recommendation understands their closet, city weather, and personal color direction.
- The result is pleasant enough to save, compare, and share.

The visual direction should combine:

- Airbnb-like trust, clarity, and approachable structure.
- Meitu/Wink-like lightweight photo-editing friendliness.
- Xiaohongshu / Huaban-like image browsing and style inspiration.

This is not a dark dashboard, a developer tool, or an AI lab interface. The main user experience should feel like a polished consumer photo app that helps users decide "does this suit me?"

### Product Frame

The main app frame combines three atomic capabilities:

- **Weather + closet recommendation**: recommends today's outfit from the user's closet and city weather.
- **Color test**: enters the existing color analysis flow directly at photo upload, not a separate marketing home.
- **Virtual try-on**: lets outfit cards enter outfit detail, try-on, and free styling.

The home screen is the product's primary entry point. It should not be a landing page. It should immediately show a useful outfit recommendation and the next actions.

## 2. Visual Theme & Atmosphere

The default product theme is light, warm, and image-first.

UI chrome should stay quiet so the uploaded person photo, garment image, and generated try-on result become the visual center. Backgrounds should be soft warm white or very light pink-gray rather than pure white. Use delicate color only to guide action, selection, and emotional tone.

The page should feel:

- trustworthy, not experimental
- aesthetic, not technical
- calm, not childish
- image-led, not decoration-led
- shareable, not dashboard-like

Avoid large dark surfaces for the primary user flow. Dark UI may be used only for internal QA/debug pages or image inspection tools where contrast is the goal.

## 3. Color Palette & Roles

### Core Colors

- **Canvas Warm White** `#fffafa`: primary app background
- **Page Blush** `#f8f2f5`: outer background / app shell background
- **Card White** `#ffffff`: primary surface for cards and upload areas
- **Soft Rose** `#fff1f6`: selected surfaces, gentle highlights
- **Mist Blue** `#eefbff`: subtle secondary wash for image/tool panels

### Brand / Action

- **Rose CTA** `#ff4f86`: primary action, selected tab, active state
- **Rose Deep** `#e83d73`: pressed state, emphasis text
- **Coral Support** `#ff7a8a`: secondary emotional accent, use sparingly

### Text

- **Ink** `#1c1b20`: primary text
- **Soft Ink** `#4f454c`: secondary strong text
- **Muted** `#8b8388`: helper text and metadata
- **Disabled** `#b9afb4`: disabled labels

### Lines & States

- **Line** `#eee4e8`: dividers and card borders
- **Success** `#23835a`: validation success
- **Warning** `#a46a00`: recoverable risk
- **Error** `#d92c4e`: blocking issue

### Color Principles

- Use rose only for user action, selection, and clear emphasis.
- Do not flood the page with pink. The product should feel refined, not candy-like.
- Use blue/lilac only as very soft ambient support, never as dominant gradients.
- Let photos provide most of the visual richness.

### Space, Radius & Shadow Tokens

Use a small shared token set before adding new one-off values. These tokens are enough for the MVP and should keep the UI feeling consistent without over-designing it.

```css
--space-1: 4px;
--space-2: 8px;
--space-3: 12px;
--space-4: 16px;
--space-5: 24px;
--space-6: 32px;

--radius-sm: 8px;
--radius-md: 16px;
--radius-lg: 24px;
--radius-pill: 999px;

--shadow-card: 0 18px 48px rgba(82, 42, 61, .09);
--shadow-cta: 0 16px 30px rgba(255, 79, 134, .24);
--shadow-float: 0 22px 60px rgba(54, 25, 38, .12);
```

- Use `--space-4` as the default card inner padding on mobile.
- Use `--space-5` for gaps between major content groups.
- Use `--radius-sm` for hero media and small image corners, `--radius-md` for thumbnails, `--radius-lg` for panels, and `--radius-pill` only for buttons, tabs, and pills.
- Avoid stacking multiple heavy shadows in the same viewport. The primary image/result and CTA should get the strongest depth.

## 4. Typography

Use the platform system stack:

```css
font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Segoe UI", sans-serif;
```

### Type Scale

| Role | Size | Weight | Line Height | Usage |
|---|---:|---:|---:|---|
| Page Title | 28-32px | 800 | 1.12 | Mobile hero / main product name |
| Screen Title | 22-24px | 800 | 1.16 | Flow screen headings |
| Section Title | 16-18px | 750 | 1.25 | Card titles |
| Body | 14-15px | 400-500 | 1.55-1.65 | Descriptions |
| Button | 15-16px | 750-800 | 1.2 | Primary actions |
| Caption | 12-13px | 500-650 | 1.45 | Hints, metadata |

### Typography Principles

- Do not use uppercase button labels in the consumer flow.
- Keep letter spacing at `0`.
- Chinese UI copy should be short, direct, and friendly.
- Avoid technical words in the main flow: `mask`, `pipeline`, `JSON`, `provider`, `confidence` should be hidden behind debug views.

## 5. Components

### Buttons

**Primary CTA**

- Background: linear rose or solid `#ff4f86`
- Text: white
- Radius: `999px`
- Height: 52-58px
- Weight: 750-800
- Shadow: soft rose shadow, e.g. `0 16px 30px rgba(255, 79, 134, .24)`
- Use for the next core action only.

**Secondary Button**

- Background: white
- Border: `1px solid #f2c6cc`
- Text: `#e83d73`
- Radius: `999px`
- Use for alternate actions like changing model or parsing links.

**Text / Ghost Button**

- No heavy border.
- Use for low-risk navigation or debug reveal.

### Cards

- Background: white or translucent white.
- Radius: 16-24px depending on size.
- Border: subtle white or `#eee4e8`.
- Shadow: soft, warm, low-opacity. Avoid heavy black shadows.
- Do not nest cards inside cards unless the inner card is a repeated item such as a model thumbnail.

### Image Frames

Image frames are the most important components.

- Use stable aspect ratios.
- Use `object-fit: contain` for inspection images.
- Use `object-fit: cover` for model thumbnails.
- Avoid dark backgrounds behind clothing and skin unless inspecting masks.
- Generated results should be larger than controls.

### Image System

The image system is the highest-impact part of the product. If a layout decision is unclear, prioritize whether the user can judge the person, garment, and generated result clearly.

| Image Type | Recommended Ratio | Fit | Visual Priority | Notes |
|---|---:|---|---|---|
| Current model preview | `3 / 4` | cover | medium | Crop consistently around upper body; face and T-shirt must remain visible. |
| Model thumbnail | `3 / 4` | cover | low | Use short labels such as `男中 1`; selected state must be obvious. |
| Person upload preview | `3 / 4` or natural | contain | medium | Never crop user-uploaded self photos in inspection areas. |
| Garment upload preview | `1 / 1` or natural | contain | medium | Preserve garment shape and empty background. |
| Generated try-on result | natural or `3 / 4` | contain | highest | This is the result hero and must be larger than all controls. |
| Link-extracted garment | `1 / 1` | contain | medium | Use a compact grid; show only useful extracted tops in the primary view. |
| Region/mask preview | natural | contain | low | Hide inside inspection/details by default. |

#### Image Frame Rules

- Empty image frames should use warm blush or mist backgrounds, not dark gray.
- Result pages should show one primary generated image first; before/after, region preview, and raw data should be secondary.
- Before/after comparison should use equal-sized frames only when the user is explicitly comparing changes. Otherwise, the generated result gets more space.
- For multi-image Xiaohongshu extraction, use a two-column grid on mobile and keep captions short: `已找到上衣`, `未找到上衣`, or the recovery reason.
- Avoid decorative frames that compete with the photo. The photo should feel like the product, not content inside a heavy widget.

### Upload Areas

- Dashed rose border.
- Warm white / blush background.
- Large enough to feel tappable.
- Clear empty, selected, loading, and error states.
- Preview selected image immediately.

### Model Selector

- Default should show one selected model, not all models.
- Alternate models should appear in a dedicated selection screen or drawer.
- Thumbnail labels should be short: `男中 1`, `女瘦 2`, etc.
- The selected model must be visually obvious.

### Bottom Navigation

- Use only in app-like multi-page flows.
- Light translucent background.
- Active state uses soft rose fill and rose text.
- Keep touch targets at least 44px high.

### Component States

The MVP should feel complete through state quality, not through more decoration.

| Component | Required States |
|---|---|
| Primary CTA | default, disabled, loading, success handoff |
| Upload tile | empty, selected, loading, invalid file, too large, retryable failure |
| Model card | default, selected, pressed, unavailable |
| Link extraction | empty link, parsing, found tops, no usable top, private/unreachable link |
| Result page | not generated, generating, generated, needs retake, failed |
| Inspection details | collapsed by default, expanded on demand |

- Disabled buttons should keep their layout size and reduce emphasis with opacity, not disappear.
- Loading states should name the user-facing action: `正在生成试穿图`, `正在解析链接`, `正在检查图片`.
- Failure states should include the next best action, not only an error label.

## 6. Layout Principles

### Default Flow

The try-on product should use a multi-step mobile-first flow:

1. **Start / Overview**: show current model and one clear next action.
2. **Model**: choose test model or upload self-photo.
3. **Garment**: upload garment or parse Xiaohongshu link.
4. **Result**: show try-on image first, then mask/debug data behind a secondary reveal.

### Mobile First

- Primary target width: 390-430px.
- Desktop may show the mobile app shell centered, like a polished prototype.
- Avoid desktop dashboard layouts unless building an internal QA page.

### Density

- Use enough whitespace for trust and aesthetic judgment.
- Do not cram the main consumer flow like a table or dashboard.
- Do not make a marketing landing page before the usable experience.
- Keep important actions visible without overwhelming the user.

### Result Page

- Generated image is the hero.
- Secondary artifacts, including mask and JSON, should be collapsed or visually de-emphasized.
- User-facing status should be plain language.

### Page-Level Visual Priorities

- **Home**: product name `AS IS`, city weather, one clear `今日推荐` outfit card, activity widgets, and inspiration outfit feed.
- **Today recommendation**: closet items and weather are the center; card click enters outfit detail / try-on.
- **Activity widgets**: compact horizontal widgets. The first widget is `色彩测试` and opens the color test upload step directly.
- **Inspiration feed**: two-column Xiaohongshu-like image cards. Pull-to-refresh updates only this feed.
- **Start**: one selected model, one clear CTA, and a small promise about preserving the person's look.
- **Model**: current model first; alternate models are browseable but should not visually overpower the selected model.
- **Garment**: upload area first, Xiaohongshu extraction second, status copy directly below the action.
- **Result**: generated image first, user-facing status second, inspection details third.
- **History / inspiration**: image grid first, filters and controls second.

### Home Layout Rules

The mobile home page should be ordered:

1. **Top bar**: `AS IS` on the left; city, temperature, and weather on the right.
2. **Today recommendation**: large outfit card. The outfit visual should be more important than explanatory text. Use warm light surfaces by default; dark cards are allowed only as contained recommendation cards if the rest of the page remains light.
3. **Activity / widget row**: horizontal cards such as `色彩测试`; do not include outfit calendar in this version.
4. **Inspiration outfits**: two-column masonry/grid. Cards come from backend recommendations in later versions; for MVP they may use current local outfits.

Pull-to-refresh from the top may show a small rose loading mark, but the refreshed content scope is the inspiration feed only. Today's recommendation should stay stable unless the city, weather, or closet data changes.

### Outfit Detail Rules

Outfit cards open a detail page before generation:

- Hero flat-lay of the outfit.
- Small selected model preview.
- `穿搭单品` row showing each item in the outfit.
- Bottom actions: secondary `自由搭配`, primary `试穿`.

Tap `试穿` to apply the outfit directly to the selected model or uploaded self-photo. Tap `自由搭配` to edit the current outfit on a canvas.

### Free Styling Rules

The free styling page is a focused editor, not a feed:

- Top bar: back, title `自由搭配`, save button.
- Canvas: current outfit items can be moved, scaled, rotated, deleted, and layered.
- Smart layout: one pill action `一键排版` restores a clean flat-lay arrangement.
- Add item sheet: category tabs and closet item grid.
- Save creates a new outfit plan and returns to the outfit detail or closet outfit list.

Use rose for save/selected states only when helpful; black may remain for neutral icon buttons, but primary product actions should prefer rose.

## 7. Motion & Interaction

- Page transitions: subtle fade / translate, 180-280ms.
- Button press: small opacity or translate feedback.
- Loading: visible but calm; avoid noisy spinners.
- Do not use `scrollIntoView` in embedded browser contexts.
- Preserve scroll position intentionally or reset with `window.scrollTo`.

## 8. Content Voice

The copy should sound like a trustworthy photo app, not a model pipeline. It should reduce uncertainty and give the user a clear next action.

### Voice Principles

- Plain, direct, friendly Chinese.
- Explain what the user can do next.
- Avoid exposing implementation terms in the primary flow.
- Use gentle certainty: do not overpromise perfect fit or exact garment reconstruction.

### Copy Patterns

| Situation | Prefer | Avoid |
|---|---|---|
| Generating | `正在生成试穿图...` | `image_edit running` |
| Checking image | `正在检查图片是否适合试穿` | `quality_review pending` |
| Retake needed | `这张照片上半身不够清楚，换一张肩膀完整的照片会更准。` | `mask generation failed` |
| Result rejected | `这次试穿结果变化太大，建议重新生成。` | `quality_review failed` |
| Link blocked | `这个链接暂时无法读取，可以换成图片链接或手动上传。` | `provider error` |

Technical terms such as `mask`, `pipeline`, `JSON`, `provider`, and `confidence` may appear only inside inspection/debug details.

## 9. Do's and Don'ts

### Do

- Design for trust, taste, and sharing.
- Keep images as the center of the experience.
- Use soft rose as the functional brand accent.
- Make the default path simple: select model -> upload garment -> generate.
- Hide technical/debug details by default.
- Use real generated/test model images instead of abstract illustrations.

### Don't

- Do not use Spotify-style dark immersive UI for the main user flow.
- Do not make the product feel like a developer dashboard.
- Do not overuse gradients, purple-blue blobs, or decorative orbs.
- Do not expose raw JSON or pipeline stages as primary content.
- Do not use technical labels where user-facing copy is enough.
- Do not make the first screen a marketing-only landing page.

## 10. Agent Implementation Guide

When editing frontend screens in this project:

1. Read this `DESIGN.md` first.
2. Preserve the consumer app direction unless the user explicitly asks for an internal QA/debug tool.
3. Prefer multi-page or progressive disclosure for complex flows.
4. Use warm light surfaces, rose CTAs, stable image frames, and user-friendly copy.
5. Verify with browser screenshots on mobile width and desktop-centered shell.
6. Confirm there is no horizontal overflow, no text overlap, and no broken image/resource console errors.

### MVP Self-Test Checklist

Before calling a UI change done, verify these items:

- **Image hierarchy**: the generated try-on result is the largest image on the result page.
- **Default path**: a user can go from selected model to garment upload to result without seeing all technical details.
- **State quality**: upload, link extraction, generation, success, retake, and failure states have user-facing copy.
- **Token consistency**: spacing, radius, and shadows use the small token set unless there is a clear exception.
- **No visual clutter**: debug/inspection content is collapsed or secondary.
- **Mobile fit**: at 390-430px width, no primary CTA is hidden by bottom navigation.
- **Desktop shell**: desktop keeps the mobile app shell centered instead of becoming a dashboard.
- **No technical leakage**: `mask`, `pipeline`, `JSON`, `provider`, and `confidence` are not visible in the primary user flow.
- **Browser health**: no horizontal overflow, no text overlap, and no broken image/resource console errors.

### Quick Token Reference

```css
--canvas: #fffafa;
--page: #f8f2f5;
--card: #ffffff;
--soft: #fff1f6;
--accent: #ff4f86;
--accent-deep: #e83d73;
--ink: #1c1b20;
--muted: #8b8388;
--line: #eee4e8;

--space-1: 4px;
--space-2: 8px;
--space-3: 12px;
--space-4: 16px;
--space-5: 24px;
--space-6: 32px;

--radius-sm: 8px;
--radius-md: 16px;
--radius-lg: 24px;
--radius-pill: 999px;

--shadow-card: 0 18px 48px rgba(82, 42, 61, .09);
--shadow-cta: 0 16px 30px rgba(255, 79, 134, .24);
--shadow-float: 0 22px 60px rgba(54, 25, 38, .12);
```
