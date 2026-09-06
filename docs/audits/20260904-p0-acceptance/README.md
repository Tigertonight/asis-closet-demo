# Selfit P0 验收工作区

## 最新状态：160 套候选内容齐备，正式门禁仍待执行

用户已明确允许处理剩余 15 件原始主衣。实际使用项目既有预处理脚本，仅清理 alpha<8 的低透明度杂点、
等比缩放并补足透明留白，没有修改衣服设计；生成 `generated-garments/batch11/manifest.json`，
15 件均为 1200×1200 RGBA，包版本为 `aw-generated-garments-ca1392e202ea8291fa04`，保持未发布。

最初 batch18 的 20 套整图虽技术目检正常，但与既有 140 套合并后发现 BOLT、EDGE、NEON 的支撑单品
复用超限，因此未入池。`p0-final-recipe-plan.v2.json` 只替换 4 个超限支撑位，batch19 的 20 套整图
及四张联系表已逐张查看；生产侧证据 `gap-recipes.visual-evidence.batch19.visual-review.json` 明确标记为
非独立、非四门、非正式验收，不能自动批准内容。

随后完成 P0 展示资产格式审计：160 套共引用 452 个唯一展示资产，原有 427 个 WebP，另有 25 个透明 PNG。
25 个 PNG 均转换为无损 RGBA WebP，并逐像素验证一致；PNG 原文件只作为审计源保留，不再由最新候选引用。
转换清单与新旧 SHA 见 `p0-selected-webp-migration.v1.json`。
另对当前 App 内容池做了运行时引用扫描：600 件单品 + 1,169 套穿搭共 1,769 个唯一 URL，
扩展名与实际编码均为 WebP，缺失 0、非 WebP 0。目录中仍可见的 PNG 属于 raw/source、历史版本或未入选草稿，
不在当前内容池或 v62 的展示引用中，因此保留作可追溯证据，不做破坏性删除。

有效候选清单现为 `anchor-candidates.v62.json` / `p0-gap-staging.v51.json`：

- 16 个人格 × 10 套 = 160 套；每人格 easy 4 / typical 4 / explore 2。
- 每人格均覆盖 pants / skirt / dress，单一结构不超过 5。
- 160 个父配方唯一；同人格主单品和款式家族复用均不超过 2。
- `final-batch19-preflight.v1.json` 为 `constraints_pass=true`；`production-backlog.v14.json` 为 0 个任务。
- 当前候选引用的 452/452 个展示资产扩展名和实际编码均为 WebP，缺失 0、非 WebP 0；透明材质已抽样查看。
- 新四门包 `editorial-review.v18/` 含 160 条待审及 16 张人格联系表；当前四门通过仍为 0/160。
- `recommendation-matrix.diagnostic.v4.json` 仍为 diagnostic_fail：草稿资产未获四门批准，推荐正式准入按规则拦截。
- `case-ledger.v2.json` 完整列出 94 个 Case：9 个有直接证据的数量/结构/去重项为 Pass，85 个保持 Not Run。
- `release-report.v24.json` 仍为 `do_not_release`；独立盲审、四门签字、正式 REC、浏览器和性能证据尚未完成。

回归证据：batch19 相关 47 passed；最终批次审计 2 passed；非色彩全量回归
`non-color-regression.v7.xml` 为 834 passed（244.99 秒）。完整 pytest 另有 7 个失败均位于明确排除的
`tests/test_color_analysis.py`；唯一非色彩失败是删除按钮误混入反馈可访问分组，现已把删除操作移出反馈组并复验通过。
最终验收工具回归 `final-acceptance-tooling-regression.v1.xml` 为 6 passed。本轮未改正式池、人格算法、账号资料或部署。
WebP 转换回归 `webp-migration-regression.v1.xml` 为 5 passed。

## 剩余 20 套的原始主衣供给与配方已齐，待获准规范化

使用内置 imagegen 为 BOLT、EDGE、NEON、NOIR、OOPS、VOID 的剩余结构缺口制作了 15 件原始主衣，
保存在 `generated-garments/batch05/` 至 `batch10/`；提示词均随图保存，没有使用 CLI。
`generated-garments/raw-supply-audit.v1.json` 以实际像素检查 15 件均为 1254×1254 RGBA、alpha 0–255，
且 `raw-supply-plan.v1.json` 恰好覆盖 backlog 的 20 个组合目标。原图不是候选锚点，也不是四门或盲审通过。

发布切图必须为 1200×1200，因此 15 件仍需用既有脚本作等比缩放、透明留白和低 alpha 杂点清理。
此前授权只明确覆盖 BOLT 两件，本批未自行扩大授权。注册脚本
`scripts/build_selfit_p0_generated_garment_batch11.py` 必须显式传入 `--authorized-normalization`，
无此参数会退出且不创建 manifest；已实际验证。

