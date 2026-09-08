# Onboarding optimization — 2026-09-08

## Delivered flow

Intro → like (palette optional, can clear selection) → suit upload → photo processing → editable suit results → updated vibe → report → try-on / sharing.

Photo-free users can select all three suit features manually. On the result screen each feature opens its own selection group. Save merges only that field; cancel restores the prior selection. Live results use `resolve_suit_profile` and retain manual-over-inference precedence. Missing attributes are explicitly unknown. No persona calculation weights or thresholds changed. Question 3's new visual order uses A/B/E/D/C to preserve the existing Japanese/Korean/French/Chinese/Western mapping.

The report retains the current 16-personality catalog rather than introducing the obsolete LACE example from the sketch. Warm surfaces, larger section gaps, readable summary, five colors, outfit inspiration, and try-on/share controls follow DESIGN.md. Report completion now shows the report before the user enters the mirror.

## API

- `GET /api/v1/selfit/sessions/{id}/suit`: revision, three feature records (key/title/value/source/description/advice), accepted-photo availability. Same active-session ownership and expiry checks as existing routes; no-store.
- `PATCH .../profile`: existing validated partial updates, then GET suit to refresh descriptions.
- `GET .../photos/{kind}/preview`: authorized, EXIF-oriented WebP analysis overlay, maximum 1200px, stripped metadata, no-store. Uses backend face/skin/body geometry without QA metrics, with separate derived-asset caching. Same-owner saved uploads are supported. Original assets remain intact.
- `PATCH .../preferences`: explicit null palette clears any prior choice.

No fictitious facial landmarks or percentage certainty are presented. The result photos are normalized previews alongside actual classification outputs.

## Verification

- Real local backend with an isolated temporary onboarding store; QA photo archiving disabled for the browser fixture run.
- Browser: skipped palette; completed manual selection; edited oval face to round face; confirmed updated description and unchanged skin/body; confirmed only the selected category appears in the edit view.
- Browser: uploaded `real_clear_glasses.jpg` and `female_slim_1.webp`; observed processing state and accepted previews; received oval face / warm fair skin / hourglass from the real inspector.
- Browser: checked new questionnaire and last option above its bottom dock at ~391 × 844 CSS px (no horizontal overflow).
- Browser: checked report at ~431 × 844 and centered desktop; hero, traits, colors and imagery load. Report actions remain visible from initial display, with equally sized sharing and “去试穿” buttons. A real generated LOOP report stays on the report screen and successfully opens its three-card share layer.
- Browser: at 768 × 852 the original fixed-height shell clipped its CTA; corrected the shell height and desktop report dock. Verified shell bottom 828px, CTA bottom 808px, no horizontal overflow. Final preview console has no errors or warnings.
- Tests: 93 passed, 3 deselected in the focused API/persona/onboarding suite. Added tests cover manual precedence, missing attributes, description coverage, optional/cleared palette, preview orientation and metadata stripping, and new flow / semantic option wiring.
- The three excluded pre-existing assertions expect legacy report-parent `tab` navigation, `/wearwow/demo` login destination, and the August personality catalog version. The current pre-task implementation already uses mirror `screen` navigation, `/selfit/try-on`, and the September catalog. These unrelated migrations were preserved.
- JavaScript syntax and `git diff --check` pass.

No server deployment performed. Existing unrelated working-tree changes remain intact.
