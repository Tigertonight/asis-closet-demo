# T hard_negatives_textiles_and_decoys

Textile-like objects that should not become closet garments.

## T01 folded towel decoy seed

- Expected: no closet item
- Difficulty: negative, textile_decoy
- Acceptance: No usable closet item should be created.

```text
Use case: photorealistic-natural. Asset type: closet cutout negative test image. Primary request: product-like photo of a folded white bath towel on a white shelf, textile texture but clearly a towel, no clothing, no text. Composition/framing: keep the relevant garment or object fully visible unless the case explicitly asks for crop. Lighting/mood: realistic natural or studio lighting. Constraints: avoid brand logos, readable text, watermarks, and unrelated extra garments unless requested.
```

## T02 curtain fabric decoy

- Expected: no closet item
- Difficulty: negative, fabric
- Acceptance: Curtain should not become dress or skirt.

```text
Use case: photorealistic-natural. Asset type: closet cutout negative test image. Primary request: photo of beige curtains hanging by a window, fabric folds visible, no clothing items, no people, no text. Composition/framing: keep the relevant garment or object fully visible unless the case explicitly asks for crop. Lighting/mood: realistic natural or studio lighting. Constraints: avoid brand logos, readable text, watermarks, and unrelated extra garments unless requested.
```

## T03 blanket on bed decoy

- Expected: no closet item
- Difficulty: negative, blanket
- Acceptance: Blanket should not be saved as clothing.

```text
Use case: photorealistic-natural. Asset type: closet cutout negative test image. Primary request: casual photo of a patterned blanket spread on a bed, no garments, no shoes, no bags, no text. Composition/framing: keep the relevant garment or object fully visible unless the case explicitly asks for crop. Lighting/mood: realistic natural or studio lighting. Constraints: avoid brand logos, readable text, watermarks, and unrelated extra garments unless requested.
```

## T04 apron kitchen item

- Expected: accessory x1
- Difficulty: apron, edge_taxonomy
- Acceptance: Apron can be review/accessory, not top usable.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: photo of a kitchen apron hanging on a hook against a plain wall, full apron visible, no person, no text. Composition/framing: keep the relevant garment or object fully visible unless the case explicitly asks for crop. Lighting/mood: realistic natural or studio lighting. Constraints: avoid brand logos, readable text, watermarks, and unrelated extra garments unless requested.
```

## T05 fabric shopping tote vs handbag

- Expected: bag x1
- Difficulty: bag_boundary, tote
- Acceptance: Tote bag should map to bag if clear.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: product photo of a plain canvas tote bag hanging on a white wall, handles visible, no logo, no text. Composition/framing: keep the relevant garment or object fully visible unless the case explicitly asks for crop. Lighting/mood: realistic natural or studio lighting. Constraints: avoid brand logos, readable text, watermarks, and unrelated extra garments unless requested.
```
