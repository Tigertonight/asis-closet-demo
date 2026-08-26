# Manual selection assets

The manual `信息选择` page maps every visible label to its own latest-Figma crop export.

- `face-{diamond,square,round,oval,heart}@4x.png`: direct `156 × 240px` exports of the five `image 5793` crop layers from the latest `Frame 2134052354` (`746:5409`). Runtime renders them at the Figma-native `39 × 60px` size.
- `body-{pear,inverted-triangle,hourglass,rectangle,apple}@4x.png`: direct `144 × 408px` exports of the five `image 5805` crop layers from the same latest frame. Runtime renders them at `36 × 102px`.
- Old card screenshots, diagnostic crops, the face strip, and 2× body options are retained only as provenance and are not loaded by the runtime.
- `figma-body-types-source.png`: high-resolution 2x export of the body-type group.
- `figma-manual-frame.png`: full manual-selection frame from Figma node `450:15002`, retained for visual QA.

Runtime UI loads only the ten direct `@4x` option exports.
