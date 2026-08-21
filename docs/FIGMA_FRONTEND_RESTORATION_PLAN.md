# selfit Figma Frontend Restoration Plan

## Current delivery status — onboarding complete

The onboarding slice is implemented at the canonical routes `/selfit` and `/selfit/demo`.

- Figma-exported wordmark and all three lace/handwritten cards are shipped as RGBA assets.
- The `393 × 852px` frame, title, DNA copy, cards, CTA, and footnote have measured coordinates in `DESIGN.md`.
- Motion matches the two prototype links: separated hold `1600ms`, transition `600ms` ease-out, composed hold `800ms`, reverse transition `600ms`.
- The CTA enters the `suit` step; back/restart replay the onboarding sequence.
- Reduced motion displays the composed state immediately.
- Browser QA passed at widths `390`, `393`, `430`, and desktop `1280`; there is no document or active-screen horizontal overflow, no failed resource, and no console error.

Remaining phases below are the implementation plan for the rest of the Figma project and are not part of the completed onboarding scope.

## 1. Audit Summary

The current Figma onboarding and the older closet-centric experience represent different product directions.

| Area | Figma | Current demo | Action |
|---|---|---|---|
| Brand | `selfit` / `适我` | `selfit` | Keep the unified product brand |
| Core story | Style DNA: `suit × like × vibe` | Weather, closet, AI stylist, try-on hub | Make assessment the primary journey |
| Palette | `#FAFAFA` + `#8A011B` | Blush + `#FF4F86` | Replace global tokens |
| Layout | 393×852, 40px assessment margins | 430px shell, mostly 16px margins | Rebase responsive layout |
| CTA | 313×44, radius 18 | Large rose pill | Rebuild the base button |
| Motif | Lace, mirror, paper, textile | Generic rounded cards/gradients | Export signature Figma assets |
| Main content | Assessment, reveal, visual feed | Today/weather cards and widgets | Reorder information architecture |
| Motion | 600ms editorial card animation | Generic short transitions | Build a dedicated sequence |

Existing backend capabilities remain useful. This is primarily an information-architecture and presentation rewrite, not a backend replacement.

## 2. Design Inventory

### High-confidence: build first

- Base mobile frame: 393×852, radius 40, `#FAFAFA`.
- `selfit` wordmark and onboarding statement.
- `suit / like / vibe` card motif and animation states.
- Three-step assessment progress indicator.
- `suit` upload for face and full-body photos.
- `like` preference screen with sliders and palette cards.
- Wine reveal screen with lace/mirror artwork.
- Two-column outfit feed with compact `试穿` actions.
- CTA: 313×44, radius 18, `#8A011B`.

### Medium-confidence: validate while building

- Final `vibe` questions and controls.
- Exact style-result content.
- Result-to-discovery navigation.
- Highlight-star and video-card semantics.
- Try-on details after selecting an outfit.

### Exploratory: not MVP acceptance criteria yet

- Unconnected profile, closet, AI-chat, and free-styling concepts in the broad visual/interaction section.
- Duplicate onboarding/upload variants.
- Gray feed skeletons, except as loading-state references.

## 3. Recommended Architecture

The current UI is a large inline HTML/CSS/JavaScript string in `app/closet.py`. A full restoration there would make pixel review and reuse unnecessarily difficult.

Recommended target:

```text
frontend/
  src/
    app/
    components/
    features/
      onboarding/
      assessment/
      style-result/
      discovery/
      try-on/
    assets/
    styles/
      tokens.css
      typography.css
      motion.css
  public/
  package.json
  vite.config.ts
```

- React + TypeScript + Vite.
- A reducer/state machine for the assessment; a small typed API layer for server state.
- CSS modules or scoped CSS backed by `tokens.css`; avoid a UI kit that fights the Figma language.
- FastAPI serves the built SPA and retains existing JSON/file endpoints.
- Keep both `/selfit` and `/selfit/demo` as supported canonical entries during rollout.