`p0-final-recipe-plan.v1.json` 已设计剩余 20 套：与 `production-backlog.v13.json` 的任务 ID、人格、
easy/typical/explore 和 pants/skirt/dress 精确一致；新主衣在同人格最多使用两次，20 个 item 组合唯一，
四套多主衣方案均有 layer_graph。注册工具已增加原图审计/计划/SHA 绑定和只读 `--check`；
实际返回 `ready / 15 garments / 20 planned outfits`，篡改任一原图指纹会拒绝。
`build_selfit_p0_final_recipe_batch18.py` 已实现 manifest 到 20 套渲染规格的严格绑定，CLI 入口已复测。
`raw-supply-regression.v7.xml` 为 7 passed（2.09 秒）；更宽的供给、层级、候选入列与工作集回归
`final-supply-preflight-regression.v1.xml` 为 51 passed（3.24 秒）。
这些是预生产结构检查，不替代整图判断；当前有效候选仍为 140/160、四门仍为 0/160。

## OOPS 连衣装新原图：待技术规范化，不增加候选计数

`generated-garments/batch05/` 已保存运动上身 / 斜腰细条纹褶裙的原始 RGBA、实际提示和拒绝的 RGB 棋盘编辑版。
原图结构冲突线索可见，但上下留白仅 2.63%；已询问是否扩展限定预处理授权，确认前不修改像素、不注册、不入列。
仍以 v41 / staging v30 的 140 套为准。技术细节及后续整套审查步骤见 batch05 README。

另：`runtime-unavailable.v1/` 记录真实隔离浏览器发现并修复的关闭弹层焦点问题及 7 项回归；仅为空池局部验证，不能替代完整 E2E 验收。

## 当前候选：BOLT 两套短外套方案入列（140/160）

有效清单：`anchor-candidates.v41.json` / `p0-gap-staging.v30.json`。
用户已明确允许两件原 RGBA 图的限定 Python 预处理：清理低透明度杂点、等比缩放、补透明留白，
不改变衣服设计。实际执行既有脚本，输出 1200×1200、最低有效留白 10%，两件规范化单品均已查看。
内部单品包 `generated-garments/batch04/manifest.json` 登记 n0100 短外套、n0101 偏肩折片上衣；不发布。

batch17 四套整图已逐张查看：短外套配真实长袖内搭，再配阔腿裤/H线裙的两套作为 typical 候选入列。
两套粉色折片上衣偏柔和日常，BOLT explore 证据不足，保持 needs_review，不计入清单；
候选 staging 只携带实际选中的新外套 n0100，没有把 n0101 因单品技术通过自动带入。

- 候选 140 / 160，缺口 20：BOLT 4、EDGE 4、NEON 7、NOIR 1、OOPS 2、VOID 2。
- BOLT 6 套：easy 3 / typical 3 / explore 0；裤、裙、连衣装各 2。
- 新外套与内搭均使用两次；入列工具检查了当前图片/记录指纹、主衣组合/父配方去重、主衣/家族上限和配额可完成性。
- 新四门包 `editorial-review.v16/` 共 140 条待审，BOLT 联系表已查看；待办 `production-backlog.v13.json`。
- 新报告 `release-report.v21.json`：四门 0/160，仍 do_not_release；未补写盲审或浏览器通过结果。
- `bolt-structure-regression.v1.xml`：预处理、层级与候选入列相关 36 passed（2.27 秒）。
  新单品注册脚本实际运行并重复运行，manifest 保持相同版本；`git diff --check` 通过。

审核重点仍包括：短外套与 HEIR 的人格边界、内搭领口和衣摆露出、外套扣合/袖量、长裙活动松量；
排版里外套尺度偏小，单品展示完整不等于穿着时主视觉与适体已被证明。没有修改正式池、算法或部署。

## BOLT 主衣补充：两件原图已生成，技术规范化待确认

本轮回到 22 套内容缺口，核对存量 BOLT 多为礼仪/戏剧结构后，用内置 imagegen 生成
收腰细滚边粗花呢短外套、偏肩折片上衣，保存在 `generated-garments/batch04/`。
原图有真实 alpha，但外套留白不足、上衣存在低透明度边缘杂点；图像工具技术编辑的两版
变成不透明 RGB 棋盘背景，已明确拒绝。原图、失败编辑、完整提示词和像素/SHA 检查均已保存。

已提出是否允许使用现有 Python 脚本作限定规范化的确认，未在获准前调用它编辑图像。
生成提示中的 typical/explore 是生产目标而非审美或人格结论；与 HEIR/FLOU/MELT 的相邻性还需整图复核。
该阶段没有增加锚点计数：仍 138/160、四门 0，通过数未变；没有发布或部署。
详情见 `generated-garments/batch04/README.md`。该阶段 `git diff --check` 通过，未重跑代码测试；后续进展见上方最新记录。

