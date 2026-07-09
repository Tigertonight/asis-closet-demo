# E color_background_interference

Low contrast, same-color background, patterns, and exposure stress cases.

## E01 white shirt on white bed seed

- Expected: top x1
- Difficulty: white_on_white, low_contrast, wrinkles
- Acceptance: Top should be found; edge may be review but not fully lost.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: a white cotton shirt casually placed on a white bed sheet. Subject: shirt visible with collar, sleeves, and hem; white fabric against white bedding with subtle wrinkles. Composition/framing: top-down phone photo, full shirt visible. Lighting/mood: soft natural window light. Constraints: no person, no text, no watermark, no other clothing.
```

## E02 black jacket on black chair

- Expected: top x1
- Difficulty: black_on_black, low_contrast
- Acceptance: Jacket should be review if edges are uncertain, not hallucinate extra objects.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: a black bomber jacket draped over a black chair in a simple room. Subject: jacket zipper, sleeves, collar, and hem visible but dark against dark chair. Composition/framing: casual phone photo, jacket mostly centered. Lighting/mood: soft side light revealing edges. Constraints: no person, no text, no watermark.
```

## E03 floral blouse on floral background

- Expected: top x1
- Difficulty: busy_background, pattern
- Acceptance: Blouse should be separated from floral background; heavy residue is bad.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: a colorful floral blouse laid flat on a floral patterned fabric background. Subject: blouse has a distinct collar and sleeves but similar floral colors to the background. Composition/framing: top-down photo, full blouse visible. Lighting/mood: soft daylight. Constraints: no person, no text, no watermark, no other clothes.
```

## E04 overexposed yellow skirt

- Expected: skirt x1
- Difficulty: overexposure, bright_color
- Acceptance: Skirt shape should remain visible; overexposed edge can be review.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: a bright yellow mini skirt on a white background photographed with slightly overexposed sunlight. Subject: skirt waistband and hem visible, bright fabric with some blown highlights. Composition/framing: centered product-like photo, full skirt visible. Lighting/mood: strong sunny window light, high exposure. Constraints: no person, no text, no watermark.
```

## E05 red bag on red wall

- Expected: bag x1
- Difficulty: same_color_background, bag
- Acceptance: Bag body should be detected; handle may be review.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: a red handbag placed in front of a matte red wall, with the bag slightly darker than the wall. Subject: handbag front and handles visible, same-color background challenge. Composition/framing: centered product photo, full bag visible. Lighting/mood: soft side light for subtle edge definition. Constraints: no person, no text, no watermark.
```
