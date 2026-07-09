# K mirror_selfie_and_real_scenes

User-generated mirror photos and messy real rooms.

## K01 mirror selfie full outfit seed

- Expected: top x1, bottom x1, shoes x1
- Difficulty: mirror_selfie, phone_occlusion, real_room
- Acceptance: Phone/face should not be extracted; outfit may be review.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: realistic mirror selfie in a bedroom, person wearing a black t-shirt, blue jeans, and white sneakers, phone covers part of face, cluttered room but outfit visible, no readable text. Composition/framing: keep the relevant garment or object fully visible unless the case explicitly asks for crop. Lighting/mood: realistic natural or studio lighting. Constraints: avoid brand logos, readable text, watermarks, and unrelated extra garments unless requested.
```

## K02 closet door reflection dress

- Expected: dress x1
- Difficulty: mirror, reflection, dress
- Acceptance: Dress found despite reflection and background clutter.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: mirror selfie in front of a closet door, person wearing a green dress, reflection visible, room background with shelves, no text, no watermark. Composition/framing: keep the relevant garment or object fully visible unless the case explicitly asks for crop. Lighting/mood: realistic natural or studio lighting. Constraints: avoid brand logos, readable text, watermarks, and unrelated extra garments unless requested.
```

## K03 bathroom mirror coat

- Expected: top x1
- Difficulty: mirror_selfie, lighting, coat
- Acceptance: Coat should be detected or review, phone should not be item.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: bathroom mirror selfie of a person wearing a long black coat, bright overhead light, phone in hand, tiled background, no text. Composition/framing: keep the relevant garment or object fully visible unless the case explicitly asks for crop. Lighting/mood: realistic natural or studio lighting. Constraints: avoid brand logos, readable text, watermarks, and unrelated extra garments unless requested.
```

## K04 outdoor street candid outfit

- Expected: top x1, bottom x1
- Difficulty: street_photo, busy_background, person
- Acceptance: Main garments found with busy outdoor background.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: street style photo of a person walking past storefronts wearing a red sweater and khaki trousers, background moderately busy, no readable signs, no watermark. Composition/framing: keep the relevant garment or object fully visible unless the case explicitly asks for crop. Lighting/mood: realistic natural or studio lighting. Constraints: avoid brand logos, readable text, watermarks, and unrelated extra garments unless requested.
```

## K05 laundry pile with visible shirt

- Expected: top x1
- Difficulty: messy_scene, occlusion, laundry
- Acceptance: Only clear shirt should be review; no many false items.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: casual photo of a laundry pile on a bed with one blue shirt clearly visible on top, other fabrics partly visible, indoor light, no person, no text. Composition/framing: keep the relevant garment or object fully visible unless the case explicitly asks for crop. Lighting/mood: realistic natural or studio lighting. Constraints: avoid brand logos, readable text, watermarks, and unrelated extra garments unless requested.
```