## PERF-001 完整 HTTP 采样工具已补齐（尚未执行正式性能验收）

新增 `scripts/measure_selfit_p0_http.py`，执行说明见 `HTTP_PERFORMANCE_RUNBOOK.md`，
账号配置模板为 `http-performance.accounts.template.json`（无密钥）。
工具在隔离回环服务中校验 16 个正式账号的服务端人格，执行 5 次预热及 50 次串行推荐 HTTP 请求，
保留完整响应耗时、状态码、摘要、错误与人格分配，按 nearest-rank 计算 P95。
空池、旧版本、非 P0、缺失首批 10 套或错误人格的快速响应均判失败；输入及前后健康指纹变化也判失败。
认证只从环境变量读取，不写入证据，禁用代理及重定向。不修改账号、反馈、内容、部署或共享服务。

- 回归 `http-performance-harness-regression.v2.xml`：93 passed（8.73 秒），覆盖采样工具、矩阵审计、
  个人首页及 P0 验收相关测试。包含真实回环 HTTP 传输/重定向测试，其余服务响应使用合成 fixture。
- 1000ms 边界、失败/慢样本保留、16 人格分配、身份不匹配、预热失败、运行中版本变化均有反例测试。
- CLI `--help` 与 `git diff --check` 通过。工具开发完成不代表当前 App 50 次性能采样完成；
  当前仍只有 138/160 候选、0 四门通过，尚未运行指定冻结正式池的 PERF-001。
- 输出始终保留 `PERF-001=Not Run`；测量达标须由 QA 核对运行源码和环境后单独形成正式执行记录。
  不把测试服务器 fixture 的响应耗时或历史组件测量转成 App 的性能通过结论。

## 验收工具修复：候选诊断不再冒充 REC 正式验收

`audit_selfit_p0_recommendation_matrix.py` 原先只遍历输入中存在的人格，且把单次离线选序结果
写成 REC-001 至 006 的 Pass。缺失整个人格可能被漏检，跨页/正式准入/账号链路也未实际执行。
现改为固定遍历 16 人格，检查 160 总数及每人格 10 套、重复/缺失 ID、人格冲突、当前版本及配方指纹；
清单和 staging 按实际解析字节记录 SHA，并检查诊断过程中是否被修改。
所有输出明确为 `offline_candidate_sequence_only`，14 个 REC Case 均保持 Not Run。

- 新实际诊断：`recommendation-matrix.diagnostic.v2.json`，绑定 v39 / staging v28。
- 结果 `diagnostic_fail`，16 人格全部列出；22 条诊断错误不是 22 个独立缺陷。
  BOLT、EDGE、NEON、NOIR、OOPS、VOID 的供给/选序尚不完整；VOID 的候选有裙装，
  但当前未齐的表达配额下诊断选出的短序列未覆盖裙装，不能误报成库存完全没有裙装。
- 历史 `recommendation-matrix.v1.json` 原样保留，但其中 REC-001 至 006 的 Pass 不再是有效验收证据。
- 本轮只修复验收脚本和补充测试，没有变更线上推荐策略、内容审核状态或部署。
- 验证：`matrix-evidence-regression.v2.xml` 为 48 passed（2.78 秒），覆盖矩阵审计、锚点门禁与
  P0 验收测试。包含空/缺失人格、重复 ID、人格冲突、过期版本/配方、输入中途变化以及拒绝覆盖证据。
  `git diff --check` 通过；不是全量回归、浏览器、性能或正式 REC 验收。

## 当前内容候选：138/160，四门仍全部待审

有效清单：`anchor-candidates.v39.json` / `p0-gap-staging.v28.json`。
先前 batch15/16 已将 BOLT 的圆领片丝绒裙、领结衬衫配阔腿裤两套加入候选；
本轮核对产物及 `editorial-review.v15/contact-sheets/bolt.jpg`，确认 BOLT 共 4 套：
easy 3 / typical 1，pants 1 / skirt 1 / dress 2。同件领结衬衫已使用两次。
batch16 的最终渲染记录为 `batch16.v2.rendered.json`（完整文件名带 `gap-recipes.visual-evidence.` 前缀）；
长袖描述已与实图一致，原短袖描述记录只作历史，不是有效候选指纹。

