# 男性身材图：移除图内标签

日期：2026-09-11。模式：内置 image_gen 编辑；每张独立调用，未使用 CLI/API fallback。

五张结果经视觉检查：图内底部名称和小底板已移除，外部选项名称与可访问文本保留。原始资源保留，新的无文字资源供 onboarding 和「我的档案」共用。

## 保存位置与提示词

### trapezoid

- 输入：`app/static/selfit/assets/manual-selection/male/body-trapezoid.png`
- 最终资源：`app/static/selfit/assets/manual-selection/male/body-trapezoid-no-label.png`

```text
Use case: precise-object-edit.
Input image 1 is the actual edit target: an existing 328x800 portrait UI body-shape illustration.
Change only the tiny Chinese label "梯形" and its small light-colored rounded plaque directly beneath the man's feet near the bottom. Remove both text and plaque completely and seamlessly restore the surrounding pale cream background there.
Keep every other detail unchanged: same man, identical face/hair/expression, precise body proportions and pose, hands and feet, black tank top and shorts, gold torso geometry with identical shape/position/line width, lighting, shadows, cream background, thin rounded outer border, composition, framing and canvas aspect ratio 328:800. No cropping, no added space, no new text, no redesign, no retouching or changing the person. The illustration must remain the same apart from removing that little bottom label. Return one finished edited image.
```

### triangle

- 输入：`app/static/selfit/assets/manual-selection/male/body-triangle.png`
- 最终资源：`app/static/selfit/assets/manual-selection/male/body-triangle-no-label.png`

```text
Use case: precise-object-edit.
Input image 1 is the actual edit target: an existing 328x800 portrait UI body-shape illustration.
Change only the tiny Chinese label "三角形" and its small light-colored rounded plaque directly beneath the man's feet near the bottom. Remove both text and plaque completely and seamlessly restore the surrounding pale cream background there.
Keep every other detail unchanged: same man, identical face/hair/expression, precise body proportions and pose, hands and feet, black tank top and shorts, gold torso geometry with identical shape/position/line width, lighting, shadows, cream background, thin rounded outer border, composition, framing and canvas aspect ratio 328:800. No cropping, no added space, no new text, no redesign, no retouching or changing the person. The illustration must remain the same apart from removing that little bottom label. Return one finished edited image.
```

### inverted-triangle

- 输入：`app/static/selfit/assets/manual-selection/male/body-inverted-triangle.png`
- 最终资源：`app/static/selfit/assets/manual-selection/male/body-inverted-triangle-no-label.png`

```text
Use case: precise-object-edit.
Input image 1 is the actual edit target: an existing 328x800 portrait UI body-shape illustration.
Change only the tiny Chinese label "倒三角形" and its small light-colored rounded plaque directly beneath the man's feet near the bottom. Remove both text and plaque completely and seamlessly restore the surrounding pale cream background there.
Keep every other detail unchanged: same man, identical face/hair/expression, precise body proportions and pose, hands and feet, black tank top and shorts, gold torso geometry with identical shape/position/line width, lighting, shadows, cream background, thin rounded outer border, composition, framing and canvas aspect ratio 328:800. No cropping, no added space, no new text, no redesign, no retouching or changing the person. The illustration must remain the same apart from removing that little bottom label. Return one finished edited image.
```

### rectangle

- 输入：`app/static/selfit/assets/manual-selection/male/body-rectangle.png`
- 最终资源：`app/static/selfit/assets/manual-selection/male/body-rectangle-no-label.png`

```text
Use case: precise-object-edit.
Input image 1 is the actual edit target: an existing 328x800 portrait UI body-shape illustration.
Change only the tiny Chinese label "矩形" and its small light-colored rounded plaque directly beneath the man's feet near the bottom. Remove both text and plaque completely and seamlessly restore the surrounding pale cream background there.
Keep every other detail unchanged: same man, identical face/hair/expression, precise body proportions and pose, hands and feet, black tank top and shorts, gold torso geometry with identical shape/position/line width, lighting, shadows, cream background, thin rounded outer border, composition, framing and canvas aspect ratio 328:800. No cropping, no added space, no new text, no redesign, no retouching or changing the person. The illustration must remain the same apart from removing that little bottom label. Return one finished edited image.
```

### oval

- 输入：`app/static/selfit/assets/manual-selection/male/body-oval.png`
- 最终资源：`app/static/selfit/assets/manual-selection/male/body-oval-no-label.png`

```text
Use case: precise-object-edit.
Input image 1 is the actual edit target: an existing 328x800 portrait UI body-shape illustration.
Change only the tiny Chinese label "椭圆形" and its small light-colored rounded plaque directly beneath the man's feet near the bottom. Remove both text and plaque completely and seamlessly restore the surrounding pale cream background there.
Keep every other detail unchanged: same man, identical face/hair/expression, precise body proportions and pose, hands and feet, black tank top and shorts, gold torso geometry with identical shape/position/line width, lighting, shadows, cream background, thin rounded outer border, composition, framing and canvas aspect ratio 328:800. No cropping, no added space, no new text, no redesign, no retouching or changing the person. The illustration must remain the same apart from removing that little bottom label. Return one finished edited image.
```

