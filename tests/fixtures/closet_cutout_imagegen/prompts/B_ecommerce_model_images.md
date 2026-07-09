# B ecommerce_model_images

Product photos with people, hangers, and commerce-like layouts.

## B01 model wearing white shirt seed

- Expected: top x1
- Difficulty: person, skin_occlusion, white_garment
- Acceptance: Extract shirt as top; face and hands should not dominate the cutout.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: a fashion ecommerce photo of a model wearing a crisp white button-up shirt against a light gray studio background. Subject: upper body visible from neck to hips, shirt front clear, sleeves visible, hands relaxed near sides. Composition/framing: centered ecommerce product photo. Lighting/mood: clean soft studio lighting. Constraints: no brand logo, no text, no watermark, no extra clothes.
```

## B02 full body blazer skirt shoes

- Expected: top x1, skirt x1, shoes x1
- Difficulty: person, multi_item, full_body
- Acceptance: Find main clothing pieces; human body may force review but should not create many false items.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: full body ecommerce model wearing a black blazer, cream midi skirt, and black loafers on a plain light gray studio background. Subject: standing model, clothing clearly visible, simple pose. Composition/framing: full outfit centered, full shoes visible. Lighting/mood: soft catalog lighting. Constraints: no logo, no text, no watermark, no bag.
```

## B03 hanger blouse

- Expected: top x1
- Difficulty: hanger, non_garment_attachment
- Acceptance: Top extracted; hanger should be excluded or minimal.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: a silky beige blouse hanging from a simple wooden hanger against a plain white wall. Subject: blouse front visible, sleeves hanging naturally, collar and hem clear. Composition/framing: centered vertical product photo. Lighting/mood: natural soft daylight. Constraints: no person, no logo, no text, no watermark, only one hanger.
```

## B04 model holding overlapping bag

- Expected: bag x1, top x1
- Difficulty: overlap, hand_occlusion, bag
- Acceptance: Bag should be found or marked review; top should not merge with bag.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: ecommerce model wearing a cream cardigan and holding a tan handbag partly overlapping the cardigan. Subject: torso crop, bag in front of body, handle visible, cardigan buttons visible. Composition/framing: centered, plain warm white background. Lighting/mood: soft studio lighting. Constraints: no logo, no text, no watermark.
```

## B05 dark coat on dark background

- Expected: top x1
- Difficulty: dark_on_dark, low_contrast, coat
- Acceptance: Coat outline should be usable or review, not rejected if visible.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: a black wool long coat worn by a model against a charcoal gray studio background. Subject: coat front visible from shoulders to knees, sleeves and lapels clear, model face not emphasized. Composition/framing: centered vertical ecommerce photo. Lighting/mood: soft directional light that reveals black fabric edges. Constraints: no logo, no text, no watermark, no other garments emphasized.
```
