# Selfit 16 人格单品与穿搭生图生产计划

## 目标

把现有“穿搭图片集”逐步转为可用于衣橱、搭配、推荐和试穿的内容资产：每个可发布穿搭都能追溯到具体透明单品 PNG，每件单品都有结构化属性、人格亲和度与质量记录。

## 已建立的生产资产

- V2 数据 Schema：`app/static/selfit/data/content-pool.schema.v2.json`
- 16 人格视觉约束与三类 Prompt：`app/static/selfit/data/content-generation-prompts.v1.json`
- 现有内容迁移器：`scripts/migrate_selfit_content_pool_v2.py`
- 透明图预处理器：`scripts/prepare_selfit_garment_asset.py`
- 穿搭平铺生成器：`scripts/build_selfit_outfit_flatlay.py`
- Prompt 队列生成器：`scripts/build_selfit_imagegen_queue.py`
- 第一套样板：`app/static/selfit/data/capsules/mute-01.json`

## 单个资产生产链

1. 从 Prompt 队列取一个 job；不同单品必须分别调用一次 built-in imagegen。
2. 保存 imagegen 原图为 `*-raw-v1.png`，不覆盖原始生成结果。
3. 运行透明图预处理器：清除 alpha<8 的边缘噪声，裁切有效主体，置入 1200×1200 透明画布，默认四边 10% 留白。
4. 输出 `*-v1.png` 和同名 `.qa.json`。
5. 人工检查品类、颜色、材质、结构、边缘、左右完整性和是否多出物件。
6. 将单品写入 capsule manifest；每件单品都要包含 16 人格亲和度、场景、季节、表达和试穿槽位。
7. 用确定性平铺脚本生成 1200×1500 WebP，不让模型擅自修改单品。
8. 将 capsule 合并进 `content-pool.v2.draft.json`，通过 Schema 和推荐兼容测试。
9. 完成试穿 QA 后，才把 annotation 状态从 `designer_reviewed` 提升到 `published`。

## 生图 Prompt 结构

单品使用 `product-mockup`，核心约束如下：

```text
Use case: product-mockup
Asset type: Selfit wardrobe garment cutout
Primary request: create exactly one {人格、品类、版型、细节明确的单品}
Scene/backdrop: genuinely transparent background
Subject: exactly one isolated garment, front-facing, naturally shaped as if invisibly supported
Style/medium: photorealistic premium fashion e-commerce product photography
Composition/framing: centered square canvas, complete silhouette, 12% padding, no crop
Lighting/mood: soft neutral studio light
Color palette: {人格色彩规则}
Materials/textures: {具体材质}
Constraints: actual transparent alpha; no person, mannequin, hanger, floor, text, logo or watermark
Avoid: fake white/checkerboard background; clipped sleeves, hems, handles or shoe toes; duplicate items
```

穿搭平铺 Prompt 只用于需要 AI 做视觉排版的备选方案。正式数据库优先使用确定性平铺脚本，确保输入单品一件不少、一件不改。

试穿 Prompt 必须使用 `identity-preserve`：仅替换画面中可见且兼容的服装区域；保留脸、身形、姿势、头发、手部、背景和镜头，不要求未入镜部位全部出现。

完整可复制 Prompt 和 16 人格差异变量以 JSON 保存，不在多个文档重复维护。

## 生产波次

### Wave 0：MUTE 样板（已完成首套）

- 4 件：烟白衬衫、炭灰直筒裤、黑色乐福鞋、灰褐托特包。
- 1 套：烟白直线通勤。
- 验证：真实透明 alpha、10% 安全留白、包鞋完整、确定性组合、V2 推荐兼容。

### Wave 1：辨识锚点

- EASE、EDGE、JADE，每型先做 5 件标志单品与 1 套入门穿搭。
- 目的：验证柔和松弛、甜酷轻亚、东方秩序能否仅凭服装盲审区分。

### Wave 2：相邻风格拆分

- ICED、HEIR、WABI、NOIR。
- 重点处理 MUTE/ICED、HEIR/EASE、WABI/VOID、NOIR/EDGE 的相似边界。

### Wave 3：浪漫与复古梯度

- MELT、FLOU、BOLT、FILM。
- 重点用廓形、材质和完成度区分，不只依赖粉色、蕾丝或复古滤镜。

### Wave 4：高难人格

- NEON、LOOP、VOID、OOPS。
- LOOP 用“可转换且高完成度”表达；VOID 用“有控制的未完成”；OOPS 必须有重复色或母题，避免真随机。

## P0 生产量

- Prompt 队列首批 80 件：16 人格 × 5 件标志单品。
- 首轮 16 套：每人格 1 套可拆、可替换、可试穿的样板穿搭。
- 每套至少覆盖主衣、下装或连衣装、鞋、包/配饰 4 个槽位。
- 样板通过后扩到每人格 12 件单品和 3 套配方，共 192 个单品记录、48 套穿搭。

## 自动验收

- PNG 必须是 RGBA，alpha 同时包含 0 和 255。
- 1200×1200，主体不得触边，四边最小安全留白不少于 5.5%，目标 10%。
- 单品图只能包含一个数据库单品；鞋允许“一双”作为一个单品。
- 包提手、帽檐、袖口、裤脚、鞋头必须完整。
- 平铺图必须包含 recipe 的全部 `garment_ids` 且各出现一次。
- Schema 校验通过；V2 池能被当前 Suit 推荐器读取。
- 发布前再进行视觉盲审和真实试穿 QA，自动通过不代表可直接上线。

## 版本与失败处理

- 生成失败不覆盖：保留 `raw-v1`，重生使用 `raw-v2`。
- 单纯 alpha 噪声使用预处理器；形状、材质、颜色错误必须重新生成，不能用裁切掩盖。
- 彩边、伪背景、额外配饰、图案漂移标记为 `rejected`。
- Capsule 未完成全部验证前，只进入 `content-pool.v2.draft.json`，不替换线上 V1。
