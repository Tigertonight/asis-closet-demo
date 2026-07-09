# S duplicates_and_near_duplicates

Test duplicate detection and outfit dedupe logic using similar items.

## S01 two similar white sneakers seed

- Expected: shoes x2
- Difficulty: duplicate_category, similarity, shoes
- Acceptance: Closet may save two shoe items; outfit builder should later dedupe.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: top-down product photo with two separate pairs of white sneakers side by side on white background, subtle differences, no feet, no text. Composition/framing: keep the relevant garment or object fully visible unless the case explicitly asks for crop. Lighting/mood: realistic natural or studio lighting. Constraints: avoid brand logos, readable text, watermarks, and unrelated extra garments unless requested.
```

## S02 two black trousers

- Expected: bottom x2
- Difficulty: duplicate_category, bottom
- Acceptance: Two bottoms as separate closet items; outfit cover should not use both.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: top-down flatlay of two pairs of black trousers side by side on a light gray background, both full visible, no text. Composition/framing: keep the relevant garment or object fully visible unless the case explicitly asks for crop. Lighting/mood: realistic natural or studio lighting. Constraints: avoid brand logos, readable text, watermarks, and unrelated extra garments unless requested.
```

## S03 same shirt front and back

- Expected: top x2
- Difficulty: duplicate_view, top
- Acceptance: May save two top views; should be flagged by similarity later.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: catalog image showing the same blue shirt front view and back view side by side on white background, two separate views, no text. Composition/framing: keep the relevant garment or object fully visible unless the case explicitly asks for crop. Lighting/mood: realistic natural or studio lighting. Constraints: avoid brand logos, readable text, watermarks, and unrelated extra garments unless requested.
```

## S04 shoe plus shoe reflection

- Expected: shoes x1
- Difficulty: reflection_duplicate, shoes
- Acceptance: Reflection should not become second shoes item.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: single pair of black loafers on a glossy surface with strong reflection below, plain background, no text. Composition/framing: keep the relevant garment or object fully visible unless the case explicitly asks for crop. Lighting/mood: realistic natural or studio lighting. Constraints: avoid brand logos, readable text, watermarks, and unrelated extra garments unless requested.
```

## S05 outfit with extra duplicate bag

- Expected: top x1, bottom x1, bag x2
- Difficulty: duplicate_bag, outfit
- Acceptance: Closet can detect two bags; outfit card should show one.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: top-down flatlay outfit with one sweater, one skirt, and two similar small handbags on the side, white background, no text. Composition/framing: keep the relevant garment or object fully visible unless the case explicitly asks for crop. Lighting/mood: realistic natural or studio lighting. Constraints: avoid brand logos, readable text, watermarks, and unrelated extra garments unless requested.
```