- 剩余 22 套：BOLT 6、EDGE 4、NEON 7、NOIR 1、OOPS 2、VOID 2。
- 审核包 `editorial-review.v15/`、待办 `production-backlog.v12.json`。
- `release-report.v20.json` 已生成：138 条锚点、当前四门审核 0/160，结论仍 `do_not_release`。
- 联系表可见三套领结/浅色造型与一套酒红裙；仍需审查 BOLT 与 HEIR/MELT 的独立辨识、
  丝绒裙节庆感与日常场景边界，不能把配额满足或平铺整齐视为审美/人格通过。

## 最新候选：VOID 两套连衣装入列（136/160）

有效清单：`anchor-candidates.v37.json` / `p0-gap-staging.v26.json`。
batch14 四套实际整图均已查看；斜缝、偏置口袋和微错位下摆的宽直T恤裙，以及其加素面开衫方案，
作为 easy 候选入列。源裙仅使用两次，第二套有明确裙内开衫外关系，不只是换配件。
两套水洗半裙搭针织/垂褶上衣与 MUTE、EASE、WABI 的边界不足，标 needs_review，不入列。

- 候选 136 / 160，剩余 24：BOLT 8、EDGE 4、NEON 7、NOIR 1、OOPS 2、VOID 2。
- VOID 8 套：easy 2 / typical 4 / explore 2；pants 5 / skirt 1 / dress 2，连衣装结构缺口已补，裤装不能继续增加。
- 两个候选的配额、结构可完成性、主衣组合/父配方唯一及当前家族上限经入列工具检查。
- 逐套观察与实际图 SHA：`gap-recipes.visual-evidence.batch14.visual-review.json`。
- 四门审核包 `editorial-review.v14/` 共 136 条待审，VOID 联系表已查看。
- 待办 `production-backlog.v11.json`；报告 `release-report.v19.json` 仍 do_not_release。
- 本轮仅新增内容草稿、观察及候选审核产物，没有修改生产代码、正式池或部署；`git diff --check` 通过。
  未将历史 pytest 绿灯算成本轮内容或浏览器验收通过。

待审重点：T恤裙短袖的天气适用性、真实面料重量、开衫袖量与主裙口袋遮挡；VOID 与 WABI/EASE 的独立辨识。
已向用户提出后续独立盲审人选问题；需未参与该批内容制作、未见答案的审核者，uncertain 时还需第二人复核。
目前还不能生成最终冻结的 160 套盲审包，不能由生产者自审冒充独立结果。

## 最新候选：OOPS 两套入门入列（134/160）

有效清单：`anchor-candidates.v35.json` / `p0-gap-staging.v24.json`。
本轮查看已有新单品大图并实际渲染 batch13 四套：两套半西装半工装裙进入候选；
两套左右拼片衬衫裙虽完整，但主要依赖图案/色块分区，OOPS 证据不足，保持 needs_review。
裙装候选依据为条纹压褶西装片与工装侧袋的结构/正式度冲突，不由蓝色口袋或鞋包标签定人格。
第二套衬衫的实际衣摆遮挡、两套裙腰厚度与行走开合仍须审核。

- 当前 134 / 160；剩余 26：BOLT 8、EDGE 4、NEON 7、NOIR 1、OOPS 2、VOID 4。
- OOPS 8 套：easy 2 / typical 4 / explore 2；pants 4 / skirt 4，仍缺连衣装。
- 新裙使用两次；不同主衣组合/父配方、配额、结构可完成性及当前家族上限已由入列工具校验。
- 原始观察与指纹：`gap-recipes.visual-evidence.batch13.visual-review.json`；新版联系表已查看。
- `editorial-review.v13/` 共 134 条待审；`production-backlog.v10.json`、`release-report.v18.json` 已重建，仍 do_not_release。
- 本轮没有修改 Python 源码、正式池或部署；`git diff --check` 通过。

代码复验 v5：746 passed / 0 failures / 0 errors / 0 skipped，203.56 秒。
前后 234 个 Python 文件指纹对比发现其他工作修改了 `app/closet.py`，因此不能当作当前源码冻结验收。
详情见 `REGRESSION_STATUS.md` 与 `non-color-regression.v5.verification.json`。

## P0 视觉校验范围优化（内容候选仍为 132/160）

发现取消 mtime 缓存后，推荐入口仍对全部 1,169 套库存做图片证据校验；单次组件诊断为 2.184 秒，
已超过完整推荐请求 1 秒的目标预算。新增 `anchor_visual_workset`，仅在 P0 开关开启时预选清单的 160 个唯一 ID，
再做视觉校验及原有完整 `approved_anchor_pool` 校验；未改非 P0 路径，也不缓存过期图片摘要。
预选不是准入：清单数量/ID 错误返回空，未审核或盲审缺失仍不能发布；每次读取实际清单字节。

