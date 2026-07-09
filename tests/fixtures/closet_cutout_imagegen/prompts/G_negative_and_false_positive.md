# G negative_and_false_positive

Images that should not create usable closet items.

## G01 landscape no garments seed

- Expected: no closet item
- Difficulty: negative, no_item
- Acceptance: No closet item should be created.

```text
Use case: photorealistic-natural. Asset type: closet cutout negative test image. Primary request: a peaceful outdoor landscape photo with trees, grass, and sky, no people and no clothing items. Composition/framing: natural scenic photo. Lighting/mood: soft daylight. Constraints: no garments, no bags, no shoes, no text, no watermark.
```

## G02 table objects no garments

- Expected: no closet item
- Difficulty: negative, household_objects
- Acceptance: No closet item should be created from cups/books.

```text
Use case: photorealistic-natural. Asset type: closet cutout negative test image. Primary request: a tabletop still life with a coffee cup, notebook, pen, and phone on a wooden desk. Subject: household objects only. Composition/framing: top-down desk photo. Lighting/mood: soft indoor daylight. Constraints: no clothing, no shoes, no bags, no textile scarf, no text labels, no watermark.
```

## G03 shoe box no shoes

- Expected: no closet item
- Difficulty: negative, box_like_shoe
- Acceptance: No shoes item should be created from shoe box.

```text
Use case: photorealistic-natural. Asset type: closet cutout negative test image. Primary request: a plain cardboard shoe box on a white floor, closed, with no shoes visible. Subject: simple rectangular box only. Composition/framing: centered product-like photo. Lighting/mood: soft studio light. Constraints: no shoes, no clothing, no logo, no readable text, no watermark.
```

## G04 UI screenshot no clear product

- Expected: no closet item
- Difficulty: negative, screenshot, low_product_clarity
- Acceptance: Should ask for clear image or return no usable items.

```text
Use case: ui-mockup. Asset type: closet cutout negative test image. Primary request: a realistic smartphone screenshot of a shopping app feed with many tiny fashion thumbnails and interface buttons, but no single clear large clothing product. Composition/framing: full phone screenshot style, dense UI. Lighting/mood: flat digital screenshot. Text: use small unreadable placeholder text only. Constraints: no brand names, no readable logos, no watermark.
```

## G05 pet wearing tiny costume

- Expected: no closet item
- Difficulty: negative, pet, non_human_garment
- Acceptance: Should be review or rejected, not usable human closet item.

```text
Use case: photorealistic-natural. Asset type: closet cutout negative test image. Primary request: a small dog wearing a tiny costume vest in a living room. Subject: pet is the main subject, costume is small and fitted to pet. Composition/framing: casual indoor photo. Lighting/mood: soft natural light. Constraints: no human clothing laid flat, no shoes, no bag, no text, no watermark.
```
