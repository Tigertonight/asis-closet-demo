# selfit Design System

This file is the frontend source of truth for the consumer product in the Figma file `🪞 适我`.

## Public website — 2026-09-11

- The public website at `/docs` keeps its mobile reading flow and centered desktop layout. Use consistent side gutters, vertically stacked hero actions on phones, and a two-column personality grid; expand columns only when there is room.
- All website artwork scales proportionally. The hero uses its actual intrinsic dimensions with responsive width and automatic height. Personality cards use complete-image `contain` fitting; never stretch or crop the fused artwork to fill a card.
- Keep the primary test entry at least 44px tall, allow card captions to wrap, and offset section anchors below the sticky header. Verify narrow phones, 390–430px phones, tablets and desktop without horizontal overflow.

## Onboarding update — 2026-09-08

- “使用示例照片” submits a fixed sample ID; the server reads the bundled original and shares the normal photo-analysis/storage pipeline. Show a proportional lightweight WebP preview immediately with “正在分析示例照片…”, then offer “重新使用示例照片” on failure. Never download the full sample and upload it again. Cache actual sample analysis/overlays by original and algorithm/model fingerprint, with independent session records and manual corrections. Cancel pending selections when changing gender/photos; late responses cannot overwrite the current choice. Two accepted sample photos use a short 450ms reveal, while regular photo uploads retain the existing reveal timing (2026-09-13).

- Male report generation currently chooses only EASE, EDGE, MUTE and WABI, whose male materials are delivered. Primary/secondary matches and confidence use that same candidate set; female reports retain all 16. Expand the synchronized algorithm allowlist only after more male materials are ready. Historical reports remain snapshots and retesting uses the new scope (2026-09-12).
- Gender selections persist in the account profile and drive model selection, sample photos, report variants and white-T matches. “我的档案” includes a gender row opening a dedicated two-option editor, available before or after testing. Save updates the current recommendations without changing the personality score or deleting photos/history; keep the header free of an edit icon. Use rose selection and save states, a 44px minimum touch target, and visible save/error feedback.
- When a male personality template is not yet supplied, keep “去试穿” visible on the report. Open the normal mirror with four actual male-library outfits and the notice “这个型格的男生穿搭正在准备中，先试试男生穿搭参考。” This is explicitly labeled library content; do not present it as that personality's four original notes, and do not invent missing male templates. Broken existing deliveries still show retry states.
- Reports with neither a cover nor an illustration use a compact text header with a dark personality title and muted code. Remove the cover's reserved aspect ratio in this state so keywords, the content notice and available colors remain visible without a large blank area.

- Item and outfit cards do not show a decorative favorite-star corner badge. Preserve saved state and the existing favorite actions; mirror selection and pending indicators remain separate (user correction, 2026-09-10).

- Outfit and photo-note detail headers show only the back action and centered title; remove the duplicate favorite star. Keep the two existing favorite/try-on buttons in a stationary bottom row inside the app shell, with an opaque warm-white background across the full width and safe area and a short fade above it. Only detail content scrolls, with enough bottom space to reveal the last garment completely. Preserve content scroll when a favorite action rerenders the page.

- The mirror history icon opens a dedicated “试穿历史” page, with a 44px back button to the mirror and no bottom navigation. Use a warm light background, a two-column grid of rounded cards, complete-image fitting and the local creation date below each photo. Reuse the account history endpoint, newest first. Include loading, empty and retry states. Opening a card enters the large viewer; closing it returns to history, including after reload or browser back/forward.

The latest user corrections in this section supersede all older ordering, validation and layout rules below, including section 14:

- Theme-name pills on inspiration collection cards render at 70% of their previous size, anchored at the upper-left, with a light-gray background at 60% opacity. Keep the text opaque and the full card clickable (user correction, 2026-09-11).
- Flat inspiration notebook cards retain the same upper-left pill, showing the owning personality's Chinese name. The pill must not block opening the note (user correction, 2026-09-13).
- Keep the inspiration page on the shared default canvas, matching the other pages. Distinguish collection cards using a light warm-gray `#f0eceb` card background (user correction, 2026-09-11).
- Inspiration keeps only the four scene/trend collections (通勤场景、约会场景、度假场景、潮流趋势) in a two-column grid. Below them, flatten all personality collections into individual notebook cards in two columns, including curvy variants and supplied male outfits. Preserve notebook/outfit identities, favorite and direct try-on actions, deduplicate repeated outfit IDs, and load offscreen photos lazily. Do not repeat scene-only notes in this flat list. Each remaining collection keeps its cover, three previews and upper-left theme pill (user correction, 2026-09-13).
- Historical personality-collection links remain accessible with separate “微胖穿搭” and “男生穿搭” groups; the inspiration landing page no longer shows personality collection cards. Untested accounts still sample four notes for their gender on the mirror; tested accounts use the four notes of their latest report, preserving its template variant.
- The mirror's link icon opens the device-code dialog: title “绑定你的智能穿衣镜”, description “每日记录身材和穿搭”, and a single four-digit numeric input with placeholder “请输入设备码”. Preserve leading zeros and reject other characters. The separate history icon remains available after try-on.