相关回归 `anchor-workset-regression.v1.xml`：73 passed（10.44 秒）。
组件原始采样 `anchor-workset-component-diagnostic.v1.json`：全池五次 1.497–1.914 秒，
160 条子集五次 0.235–0.343 秒。子集取自真实库存前 160 条，不是合格锚点；同时有 pytest 负载，
只说明缩小工作范围有效，不是 PERF-001 的 50 次 HTTP P95 验收。

本地浏览器诊断：原标签 7 保持登录个人页，新建隔离标签 8 重定向到登录入口。
8000 服务 PID 5647 于 22:43:47 启动且无热重载，早于 22:46:33 的视觉缓存修复及本轮范围优化；
`/health` 返回 git:bbf454c48 persona:v1.4-bolt-korean。不能把该服务的浏览器结果绑定为最新工作区验收。
未重启共享服务、未改账号资料、未发布。完整浏览器矩阵仍需在冻结代码与内容的环境执行。

## 最新候选：NOIR 两套典型入列（132/160）

有效清单：`anchor-candidates.v33.json` / `p0-gap-staging.v22.json`。
batch12 三套整图均已逐张查看。两套尖领收腰马甲分别搭配阔腿裤、窄裙与真实长袖内搭，作为典型候选入列；
锐肩斜拉链外套搭素裙的日常/主题边界不明确，标为 needs_review，未入列。
生产侧记录见 `gap-recipes.visual-evidence.batch12.visual-review.json`；四门和独立盲审均未因此通过。

- 当前 132 / 160；缺口 28：BOLT 8、EDGE 4、NEON 7、NOIR 1、OOPS 4、VOID 4。
- NOIR 9 套：easy 4 / typical 4 / explore 1；pants 4 / skirt 3 / dress 2。
- 两套新候选主衣、内搭各使用两次；入列工具已校验全局主衣组合/父配方唯一、家族上限及配额。
- 新审核包 `editorial-review.v12/` 有 132 条待审；待办 `production-backlog.v9.json`。
- 放行报告 `release-report.v17.json` 仍为 do_not_release。缺少完整 Case 证据、合格内容、独立盲审、浏览器与性能验收。

开发修复：原排版器把马甲与内搭均视作 top 而报冲突；试稿工具现在仅在两个 top 有显式内外顺序时，
将外层映射到既有 outer 展示槽位。源单品类别、配方和指纹不被改写，不是把马甲库存伪改为外套。
该适配仅覆盖内部试稿渲染，不宣称所有线上双上衣或三层试穿链路已支持。
回归 65 passed（9.33 秒），证据 `noir-layer-regression.v1.xml`；三张实际渲染图与新版 NOIR 联系表已查看，
`git diff --check` 通过；没有运行本轮浏览器验收或全量测试。

联系表新增风险记录：原候选中的基础针织/垂领、普通衬衫裤装及配显眼鞋包的组合，
NOIR 证据可能仍主要依赖深色和配件，尤其 `outfit_edge_master_01_v1__p0-persona-noir` 的 explore 定级。
这些记录本来就是待审，不可因数量入选视为合格；四门逐图审核应优先重看，而不能只补最后一个数量槽。

## NEON batch11 复核：未增加候选；视觉版本缓存修复

逐张查看五张实际整套图，记录于 `gap-recipes.visual-evidence.batch11.visual-review.json`。
两套 Polo 缺少独立于撞色的人格证据，标为 needs_review；两套拼接外套仍有主题造型强度，标为 reject。
侧片连衣裙有偏置结构线索，但生产侧观察置信度 0.73 未达到候选工具 0.75 门槛，标为 needs_review。
首次入列尝试被工具拒绝，未提高评分或放宽阈值，未生成新清单。有效候选仍为 v31 / staging v20，130/160。
这些判断不是独立盲审或四门审批，正式池未变。

同时修复 `recommendation_visual.py`：视觉索引及图片摘要不再按文件时间/大小复用旧缓存，
防止保留时间戳替换图片、撤回审核后旧证据继续生效。新增测试覆盖同大小同时间戳换图、审核撤回、损坏与删除。
性能影响需后续按 PERF 原始采样验证，不以这次正确性修复宣称性能达标。
验证：视觉版本回归、候选入列、秋冬供给及 P0 验收测试共 49 passed（11.08 秒），
证据 `visual-revision-regression.v1.xml`；`git diff --check` 通过。未执行本轮全量回归或真实浏览器矩阵。

## 最新候选：MUTE 两套入列（130/160）

最新清单：`anchor-candidates.v31.json` / `p0-gap-staging.v20.json`。
本轮复用存量单品制作并查看两张整图：侧带直线裙；垂领上衣配窄直裙。
两套均作为 typical 候选送审，依据为低装饰完成度、直线轮廓、细节与材质关系，不以整身深色替代人格证据。
衣物完整、鞋履成对；未改正式池、未生成新的单品素材。

