# C multi_item_flatlay_outfits

One image containing several closet items that should be split into multiple items.

## C01 shirt jeans sneakers flatlay seed

- Expected: top x1, bottom x1, shoes x1
- Difficulty: flatlay, multi_item, outfit
- Acceptance: Create three items without merging shirt, jeans, and shoes.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: top-down flatlay outfit on a clean white background: a blue striped shirt at the top, light blue jeans below it, and one pair of white sneakers near the bottom. Subject: three separate garments with small gaps between them, no overlap. Composition/framing: organized outfit flatlay, all items fully visible. Lighting/mood: soft even daylight. Constraints: no body, no text, no watermark, no extra accessories.
```

## C02 cardigan skirt heels bag flatlay

- Expected: top x1, skirt x1, shoes x1, bag x1
- Difficulty: flatlay, multi_item, bag_side
- Acceptance: Four items, no duplicate shoes or merged bag.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: top-down fashion flatlay on a clean white background: pale yellow cropped cardigan, navy pleated midi skirt, black heels, and a pale yellow handbag placed on the right side. Subject: each item separate with clear white gaps. Composition/framing: balanced outfit layout, all items fully visible. Lighting/mood: soft studio light. Constraints: no model, no text, no watermark.
```

## C03 dress bag shoes flatlay

- Expected: dress x1, bag x1, shoes x1
- Difficulty: flatlay, dress_not_top_skirt
- Acceptance: Dress should remain dress, not split into top and skirt.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: top-down flatlay on a white background: one ivory sleeveless midi dress in the center, a small beige handbag on the right, and black slingback heels near the bottom. Subject: three separate items, full dress silhouette visible. Composition/framing: clean fashion outfit layout. Lighting/mood: soft even studio light. Constraints: no model, no text, no watermark, no extra garments.
```

## C04 light overlap outfit flatlay

- Expected: top x1, bottom x1, shoes x1, bag x1
- Difficulty: flatlay, slight_overlap
- Acceptance: Main items should be separated; overlap area may be review.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: top-down flatlay on a warm white background: a cream sweater slightly overlapping the waistband of black trousers, white sneakers below, and a brown crossbody bag partly overlapping one sleeve. Subject: four fashion items, light natural overlap but every item mostly visible. Composition/framing: full outfit visible. Lighting/mood: soft daylight. Constraints: no person, no text, no watermark.
```

## C05 many item busy flatlay

- Expected: top x2, bottom x1, shoes x2, bag x1, accessory x2
- Difficulty: flatlay, many_items, dedupe_pressure
- Acceptance: Find major clothing items; duplicates are acceptable as separate closet items but later outfit rules should dedupe.

```text
Use case: photorealistic-natural. Asset type: closet cutout stress test image. Primary request: top-down busy closet flatlay on a white floor with eight separate items: two tops, one pair of trousers, two pairs of shoes, one handbag, one scarf, and one cap. Subject: all items visible with small gaps, no body. Composition/framing: organized but dense, all items inside frame. Lighting/mood: soft room light. Constraints: no text, no watermark, no brand logos.
```