- Initial entry includes login before onboarding; restore existing signed-in users, but do not treat a visitor session as completed login. Direct mirror entry retains isolated visitor support. Report actions stay visible and equally sized, with “保存并分享” and “去试穿”; no retake button.
- Journey: intro → **like → suit → vibe → report**. The suit screen is a single page with no separate result screen, but observation cards appear only after both the face and body photos pass detection; until then the area below the upload module stays completely empty (user correction, 2026-09-09).
- The main-site profile keeps the existing report cover and places “重新测试” inside the card, centered with a 12px bottom inset, using the same pill style as the untested profile's “去测试”. The cover still opens the saved report. Retesting starts a fresh onboarding session instead of redirecting to the existing report; previous reports remain available. The retest entry skips the splash pass entirely — it opens straight on like (falling back to the login screen only when the session is gone), jumps from like straight to vibe (skipping the suit step, because photos and features are editable on the archive page), and its stepper shows only the two like / vibe circles joined by one line (the suit step is hidden; like hides its back arrow as the first step). First-time onboarding keeps the full splash → intro → like → suit → vibe journey with the three-circle stepper.
- The profile header shows no edit icon for any state; its symmetric spacing keeps the title centered. The archive page's suit module matches the onboarding suit screen interactions: tapping either photo directly opens the file picker and replaces that photo in place (upload + refresh, no edit screen, no save step), and each suit feature card carries its own “修改” action opening the single-feature editor which saves immediately and returns to the archive. The archive suit data always reflects the account's latest state: photos resolve from the user's latest accepted photo index (never shadowed by the report-generating session's older photos), and a newly accepted upload clears the archive's stored manual choices for that photo's attributes — exactly like the onboarding suit screen — so the feature cards, labels and measurement rows update to the new photo's algorithm results immediately after a replacement.
- Report “去试穿” carries the four visible notebook IDs in order into the mirror. The delivered styling JSON maps each note and report template to its actual outfit and garment images, names, wearing instructions and layering order. Show the original note image and remove “示例搭配”; select the first by default and preserve later selections on refresh. Legacy report links without image identities resolve the same template/notebook IDs to the current delivered outfits, replace placeholder URL parameters with actual asset IDs without a success toast. Concrete mismatched IDs still fail. A missing mapping shows a retry state, never unrelated recommendations. See `docs/SELFIT_REPORT_OUTFITS.md`.
- Structured outfit try-on actions directly open the mirror loading state and submits every outfit item, without a piece-selection confirmation dialog. This entry uses `wear_all_items=true` so approximate photo-coverage checks do not remove shoes or other pieces from the generation reference. Missing photos still open model selection; failed generation retains the outfit and offers retry.
- Try-on failure dialogs keep the service's specific user-facing reason and suggested next action. Do not replace every failure with a request to change photos; retain the original photo/outfit and the retry action (2026-09-11).
- Photo-note “试穿” actions also submit directly and open the mirror loading state. Do not show the “试穿这张照片中的搭配” confirmation dialog or require a second “生成试穿图” click.
- Background try-on completion uses a compact light-gray pill with a 78% opaque background centered above the bottom navigation, with a small wine check icon, “试穿成功” and a muted chevron. Keep the 44px click target and the existing view-result action; remove the solid wine speech bubble and pointed tail.
- Fixed-model try-on of an unchanged delivered outfit reuses its verified published preset when available. Match the model image and complete notebook outfit, including its audience variant, and allow cutout-only asset updates. Show the existing mirror loading state for at least 3 seconds, preload the result, then display it with normal history/comparison actions. Personal photos, edited outfits, unavailable or failed presets retain live generation. A late preset result must not replace a newly selected outfit/model or navigate away from another screen.
- Switching the mirror model or choosing the user's own photo updates the preview without an “已选择…” success toast.
- The default female model is “匀称型” (`female_medium_1`). Use it when a fixed-model fallback is needed; keep an existing manual model or own-photo selection (user correction, 2026-09-11).
- Fixed models use a cached, proportional WebP preview (up to 960 × 1280) for display; preserve the full original for generation and downloads. Reveal the ready model while its notebook strip loads. If a slow image finishes after the retry state appears, recover automatically without requiring a page reload (2026-09-12).
- All raster artwork and material displays use WebP: reports, notes, garments, inspiration, models, results, history and photo previews. Bitmap-heavy SVG compositions are bundled as proportional transparent WebP; vector icons stay vector. Runtime images use a server cache (up to 1600 px per axis), preserving alpha and orientation. Authorize private files before every cache response; keep generation/download originals and material IDs unchanged. Explicit display URLs and Vary/ETag separate WebP from original responses (2026-09-13).
- Mirror image transfers show a slow-loading state after 20 seconds and keep accepting late success. Retry network/decode failures twice; manual retry reloads only the image and retains the outfit/job. Distinguish a failed result image from a failed model photo, and keep fixed-model display URLs after a job completes instead of switching to its full-size input copy (2026-09-13).
- Use the current account's `gender` returned with wardrobe preferences to select the model library. Male accounts default to the supplied “男标准型” model (`male_standard_1`), replacing the historical female default, including onboarding entry. Preserve an explicit own-photo choice or a saved model of the same gender. Female/unknown accounts retain the female library. Shared model images may use material IDs; keep local image copies out of Git.
- The mirror mode switch names its destination: “看单品” on the full-body model view and “全身镜” on the item styling view. Use the same text for the visible label and accessible name; retain the turn animation and selected outfit.
- Live mirror portraits (width/height ≤ 3/4) use the full available mirror height before and after try-on, including comparison. Scale proportionally, retain the complete vertical extent and clip excess width inside the arch. Wide or undecoded photos retain complete-image `contain` fitting. Hide the separate empty arch when a photo is shown and never expose a solid letterbox. A display-only preview may remove a confidently detected, uniform four-sided image border. Generated results may also have lightly textured, symmetric left/right or top/bottom white bands: trim only when both boundaries are sharp and nearly continuous, preserving the full extent on the other axis. Gradients, edge-touching subjects and uncertain borders retain the original pixels. Preview failure falls back to the original. Keep uploads, generation inputs, history and downloads unchanged. In-place completion displays the result directly without the “试穿图已经好了…” toast.
- The live large-photo viewer centers the complete photo with proportional `contain` sizing and 24px corners on the fitted image itself. Reuse the mirror's display-only border trim for model photos, results and history; fit the full trimmed preview without the mirror's horizontal clipping. Keep original files and download sources unchanged. Use the mirror's warm textile background without a baked-in white arch. Reserve a separate bottom row for the 44px “收起大图” action; it stays clear of the photo and inside the viewport on short screens. Current results, model photos and saved history use this same layout.
- The default mirror strip shows exactly four delivered notebook photos with their real outfit items. Accounts without a completed report get a random, distinct sample for their gender; keep it stable while navigating and resample on refresh, retaining the selected notebook. Accounts with a report get the four notes for their latest report's personality and template variant (including male/curvy), preserving report order. An unrelated selected outfit must not displace those four. Report handoff keeps its explicit four notes, and the personal wardrobe keeps its own outfits. Missing report content shows recovery copy instead of unrelated random notes (user correction, 2026-09-11).
- Mirror notebook cards show the translucent gray “试穿” pill in the lower-right. Only this visible button submits the notebook’s full outfit; use a 44px target with no invisible extension outside the button. Tapping the rest of the card opens the exact card image in a proportional large preview, preserving the selected outfit, current try-on result and scroll position. Image preview and try-on are separate sibling buttons. Keep the active/pending mark in the upper-left and retain horizontal swiping. The mirror has no separate upper-right “试穿这套搭配” action (user correction, 2026-09-10).
- Like palettes are optional; no selection is persisted as `null`, including clearing an earlier choice. Sliders remain adjustable.
- Below the like page title, show the muted-gray text link “先不测试，去 App 逛逛 →”. It opens the main mirror directly at `/selfit/try-on?screen=mirror` without requiring questionnaire completion.
- Like and suit actions sit in a full-width, opaque sticky footer that covers the bottom safe area. The footer participates in layout so the final options can scroll fully above it; do not use a button-shaped shadow as the content mask.
- Suit surfaces retain the original near-white canvas (`#fafafa`), white cards and neutral gray image wells/borders. The prototype informs layout and copy, not its beige background colors (user correction, 2026-09-08).
- Suit copy follows the supplied warm prototype: warm brown headings, muted brown helper text, photo-purpose subtitles, and a separate manual-entry heading/helper/action. “手动选择” and its arrow use the same muted brown as the adjacent helper text. The standalone entry blocks are removed (2026-09-09): neither “不想上传照片？” nor “想先看看效果？” appears on the suit screen, and the manual screen remains reachable only through each card's “修改” button, with its assets staying in place. Instead each upload slot ends with its own quiet “使用示例照片” text action (`data-sample-photo="face" / "body"`) that swaps just that photo — 面部照 or 全身照 — for a built-in sample (`app/static/selfit/assets/samples/face-sample.jpg` from `qa_photos/face/face_07.jpg`, `body-sample.jpg` from `qa_photos/body/body_10.jpg`) loaded through the normal upload pipeline, so visitors can mix their own photo with a sample on the other slot, experience the real analysis, and then edit skin/face/body via the same 修改 affordance.
- Suit explains why photos help. Keep each photo's upload/check status on the upload screen. Observation cards render only once both photos are accepted: the second acceptance plays a short inline “正在进行算法分析...” moment (breathing dots plus a soft scan light over the photos, about 2.6s), then all three cards appear together with a staggered entrance under a “从照片里认识到的你” heading, while the two photos shrink into centered compact thumbnails and the result section scrolls to the top of the viewport as the visual hero (user correction, 2026-09-09). Re-uploading either photo clears the cards and replays the same sequence. Each accepted photo still swaps its upload-card preview for the server-rendered analysis image so the lines are drawn directly on the uploaded photo — there is no separate analysis-photo gallery and no tap-to-zoom dialog. The bottom primary action “说说我想表达的风格 →” enters vibe and enables once every visible suit attribute has a value (photo or manual). The “身材比例” card stays hidden until a body photo is accepted or the user set it manually. A failed photo stays on the upload screen for retry. A failed summary request keeps the upload cards and shows a retry toast. Unknown attributes stay unknown and offer manual selection. No privacy footnote under the upload grid (user correction, 2026-09-09).
- Manual face/body illustrations in both editors, the splash artwork and the login personality collage use bundled lightweight WebP derivatives. Keep the PNG masters; preserve proportions and alpha, and do not upscale the small female illustrations (2026-09-13).
- Manual setup shows all three questions with compact single-row options per question. Single-feature edits use larger illustrations/swatches with centered wrapping: five choices use 3 + 2 (second row centered), six choices use 3 + 3. Keep content scrollable above the save action.
- Each observation opens only its corresponding manual selection group. Save returns to the result with updated server copy; cancel discards that edit. Explicit edits override photo inference. A newly accepted upload clears previous choices only for its own attributes (face/skin or body). Photo-inferred attributes carry no source caption on the result; manual choices display “由你选择” (suit result update, 2026-09-09: removed the “照片分析结果” caption, “通过/存疑” confidence badges, “也比较接近” runner-up row, “查看分析大图” action, and the “【脸型 肤色】/【身材比例】” caption prefixes).
- Report generation opens the report first. The report retains the fused personality cover, keywords, summary, five colors and recommendations, with warm spacing and readable editorial hierarchy. Its primary action enters the existing try-on mirror; share remains available. This supersedes the older automatic redirect after onboarding.
- The report's five color swatches share the available row width equally. Swatches shrink within their columns, and long names wrap; all five colors remain visible without horizontal clipping on mobile and in saved reports.
- Report loading chooses one of the four existing lace illustrations at random on each entry and keeps it throughout that load. Show the percentage above a cumulative text stack: 25 / 50 / 75 / 100 each adds its complete sentence immediately. Repeated progress does not duplicate rows; skipped milestones appear in order. Reset on a new load. Keep the signature clear of all four lines on short screens.
- Vibe uses the prototype's reflective copy. In question 3 the displayed order is Japanese, Korean, French, Chinese, Western; wire codes remain **A, B, E, D, C** to preserve the existing regional meaning. No persona weights, thresholds or centers change.
- Suit API: `GET /api/v1/selfit/sessions/{id}/suit`; edits use the existing `PATCH .../profile`; protected `GET .../photos/{kind}/preview` supplies an orientation-corrected, metadata-free WebP analysis image up to 1200px. Reuse backend face geometry / skin sampling and body proportion overlays; omit QA metrics. Cache derived assets separately and resolve history only for the same authenticated user. Never draw fictitious recognition landmarks.

