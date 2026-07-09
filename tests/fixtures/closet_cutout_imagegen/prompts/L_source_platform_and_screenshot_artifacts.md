# L source_platform_and_screenshot_artifacts

Images copied from social feeds, screenshots, posters, and collages.

## L01 xhs style note cover collage seed

- Expected: top x1, bottom x1
- Difficulty: screenshot, collage, text_noise
- Acceptance: Main clothing should be found if large enough; UI text ignored.

```text
Use case: ui-mockup. Asset type: closet cutout test image. Primary request: a realistic social media note cover collage showing one large outfit flatlay with a sweater and jeans, small decorative stickers and unreadable UI text around edges, no brand names. Composition/framing: keep the relevant garment or object fully visible unless the case explicitly asks for crop. Lighting/mood: realistic natural or studio lighting. Constraints: avoid brand logos, readable text, watermarks, and unrelated extra garments unless requested.
```

## L02 shopping product grid screenshot

- Expected: no closet item
- Difficulty: screenshot, tiny_products, negative
- Acceptance: Should not create usable items from tiny thumbnails.

```text
Use case: ui-mockup. Asset type: closet cutout negative test image. Primary request: smartphone shopping app screenshot with a grid of many tiny clothing product thumbnails, interface bars and unreadable placeholder text, no single large item, no brand names. Composition/framing: keep the relevant garment or object fully visible unless the case explicitly asks for crop. Lighting/mood: realistic natural or studio lighting. Constraints: avoid brand logos, readable text, watermarks, and unrelated extra garments unless requested.
```

## L03 poster model with big typography

- Expected: dress x1
- Difficulty: poster, text_occlusion, person
- Acceptance: Dress extracted or review; typography ignored.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: fashion poster style image with a model wearing a red dress and large abstract typography shapes in the background, text unreadable, model full body, no brand logo. Composition/framing: keep the relevant garment or object fully visible unless the case explicitly asks for crop. Lighting/mood: realistic natural or studio lighting. Constraints: avoid brand logos, readable text, watermarks, and unrelated extra garments unless requested.
```

## L04 watermarked ecommerce image

- Expected: bag x1
- Difficulty: watermark, commerce, bag
- Acceptance: Bag should be item; watermark not saved.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: ecommerce product image of a white handbag on a plain background with faint diagonal generic watermark pattern, no readable brand, bag centered. Composition/framing: keep the relevant garment or object fully visible unless the case explicitly asks for crop. Lighting/mood: realistic natural or studio lighting. Constraints: avoid brand logos, readable text, watermarks, and unrelated extra garments unless requested.
```

## L05 video cover with play icon

- Expected: top x1
- Difficulty: video_cover, overlay_icon
- Acceptance: Overlay icon should not be mask foreground.

```text
Use case: photorealistic-natural. Asset type: closet cutout test image. Primary request: social video cover image of a person wearing a denim jacket, with a translucent play button overlay in the center and small unreadable UI elements, no watermark. Composition/framing: keep the relevant garment or object fully visible unless the case explicitly asks for crop. Lighting/mood: realistic natural or studio lighting. Constraints: avoid brand logos, readable text, watermarks, and unrelated extra garments unless requested.
```
