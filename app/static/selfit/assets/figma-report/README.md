# Figma report assets

Source of truth: report long-page node `450:13461`; share-report node `450:16203` in Figma file `7WvSROZhohAyvpEMfxZ3Dd`.

The report renders these exports as two-column cards. `makeup-*` and `hair-*` are retained as a reusable backend-driven pool; the default report selects two of each. `outfit-01` through `outfit-03` are the currently available exact Figma exports. Do not synthesize or duplicate a fourth outfit image: render additional backend/CDN items when supplied.

The current View-seat MCP quota prevented refreshing the binary exports on 2026-08-24. Existing 2×/4× Figma exports remain authoritative until a Full-seat export can replace them byte-for-byte.

Runtime asset mapping:

- `makeup-01@2x.png` through `makeup-04@2x.png`: high-density makeup references used by the two-column module in node `450:13461`.
- `hair-01@2x.png` through `hair-04@2x.png`: high-density hairstyle references used by the two-column module in node `450:13461`.
- `outfit-01@2x.png` through `outfit-03@2x.png`: `220 × 292px` high-density covers used by the two-column outfit module in node `450:13461`.
- `report-frame-top.png` and `report-frame-scroll.png`: legacy visual QA references, not loaded by the product UI.

Runtime mapping and backend replacement fields are documented in `docs/SELFIT_REPORT_DATA_CONTRACT.md`.