- Show profile information and the saved report as soon as the profile data arrives. Load face and body previews concurrently with independent loading/retry states; update only the completed photo slot, preserving scroll position and feature edits. Late photo requests cannot overwrite a refreshed or replaced photo (user correction, 2026-09-11).

## Wardrobe item actions — 2026-09-09

- The “单品搭配” bottom actions read “收藏” on the left and “去试穿” on the right (user correction, 2026-09-11).
- The “单品搭配” result leads with a mixed flat-lay of the complete selected outfit: the user's white T (or other anchor garment) plus every retained notebook piece. Replace the old anchor-only hero. Use the shared garment layout in a 3:4 white card, preserve all silhouettes, and update the composition when a different suggested notebook is selected. The displayed pieces must match the saved/try-on item IDs (user correction, 2026-09-11).
- In “我的单品”, the “帮我搭配” pill asks AI to compare described notebook outfits and replace exactly one matching garment with the user's item. Show a loading state, then the complete editable outfit, source notebook and recommendation reason; save only when the user chooses to save. Keep accessory types distinct, preserve the other pieces and support up to 16 items without truncation. Failure offers retry; leaving the screen must not let a late result navigate back. Tapping the image does not open a dialog; retain names in accessible labels.
- Holding an item image for 500ms reveals its delete button. Scrolling, moving more than 10px, or cancelling the pointer cancels the hold. Release never deletes; a separate tap on the revealed control calls the existing item deletion endpoint. Dismiss controls when scrolling or tapping elsewhere. Desktop right-click and keyboard Shift+F10 expose the same control; Escape closes it.
- Keep all action targets at least 44px. While deleting, prevent duplicate requests; retain the item and allow retry on failure. Refresh wardrobe outfits after successful deletion, and preserve category-row scroll positions.

## Mirror reverse layout — 2026-09-09

- Crop transparent margins before measuring each cutout, including faint chain and frame edges. Preserve complete garment and accessory silhouettes with `contain` and a 1% inset in each assigned zone.
- Arrange by wearing position (latest user correction): fine necklaces, glasses and earrings occupy the upper part of the mirror; bags and wrist pieces sit below the upper garments, followed by lower garments, socks and shoes. Keep two clothing columns, with one or two upper pieces and at least one lower piece on the left when separates are available. Balance the clothing area and compact accessory groups within that structure.
- Default cutout envelope areas are outerwear/dress = 1, top/pants/skirt = 2/3, and shoes/bags/accessories = 2/9. Use a shared fit scale and maintain at least 0.6% separation between every pair of item bounds. Never crop or obscure an item to fit.
- Filename recognition checks dresses before generic skirt names, including Chinese “迷你裙”; unrecognized pieces ask for category confirmation. The mirror's display category does not change the source wardrobe item.
- Fine chains and frames retain low-alpha edges and receive a restrained display-only contrast enhancement. Give glasses/chains a legible minimum size when space allows, and cap rings/earrings so narrow or hollow outlines cannot become oversized. Category-zone containment takes priority over enlargement. Originals, downloads and generation inputs are unchanged.
- Earrings use a smaller display target: about 8% of mirror width by default, capped at 10% width and 6% height, including manual enlargement. Their outline must remain subordinate to the garments and other accessories.
- Fine accessories display directly on the mirror backing with no doodle or colored backdrop (latest user correction). Preserve their original metal color, subtle edge enhancement, current placement, size and 2% zone inset.
- Fill more of the mirror with the clothing: use the area from 4% to 96% of mirror width, a 2% column gap and a 95% lower boundary. Enlarge all ordinary items with the shared fit scale while preserving the separate upper accessory band and the small earring cap; use the extra space for larger silhouettes rather than extra spacing.
- Keep rows compact at the 0.6% zone gap instead of distributing spare height down each column. Adjacent fine accessories may share a row; upper accessories use up to three cells across. Align the clothing columns at the top; a column beginning with bags or wrist pieces starts below the upper garment in the other column. Give clothing more display area while keeping the visual weight balanced; never expand a hollow accessory to consume its row's empty area.
- Preserve each presentation slot, category zone and manual scale when its image changes. A different wardrobe item keeps its own actual item ID for try-on while inheriting the replaced presentation slot. Classification, scale and removal support undo/redo; changes to the item set may rebalance the columns.

