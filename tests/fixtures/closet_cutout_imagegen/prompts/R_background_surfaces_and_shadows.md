# R background_surfaces_and_shadows

Different surfaces and shadows that can leak into masks.

## R01 shirt on wooden floor shadow seed

- Expected: top x1
- Difficulty: wood_floor, shadow
- Acceptance: Shadow should not become part of cutout.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: top-down photo of a white shirt on a warm wooden floor with a soft natural cast shadow, full shirt visible, no person, no text. Composition/framing: keep the relevant garment or object fully visible unless the case explicitly asks for crop. Lighting/mood: realistic natural or studio lighting. Constraints: avoid brand logos, readable text, watermarks, and unrelated extra garments unless requested.
```

## R02 dress on grass

- Expected: dress x1
- Difficulty: grass_background, texture
- Acceptance: Grass should not leak heavily into dress mask.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: casual photo of a blue summer dress laid flat on green grass, full dress visible, outdoor daylight, no person, no text. Composition/framing: keep the relevant garment or object fully visible unless the case explicitly asks for crop. Lighting/mood: realistic natural or studio lighting. Constraints: avoid brand logos, readable text, watermarks, and unrelated extra garments unless requested.
```

## R03 black boots on concrete

- Expected: shoes x1
- Difficulty: concrete, shadow, dark_item
- Acceptance: Boot outline clean enough or review.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: product-like photo of black ankle boots on gray concrete with visible shadow, both boots full frame, no legs, no text. Composition/framing: keep the relevant garment or object fully visible unless the case explicitly asks for crop. Lighting/mood: realistic natural or studio lighting. Constraints: avoid brand logos, readable text, watermarks, and unrelated extra garments unless requested.
```

## R04 bag on reflective table

- Expected: bag x1
- Difficulty: reflection, bag
- Acceptance: Reflection should not be included as bag body.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: a red handbag standing on a glossy reflective table, plain background, reflection visible below, no text, no logo. Composition/framing: keep the relevant garment or object fully visible unless the case explicitly asks for crop. Lighting/mood: realistic natural or studio lighting. Constraints: avoid brand logos, readable text, watermarks, and unrelated extra garments unless requested.
```

## R05 transparent hanger shadow

- Expected: top x1
- Difficulty: hanger_shadow, shadow
- Acceptance: Garment extracted; hanger/shadow minimized.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: white blouse on a clear plastic hanger against a white wall, soft hanger shadow visible, no person, no text. Composition/framing: keep the relevant garment or object fully visible unless the case explicitly asks for crop. Lighting/mood: realistic natural or studio lighting. Constraints: avoid brand logos, readable text, watermarks, and unrelated extra garments unless requested.
```