- 当前候选 130 / 160，剩余 30：BOLT 8、EDGE 4、NEON 7、NOIR 3、OOPS 4、VOID 4。
- MUTE 10 套：easy 4 / typical 4 / explore 2；pants 3 / skirt 4 / dress 3。
- 配方、图片和生产侧观察：`gap-recipes.visual-evidence.batch10.json`、`.rendered.json`、`.visual-review.json`。
- 四门审核包：`editorial-review.v11/`，130 条全部待审；待办：`production-backlog.v8.json`。
- 当前放行报告：`release-report.v16.json`，仍 `do_not_release`；没有增加四门通过数或独立盲审命中率。
- 当前指纹、候选准入、表达配额、结构、主衣/父配方去重和家族上限均经工具检查；
  新版审核包及门禁已实际生成，联系表已查看，`git diff --check` 通过。

需重点复核：两个新候选的 easy/typical 边界；与 EASE/NOIR 的人格区分；短袖裙的天气适用性、开衩与贴合，
垂领上衣的实际穿着腰线。平铺观察不替代这些穿着判断。上一轮代码测试不能直接证明本轮两套内容审美通过。

## 最新候选：JADE 六套入列，候选结构齐备（128/160）

最新清单：`anchor-candidates.v29.json` / `p0-gap-staging.v18.json`。
本轮先核对 JADE 原有上衣已各用两次，未继续超限复用；制作并逐图查看 batch08 的五套、batch09 的一套。
新增包括简洁斜襟裙、交领侧系带上衣配裤/裙、盘扣宽袖配裤/裙，以及斜襟裙加素面无扣开衫。
最后一套增加实际主衣外层，不是只换鞋包；层级明确为裙在内、开衫在外。

- 当前候选 128 / 160，剩余 32：BOLT 8、EDGE 4、MUTE 2、NEON 7、NOIR 3、OOPS 4、VOID 4。
- JADE 10 套：easy 4 / typical 4 / explore 2；pants 5 / skirt 3 / dress 2。
- 当前映射（含 singleton）下 JADE 同主衣、同家族最高均为 2；全清单 128 个主衣组合无重复。
- 四门审核包：`editorial-review.v10/`，128 条全部待审；待办：`production-backlog.v7.json`。
- 最新放行报告：`release-report.v15.json`，JADE 数量/结构错误已消除，但总体仍 `do_not_release`。
- 新观察与指纹：`gap-recipes.visual-evidence.batch08.visual-review.json`、`gap-recipes.visual-evidence.batch09.visual-review.json`。
- 本轮复用了候选工具，未改生产代码；渲染、当前指纹加载、候选配额/去重检查、审核包生成及门禁检查均实际执行。
  未以历史 pytest 结果声称本批内容已通过四门或独立盲审；`git diff --check` 通过。

必须继续审核的风险：宽袖水墨上衣的主题化边界；交领上衣活动时的覆盖与内层；
斜襟裙开衩高度、贴合程度；开衫与裙子的实际长度和领襟露出。短袖/无袖款只按温暖天气候选，
不宣称适合全部秋季。联系表可见主衣各最多两次，但不能因此替代审美差异和独立人格辨识检查。

## 最新候选：EDGE 三套入列（122/160）

最新清单：`anchor-candidates.v23.json` / `p0-gap-staging.v12.json`。
本轮查看已有生成针织、连衣裙及存量外套/下装的大图后，渲染并逐张检查 batch07：
两套 easy 为不对称针织配阔腿裤、配素面长裙；一套 typical 为短机车外套配方领连衣裙。
新增裙装不是仅换鞋包；但针织复用两次，已按同主衣/家族合并计数，不将它们当作完全独立视觉语言。

- 当前候选 122 / 160；缺 BOLT 8、EDGE 4、JADE 6、MUTE 2、NEON 7、NOIR 3、OOPS 4、VOID 4，共 38。
- EDGE 当前 6 套：easy 2 / typical 3 / explore 1；pants 2 / skirt 2 / dress 2。
  当前家族映射（含 singleton）下同主衣、同家族最高均为 2；全清单 122 个主衣组合无重复。
- 配方、渲染、生产侧观察：`gap-recipes.visual-evidence.batch07.json`、`.rendered.json`、`.visual-review.json`。
- 审核包：`editorial-review.v9/`，122 条全部待审；待办：`production-backlog.v6.json`。
- 放行报告：`release-report.v14.json`，仍 `do_not_release`；真实内容审核与独立盲审未通过。
- 回归：`edge-candidate-regression.v1.xml`，71 passed；未改动正式池或部署。