## Default wardrobe update — 2026-09-09

Per user request, every first-time user receives one shared starter item: a white T-shirt. This replaces the previous three-item starter set and supersedes the empty-wardrobe rule below. Preserve previously saved items, personal uploads, edits and deletion choices; never regenerate a deleted default.

“我的单品” groups clothing into vertically stacked categories. Each nonempty category has a compact icon/title and a single horizontally scrollable row of image cards with item names. Hide empty categories and remove the category filter tabs. “我的单品 / 我的搭配” remain the top-level tabs, and outfit cards retain their existing grid.

## 1. Source of Truth

Use this priority when implementation details conflict:

1. Figma Ready for Dev frames and their inspected properties.
2. This `DESIGN.md`.
3. Existing product behavior and backend contracts.
4. Existing demo CSS and exploratory Figma frames.

Reference:

- Figma file: `7WvSROZhohAyvpEMfxZ3Dd`
- Current onboarding section: node `1079:3828` on `onboarding+mirror`; see section 14.
- Earlier Ready for Dev section: node `450:11872` (asset provenance and historical measurements).
- Base mobile frame: `393 × 852px`, frame radius `40px`

The visible wordmark is `selfit`; the Chinese product concept/file name is `适我`. Do not show `AS IS` or another legacy brand in the consumer UI unless the product owner explicitly changes the Figma source.

## 2. Product Idea

### Mirror-first delivery (2026-09-06)

The mirror's initial load waits only for the current model and visible notebook collection.
Fetch the report's exact outfits directly on report entry; fetch the six random notes on
normal entry. Preload the selected model image while outfit metadata is loading. Load
wardrobe and full inspiration data when their screens are opened, with local loading
and retry states. A saved fixed-model selection must not download the user's unused
full-body photo; retrieve the latest own photo when the model chooser needs it.

This flow replaces the legacy main App as the post-onboarding destination.
After onboarding completes, open `/selfit/try-on` directly. The mirror is the home;
retain its original mirror composition, model/free-styling controls, garment strip,
and decorative bottom navigation for the mirror, personal wardrobe, and inspiration library.
Only the legacy main App and its bottom tabs are removed from the delivery flow.
Do not replace the mirror's own navigation with a top bar or redesign its layout.
Load models from their existing master-data manifest. Prefer the user's saved photo;
when absent, show an explicitly labelled example model and offer photo upload.
Recommendations belong to the inspiration library and use the account's stored persona.
The wardrobe contains uploaded/favorited garments, favorited outfits, and outfits made
with personal garments. Trying a library outfit alone never means the user owns its pieces.
An empty wardrobe must remain empty. Recommendation failures never fall back to personal data.
Keep outfit details, favorites, garment upload, garment-led outfit creation, and try-on in
the mirror experience. The generated style report remains accessible from the mirror.

selfit helps a person understand their style before deciding what to wear.

> 个人风格 DNA = suit 你适合的 × like 你喜欢的 × vibe 你表达的

The primary journey is:

1. Splash: establish the `selfit / 适我` identity on the wine-red textile.
2. Login: choose phone verification or invitation-code login; restored sessions skip the login screens.
3. Onboarding: explain `suit / like / vibe`.
4. `suit`: first collect skin tone, face shape and body shape on `信息选择`, then show the portrait and full-body photo upload screen.
5. `like`: capture aesthetic preferences, style spectrums, and color combinations.
6. `vibe`: capture the way the user wants to present themselves.
7. Reveal: transition into the user's style result.
8. Discovery: browse a two-column visual outfit feed.
9. Action: try an outfit with the lightweight `试穿` action.

This is not a weather dashboard or a technical AI workflow. It should feel introspective, editorial, personal, and quietly romantic.

## 3. Visual Direction

- Warm off-white canvas with generous negative space.
- Deep wine red as the single brand/action color.
- Editorial black and soft gray typography.
- Vintage lace frames, mirrors, paper cards, and tactile textile imagery as recurring motifs.
- Real fashion photography and flat-lay outfit images carry most of the visual density.
- Deep wine full-screen surfaces are reserved for the opening identity frame, narrative transitions, and reveal moments.

Avoid:

- Legacy rose `#ff4f86` as the primary CTA.
- Blue/lilac ambient gradients as a default surface.
- Heavy shadows on every card.
- Dashboard cards, weather-first home modules, or technical pipeline panels.
- Decorative UI that competes with photos or the `suit / like / vibe` motif.

## 4. Color Tokens

Verified Figma values take precedence over approximations.

```css
:root {
  --color-canvas: #fafafa;
  --color-surface: #ffffff;
  --color-brand: #8a011b;
  --color-brand-pressed: #720015;
  --color-text: #222222;
  --color-text-secondary: #666666;
  --color-text-muted: #999999;
  --color-line: #e7e7e7;
  --color-control: #b8b8b8;
  --color-scrim: rgba(0, 0, 0, 0.42);
  --color-shadow: rgba(0, 0, 0, 0.06);
}
```

Verified:

- Base frame background: `#FAFAFA` (`Backgrounds/Bg0Lighter`).
- Onboarding title bar background: `#F5F5F5` (`Bg0`).
- Primary button fill: `#8A011B`.
- White translucent decorative group: `#FFFFFF` at `10%` opacity.
- An observed decorative gradient `#F8FFFE → #5DE3CC → #F8FFFE` is asset-specific, not a global product gradient.

Use wine red for the wordmark, primary CTA, active assessment step, important plus controls, and selected states. Use full wine-red screens only for the opening identity frame and reveal sequence.

## 5. Typography

- UI and Chinese copy: `-apple-system, BlinkMacSystemFont, "PingFang SC", "Helvetica Neue", sans-serif`.
- `selfit` wordmark: use the exported Figma asset. A high-contrast serif is only a temporary fallback.
- Handwritten `suit / like / vibe`: use exported artwork; do not imitate it with a generic font.

Use the Figma semantic type variables rather than hand-entered approximations:

| Role | Figma token | Verified style |
|---|---|---|
| Main/screen title | `Title/T1` | `18px / 26px`, Semibold, `#000000` at 80% |
| CTA label | `Title/T3` | Figma token source; implemented at the product-governed `14px / 20px`, Medium, white, centered |
| Result/progress line | `Body/B1` | Regular, `#000000` at 80% |
| Onboarding formula | `Body/B2 Loose` | `15px / 26px`, Regular, `#000000` at 80% |
| Helper/description | `Body/B2 Loose` | Regular, `#000000` at 45% |

