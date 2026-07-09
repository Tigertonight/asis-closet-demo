# I human_pose_and_occlusion

Human poses that partially hide garments and often confuse masks with skin, hair, or hands.

## I01 crossed arms blazer seed

- Expected: top x1
- Difficulty: pose, arm_occlusion, person
- Acceptance: Blazer should be found; crossed arms should not become part of garment.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: a fashion ecommerce model wearing a camel blazer with arms crossed in front of the body against a plain light gray background, torso visible, blazer lapels and sleeves clear, no logo, no text, no watermark. Composition/framing: keep the relevant garment or object fully visible unless the case explicitly asks for crop. Lighting/mood: realistic natural or studio lighting. Constraints: avoid brand logos, readable text, watermarks, and unrelated extra garments unless requested.
```

## I02 hands in hoodie pocket

- Expected: top x1
- Difficulty: pose, hand_occlusion, hoodie
- Acceptance: Hoodie remains one top; hands inside pocket should not create holes.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: a model wearing an oversized navy hoodie with both hands inside the front pocket, plain studio background, full hoodie visible from hood to hem, no logo, no text, no watermark. Composition/framing: keep the relevant garment or object fully visible unless the case explicitly asks for crop. Lighting/mood: realistic natural or studio lighting. Constraints: avoid brand logos, readable text, watermarks, and unrelated extra garments unless requested.
```

## I03 seated trousers bent knees

- Expected: bottom x1
- Difficulty: pose, seated, bent_pants
- Acceptance: Trousers should be review if legs are folded, not split into two items.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: a seated model wearing beige trousers, knees bent, simple studio chair, trousers clearly visible but folded by pose, plain background, no logo, no text, no watermark. Composition/framing: keep the relevant garment or object fully visible unless the case explicitly asks for crop. Lighting/mood: realistic natural or studio lighting. Constraints: avoid brand logos, readable text, watermarks, and unrelated extra garments unless requested.
```

## I04 hair covering scarf and coat

- Expected: top x1, accessory x1
- Difficulty: hair_occlusion, scarf, coat
- Acceptance: Coat/scarf can be review; hair should not be saved as accessory.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: a model with long dark hair wearing a wool coat and a scarf, hair partially covering the scarf edges, plain winter ecommerce background, no text, no watermark. Composition/framing: keep the relevant garment or object fully visible unless the case explicitly asks for crop. Lighting/mood: realistic natural or studio lighting. Constraints: avoid brand logos, readable text, watermarks, and unrelated extra garments unless requested.
```

## I05 walking pose skirt motion

- Expected: skirt x1, shoes x1
- Difficulty: motion_pose, skirt, full_body
- Acceptance: Skirt should be detected despite asymmetric walking shape.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: full body fashion photo of a model walking, wearing a pleated midi skirt and loafers, skirt slightly moving, clean street-style neutral wall background, no logo, no watermark. Composition/framing: keep the relevant garment or object fully visible unless the case explicitly asks for crop. Lighting/mood: realistic natural or studio lighting. Constraints: avoid brand logos, readable text, watermarks, and unrelated extra garments unless requested.
```
