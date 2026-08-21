# selfit / selfit Product Interaction Plan

## 1. Product Frame

`selfit` is the unified product name. Use `selfit` only when a Chinese product name is needed.

The main product should combine three existing or planned atomic abilities:

- Closet-aware outfit recommendation.
- Color test from user-uploaded photo.
- Virtual try-on from outfit or single garment.

The first screen must be useful immediately. It should answer: "What can I wear today, and can I see whether it suits me?"

## 2. Home Information Architecture

### 2.1 Top Bar

Content:

- Left: `selfit`.
- Right: current city, temperature range, weather icon or short weather text.

Interaction:

- Tap weather area: opens city/weather permission or city switch sheet.
- If no city permission: show `选择城市` and a soft prompt in the recommendation card.

States:

- Ready: `24~29°C 南京市`.
- Locating: `正在获取天气`.
- Failed: `选择城市后推荐会更准`.

### 2.2 Today Recommendation

Purpose:

- Recommend one outfit combination from the user's closet based on city weather.
- This is the top module and the strongest visual signal.

Card content:

- Tag: `今日推荐`.
- Outfit title, such as `白日漫游`.
- Short reason: weather + occasion + comfort + color/style logic.
- Flat-lay outfit image with 2-5 items.
- Optional small carousel dots if multiple recommendations exist.

Primary interaction:

- Tap card body: open `Outfit Detail`.
- Swipe card horizontally: switch between today's candidate outfits.
- Long press or secondary icon: save/favorite.

Recommendation logic for MVP:

- Input: closet items, weather temperature, precipitation, user color test result if available.
- Output: outfit id, title, reason, item ids, weather tags.
- If closet is empty: show an upload-oriented empty card: `先添加几件常穿单品，我来帮你搭今天这一套`.

### 2.3 Activity / Widget Row

Purpose:

- Lightweight feature entry, not a marketing section.

First widget:

- `色彩测试`.
- Tap directly enters the photo upload step of the existing color test flow.
- Do not enter a separate color test landing page.

Other placeholder widgets:

- `AI穿搭师`.
- `单品入柜`.
- `鞋包搭配`.

Rules:

- Horizontal scroll.
- Each card uses image-led background or real feature asset.
- Keep labels short and non-technical.
- Do not include outfit calendar in this version.

### 2.4 Inspiration Outfits

Purpose:

- Browse and try recommended outfits in a Xiaohongshu-like two-column feed.

Card content:

- Outfit image.
- Optional title, reason, item count, favorite count.
- Small `试穿` action can remain visible.

Interaction:

- Tap card image: open outfit detail.
- Tap `试穿`: enter try-on directly with this outfit.
- Pull down from page top: refresh only the inspiration feed.

Refresh behavior:

- Show a small rose loading mark.
- Keep top bar, today recommendation, and widgets stable.
- Replace or append a new backend recommendation batch.
- If backend is unavailable, keep current cards and show `暂时没有新的灵感`.

## 3. Outfit Detail

Entry:

- Today recommendation card.
- Inspiration card.
- Saved outfit in closet.
- AI stylist recommendation.

Layout:

- Top: back, share.
- Hero: outfit flat-lay.
- Floating selected model preview.
- Action icons: favorite, save to closet/calendar later.
- Section: `穿搭单品`, horizontal item cards.
- Bottom fixed actions: `自由搭配` and `试穿`.

Interactions:

- Tap item card: open single item detail sheet.
- Tap model preview: switch model or upload self-photo.
- Tap `试穿`: generate try-on using the current outfit.
- Tap `自由搭配`: open free styling editor with current outfit preloaded.

MVP try-on rule:

- If the outfit has a supported top, use the existing top try-on pipeline with outfit context.
- If the outfit has no supported top, show: `这套搭配暂时没有可试穿上衣，可以先保存为搭配参考。`

## 4. Try-On Flow

Entry:

- Outfit detail `试穿`.
- Inspiration card `试穿`.
- Closet item `用于试穿`.

Default path:

1. Use selected model or previously uploaded self-photo.
2. Apply the outfit's supported garment directly.
3. Show generating overlay.
4. Show generated result as hero.

Generating state:

