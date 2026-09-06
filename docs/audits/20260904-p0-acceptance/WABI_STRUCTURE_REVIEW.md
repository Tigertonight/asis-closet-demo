# WABI 连衣装结构缺口：探索级替换候选

日期：2026-09-05。状态：生产侧整图复核完成，但历史拒绝原因未消除，暂不进入候选清单；不计入正式通过量。

## 版本与替换对象

- 基准：`anchor-candidates.v16.json` 与 `p0-gap-staging.v6.json`。
- 被替换项：`outfit_void_master_14_v1__p0-persona-wabi`（探索级裙装）。
- 新候选：`outfit_wabi_p0-wabi-structure-05_01`。
- 配方与渲染记录：`gap-recipes.visual-evidence.batch05.json`、`gap-recipes.visual-evidence.batch05.rendered.json`。
- 主衣：`garment_wabi_dress_0470`；支撑单品为成对乐福鞋 `garment_mute_shoes_0004`、托特包 `garment_jade_bag_0284`。
- 父配方：`main-recipe-04951de142d1f5e2c350b803`。
- 实际展示图：`app/static/selfit/assets/content_v2/layouts/unified-flatlay-v1/5505a60f6f9190eaeb19d7db.webp`。
- 图片 SHA-256：`2e4d3c2e72eb2b6a32c4168053298dd3ff7fc95ca351037d7cfe183ebc3d1232`。

仅提出替换；本轮未改写 v16 清单、正式池、历史审核或历史盲审结论。

## 实际整图观察

连衣裙完整显示；自然粗纹理、非对称拼片、收拢裙摆集中在唯一主衣上，鞋包没有另设强烈装饰主角。
鞋是一双，包带和裙摆未见明显裁切；没有额外穿着内外层，不能将裙身拼片误填成外套叠穿。
主衣较强的体量和拼片复杂度不宜归为 easy；探索级目标比入门级合理。
这些是生产侧可见观察，不是独立人格命中结论。

场景仍需重点审核：它不是晚礼服，但无袖长裙仅适合温暖天气下的休闲日常，不能凭 `autumn` 标签
宣称适合全季通勤或寒冷天气。若审核认为接近主题服装，须返工，不能为补齐连衣装结构而强行准入。
人格辨识需确认来自粗纹理与不规则结构，而非仅凭灰褐色或命名；不能由生产者代填独立答卷。
用户端发布前还须重写内部标题和说明，当前渲染记录仍是 draft。

## 替换后约束预检（不是正式清单验收）

从上述基准读取真实选中项，移除被替换项并以新连衣装占用相同 explore 位置，结果：

| 项目 | 预检结果 |
|---|---|
| WABI 数量 | 10 |
| 表达层级 | easy 4 / typical 4 / explore 2 |
| 主结构 | pants 5 / skirt 4 / dress 1 |
| 同主单品最高次数 | 1 |
| 同当前家族最高次数（含 singleton） | 1 |
| 新主衣组合与其他已选锚点重复 | 0 |

无需强求连衣装必须是 easy。现有 backlog 的 easy 替换只是分配方案，不是验收要求。
本方案可避免使用有假透明底的新生成素材，但仍须通过当前图片四门审核，才可纳入下一版候选清单及盲审包。
上述 10 套的结构潜在可行不代表全局 160 套已齐，也不代表家族人工审核覆盖率已经通过。

## 历史反证复核：本次不采纳

回查 `gap-recipes.batch01.rendered.json` 的 `outfit_wabi_p0-gap-01_04`，发现使用同一件
`garment_wabi_dress_0470`。`scripts/compile_selfit_p0_gap_visual_review.py` 中留存的拒绝理由是
“主裙体积和层片过强，更接近主题化造型，不符合 everyday_with_statement”。
本轮同时重新查看历史整图 `45de7616aa827316ac74710f.webp` 与新整图，确认裙身结构完全未变。
由低跟鞋/软包换成乐福鞋/托特包只改变辅助单品，不能直接证明主裙主题化问题已经消除。

因此本次不将其升级为 ai_candidate、不纳入 v16 后继清单，也不减少 WABI 的结构缺口。
上面的结构计数仅说明 explore 位置替换在组合约束上可行，不说明这件裙子可用。
下一步须寻找或生产主衣体量更克制、少层片的连衣装；可以是 explore，无需限定 easy。
