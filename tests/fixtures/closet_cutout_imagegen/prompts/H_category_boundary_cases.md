# H category_boundary_cases

Ambiguous fashion items that expose taxonomy gaps.

## H01 shirt dress seed

- Expected: dress x1
- Difficulty: ambiguous, dress_vs_top
- Acceptance: Prefer dress; top review is acceptable but should not split into top and bottom.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: a long white shirt dress laid flat on a clean light gray background. Subject: button-up collar, long sleeves, dress-length hem reaching mid-thigh, single continuous garment. Composition/framing: centered full garment product photo. Lighting/mood: soft even studio lighting. Constraints: no model, no hanger, no belt, no text, no watermark.
```

## H02 jumpsuit

- Expected: dress x1
- Difficulty: ambiguous, jumpsuit, taxonomy_gap
- Acceptance: May map to dress or review; should not create separate top and pants unless pipeline is intentionally splitting.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: a sleeveless black jumpsuit laid flat on a pure white background. Subject: one-piece garment with top connected to wide-leg pants, waist seam visible. Composition/framing: centered full garment product photo. Lighting/mood: soft studio light. Constraints: no model, no hanger, no text, no watermark.
```

## H03 skort

- Expected: skirt x1
- Difficulty: ambiguous, skirt_vs_shorts
- Acceptance: Skirt or bottom review acceptable; should remain one item.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: a beige skort laid flat on a white studio background, looking like a wrap mini skirt in front with hidden shorts structure visible slightly underneath. Subject: waistband and asymmetric wrap panel clear. Composition/framing: centered catalog shot. Lighting/mood: soft even light. Constraints: no model, no text, no watermark.
```

## H04 knee high boots

- Expected: shoes x1
- Difficulty: ambiguous, boots_tall_shape
- Acceptance: Classify as shoes, not pants.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: a pair of dark brown knee-high leather boots on a pure white studio background. Subject: tall boot shafts, pointed toes, both boots visible as a pair. Composition/framing: centered vertical product shot with full boots visible. Lighting/mood: soft studio light. Constraints: no legs, no model, no text, no watermark.
```

## H05 scarf hat socks accessories flatlay

- Expected: accessory x3
- Difficulty: accessory_slots, hat, scarf, socks
- Acceptance: Accessories may map to accessory; future slot inference should identify hat/scarf/socks.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: top-down flatlay on a white background with three separate accessories: a knitted beanie hat, a folded scarf, and a pair of ribbed socks. Subject: each accessory separate, fully visible, no other garments. Composition/framing: clean product flatlay with gaps between items. Lighting/mood: soft studio light. Constraints: no text, no watermark, no model.
```