- Overlay copy: `正在生成试穿图`.
- Percentage can be shown if available.
- Button: `取消`.
- Background remains the selected model/result area, dimmed.

Success state:

- Generated image is the largest element.
- Actions: `保存`, `分享`, `换一套`, `重新生成`.
- Show outfit item strip below result.

Failure states:

- No model: `先选择模特或上传一张正面照，会更像你。`
- Unsupported outfit: `当前只支持上衣试穿，这套搭配已作为参考保存。`
- Image generation failed: `这次没有生成成功，可以换张更清楚的照片再试。`

## 5. Free Styling Editor

Entry:

- Outfit detail `自由搭配`.
- Closet tab floating `自由搭配`.
- Add item flow after uploading closet items.

Layout:

- Top bar: back, centered title `自由搭配`, right `保存`.
- Main canvas: light neutral board with current outfit items.
- Canvas action: `一键排版`.
- Bottom sheet: `添加单品`, category tabs, item grid.

Item editing:

- Drag to move.
- Pinch or handle to resize.
- Rotate handle.
- Delete button on selected item.
- Tap empty canvas clears selection.
- Layering follows clothing logic by default: outerwear above top, bottom below top, shoes low, accessories above.

Smart layout:

- Tap `一键排版` arranges items into clean flat-lay positions.
- Keep user's item set unchanged.
- Show a short toast: `已整理版面`.

Save behavior:

- Create a new outfit plan rather than overwriting the source outfit.
- Return to outfit detail for the new outfit.
- Toast: `已保存新的穿搭方案`.

Unsaved changes:

- Back with changes opens sheet: `保存这套搭配吗？`
- Actions: `保存`, `不保存`, `继续编辑`.

## 6. Color Test Integration

Entry:

- Home widget `色彩测试`.
- Profile can keep a secondary entry, but home widget is primary.

Landing behavior:

- Enter directly at upload step.
- Use the selfit warm light visual system.
- Do not show algorithm/debug content in the primary flow.

Upload step:

- Title: `上传一张自然光自拍`.
- Helper: `脸部清楚、少滤镜，结果会更准。`
- CTA: `开始色彩测试`.

Result use:

- Save user's color direction as styling preference.
- Use it in today recommendation reasons, such as `这套低饱和蓝白更贴近你的清爽冷调方向`.
- Let the user retake from the result page.

## 7. Navigation

Bottom tabs:

- `首页`.
- `AI`.
- Center `+`.
- `衣橱`.
- `我`.

Rules:

- Active tab uses soft rose fill/text.
- Center plus opens add sheet: upload single item, upload outfit image, paste link, camera.
- Main flows launched from cards can hide bottom nav when focus is needed, especially try-on and free styling.

## 8. Backend Contracts Needed Later

Home recommendation:

```json
{
  "city": "南京市",
  "weather": { "temperature_min": 24, "temperature_max": 29, "condition": "rain" },
  "today_recommendations": [
    {
      "outfit_id": "outfit_123",
      "title": "白日漫游",
      "reason": "纯白衬衫搭配伞裙，适合今天湿热小雨的城市通勤。",
      "item_ids": ["item_top", "item_skirt", "item_shoes"],
      "cover_path": "/tryon-outputs/outfits/outfit_123.png"
    }
  ]
}
```

Inspiration feed:

```json
{
  "cursor": "next_cursor",
  "cards": [
    {
      "outfit_id": "outfit_456",
      "title": "清爽浅蓝",
      "cover_path": "/tryon-outputs/outfits/outfit_456.png",
      "source": "recommended",
      "tryon_ready": true
    }
  ]
}
```

## 9. MVP Scope

Do now:

- Rename visible product name to `selfit` / `selfit`.
- Home: top bar, today recommendation, activity row, inspiration feed.
- Wire color test widget directly to upload.
- Outfit detail page from home/inspiration cards.
- Direct try-on from outfit using existing supported garment path.
- Free styling editor with add item, drag/scale/rotate/delete, one-click layout, save as new outfit.

Defer:

- Outfit calendar.
- Multi-day planning.
- Production-grade recommendation ranking.
- Full-body multi-garment try-on if the current model only supports tops.
- Social comments/community.