Frontend type-size governance:

- Consumer-facing helper copy, option labels, validation feedback, secondary actions, and compact body copy use `14px` as the minimum default size.
- The report and share surfaces may use `12px` only for metadata, captions, badges, authors, and other tertiary information.
- Do not introduce `8–13px` one-off body text outside the report/share surfaces. Icons and purely decorative glyphs are exempt.

The numeric onboarding values above were measured from the rendered Figma variable styles. For future screens, resolve unresolved family, size, line-height, paragraph spacing, and letter spacing from the Figma variables before implementation.

Copy is restrained and reflective. Prefer:

- `先认识自己，再决定怎么穿`
- `风格不是你穿了什么，而是你整个人呈现的样子。`
- `选择你更喜欢的`
- `看见你本来的样子`

## 6. Layout System

- Design viewport: `393 × 852px`.
- Product is mobile-first; desktop centers the mobile surface and must not expand into a dashboard.
- Do not render simulated time, signal, or battery chrome. The browser/device owns those elements.
- On onboarding form screens, reserve the latest Figma top inset with `max(54px, env(safe-area-inset-top))`. The shared back/step row begins after this inset; do not add the inset a second time on devices with a native safe area.
- Main text blocks are `329px` wide with `32px` horizontal margins.
- The primary CTA is `313px` wide with `40px` horizontal margins.

```css
--space-1: 4px;
--space-2: 8px;
--space-3: 12px;
--space-4: 16px;
--space-5: 24px;
--space-6: 32px;
--space-page-text: 32px;
--space-page-action: 40px;

--radius-control: 18px;
--radius-card: 12px;
--radius-media: 8px;
--radius-device: 40px;
--shadow-soft: 0 5px 24px rgba(0, 0, 0, 0.06);
```

Use measured Figma positions before generic tokens. Do not turn every control into a `999px` pill; the verified CTA uses an `18px` radius at `44px` height.

## 7. Core Components

### Primary CTA

- Width: `313px`.
- Height: `44px`.
- Left/right margin: `40px` on a `393px` frame.
- Radius: `18px`.
- Fill: `#8A011B`.
- Padding: `12px 60px`.
- Text: white and centered.
- Label box observed in onboarding: `193 × 20px`, `Title/T3`, Medium; runtime label size follows the product-governed `14px / 20px` minimum.
- States: default, pressed, disabled, loading.

### Title and helper blocks

- Onboarding title `先认识自己，再决定怎么穿`: `329 × 26px`, left `32px`, top `157px`, `Title/T1`.
- Photo-upload title `上传一张面部照和全身照`: `329 × 26px`, `Title/T1`.
- Upload helper `数据仅用于本地处理，方便 selfit 为你量身定制`: `329 × 22px`, `Body/B2 Loose`, `#000000` at 45%.

### Assessment stepper

- Three connected steps: `suit`, `like`, `vibe`.
- The back control and progress track share one `393 × 46px` top row after the `54px` onboarding top inset. Within that row, the visible `20px` back icon begins at `(32,13)` while its accessible hit area remains at least `44px`; the stepper begins at `(64,4)` (absolute frame position `(64,58)`).
- The latest Ready for Dev stepper is `265 × 38px`; the three `35px` step cells begin at `0 / 115 / 230px`, with `102.5px` connector segments at `y=7px`.
- The current step and completed steps/connectors use wine red; future steps and connectors use pale gray.
- Active marker is outlined, not a large filled badge.
- Labels sit `4px` below their markers; current and completed labels use wine red, while future labels remain pale gray.

### `suit / like / vibe` cards

- Use the exported lace-frame artwork and the dedicated 2× Figma PNG exports for `suit / like / vibe`; do not substitute a system font or upscale a lower-resolution cut.
- The onboarding reference card artwork includes the blue shoe, embroidered star, and cherry elements; these are part of the cards and must not be omitted.
- Onboarding animates from separated cards to an overlapping composition.
- Do not redraw the lace border with an unrelated CSS border.

### Opening splash

- The splash is the first rendered product screen; do not place a simulated iOS status bar above it.
- Fill the entire `393 × 852px` shell with the deep wine textile. The verified base red is `#8A011B`.
- Center the white serif `selfit` wordmark at approximately `38.2%` of the frame height, surrounded by a loose ring of small cyan, coral, pink, mint, cream, and white stars.
- Center `适我` near the bottom in `Songti SC Light` (`300`, `20px / 28px`, `.08em` tracking), with a nominal `55px` bottom inset plus the real device safe area.
- Hold the frame for `1800ms`, then cross-fade to onboarding over `420ms`. A tap/click may advance early.
- Under `prefers-reduced-motion`, avoid the cross-fade and advance after a shorter `900ms` identity hold.
- The textile is a distinct background asset; the wordmark, stars, and Chinese name remain separate UI layers for sharp rendering and responsive placement.

### Mirror opening screen

- The mirror/kiosk route owns the full proposition screen: `适我，不适众`, `1 分钟，找到真正衬你的颜色与穿搭风格`, the `开始风格测试` camera CTA, embroidered ornament, and `everyone has a code.` signature.
- These proposition elements do not appear on the onboarding splash; onboarding keeps the timed identity-only frame described above.

### Onboarding measured layout

The table below records the earlier `450:11872` layout. It is retained for asset provenance; section 14 supersedes its title, DNA, and card coordinates. All positions are absolute coordinates in the `393 × 852px` base frame.

| Element | Figma node | Position / size | Style |
|---|---|---|---|
| Title bar | `标题栏` component | `0, 0`; `393 × 56px`; padding `10px 16px` | `#F5F5F5`, horizontal auto layout |
| Wordmark | `_图层_1` | centered at `169, 13`; `55 × 20px` | exported artwork |
| Title | `110:20492` | `32, 96`; `329 × 26px` | `Title/T1`, `18/26`, Semibold |
| DNA copy group | `2134052794` | `34, 154`; `333 × 59px`; row gap `8px` | `Body/B2 Loose`, `15/26` |
| Primary CTA | `110:20509` | `40, 736`; `313 × 44px` | radius `18px`, `#8A011B` |
| CTA label | `110:20510` | `193 × 20px` centered | `Title/T3`, `12/20`, Medium |

Card positions use the normalized exported `102 × 151px` artwork. The source layers are rotated `-90°`; the shipped PNGs are normalized upright.

In the composed state, each lace/image layer is exactly `50%` opacity while the `suit / like / vibe` text layer remains `100%`. Treat the artwork and word as separate layers; never apply `opacity: .5` to the entire card container.

### Login extension

