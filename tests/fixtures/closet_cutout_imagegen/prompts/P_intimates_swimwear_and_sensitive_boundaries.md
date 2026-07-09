# P intimates_swimwear_and_sensitive_boundaries

Allowed clothing categories that need product-safe handling and clear taxonomy.

## P01 one piece swimsuit seed

- Expected: dress x1
- Difficulty: swimwear, taxonomy_gap
- Acceptance: May map to dress/accessory/review; should be one item.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: catalog product photo of a black one-piece swimsuit laid flat on a pure white background, full swimsuit visible, no model, no text. Composition/framing: keep the relevant garment or object fully visible unless the case explicitly asks for crop. Lighting/mood: realistic natural or studio lighting. Constraints: avoid brand logos, readable text, watermarks, and unrelated extra garments unless requested.
```

## P02 bikini set flatlay

- Expected: top x1, bottom x1
- Difficulty: swimwear, two_piece, small_items
- Acceptance: Two pieces detected or review.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: top-down product photo of a simple blue bikini set laid flat on white background, top and bottom separated with clear gap, no model, no text. Composition/framing: keep the relevant garment or object fully visible unless the case explicitly asks for crop. Lighting/mood: realistic natural or studio lighting. Constraints: avoid brand logos, readable text, watermarks, and unrelated extra garments unless requested.
```

## P03 sports bra

- Expected: top x1
- Difficulty: activewear, small_top
- Acceptance: Classify as top or review.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: catalog product photo of a black sports bra laid flat on white background, front view, no model, no text. Composition/framing: keep the relevant garment or object fully visible unless the case explicitly asks for crop. Lighting/mood: realistic natural or studio lighting. Constraints: avoid brand logos, readable text, watermarks, and unrelated extra garments unless requested.
```

## P04 thermal leggings

- Expected: bottom x1
- Difficulty: leggings, tight_shape
- Acceptance: Classify as bottom, not accessory.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: product photo of black thermal leggings laid flat on white background, waistband and leg openings visible, no model, no text. Composition/framing: keep the relevant garment or object fully visible unless the case explicitly asks for crop. Lighting/mood: realistic natural or studio lighting. Constraints: avoid brand logos, readable text, watermarks, and unrelated extra garments unless requested.
```

## P05 pajama set

- Expected: top x1, bottom x1
- Difficulty: sleepwear, set, pattern
- Acceptance: Two items or one review set acceptable; no false accessories.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: top-down flatlay of a matching striped pajama shirt and pajama pants on white bedding, both pieces visible, no person, no text. Composition/framing: keep the relevant garment or object fully visible unless the case explicitly asks for crop. Lighting/mood: realistic natural or studio lighting. Constraints: avoid brand logos, readable text, watermarks, and unrelated extra garments unless requested.
```
