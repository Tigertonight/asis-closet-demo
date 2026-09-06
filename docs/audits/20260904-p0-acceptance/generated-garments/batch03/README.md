# WABI 入门连衣裙候选（未通过技术门）

目标：`production-backlog.v3.json` 的 P0-CONTENT-WABI-01，以新主衣配方替换一套冗余结构，保持 easy 层级和最终 10 套总数。

使用内置 imagegen，未使用 CLI/API 后备。三版均保存在本目录，没有发布、没有登记为合格单品，亦未减少 43 个新增 + 1 个替换的待办数。

## 实际检查

- 现有 g0470 是多层拼片不对称裙，不能仅凭 WABI 标签当作 easy。
- v1：新生成的圆领、落肩肘袖、无腰带茧形中长裙，装饰克制；但外部有明显灰色光晕。文件为 RGBA、1024×1536、alpha 范围 0–254，不满足干净素材要求。
- v2：尝试只去掉光晕。实际为 RGB，棋盘格已画入像素，没有 alpha。技术门拒绝。
- v3：明确要求删除棋盘格并输出真实 RGBA，仍可见棋盘格背景；不得因看似“透明预览”直接登记通过。
- 自然肌理、宽松茧形可作为 WABI 入门方向的视觉依据，但是否足够可辨仍需搭配后的整图审核及独立盲审。未赋造人格通过分数。

## 完整生成提示词

### v1

Use case: product-mockup. Asset type: one standalone original garment asset for a personal-style outfit catalog. Generate a realistic front-facing ecommerce cutout photograph of a single women's everyday cocoon midi dress, no person or mannequin. Wabi-sabi entry-level aesthetic: quiet natural oatmeal gray-taupe washed linen texture with tiny irregular slubs, soft dropped shoulders and simple elbow-length sleeves, modest shallow round neckline, loose unbelted waist, subtly rounded volume through hips narrowing gently toward calf-length hem. Two discreet curved vertical panel seams and hidden side pockets. Construction must be simple and wearable, with clean finished edges: no patchwork, no torn fabric, no ruffles, no ribbons, no belt, no asymmetrical layers, no jewelry. The visual identity comes from tactile irregular weave and understated cocoon silhouette, not decorative accessories. Entire garment fully visible, straight front view, centered with generous transparent margins, sleeves separate from torso enough to read construction. Genuine transparent background with alpha, soft even studio light, no background shadow, no text, no labels, no logos, no hanger. One garment only, high detail cloth texture.

### v2（编辑 v1）

Use case: background-extraction. Edit target: the attached generated oatmeal cocoon dress product cutout. Remove ONLY the large gray glow/shadow/background surrounding the garment. Preserve exactly the dress shape, sleeves, round neck, woven texture, seam positions, hem, proportions and color. Output a clean hard-edged ecommerce clothing cutout with genuinely fully transparent alpha background all around the dress, fully opaque fabric interior, no floor shadow, no white/gray/black backdrop, no glow, no feathered halo. Entire garment visible with clean natural anti-aliased edges. Do not redesign or add anything.

### v3（编辑 v2）

Background extraction only. Preserve this exact dress unchanged. The checkerboard visible around it is baked into RGB and must be removed, NOT recreated. Deliver an actual transparent RGBA PNG cutout of the dress: exterior pixels alpha zero; cloth interior alpha 255. Do not draw checkerboard tiles, white backdrop, gray backdrop, glow, drop shadow, or any illustration of transparency. Keep neckline and sleeves accurate, entire dress in frame. This is a technical garment asset, not a preview mockup.

## 下一步

先解决透明背景与边缘质量，再登记不可变候选单品，组合低装饰鞋包并审核整图。不得把本次生成动作或提示词目标当作该缺口已完成的证据。

## 预处理入口修复

`prepare_selfit_garment_asset.py` 原先会先转 RGBA 再添加透明画布，导致 RGB 棋盘格或完全不透明的
RGBA 图片也可能仅因新画布留白而通过。现在源图没有透明信息、或源 alpha 完全不透明时直接拒绝，
不输出预处理文件。4 项新增反例/正例与 4 项既有内容 v2 测试共 8 项通过。
此检查只验证真实源透明度，不证明无光晕、无棋盘格残留或服装完整，不能替代人工素材复核。