需要审核的具体风险：入门针织的金属环/斜带在小图中较细，裙装版本更易接近普通柔和风，
不能只凭粉黑配色判定 EDGE；机车外套方案平铺无法证明实际腰线与下摆比例，需复核穿着效果。
鞋履已统一为完整一双，不继续采用旧裤装配方中的单只高靴。

## 最新候选：两套 BOLT 纳入隔离审核（119/160）

最新清单为 `anchor-candidates.v20.json` / `p0-gap-staging.v9.json`。
将已经重建且本轮重新查看整图的两套 BOLT 纳入候选，分别为领结衬衫配素面长裙、领结衬衫裙配软包。
两套均按 easy 候选送审，不将目标标签或生产侧观察当成四门通过；第一套的缎面高光与领结是否过强、
两件主衣相似程度，以及 BOLT 与 HEIR/MELT 的边界都明确留待复核。

- 当前候选 119，缺 41：BOLT 8、EDGE 7、JADE 6、MUTE 2、NEON 7、NOIR 3、OOPS 4、VOID 4。
- 观察与当前指纹：`gap-recipes.visual-evidence.batch04.visual-review.json`。
- 当前四门审核包：`editorial-review.v8/`，119 条全部待审，新增 BOLT 联系表。
- 当前生产任务：`production-backlog.v5.json`；门禁：`release-report.v13.json`，仍为 `do_not_release`。
- 候选工具增加 `--add`、`--candidate-id` 与生成单品清单输入，保持正式池不变，只注册被实际使用的新单品。
  新增检查包含表达配额、结构上限和未来覆盖可行性、主衣/父配方去重、家族上限。
- `candidate-addition-regression.v1.xml`：71 passed；`git diff --check` 通过。

readiness 中 `eligible_supply` 继承原选池统计，不是本次新增后的全库重新召回结果；
当前完成量与生产缺口以实际 anchors、selected_mix、missing_by_expression 为准。
生成单品当前按 singleton 参与保守去重；这不代表它们的人工家族审核覆盖已通过。

## 最新候选：WABI 连衣装结构修复（仍待审核）

`anchor-candidates.v18.json` / `p0-gap-staging.v7.json` 替换了 WABI 一套探索级裙装：
新候选 `outfit_wabi_p0-wabi-layer-06_01` 用素面短袖连衣裙与手作拼接外套组合，
不再使用 batch05 中历史拒绝原因尚未消除的多层茧形裙。
WABI 仍为 10 套、4 easy / 4 typical / 2 explore，结构为 5 pants / 4 skirt / 1 dress。
这是生产侧整图复核后的候选调整；正式内容池、四门通过数、独立盲审成绩均未增加。

- 新整图、观察与指纹：`gap-recipes.visual-evidence.batch06.rendered.json` / `.visual-review.json`。
- 新四门审核包：`editorial-review.v7/`，117 条全部待审。
- 最新生产待办：`production-backlog.v4.json`，43 项新增，0 项结构替换；若候选审核拒绝须重新计入替换需求。
- 最新门禁：`release-report.v12.json`，仍为 `do_not_release`；G3 的 WABI 缺结构错误已消除，其他人格数量缺口仍在。
- 新增 `stage_selfit_p0_replacement.py`：在隔离清单中替换单个候选，保留旧证据，校验人格/表达位置、结构、主衣组合、父配方与家族上限，不自动批准。
- 配方渲染器新增显式层级校验，避免外套+连衣裙静默输出空 `layer_graph`；本方案明确裙在内、外套在外。
- `candidate-replacement-regression.v1.xml`：50 passed。上轮较大回归 `non-color-regression.v3.xml` 为 698 passed，早于本轮脚本修改，不将其当作本轮新脚本的全量复验。

平铺图不能证明真实上身的袖量/下摆效果。外套拼片偏强、WABI 与 VOID 边界、外套在平铺中偏小等问题已在观察中明确保留，需四门及独立审核复核。

## 审核文件内容身份与校验期间变化防护

`recommendation_anchors.py` 不再按 mtime 缓存审核 JSON；读取同一份 bytes 后同时解析与计算 SHA，
避免“读到旧清单、却记录新文件 SHA”的错配。校验结束前重新检查锚点、盲审和家族文件，
若任一变化则返回空候选并拒绝放行。保持时间戳不变的文件替换也会读取新内容。

新增测试覆盖相同 mtime 修改、非法编码、三类证据在验证期间变化，以及未变化的有效清单仍可返回
160 条 fixture。相关锚点、验收工具与推荐接口回归 63 passed；此前 693 项较大回归早于本次修复，
不能当作此修改已完成全量复验的证据。正式内容和端到端门禁仍未通过。

## P0 开关与分页版本隔离修复

新增接口反例先复现 3 Fail / 1 Pass：P0 开启但旧版推荐开关关闭时会走 legacy；
带旧 session/cursor 的请求会在审核锚点前提前返回旧快照。现在 P0 开关优先于旧版路径，
续页前同样检查当前准入，不可用时返回空内容和明确缺口，不访问旧池兜底。

