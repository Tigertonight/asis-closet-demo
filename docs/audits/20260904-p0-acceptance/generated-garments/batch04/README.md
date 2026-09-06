# BOLT 主衣补充草稿：内部候选，未发布

初始生成使用 imagegen 技能、内置图像生成工具；未使用 CLI 后备。后续获用户明确允许后执行限定 Python 预处理，见下方续记。
完整初始提示词见 `prompts.json`，技术编辑提示词及输入输出映射见 `edit-prompt.json`。
所有原图和失败编辑图均已逐张查看，并从工具输出目录复制至本目录，未覆盖既有资产。

## 原图观察（不是人格审批）

- `raw/bolt-shaped-tweed-jacket-raw-v1.png`：象牙色细颗粒织纹、酒红细滚边、四枚圆珠扣，
  无领方圆开口、微抬肩和公主线收腰；口袋和短下摆干净，无披肩、刺绣或大蝴蝶结。
  作为 BOLT 典型主衣的生产目标，但与 HEIR 的相邻性明显，必须由整套关系及独立盲审判断。
- `raw/bolt-folded-shoulder-blouse-raw-v1.png`：粉色长袖合腰上衣，偏一侧肩部折片连接胸腰斜褶，
  肩部覆盖，袖身收窄、装饰集中。实图更接近哑光绉感，不以提示词中的缎面代替实际观察。
  轻探索只是目标；与 FLOU/MELT 的边界及实际肩褶体积仍须整图复核，未赋予通过分数。

## 技术检查

原图均为 1254×1254 RGBA。外套以 alpha≥8 统计的上下留白为 3.75%，低于既有注册门槛 5.5%；
上衣有效轮廓留白最低 5.82%，但低透明度杂点触达画布边缘。原图保留真实 alpha；
大多数服装内部 alpha 约 252–254，部分透明像素占比高不等于大面积肉眼可见透明或织物本身透明。
具体像素统计、文件 SHA 与状态见 `asset-inspection.json`。

尝试只修正留白和透明边缘后，两张编辑结果均变成 RGB，棋盘格被绘入像素，故移入 `rejected/`。
未将这些棋盘图转 RGBA 后假称抠图通过，也未调用预处理脚本绕过限制。

## 后续路径

已请求用户确认是否允许项目现有 Python 预处理：仅去除低透明度杂点、等比缩放、增加透明留白，
不重绘衣服。获准后优先处理原 RGBA 文件，而不是不透明的编辑图，再查看实际输出及统一排版大图。
若不允许，则继续使用图像工具修正；不得自动切换其他图像处理途径。

素材通过技术检查后，拟检验：外套 + 真实低领内搭 + 素裤/素裙；肩褶上衣 + 素裤/素裙。
有内外叠穿时须明确 layer_graph，每件最多两次；标题、人格、表达等级均以整图观察决定。
以上为取得预处理授权前的记录，当时未注册 manifest 或增加锚点，数量为 138/160。

## 用户授权后的实际处理与送审

用户确认“允许这种限定的预处理”。已对原 RGBA 文件执行既有 `prepare_selfit_garment_asset.py`，
参数 size=1200、padding=.10、alpha_noise=8；没有处理不透明棋盘图，也没有重绘款式。
结果见 `prepared/`，QA 为本目录两个 `*-qa.v1.json`（副本在 `qa/`）；输出实际逐张查看，
外套最低有效留白 10%，上衣最低有效留白 10%，主体和袖口均完整。
初始 `asset-inspection.json` 保留原图/失败编辑的历史状态，不是最终注册状态。

`scripts/build_selfit_p0_generated_garment_batch04.py` 实际注册内部 manifest 并执行重复生成一致性检查：
`aw-generated-garments-c8e78c03442f4fc69f27`，两件均为单品 ai_candidate，production_approved=false。
最终工作区素材：

- `app/static/selfit/assets/content_v2_drafts/p0-bolt-structure-04/garments/bolt-shaped-tweed-jacket-v1.png`，n0100。
- `app/static/selfit/assets/content_v2_drafts/p0-bolt-structure-04/garments/bolt-folded-shoulder-blouse-v1.png`，n0101。

`gap-recipes.visual-evidence.batch17.rendered.json` 的四张实际整图均已查看。
两套外套方案作为 BOLT typical 候选进入 v40/v41 清单；外套及真实内搭各复用两次，裤/裙不同主衣组合。
两套粉色上衣方案轻探索及 BOLT 证据不足，标 needs_review，未进入候选；不通过提高评分填槽。
完整观察见 `gap-recipes.visual-evidence.batch17.visual-review.json`。

当前总候选 140/160，正式四门通过仍 0。BOLT/HEIR 边界、袖量/衣摆/领口和实际穿着主视觉须继续审核。
`bolt-structure-regression.v1.xml` 记录相关 36 项回归通过；这不代表审美或人格通过。
