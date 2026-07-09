# F capture_quality_problems

Real user upload defects: blur, low resolution, dark, crop, and occlusion.

## F01 casual phone photo wrinkled shirt on bed seed

- Expected: top x1
- Difficulty: phone_photo, wrinkles, bed_background
- Acceptance: Top can be usable or review, but should not fail if clear enough.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: casual smartphone photo of a wrinkled blue shirt lying on a beige bedspread. Subject: shirt fully visible but not perfectly arranged, sleeves slightly folded. Composition/framing: handheld top-down photo with mild perspective distortion. Lighting/mood: indoor daylight, natural shadows. Constraints: no person, no text, no watermark, no other clothing.
```

## F02 motion blurred hoodie

- Expected: top x1
- Difficulty: blur, review_expected
- Acceptance: Should route to review or rejected if too blurry; no false high confidence.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: a slightly motion-blurred smartphone photo of a gray hoodie on a wooden floor. Subject: hoodie shape still visible, hood and sleeves discernible, image blur noticeable. Composition/framing: top-down casual photo, full hoodie inside frame. Lighting/mood: indoor warm light. Constraints: no person, no text, no watermark, no other clothes.
```

## F03 dark photo trousers

- Expected: bottom x1
- Difficulty: low_light, noise
- Acceptance: Likely review; should not invent additional items.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: low-light noisy smartphone photo of black trousers lying on a dark gray carpet. Subject: trousers mostly visible, waistband and both legs discernible but dim. Composition/framing: casual top-down photo. Lighting/mood: underexposed room light, mild image noise. Constraints: no person, no text, no watermark, no other clothes.
```

## F04 cropped shoes

- Expected: shoes x1
- Difficulty: cropped_subject, partial_item
- Acceptance: Shoes should be review due to missing parts.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: casual smartphone photo of a pair of sneakers where one shoe is partly cropped by the image edge. Subject: pair of white sneakers on a tiled floor, one toe and one heel cut off by the frame. Composition/framing: imperfect user upload, close crop. Lighting/mood: indoor light. Constraints: no foot, no person, no text, no watermark.
```

## F05 hand occluded bag

- Expected: bag x1
- Difficulty: occlusion, hand, review_expected
- Acceptance: Bag may be review; hand should not be saved as garment.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: smartphone photo of a beige handbag partly covered by a person's hand while holding it up. Subject: bag body visible but one side and handle partly occluded by hand, neutral wall background. Composition/framing: casual close shot. Lighting/mood: soft indoor daylight. Constraints: no face, no logo, no text, no watermark.
```