- The splash transitions to the login-choice screen when no valid auth session is restored; authenticated users continue directly to `intro`.
- Login choice uses the centered `selfit` wordmark, `适我，不适众`, the provided `Fit yourself, not in.` line, and the paired bottom actions `邀请码登录 / 手机号登录`.
- The Figma phone-login reference uses an `+86` prefix, an 11-digit mobile number and a verification code. The current main-site product uses direct phone login; the September 8 onboarding layout update preserves that existing authentication contract. Do not enable SMS or expose invitation login solely to match a static reference.
- Invitation login uses one invitation-code field and the same bottom CTA. The production endpoint remains `/auth/invite/verify`; until its backend capability is delivered, only the explicit frontend mock mode may complete this path.
- Auth tokens live in `sessionStorage`, are restored through `/auth/me`, and are attached as Bearer credentials to live onboarding calls. Onboarding session storage is scoped to the authenticated user ID.
- The login-choice curved tagline and button ornament use the supplied design crops at their 2× source density. The Figma View-seat MCP quota still blocks direct binary export; replace these two isolated image assets with the corresponding Figma exports when access is restored, without changing their layout boxes.

| Card | Separated state `(x, y, rotation)` | Composed state `(x, y, rotation)` | z-index |
|---|---|---|---|
| `suit` | `30.02, 280.49, 0°` | `144.42, 247, 0°` | 1 |
| `like` | `149.34, 278.45, 0°` | `104, 320.45, 7.88°` | 3 |
| `vibe` | `265.06, 280.49, 0°` | `167, 292.45, -11.01°` | 2 |

### Photo upload

- Two explicit inputs: `面部照` and `全身照`.
- White `166 × 203px` rounded placeholders with pale-gray explanatory silhouettes and a wine circular plus control centered above the silhouette.
- The face placeholder uses a broad front-facing head-and-shoulders bust; the body placeholder uses a narrow standing full-body figure. These are instructional background assets, not generic empty boxes.
- Placeholder silhouettes disappear completely when a selected photo preview is rendered.
- Helper copy explains local processing and why photos are needed.
- Preview immediately after selection.
- States: empty, selected, checking, invalid, permission denied, retry.

### Preference controls

- Spectrum sliders use two semantic endpoints, such as `利落` and `柔和`.
- Track is neutral gray; thumb is compact, white, and rounded.
- Color choices are composed palettes, not isolated technical swatches.
- Selected palette uses a restrained wine outline.

### Inspiration feed

- Two-column masonry/grid with narrow gutters.
- Mix full-person photography and outfit flat-lays.
- Images dominate and card chrome is minimal.
- `试穿` is a small translucent action in the image's lower-right.
- Video cards may show a compact circular play marker.
- A small decorative star may mark a highlight; do not use it everywhere.

### Reveal screen

- Full deep wine-red textile background.
- Centered exported lace/mirror artwork.
- A short line such as `看见你本来的样子` sits near the lower hero.
- This is a transition, not the default app background.

### Recognition/progress screen

- The mirror/kiosk canvas uses the latest approved `393 × 746px` proportion. The full wine-textile frame contains the white `selfit` wordmark at `40px` from the top, narrative and progress around `229px`, and the exported blue arced `Know yourself first.` signature `32px` above the bottom edge. The signature baseline is curved artwork, not a straight text line rotated with CSS.
- The latest loading reference does not show the mirror-opening embroidered ornament. Keep that ornament on the opening proposition screen only.
- Observed sequence/copy:
  - `看见你本来的样子` — `25%`
  - `你不需要成为谁` — `50%`
  - `只需要更准确地做自己` — `75%`
- The completed job remains on the third frame briefly before the report opens; it does not introduce a fourth narrative sentence.
- This state must express staged recognition, not a generic spinner.

## 8. Motion

Verified onboarding motion:

- Smart Animate equivalent.
- Duration: `600ms`.
- Easing: ease-out.
- Separated state holds for `1600ms`, then animates to composed.
- Composed state holds for `800ms`, then animates back.
- The complete loop is `3600ms` (`1600 + 600 + 800 + 600`).

Recreate card arrangement with transforms and opacity, not unrelated screenshots. Provide `prefers-reduced-motion` behavior that shows the final composition immediately. Routine page transitions stay shorter (`180-280ms`).

## 9. Product States and Copy

Every interactive page defines initial, active/editing, loading/checking, success, recoverable failure, and blocking failure states.

Technical terms such as `mask`, `pipeline`, `provider`, `JSON`, and `confidence` stay out of the consumer flow. Failure copy describes the next useful action.

### Complete onboarding state matrix

The current Figma `onboarding` group (`1079:3828`, `6734 × 5573px`) is the visual reference for the complete sequence; retain the explicit product exceptions in section 14:

1. `splash`: timed textile identity frame with the centered `selfit` star halo and `适我` near the bottom; tap may advance early.
2. `login / phone-login / invite-login`: login choice and the two credential paths, including validation, sending, pending, failure, and restored-session states.
3. `intro`: separated and composed lace-card states.
4. `suit`: `信息选择` comes first; its Next action saves the choices and opens photo upload. Upload supports empty, checking, one-photo valid, both valid and insufficient-light states. Users who cannot upload may continue with their previously saved choices.
5. `like`: three continuous axes — `硬朗锐利 / 柔和温柔`, `简约克制 / 精致繁复`, `经典耐看 / 时髦先锋` — plus six composed palettes. The CTA stays disabled until a palette is selected.
6. `vibe`: title `最后一步，了解你想表达的` and three single-choice questions. The CTA reads `下一步` while disabled; once every question has an answer it becomes enabled and reads `生成风格报告`.
7. `loading`: the onboarding/report-generation loading sequence is four wine-textile stages at `25 / 50 / 75 / 100%`: `先看见真实的你`, `寻找你同频的灵感`, `拼出更像你的样子`, and `我们认识你了...`. The current artwork is, respectively, `薰衣草+花拱+蓝鞋`, `戒指+画作+咖啡`, `樱桃+蛋糕+绿包`, and the `selfit` wordmark. Each stage uses its direct 2× Figma export and transitions over `300ms` with an ease-out cross-fade. The latest `450:11872` matrix uses the dark-wine, three-line embroidered `Fit / yourself / not in` artwork centered near the bottom throughout all four stages.

The mirror route owns a separate three-stage recognition sequence at `25 / 50 / 75%`: `看见你本来的样子`, `你不需要成为谁`, and `只需要更准确地做自己`. Its bottom branding is the exported blue curved `Know yourself first.` signature plus stage-specific ornament artwork. Never reuse the mirror copy, blue signature, or mirror-opening ornament inside onboarding loading; never reuse the onboarding lace cards or embroidered three-line brandmark inside mirror loading; and never replace the mirror sequence with the generic `正在分析中` label.
8. `report`: the `450:13461` editorial long page — style cover, identity summary, five rounded-square recommended colors, two-column makeup/hair references, outfit analysis and four-card visual recommendations, a pale-pink bordered interpretation list, centered lace `selfit` signoff with multicolor dots, and the paired actions `返回重测 / 保存并分享`.
9. `share`: full-height report sharing layer with `保存单张 / 发笔记 / 微信好友 / 朋友圈` actions.

The share layer uses a real three-card carousel: style summary, recommended colors, and visual inspiration. Adjacent cards remain partially visible as a swipe affordance. Touch/trackpad scrolling uses horizontal scroll snap; pagination dots, `ArrowLeft / ArrowRight`, `Home`, and `End` provide equivalent direct navigation. The active dot and live `第 n 张，共 3 张` status always follow native swiping.