If a new build tool is out of scope, preserve the same boundaries with ES modules and static CSS. Do not add another multi-thousand-line inline string to `app/closet.py`.

## 4. Route and State Map

```text
/selfit
  └─ onboarding
      └─ assessment/suit
          └─ assessment/like
              └─ assessment/vibe
                  └─ reveal
                      └─ style-result
                          └─ discover
                              ├─ outfit/:id
                              └─ try-on/:id
```

Persist assessment progress locally until completion. A refresh must not silently lose answers or uploaded-photo previews. Persist the completed profile through a backend contract when available.

## 5. Backend Plan

### Reuse now

- Authentication: `/auth/*`.
- Photo/color analysis: `/analyze` and existing quality gates.
- Closet data: `/closet/items`, `/closet/outfits`.
- Inspiration try-on: `/try-on/from-inspiration`.
- Outfit try-on: `/try-on/from-outfit` or the branded `/selfit/try-on/from-outfit` endpoint.
- Generated asset serving and try-on capability/status endpoints.

### Add or normalize

- `GET /selfit/profile`: current assessment/profile.
- `PATCH /selfit/profile`: save `suit`, `like`, or `vibe` independently.
- `POST /selfit/profile/complete`: produce and persist the style result.
- `GET /selfit/discovery?cursor=`: normalized feed cards.
- A compatibility adapter for retired endpoint names, so new frontend code only encodes `selfit`.

The first slice may use typed fixtures for `like`, `vibe`, and result content, but fixture shapes must match the planned APIs.

## 6. Component Order

1. `MobileShell`, safe areas, and centered desktop canvas.
2. `SelfitWordmark` and exported signature artwork.
3. `PrimaryButton` with verified dimensions.
4. `AssessmentStepper`.
5. `StyleCardStack` with separated/overlapping states.
6. `PhotoUploadPair` with complete validation states.
7. `SemanticSlider` and `PaletteChoice`.
8. `RevealScene`.
9. `MasonryFeed`, `OutfitCard`, and `TryOnChip`.
10. `TryOnFlow` adapter over current APIs.

Each component needs a visual-state fixture route or Storybook equivalent for pixel review, including error and loading states absent from the happy-path Figma frames.

## 7. Delivery Phases

### Phase 0: foundation and assets

- Confirm consumer route and legacy-route policy.
- Export wordmark, handwritten words, lace frames, mirror/apple art, and textile backgrounds.
- Create frontend project, tokens, API client, and mobile shell.
- Add 393×852 screenshot baselines.

Exit: the empty shell matches dimensions, background, spacing, typography, and CTA.

### Phase 1: onboarding

- Implement message hierarchy and card sequence.
- Reproduce 800ms/1600ms beats with 600ms ease-out transitions.
- Add reduced-motion behavior.
- Connect CTA to `assessment/suit`.

Exit: pixel review passes for initial, separated-card, and overlapping-card states.

### Phase 2: `suit / like / vibe`

- Implement stepper and route/state machine.
- Wire face/full-body uploads to analysis gates where applicable.
- Implement sliders, palettes, validation, save/resume, and final `vibe` schema.
- Add loading and recovery copy.

Exit: refresh-safe completion through all three steps, including invalid-photo and network-failure paths.

### Phase 3: reveal and result

- Implement wine textile reveal and signature art.
- Finalize result contract/page.
- Add continue, retake, and edit-preferences paths.

Exit: fixture-based result is deterministic, persists, and leads to discovery.

### Phase 4: discovery and try-on

- Build two-column feed, video marker, highlight star, pagination, and skeleton.
- Wire `试穿` to existing endpoints.
- Keep result imagery dominant and technical data hidden.

Exit: feed scrolling is stable, image ratios hold, and try-on success/failure completes from a card.

### Phase 5: migration and cleanup

