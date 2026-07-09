# M demographic_and_body_diversity

Ensure garment extraction works across genders, ages, sizes, and body proportions.

## M01 mens suit full body seed

- Expected: top x1, bottom x1, shoes x1
- Difficulty: menswear, suit, full_body
- Acceptance: Suit jacket and trousers classified sensibly; no person-heavy usable item.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: full body ecommerce photo of an adult man wearing a navy suit, white shirt, and black dress shoes, plain gray studio background, no tie logo, no text. Composition/framing: keep the relevant garment or object fully visible unless the case explicitly asks for crop. Lighting/mood: realistic natural or studio lighting. Constraints: avoid brand logos, readable text, watermarks, and unrelated extra garments unless requested.
```

## M02 plus size dress model

- Expected: dress x1
- Difficulty: plus_size, dress, person
- Acceptance: Dress detected without penalizing body shape.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: full body ecommerce photo of a plus-size woman wearing a black wrap dress, plain light studio background, full dress visible, no text, no watermark. Composition/framing: keep the relevant garment or object fully visible unless the case explicitly asks for crop. Lighting/mood: realistic natural or studio lighting. Constraints: avoid brand logos, readable text, watermarks, and unrelated extra garments unless requested.
```

## M03 elderly model cardigan trousers

- Expected: top x1, bottom x1
- Difficulty: older_adult, cardigan, trousers
- Acceptance: Garments detected across age styling.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: studio photo of an older adult wearing a beige cardigan and brown trousers, full body visible, simple neutral background, no text. Composition/framing: keep the relevant garment or object fully visible unless the case explicitly asks for crop. Lighting/mood: realistic natural or studio lighting. Constraints: avoid brand logos, readable text, watermarks, and unrelated extra garments unless requested.
```

## M04 child jacket negative review

- Expected: top x1
- Difficulty: child_clothing, size_edge
- Acceptance: Can be review; product may not be adult closet item.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: catalog photo of a child-size puffer jacket laid flat on white background, small proportions, no person, no logo, no text. Composition/framing: keep the relevant garment or object fully visible unless the case explicitly asks for crop. Lighting/mood: realistic natural or studio lighting. Constraints: avoid brand logos, readable text, watermarks, and unrelated extra garments unless requested.
```

## M05 maternity dress

- Expected: dress x1
- Difficulty: maternity, dress, person
- Acceptance: Dress detected despite non-standard silhouette.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: ecommerce photo of a pregnant model wearing a soft blue maternity dress, full body, plain light background, no text, no watermark. Composition/framing: keep the relevant garment or object fully visible unless the case explicitly asks for crop. Lighting/mood: realistic natural or studio lighting. Constraints: avoid brand logos, readable text, watermarks, and unrelated extra garments unless requested.
```