The current sequence is `intro → suit-manual → suit → like`; report generation must never require debug data or expose technical pipeline language.

The `vibe` questionnaire scrolls inside the `361px`-wide content panel beginning at `y=137px`; its title starts at `y=157px` and the first question at `y=221px`. Options are content-width pills with a fixed `42px` height and `16px` vertical gaps. The CTA remains in a `114px` bottom gradient dock, disabled until every question has an answer. At maximum scroll, the final `E` option must sit completely above the CTA; touch scrolling and keyboard focus must never leave an answer hidden beneath the dock.

The current report reference (`1079:6764`) shows the paired actions on the first viewport, docked above the bottom safe area. `返回重测` returns to `vibe` with existing answers intact; `保存并分享` opens the share layer. Empty reports and public shared reports do not expose these owner actions. Hidden screens and actions must not remain keyboard-focusable or intercept pointer input.

The report keeps a visible, sticky top navigation bar with a `44 × 44px` back target and centered `风格报告` label. Back returns to `vibe`, preserving the user's existing questionnaire selections so they can revise an answer and generate the report again.

## 10. Asset Rules

- Export and reuse the wordmark, `suit / like / vibe` artwork, lace frames, mirror/apple illustration, and textile backgrounds. Signature text artwork uses direct Figma exports rather than system-font recreation.
- Prefer SVG for line art/wordmarks and WebP/AVIF for photos; keep PNG only when alpha detail requires it.
- Raster exports must ship at a minimum of `2×` their intended CSS dimensions. Keep CSS width/height at the design size; the filename uses `@2x` (or a higher-density suffix such as `@4x`) to make density explicit.
- Maintain an asset manifest mapping Figma node/purpose to shipped filename.
- Never approximate signature artwork with emoji or a random icon library.
- Product photos use `object-fit: cover`; garment flat-lays and upload inspection use `contain`.

Onboarding asset manifest:

| Figma artwork | Shipped file | Intrinsic size |
|---|---|---|
| `_图层_1` wordmark | `app/static/selfit/assets/selfit-wordmark.svg` | Figma-exported vector, rendered at `55 × 20px` |
| Shared lace card | `app/static/selfit/assets/lace-card@4x.png` | `408 × 604px` RGBA, rendered at `102 × 151px` |
| `suit / like / vibe` card bases | `app/static/selfit/assets/{suit,like,vibe}-card-base@2x.png` | Three Figma-derived `204 × 302px` RGBA exports containing the complete lace frame and shoe/star/cherry artwork; rendered at `102 × 151px` |
| `suit` overlay | `app/static/selfit/assets/suit-word@2x.png` | Direct Figma 2× PNG, `96 × 45px`, rendered at `48 × 22.5px` |
| `like` overlay | `app/static/selfit/assets/like-word@2x.png` | Direct Figma 2× PNG, `78 × 41px`, rendered at `39 × 20.5px` |
| `vibe` overlay | `app/static/selfit/assets/vibe-word@2x.png` | Direct Figma 2× PNG, `95 × 50px`, rendered at `47.5 × 25px` |
| Opening textile derived from the approved splash reference | `app/static/selfit/assets/splash-textile@2x.png` | `786 × 1704px` RGB, rendered at `393 × 852px` |
| Face upload instructional silhouette | `app/static/selfit/assets/face-upload-guide@4x.png` | Direct Figma Vectorized export, `520 × 634px` RGBA, rendered at approximately `128 × 158px` |
| Full-body upload instructional silhouette | `app/static/selfit/assets/body-upload-guide@4x.png` | Direct Figma Vectorized export, `424 × 634px` RGBA, rendered at approximately `105 × 158px` |
| Face-shape comparison strip | `app/static/selfit/assets/face-shapes-guide.png` | `368 × 110px` RGB |
| Manual face-shape options (5) | `app/static/selfit/assets/manual-selection/face-*@4x.png` | Direct 4× exports from the latest `image 5793` crop layers in node `746:5409`; `156 × 240px`, rendered at `39 × 60px` inside `59 × 80px` cards |
| Manual full-body shape options (5) | `app/static/selfit/assets/manual-selection/body-*@4x.png` | Direct 4× exports from the latest `image 5805` crop layers in node `746:5409`; `144 × 408px`, rendered at `36 × 102px` inside `60 × 122px` cards |
| Mirror opening composition | `app/static/selfit/assets/mirror-home-manifesto@2x.png` | `452 × 340px` RGBA design composite, rendered at `226 × 170px`; includes the ornament and the true arced `everyone has a code.` artwork |
| Mirror ornament source | `app/static/selfit/assets/mirror-loading-ornament@2x.png` | `300 × 340px` RGBA source export retained for asset provenance; runtime uses the corrected home composition above |
| Mirror recognition signature | `app/static/selfit/assets/mirror-signature-know-yourself@2x.png` | `452 × 140px` RGBA design export, rendered at `226 × 70px`; preserves the curved baseline |
| Onboarding loading stages | `app/static/selfit/assets/loading-stage-{25,50,75,100}@2x.png` | Four direct 2× Figma lace illustrations: `480×324`, `480×325`, `492×332`, `480×325px`; rendered at their measured `240×162`, `240×162.1`, `246×166`, `240×162.1px` sizes |
| Opening/onboarding loading signature | `app/static/selfit/assets/splash-signature@2x.png` | Latest Ready for Dev dark-wine stacked `Fit yourself not in` artwork, rendered at approximately `103 × 66px` on splash/loading |
| Superseded onboarding loading brandmark | `app/static/selfit/assets/onboarding-loading-signature@2x.png` | Older `Know yourself first` crop retained for provenance; not used by the latest `450:11872` runtime |
| Camera CTA icon | `app/static/selfit/assets/icon-camera.svg` | Original `24 × 24px` vector retained from the approved mirror design implementation; rendered at `30 × 30px` on the mirror opening CTA |
| Share: save | `app/static/selfit/assets/iconfont-share/icon-save.svg` | Iconfont ID `4880421`, monochrome SVG |
| Share: Xiaohongshu note | `app/static/selfit/assets/iconfont-share/icon-xiaohongshu.svg` | Iconfont ID `47505733`, monochrome SVG |
| Share: WeChat friend | `app/static/selfit/assets/iconfont-share/icon-wechat.svg` | Iconfont ID `11372717`, monochrome SVG |
| Share: WeChat Moments | `app/static/selfit/assets/iconfont-share/icon-moments.svg` | Iconfont ID `77151`, monochrome SVG |
| Report style illustration | `app/static/selfit/assets/report-style-soft-cool@4x.png` | Fallback/dynamic report illustration rendered inside the `188 × 180px` cover artwork area; Figma report node `450:13461` |
| `造梦浪漫型人 / LACE` cover | `app/static/selfit/assets/personality/lace-hero.png` | Fused hero artwork: the Chinese/English title, safety pin, central illustration and signature are rendered as one image; the UI must not crop or redraw its parts |
| Report makeup references | `app/static/selfit/assets/figma-report/makeup-01@2x.png` … `makeup-04@2x.png` | Two-column cards; default report uses two images; Figma report node `450:13461` |
| Report hairstyle references | `app/static/selfit/assets/figma-report/hair-01@2x.png` … `hair-04@2x.png` | Two-column cards; default report uses two images; Figma report node `450:13461` |
| Report outfit references | `app/static/selfit/assets/figma-report/outfit-01@2x.png` … `outfit-03@2x.png` | `220 × 292px` source exports rendered in the two-column feed; Figma report node `450:13461` |
| 16-personality recommendation library | `app/static/selfit/assets/personality/{typeId}/` | Per type: original color card, two makeup WebPs, two hairstyle WebPs, four outfit WebPs, plus a full-image Hero placeholder until the final fused Hero is delivered |
| 16-personality template catalog | `app/static/selfit/data/personality-report-templates.v1.json` | Stores all 112 sampled sRGB colors and recommendation metadata; runtime intentionally renders the first five colors only |
| Share-card QR artwork | `app/static/selfit/assets/mirror-report-qr.png` | Rendered at `28 × 28px` in the report card footer; Figma share node `450:16203` |