- Point the approved consumer route to the new frontend.
- Keep `/selfit` and `/selfit/demo` aligned to the same production frontend.
- Remove duplicated presentation code after parity acceptance.
- Update README, deployment build steps, and browser smoke tests.

Exit: no legacy brand in consumer pages, APIs remain covered, and builds are reproducible.

## 8. Verification Matrix

### Visual

- Viewports: 390×844, 393×852, 430×932, 768px, desktop centered shell.
- Overlay implementation and Figma at 393×852 for every high-confidence screen.
- Confirm CTA dimensions, page margins, accent color, and artwork placement.
- Confirm no signature asset is replaced with emoji/generic icons.

### Interaction

- Keyboard and touch completion.
- Upload permission denied, invalid/oversized file, retry, and preview.
- Refresh/back-navigation retention.
- Reduced-motion onboarding.
- Feed pagination and duplicate prevention.
- Try-on loading, success, failure, retake, save, and share-handoff states.

### Technical

- No horizontal overflow or safe-area collision.
- No console errors or broken resources.
- Image-heavy feed performance measured with realistic fixtures.
- Route-level lazy loading for discovery and try-on.
- API/asset URLs work locally and behind the deployed FastAPI base path.

## 9. Decisions Needed Before Phase 2 Ends

- Final external brand: `selfit`, `适我`, or bilingual lockup?
- Final `vibe` questions and result taxonomy?
- Is authenticated profile persistence required for MVP?
- Which exploratory profile/closet/AI/free-styling screens remain in scope?
- Confirm the long-term retirement window for pre-`selfit` compatibility endpoints.
- Which Figma assets/fonts are licensed for shipping?

These decisions do not block Phase 0 or Phase 1.

## 10. Definition of 100% Restoration

`100%` means there are no unexplained or intentionally simplified differences in four dimensions:

1. **Visual parity**: geometry, spacing, typography variables, colors, opacity, borders, radii, shadows, imagery, cropping, and layering match the Figma frame.
2. **Interaction parity**: tap targets, navigation, scroll/fixed behavior, selection, disabled states, upload behavior, back behavior, and gestures match the prototype or an approved UX decision.
3. **Motion parity**: trigger, delay, duration, easing, transform origin, entering/exiting layers, and interruption behavior match the prototype.
4. **State parity**: initial, intermediate, loading, empty, success, failure, retry, permission-denied, offline, and restored-session states are explicitly implemented.

Automated screenshot comparison may allow a small rasterization tolerance for fonts and photos, but acceptance requires **zero unexplained design differences**. A difference caused by browser text rasterization is documented; a missing asset, wrong margin, approximate icon, or changed interaction is a failure.

## 11. Figma Traceability Manifest

Every implementation route and screenshot test must reference its source Figma node. Current inspected nodes:

| Manifest ID | Figma node | Prototype flow | Observed purpose | Treatment |
|---|---|---|---|---|
| `ONB-01` | `110:20471` | Flow 1 | Onboarding entry/overlapping card state | Build and compare |
| `ONB-02` | `450:15210` | Flow 12 | Three separated `suit/like/vibe` cards | Animation keyframe |
| `ONB-03` | `255:5217` | Flow 8 | Alternate onboarding explanation | Confirm whether retained |
| `ONB-TITLE` | `110:20492` | — | Main title geometry/type token | Token baseline |
| `CTA-BASE` | `110:20509` | — | 313×44 wine primary button | Component baseline |
| `CTA-LABEL` | `110:20510` | — | `去认识自己` label | Type baseline |
| `SUIT-01` | `110:19900` | Flow 4 | Face/full-body upload with stepper | Build and compare |
| `SUIT-02` | `450:14606` | Flow 11 | Upload duplicate/variant | Diff against `SUIT-01` |
| `SUIT-03` | `255:4726` | Flow 7 | Simplified upload variant | Treat as exploration until approved |
| `SUIT-TITLE` | `110:19927` | — | Upload title | Type baseline |
| `SUIT-HELP` | `110:19929` | — | Local-processing helper copy | Type/copy baseline |
| `LIKE-01` | `255:2719` | Flow 5 | Like step, sliders, palettes | Build and compare |
| `REC-01` | `438:8828` | — | Recognition progress narrative | Build and compare |
| `REV-01` | `438:9515` | Flow 9 | Wine reveal, empty lace frame | Animation keyframe |
| `REV-02` | `450:15496` | Flow 13 | Wine reveal, apple/mirror artwork | Animation keyframe |
| `FEED-LOAD` | `110:18976` | Flow 2 | Two-column feed skeleton | Loading state |
| `FEED-READY` | `255:3275` | Flow 6 | Photo/flat-lay masonry feed | Build and compare |