新会话保存 `anchor_release`（锚点清单 SHA、盲审结果 SHA）；续页必须与当前审核通过版本
完全一致。旧会话缺绑定、内容版本变化、盲审版本变化或从 P0 切回普通快照模式均返回 409，
提示换一批，不允许把审核前的缓存视为当前合格内容。
65 项初轮定向回归通过；较大回归原始报告为 `p0-release-isolation-regression.v1.xml`。
这些测试使用隔离 fixture，不代表真实 160 套内容或完整端到端验收通过。

## 2026-09-05 负反馈与真实耗尽修复

新增反例先复现两个 Fail：同游标重试会重新返回被点过“不喜欢”的 outfit；
剩余原始行全部被屏蔽时仍返回 `has_more=true`。运行时现将目标本身及相关主衣/家族
加入本会话屏蔽集合（含早先页，防止重试带回），分页在保持快照偏移边界的前提下跳过
完全屏蔽的后续批次，真实无可用供给时终止游标。

修复后 66 项定向回归通过，原始测试报告：`feed-feedback-regression.v1.xml`。
覆盖推荐、分页、去重、P0 验收工具及锚点规则；属于合成数据/接口规则证据，
不能代替真实内容集 REC-008、浏览器 E2E 或完整 P0 放行。

## 当前放行报告：v11（完整 Case 证据门禁）

`release-report.v11.json` 基于 v16 / staging v6 重新审计，仍为 `do_not_release`。
审计工具现在要求完整 94-case 执行 ledger（`--case-evidence`），每个门禁既检查原有
数据规则，也检查该门禁下的全部 Case 记录；补上此前遗漏的 PERF-007/008 与 FAMILY Case。
只有 Pass 字符串不能证明执行；通过项必须提供执行人、时间、实际结果及存在且 SHA 匹配的
证据文件。重复 Case ID、缺失/变化的证据均拒绝。历史文件原样保留，不自动升级结论。

本次相关回归 29 passed。完整 Case 集与文档的 94 个 ID 已通过集合对拍测试。
当前没有完整执行 ledger，不能以这些定向测试替代内容、独立盲审、浏览器和性能验收。
下方 report v10 为历史审计；待审内容仍是 v16 / staging v6，v17 仅为结构重选诊断。

## 2026-09-05 结构完整性修复与生产缺口复测

选择器已修复回溯后 Counter 的零值键造成虚假结构覆盖的问题，并加入剩余角色的
结构/资源可行性剪枝。缺口报告独立检查数量、4/4/2 和实际结构；选满 10 套但缺一种
结构时仍报告 `replacement_required`，不再因数量已满漏报。

以当前素材和 staging v5 重选得到 `anchor-candidates.v17.json`：117 套候选，
0 套当前四门通过；43 个新增位置，另有 WABI 裤装 5 / 裙装 5 / 连衣装 0 的替换需求。
`production-backlog.v3.json` 已生成 43 个新增任务和 1 个替换任务，替换保留原表达层级，
明确记录待替换 outfit ID，要求新主衣配方；不把替换当作第 161 套。

v17 是验证选择器和生产缺口的重选证据，未迁移人格修订，不替代下方 v16 / staging v6
的待审包或 report v10 的审计绑定。未继承任何历史审核或放行结论。
新增回归覆盖满额缺结构、回溯冲突、可行结构选取和替换任务不膨胀目标数量。

## 最新复核：当前以 v16 / staging v6 / report v10 为准

当前审核包为 `editorial-review.v6/`，包含 117 套，全部 pending。
其中 83 套目标人格与原记录不同，已通过 `stage_selfit_p0_persona_revisions.py`
创建新待审版本，保留旧内容、原父配方与源指纹，未继承旧审核。
`release-report.v10.json` 已无人格归属不一致错误；仍缺 43 个数量位置，
并另有 WABI 三结构覆盖问题，不能只补数量就宣称完整。
相关定向测试 19 passed，完整验收仍未完成。

对下方图片失效记录的更正：复查时目录实际使用统一排版预览图，原始封面并非审核目标；
原图 SHA 与预览 SHA 不应直接比较。审核索引在排查期间更新，目前重新验证得到
952 套视觉候选、217 套待审/过期。曾出现的 1,169 套拦截仅是当时快照，不能作为当前结论。
索引更新后版本字符串仍相同，选择器已增加文件 SHA 记录和生成期间变化检查。
后续新增清单应使用该检查；v16 的对应索引 SHA 可在 report v10 中查询。

下方均保留为历史排查记录，遇到冲突以上述最新复核为准。

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
