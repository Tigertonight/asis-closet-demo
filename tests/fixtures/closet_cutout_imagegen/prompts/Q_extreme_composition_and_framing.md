# Q extreme_composition_and_framing

Unusual crop, perspective, rotation, scale, and object placement.

## Q01 tiny centered shirt lots of empty space seed

- Expected: top x1
- Difficulty: tiny_subject, scale
- Acceptance: Should find item or reject for too small, but not hallucinate.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: a very small red t-shirt centered in a large white image with lots of empty space around it, product photo, no text. Composition/framing: keep the relevant garment or object fully visible unless the case explicitly asks for crop. Lighting/mood: realistic natural or studio lighting. Constraints: avoid brand logos, readable text, watermarks, and unrelated extra garments unless requested.
```

## Q02 garment at image edge

- Expected: top x1
- Difficulty: edge_crop, partial
- Acceptance: Review due to edge crop.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: a green sweater partly cut off by the left edge of the image on a white background, only 80 percent visible, no text. Composition/framing: keep the relevant garment or object fully visible unless the case explicitly asks for crop. Lighting/mood: realistic natural or studio lighting. Constraints: avoid brand logos, readable text, watermarks, and unrelated extra garments unless requested.
```

## Q03 rotated pants diagonal

- Expected: bottom x1
- Difficulty: rotation, diagonal
- Acceptance: Pants detected despite diagonal orientation.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: product photo of blue jeans laid diagonally at a 35 degree angle on a white background, full jeans visible, no text. Composition/framing: keep the relevant garment or object fully visible unless the case explicitly asks for crop. Lighting/mood: realistic natural or studio lighting. Constraints: avoid brand logos, readable text, watermarks, and unrelated extra garments unless requested.
```

## Q04 perspective shoes closeup

- Expected: shoes x1
- Difficulty: perspective, closeup, shoes
- Acceptance: Shoes review if too cropped; not merge with floor.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: close perspective smartphone photo of sneakers on the floor, shoes very large in foreground, full pair mostly visible, no feet, no text. Composition/framing: keep the relevant garment or object fully visible unless the case explicitly asks for crop. Lighting/mood: realistic natural or studio lighting. Constraints: avoid brand logos, readable text, watermarks, and unrelated extra garments unless requested.
```

## Q05 wide panorama clothing rack

- Expected: top x3
- Difficulty: wide_image, rack, multi_item
- Acceptance: Should handle aspect ratio or review; not crash.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: wide horizontal photo of a clothing rack with three shirts hanging separately against a plain wall, full shirts visible, no text. Composition/framing: keep the relevant garment or object fully visible unless the case explicitly asks for crop. Lighting/mood: realistic natural or studio lighting. Constraints: avoid brand logos, readable text, watermarks, and unrelated extra garments unless requested.
```
