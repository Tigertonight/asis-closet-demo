# Selfit P0 验收工作区

## 2026-09-05 当前状态（替代下方历史结论）

最新重选 `anchor-candidates.v14.json` 已发现外部版本变化：当前款式家族表 SHA 为
`73d839eaccf4f94aac0a8fcaf49bfe07c86cc8da683376debbf1de753f5f13ab`，
原 v4 staging 绑定旧家族表。`p0-gap-staging.v5.json` 已按当前表重算 staging 单品家族。
重选时 1,169 套正式库存均被整图校验拦截；抽查 `outfit_mute_master_01`，配方指纹一致，
但当前图片 SHA 为 `16230f64b352f55793eb967cbaa190d47ac792acb1da0cda9f6b74bb5024f32c`，
审核记录为 `ce6d45b57817eeff0796b56bbf809e4517bf99ca5dceb603b34a47e93786ca80`。
因此下方 117 套是历史版本结果，不能用于当前放行；v14 仅选出 7 条 staging 行，也尚未通过完整审核。
待排查图片变化来源并复核当前图片，禁止直接补写旧审核 SHA 使之通过。

新增 `stage_selfit_p0_persona_revisions.py` 可将有整图证据的人格纠正保存为独立待审版本，
保留原记录及父配方，并清除旧审核。2 项定向测试通过；对旧 v13/v4 输入的实跑被版本校验拦截，未产生迁移结果。

盲审门禁现已从逐条答卷重新计算命中率，核对样本 token / outfit ID 唯一性、
当前锚点覆盖、人格归属和内容指纹；汇总统计不一致、非法数值、独立性或隐藏答案声明缺失均拒绝放行。
两个评分工具均保留声明字段，统一审计与运行时使用同一校验。
本轮相关回归 25 passed（锚点准入、P0 验收工具、独立盲审工具），尚无真实独立盲审结果。

当前候选为 `anchor-candidates.v13.json`，放行报告为 `release-report.v9.json`。
选择器按当前整图人格分数、日常场景、不同主衣组合和父配方筛选，得到 117 套；
`persona-preflight.v2.json` 对这 117 套的预检通过只证明筛选条件一致，不证明人工验收通过。
`production-backlog.v2.json` 记录当前选择结果下的 43 个待补位置；这不是全局最优供给不足的数学证明。

放行仍未通过。跨人格重选还需要正式修改内容归属并重新审核；候选清单中的目标人格不能替代原始内容记录。
四门审核、独立盲审、完整浏览器和性能证据仍待完成。

本次修复了一个会虚增丰富度的问题：仅更换鞋包的相同主衣组合不能当作不同父配方。
渲染器为主衣组合生成稳定父配方标识，选择器排除重复组合，放行校验再次拦截伪造不同父 ID 的配饰变体。
历史稿件保持原样，但必须按新规则重建后才能用于验收。

`generated-garments/batch01/manifest.json` 和 `batch02/manifest.json` 共记录 12 件内部候选素材。
`gap-recipes.visual-evidence.batch02.rendered.json` 中多套连衣装仅换鞋包，不能计为独立锚点。
此前对该批“28/29 可用”的口头判断已撤回；该批没有正式四门通过结论。
下一步需按真实主衣组合重做缺口配方，先解决同款变体和正式人格归属，再冻结审核包。

定向回归：`tests/test_recommendation_anchors.py`、`tests/test_selfit_p0_acceptance.py`、
`tests/test_recommendation_diversity.py`，23 passed。这不是完整 P0 验收。

## 以下为 2026-09-04 历史记录

当前有效候选清单是 `anchor-candidates.v11.json`，对应的四门审核包是
`editorial-review.v5/`，统一放行报告是 `release-report.v8.json`。
7 套新增/补充候选由 `p0-gap-staging.v4.json` 冻结。
生成，不得手工将门禁状态改为 Pass。

当前状态：

- 160/160 套结构可用的视觉候选，G3 锚点完整性门禁已通过；
- 16 人格的静态推荐矩阵均可输出 10 套，REC-001 至 REC-006 已通过；
- 160 套四门审核表已准备，全部仍为 pending，因此 G2 仍失败；
- 原 7 套缺口已补齐；首批两套人格/场景方向不足的方案已 reject，有效修复稿纳入 staging；
- `persona-preflight.v1.json` 的保守 AI 预检只有 51/160 同时达到当前人格信号和日常场景条件，109 套需内容审核者重点复核或替换；该预检不是四门结论，但证明不能把“结构齐全”误报为“人格适配已验收”；
- 独立盲审必须等 160 套内容和四门审核冻结后重新生成；
- `browser-evidence.partial.v2.json` 仅记录了本轮已实跑的桌面首屏、静置和负反馈观察，其余 Case 如实标为 Not Run；
- 未达到 160/160、四门全通过、盲审阈值和浏览器/性能证据前，结论一律是 `do_not_release`。

`anchor-candidates.v1.json` 至 `v10.json`、`editorial-review.v1/` 至 `v4/` 和
`release-report.v1.json` 至 `v7.json` 仅保留为历史证据，不能用于放行。
