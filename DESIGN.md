# selfit Design System

This file is the frontend source of truth for the consumer product in the Figma file `🪞 适我`.

## 1. Source of Truth

Use this priority when implementation details conflict:

1. Figma Ready for Dev frames and their inspected properties.
2. This `DESIGN.md`.
3. Existing product behavior and backend contracts.
4. Existing demo CSS and exploratory Figma frames.

Reference:

- Figma file: `7WvSROZhohAyvpEMfxZ3Dd`
- Ready for Dev section: node `450:11872`
- Base mobile frame: `393 × 852px`, frame radius `40px`

The visible wordmark is `selfit`; the Chinese product concept/file name is `适我`. Do not show `AS IS` or another legacy brand in the consumer UI unless the product owner explicitly changes the Figma source.

## 2. Product Idea

selfit helps a person understand their style before deciding what to wear.

> 个人风格 DNA = suit 你适合的 × like 你喜欢的 × vibe 你表达的

The primary journey is:

1. Splash: establish the `selfit / 适我` identity on the wine-red textile.
2. Login: choose phone verification or invitation-code login; restored sessions skip the login screens.
3. Onboarding: explain `suit / like / vibe`.
4. `suit`: collect a front-facing portrait and a full-body photo.
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

All positions below are absolute coordinates in the `393 × 852px` base frame.

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
- Phone login uses an `+86` prefix, an 11-digit mobile number, a 4–6 digit verification code, send/resend countdown, inline feedback, and a disabled-until-valid login CTA.
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

The Figma `onboarding` group (`4948 × 4552px`) is the acceptance matrix for the complete sequence:

1. `splash`: timed textile identity frame with the centered `selfit` star halo and `适我` near the bottom; tap may advance early.
2. `login / phone-login / invite-login`: login choice and the two credential paths, including validation, sending, pending, failure, and restored-session states.
3. `intro`: separated and composed lace-card states.
4. `suit`: empty upload, checking, one-photo valid, both valid, insufficient-light failure, and manual `信息选择` fallback.
5. `like`: three continuous axes — `硬朗锐利 / 柔和温柔`, `简约克制 / 精致繁复`, `经典耐看 / 时髦先锋` — plus six composed palettes. The CTA stays disabled until a palette is selected.
6. `vibe`: three single-choice questions. The CTA stays disabled until every question has an answer and then reads `生成风格报告`.
7. `loading`: the onboarding/report-generation loading sequence is four wine-textile stages at `25 / 50 / 75 / 100%`: `先看见真实的你`, `寻找你同频的灵感`, `拼出更像你的样子`, and `我们认识你了...`. The current artwork is, respectively, `薰衣草+花拱+蓝鞋`, `戒指+画作+咖啡`, `樱桃+蛋糕+绿包`, and the `selfit` wordmark. Each stage uses its direct 2× Figma export and transitions over `300ms` with an ease-out cross-fade. The latest `450:11872` matrix uses the dark-wine, three-line embroidered `Fit / yourself / not in` artwork centered near the bottom throughout all four stages.

The mirror route owns a separate three-stage recognition sequence at `25 / 50 / 75%`: `看见你本来的样子`, `你不需要成为谁`, and `只需要更准确地做自己`. Its bottom branding is the exported blue curved `Know yourself first.` signature plus stage-specific ornament artwork. Never reuse the mirror copy, blue signature, or mirror-opening ornament inside onboarding loading; never reuse the onboarding lace cards or embroidered three-line brandmark inside mirror loading; and never replace the mirror sequence with the generic `正在分析中` label.
8. `report`: the `450:13461` editorial long page — style cover, identity summary, five rounded-square recommended colors, two-column makeup/hair references, outfit analysis and four-card visual recommendations, a pale-pink bordered interpretation list, centered lace `selfit` signoff with multicolor dots, and the paired actions `返回重测 / 保存并分享`.
9. `share`: full-height report sharing layer with `保存单张 / 发笔记 / 微信好友 / 朋友圈` actions.

The share layer uses a real three-card carousel: style summary, recommended colors, and visual inspiration. Adjacent cards remain partially visible as a swipe affordance. Touch/trackpad scrolling uses horizontal scroll snap; pagination dots, `ArrowLeft / ArrowRight`, `Home`, and `End` provide equivalent direct navigation. The active dot and live `第 n 张，共 3 张` status always follow native swiping.

The upload route and manual-selection route converge on `like`; report generation must never require debug data or expose technical pipeline language.

The `vibe` questionnaire scrolls inside the `361px`-wide content panel beginning at `y=137px`; its title starts at `y=157px` and the first question at `y=221px`. Options are content-width pills with a fixed `42px` height and `16px` vertical gaps. The CTA remains in a `114px` bottom gradient dock, disabled until every question has an answer. At maximum scroll, the final `E` option must sit completely above the CTA; touch scrolling and keyboard focus must never leave an answer hidden beneath the dock.

The paired report actions are progressively disclosed: they are hidden on the report's initial viewport, appear when the user scrolls into `你最适合的穿搭`, and then dock above the bottom safe area. `返回重测` returns to `vibe` with existing answers intact; `保存并分享` opens the share layer. Scrolling back above the outfit section hides them again. Hidden actions must not remain keyboard-focusable or intercept pointer input.

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