Share action icons render at `22 × 22px` inside a `44 × 44px` white circular surface. They use the onboarding wine red `#8A011B`; labels remain outside the icon surface, and text glyphs or emoji must not substitute for the SVG artwork.

The report is data-driven: the default data reproduces the approved Figma report, while a backend response containing a stable `typeId` resolves one of the 16 local templates and may overlay personalized copy. Each personality Hero is one fused image containing its Chinese/English identity and illustration; the UI must not redraw those elements. All sampled colors remain in the catalog for provenance, while report and share surfaces render only the first five. Empty optional modules are hidden and missing assets use explicit placeholders instead of unrelated sample content. The integration contract lives in `docs/SELFIT_REPORT_DATA_CONTRACT.md`.

### Onboarding integration boundaries

- `selfit-api.js` is the only onboarding module allowed to call the backend. Screen components consume normalized domain responses and must not depend on analyzer, model-provider, storage, or queue payloads.
- The browser may perform immediate MIME/type/size preflight, derive button enabled states, map job progress to the four Figma loading frames, and control the report/share carousel. These are presentation decisions, not analysis results.
- The latest `suit / like / vibe` stepper is `265px` while the primary action remains `313px`. Share carousel cards use a binary focus treatment: current card at full opacity and adjacent cards at `40%`, without edge gradients; the three 6px pagination dots retain 20px tap targets.
- The backend is authoritative for photo usability, normalized suit/like/vibe data, style calculation, report recommendations, generated share assets, and outfit-request lifecycle.
- The onboarding flow owns one resumable session ID. Browser storage may retain only the opaque session ID and expiry; photos, inferred attributes, reports, and signed asset URLs must not be persisted in `localStorage`.
- Report generation is asynchronous (`queued → processing → completed | failed`). The UI polls the normalized report-job resource and never simulates completion when live mode is enabled.
- The complete API and error contract is defined in `docs/SELFIT_BACKEND_INTEGRATION.md`; the report payload itself remains defined in `docs/SELFIT_REPORT_DATA_CONTRACT.md`.

## 11. Responsive and Accessibility

- Validate at 390, 393, 430, 768, and desktop widths.
- Above 430px, center the mobile surface on a neutral outer canvas.
- No horizontal overflow.
- On viewports shorter than the `393 × 852` design frame, the app shell matches the visible viewport and each screen scrolls internally. Bottom actions must stay inside that screen: later-flow actions use in-page sticky positioning, while overlay dialogs become vertically scrollable before an action can be clipped.
- Touch targets are at least `44px` even when the visible icon is smaller.
- Use semantic buttons/form labels, keyboard access, and visible focus states.
- Body text and controls meet WCAG AA contrast.

## 12. Implementation Self-Test

- Screen matches the `393 × 852` composition at pixel-review scale.
- The first frame is the wine textile splash, contains no simulated status bar, and advances into onboarding.
- Visible brand is `selfit`; no `AS IS` or other legacy copy leaks into the consumer UI.
- Base CTA is `313 × 44`, `#8A011B`, radius `18px`.
- `suit / like / vibe` stepper and artwork match the Figma hierarchy.
- Onboarding respects `600ms` ease-out motion and reduced-motion fallback.
- Upload, questionnaire, reveal, feed, and try-on have loading/recovery copy.
- Feed imagery remains dominant and `试穿` stays secondary.
- Desktop centers the mobile surface instead of creating a dashboard.
- No overflow, clipped CTA, overlapping text, or bottom-navigation collision.
- Browser console has no broken resource or runtime errors.
- Signature artwork is exported from Figma rather than approximated.

## 13. Known Design Gaps

The Figma file mixes Ready for Dev work and exploratory/reference sections. Do not silently promote exploration frames to production requirements.

Confirm before later phases:

- Final copy and data model for `vibe`.
- Exact style-result page and persistence model.
- Final bottom-navigation destinations and labels.
- Whether profile, closet, AI chat, and free-styling explorations remain in MVP scope.
- Final exported font/wordmark licensing and asset formats.


## 14. Onboarding refresh (2026-09-08)

Use section `1079:3828` on `onboarding+mirror` for this refresh. The inspected
intro frames are `1079:5454` / `1079:5505`, the questionnaire frames are
`1079:5867` / `1079:5954`, and the current report is `1079:6764`.
These take precedence over the historical onboarding measurements above.

- At `393 × 852`, the intro title begins at `y=157`, DNA copy at `y=211`,
  and its `313 × 44` CTA at `(40,736)`. Reuse the existing exported lace-card
  artwork and 600ms motion. Current composed card positions are suit `y=338`,
  like `y=405`, and vibe `y=389`; the separated cards begin around `y=383`.
- The shared stepper stays above the forms. Suit, manual, like, and vibe titles
  begin at `y=157`. Taking the shared navigation out of normal document flow
  must not pull these titles upward by its 46px height.
- Suit and like content scroll independently between the navigation and bottom
  actions. The photo frames retain the current `128:160` aspect ratio. Photo
  guidance and errors wrap; they must not cover the manual-entry or Next buttons.
- Like has three labelled keyboard-accessible sliders and six named palette
  buttons with explicit selected states. A palette is required to continue.
- Per the user's requested order, `去认识自己` opens `信息选择`; saving the
  three choices opens photo upload, then Next opens like. Back follows the
  same sequence in reverse and retains choices and photos. The photo-page
  `不方便拍照？跳过` action continues with the already saved information.
- Photo replacement cancels the previous validation. Late responses cannot
  overwrite the latest photo; cancelling the chooser preserves the current
  selection, and selecting the same rejected file again supports retry.
- Desktop centers a mobile shell no taller than the available viewport minus
  48px, using the existing `--visual-viewport-height` compatibility value shared
  with the WebView viewport adapter.
  Short screens scroll their form content and keep actions visible.
- Preserve the current phone-login contract, 16-personality calculation and
  report data. Figma's LACE illustration is a visual example, not a replacement
  personality definition. The web share sheet retains its working share-link
  and save-image actions rather than displaying unsupported native channels.

The before/after differences, browser checks and deployment scope are recorded
in `docs/SELFIT_ONBOARDING_FIGMA_DIFF_2026-09-08.md`.
