# J layering_and_nested_garments

Layered outfits where visible garments overlap and should not be merged incorrectly.

## J01 shirt under vest seed

- Expected: top x2
- Difficulty: layering, vest, shirt
- Acceptance: Vest and shirt may become two tops or one review item; no false bottom.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: top-down flatlay on white background with a white button-up shirt under a black sleeveless knit vest, both garments visible as layered outfit, no body, no text, no watermark. Composition/framing: keep the relevant garment or object fully visible unless the case explicitly asks for crop. Lighting/mood: realistic natural or studio lighting. Constraints: avoid brand logos, readable text, watermarks, and unrelated extra garments unless requested.
```

## J02 coat over dress on model

- Expected: top x1, dress x1
- Difficulty: layering, coat, dress, person
- Acceptance: Detect coat/dress or mark review; should not create many fragments.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: full body ecommerce model wearing a beige trench coat open over a floral midi dress, plain studio background, full outfit and shoes visible, no text, no watermark. Composition/framing: keep the relevant garment or object fully visible unless the case explicitly asks for crop. Lighting/mood: realistic natural or studio lighting. Constraints: avoid brand logos, readable text, watermarks, and unrelated extra garments unless requested.
```

## J03 scarf on sweater flatlay

- Expected: top x1, accessory x1
- Difficulty: layering, scarf, overlap
- Acceptance: Scarf should not merge fully into sweater.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: top-down flatlay on white background with a gray sweater and a red scarf draped across the neckline, sweater mostly visible, no person, no text, no watermark. Composition/framing: keep the relevant garment or object fully visible unless the case explicitly asks for crop. Lighting/mood: realistic natural or studio lighting. Constraints: avoid brand logos, readable text, watermarks, and unrelated extra garments unless requested.
```

## J04 open cardigan over camisole

- Expected: top x2
- Difficulty: layering, thin_straps, cardigan
- Acceptance: Camisole straps and cardigan edges are a challenge; review acceptable.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: ecommerce torso photo of a model wearing an open cream cardigan over a black camisole with thin straps, plain light background, no logo, no text. Composition/framing: keep the relevant garment or object fully visible unless the case explicitly asks for crop. Lighting/mood: realistic natural or studio lighting. Constraints: avoid brand logos, readable text, watermarks, and unrelated extra garments unless requested.
```

## J05 belt over blazer dress

- Expected: dress x1, accessory x1
- Difficulty: layering, belt, dress
- Acceptance: Main garment should remain one dress; belt can be accessory or ignored.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: studio product photo of a black blazer dress on a mannequin with a thin belt around the waist, plain white background, no logo, no text. Composition/framing: keep the relevant garment or object fully visible unless the case explicitly asks for crop. Lighting/mood: realistic natural or studio lighting. Constraints: avoid brand logos, readable text, watermarks, and unrelated extra garments unless requested.
```