Create `frontend/src/design/figma-manifest.ts` with these IDs, route/state names, source node, reference screenshot filename, and implementation owner. No screen is considered complete without a manifest entry.

## 12. Screen-by-Screen UI Specification

### `ONB-01..03` — onboarding

- Frame: 393×852, radius 40, `#FAFAFA`.
- Centered serif `selfit` wordmark.
- Main title begins at x=32; verified title is 329×26 at y=157.
- Supporting DNA copy stays left-aligned and low contrast.
- Lace cards move between separated and overlapping compositions.
- CTA is fixed at x=40, y=736, 313×44.
- No bottom navigation.
- Required captured states: initial, separated, transitioning, overlapping, CTA ready, reduced motion.

### `SUIT-01` — photo collection

- Three-step progress header with `suit` active.
- Title and helper occupy 329px content width.
- Two upload targets: `面部照`, `全身照`.
- Each target keeps the Figma placeholder silhouette and circular plus control.
- Preview preserves the user's chosen crop; destructive auto-cropping is not allowed.
- Continue remains disabled until the approved minimum photo set passes validation.
- Required captured states: empty, one selected, both selected, checking, invalid face photo, invalid full-body photo, permission denied, retry, ready.

### `LIKE-01` — preference capture

- Stepper switches active state to `like`.
- Title: `选择你更喜欢的`.
- Semantic slider endpoints remain text labels rather than numeric values.
- Sliders support tap, pointer drag, touch drag, arrow keys, and visible focus.
- Palette cards preserve circle sizes, grouping, order, selected outline, and scrolling behavior.
- Required states: untouched, partially answered, fully answered, validation prompt, restored answers.

### `VIBE` — expression capture

- Do not invent the final question set from the word `vibe` alone.
- Create the route/state/component shell now, but block final content parity until design supplies the exact frame or approves an existing exploration frame.
- The implementation gate requires final copy, choice mechanics, default state, completion rule, and back/edit behavior.

### `REC-01` — recognition progress

- This is a staged narrative, not a spinner modal.
- Centered copy sequence:
  1. `先看见你本来的样子`
  2. `寻找你同频的灵感`
  3. `拼出更像你的样子`
  4. `selfit 认识你了`
- Percentage sits near the bottom in wine red; a verified frame shows `20%`.
- Progress is monotonic, survives a slow response, and has an explicit timeout/retry state.

### `REV-01..02` — reveal

- Full wine textile background and white status icons.
- Lace frame remains centered with the exact exported artwork and crop.
- Reveal art changes from an empty frame to the apple/mirror composition.
- Bottom narrative changes with the approved prototype state.
- Required captured states: entry, empty frame, art revealed, exit, reduced motion.

### `FEED-LOAD/READY` — discovery

- Two-column masonry with the exact gutters and radii from the selected reference frame.
- Skeleton preserves final card dimensions to prevent layout shift.
- Mix real-person images and outfit flat-lays.
- `试穿` remains a compact translucent overlay in the lower-right.
- Video marker and highlight star only appear when their data flags are true.
- Required states: first load, ready, pagination, refreshing, empty, offline, partial image failure, all image failure.

## 13. UX State Machine

The frontend state model must be explicit rather than inferred from URL changes:

```text
boot
  -> onboarding.intro
  -> onboarding.cardsSeparated
  -> onboarding.cardsOverlapping
  -> onboarding.ready
  -> assessment.suit.empty
  -> assessment.suit.partial
  -> assessment.suit.validating
  -> assessment.suit.ready
  -> assessment.like.editing
  -> assessment.like.ready
  -> assessment.vibe.editing
  -> assessment.vibe.ready
  -> recognition.running
  -> recognition.complete
  -> reveal.entering
  -> reveal.artwork
  -> reveal.exiting
  -> result.ready
  -> discovery.loading
  -> discovery.ready
  -> tryon.preparing
  -> tryon.generating
  -> tryon.result | tryon.retry
```

Global branches from applicable states:

- `offline`
- `authRequired`
- `permissionDenied`
- `sessionRestored`
- `fatalError`

Back navigation must restore the exact previous answers and scroll position. Browser refresh must restore all serializable state. Photo object URLs must be reconstructed from persisted assets or clearly request reselection; never show a stale broken preview.

## 14. Asset Restoration Workflow

Before component implementation:

1. Export every signature asset at its source node.
2. Record node ID, export format, intrinsic dimensions, intended CSS dimensions, crop behavior, and color mode.
3. Name assets by function, not Figma's `image 5786` labels.
4. Generate an asset contact sheet and compare it with Figma.
5. Optimize only after a lossless visual baseline is approved.

Required asset groups:

- selfit wordmark.
- `suit`, `like`, `vibe` handwritten artwork.
- Lace card frames and reveal frame.
- Apple/mirror reveal art.
- Wine textile backgrounds.
- Upload silhouettes and plus controls.
- Status/navigation icons.
- Feed reference photos and flat-lays where licensing permits.

SVG exports must preserve viewBox and stroke scaling. Raster exports must include 1x/2x density or responsive source sets. No generative replacement, emoji, or approximate icon is accepted for a signature asset.

## 15. Pixel-Parity Workflow

For every manifest state:

1. Capture the Figma frame at 393×852 without editor chrome.
2. Render the implementation at the same viewport, device scale, font load state, and deterministic fixture data.
3. Produce side-by-side, 50% opacity overlay, and perceptual-diff images.
4. Classify each difference: geometry, type, color, asset, crop, state, or browser rasterization.
5. Fix all non-rasterization differences.
6. Store the approved baseline in `frontend/tests/visual/baselines/`.

Minimum automated coverage:

- Playwright screenshot test for every manifest state.
- DOM assertions for copy, active step, disabled/selected state, and semantic roles.
- Interaction tests for upload, sliders, palettes, back/refresh, reveal, feed, and try-on.
- Console/network assertion: no unexpected errors, 404 assets, or failed font loads.

Do not approve from memory or a side-by-side glance alone. Approval requires the overlay and diff artifacts.

## 16. Completion Gate and Deliverables

The restoration is complete only when all of the following exist:

- Updated `DESIGN.md` with verified tokens and no conflicting legacy rules.
- Figma traceability manifest with every production screen/state.
- Exported and audited asset library.
- Typed frontend routes, state machine, and API contracts.
- Visual fixture route for all states.
- Screenshot baselines, overlays, diffs, and approval record.
- Accessibility and responsive test results.
- Mapping of all deviations explicitly approved by design/product.
- Documented retirement decision for pre-`selfit` compatibility endpoints.
- No unresolved item in the Ready for Dev scope.

Because the current Figma contains generic flow names, duplicate variants, and unconnected exploration frames, final 100% UX parity requires a short design-freeze review to select the authoritative variant and define missing `vibe`, result, and navigation behavior. Coding can start on the verified foundation/onboarding nodes while that review is completed.
