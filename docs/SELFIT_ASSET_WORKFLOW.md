# 素材与预设维护

## 文件职责

| 文件或目录 | 内容 |
| --- | --- |
| `app/data/material-assets.v1.json` | 按图片字节 SHA-256 标识的素材 ID、已发布下载链接和存储位置 |
| `app/data/styling-delivery.v1.json` | 笔记拆款、单品描述、穿法与叠穿顺序 |
| `app/data/inspiration-styling-delivery.v1.json` | 灵感主题的真实笔记和拆款 |
| `app/data/white-tee-persona-matches.v1.json` | 男女款白 T 的人格、全库及现有微胖素材匹配，每组固定三套 |
| `tests/fixtures/tryon_models/manifest.json` | 启用模特、性别、体型、默认选择和图片素材引用 |
| `tests/fixtures/tryon_models/manifest.local.json` | 可选、受 Git 忽略的本地模特覆盖；必须匹配本地照片 SHA-256 |
| `app/data/tryon-examples.v1.json` | 原套装的固定模特试穿预设 |
| `app/data/white-tee-tryon-presets.v1.json` | 白 T 替换版预设，与原上衣的预设分开 |
| `outputs/tryon-examples/` | 本地生成批次、输入快照、原生回执、复核、失败重试及上传凭据 |
| `outputs/material-cache/` | 按素材 ID 校验的本地图片缓存 |

## 更新规则

1. 原始 ZIP、单品原图、模特原图和生成过程留在本地受忽略的目录；Git 提交代码、业务 JSON、素材引用、测试与说明。
2. 共享图片发布到既有 OSS 后回读核对 SHA-256，再登记素材。账号内用户照片继续使用独立的用户存储，不写入公共素材表。
3. 已获准发布的共享模特可使用 `id` 和 `image_asset_id`。模特选择接口返回素材地址；旧 `/tryon-models/{file}` 链接由 `ModelStaticFiles` 转到当前素材。本次三张新女模特原图按用户要求只留本地，通过本地覆盖配置读取，不上传、不提交；其他环境继续使用 Git 中已有模特。
4. 使用内置图片工具生成白 T 图时，由 `scripts/batch_female_white_tee_presets.py` 或 `scripts/batch_white_tee_presets.py` 准备请求，工具返回后再 `ingest`，检查人物、完整单品、画幅与输入绑定。用户指定其他图片模型时，保存该模型实际的请求、响应、输入哈希和原始图片，不伪造内置工具回执；仍须通过同样的素材、画幅、面部/背景和目检校验。
5. `publish` 只处理经过程序检查和逐张目检的结果，上传后回读校验，合并预设索引。失败或被工具拦截的结果保留本地记录，不登记为可用图片。
6. 预设必须匹配当前模特字节、当前白 T/拆款配方，以及用户实际保存的完整单品组合。输入变动、部分单品和自己的照片不会误用固定预设。

## 当前白 T 批次

女款共 180 张已上传：原批次 `white-tee-female-selfie-20260911` 的 177 张，加上 `soft-mint-nano-20260911` 补齐的「柔性薄荷」三张。新批次使用更新后的薄荷绿粉蕾丝背心素材，由 Google Cloud ADC 调用 Nano Banana 2 生成，逐张复核并上传七牛 `selfit` 后回读核对 SHA-256。新版背心也已登记，白 T 搭配说明同步更新为内搭被白 T 遮住。男款 12 张保留，合计 192 张，索引状态为 `complete`。

原批次 `REVIEW.md` 提供逐张查看链接，`local-validation.json` 保留当时的 177 张验证结果。补图批次保留 `selection.json`、各次真实请求/响应、目检记录及上传回执，`publication-validation.json` 验证 192 条配方绑定、原有 189 条保持不变，以及三种体型保存后命中新图并写入历史。预设命中后保持约三秒 loading；生成 API 不会再次被调用。

新女款预设绑定本地自拍原图，其他环境没有同一张原图时不会命中，按现有流程正常生成。测试同时验证有对应原图时命中和未配原图时拒绝，避免把本地素材视为代码发布的一部分。

## 提交与发布

### 新女模特原套装预设（2026-09-11）

`female-nano-one-shot-20260911` 批次覆盖 80 套报告搭配及 16 套场景/趋势搭配，与三张新女模特组合，共 288 张。用户已确认通过本地 ADC 使用 Nano Banana 2（`gemini-3.1-flash-image`）整套一次生成，并允许将验收通过的结果上传七牛 `selfit` 私有素材空间、更新原套装预设索引。原始模特照片仍按既有规则留在本地。

`scripts/batch_female_nano_presets.py` 保存输入快照、完整提示词、原生响应、耗时与重试记录，默认两个并发。每次请求同时处理服装、鞋包及配饰；参考图较多时只合并小配饰参考板。生图提示词从原描述中过滤“插口袋”等来源人物姿势，保留服装细节描述，固定模特自拍姿势。数值检查通过后仍须通过 `scripts/review_female_nano_presets.py` 逐张目检，不能把面部/背景检查视为款式还原检查。

`scripts/publish_female_nano_presets.py` 仅上传已通过数值和目检的结果，核对当前模特、配方、输入哈希及回读字节后更新 `tryon-examples.v1.json`，保留原男模特预设。运行进度在批次 `progress.json`，已登记数量在索引 `femaleOneShotBatch`。单次整套预设必须额外匹配完整 `outfitId` 和对应图片的目检记录；场景/趋势原套装使用相同的预设读取校验。

**2026-09-11 18:04 用户要求暂停调用。** 已停止全部后续请求，无在途请求；本批为 17 张已登记、2 张待目检、6 张失败待重试/返工、263 张尚未生成。保持批次 `STOP`，收到新的恢复指令后再调用。接手先读 [交接说明](FEMALE_NANO_PRESETS_HANDOFF_20260911.md) 和 [TODO](FEMALE_NANO_PRESETS_TODO_20260911.md)，不要用顶层历史索引数量推算本批完成量。

批量请求保留最长 10 分钟的响应等待，限流重试采用带随机偏移的指数退避，必要时通过 `--concurrency 1` 降低并发。`review_female_nano_presets.py pending` 可列出单个体型已完成的待审核结果，无需等待同套三张全部生成。发布脚本的 `verify` 核对已登记行与当前输入、缓存及上传回执，并确认原 16 条男模特数据不变；`finalize` 仅在 288 张女模特预设全部通过并上传后才更新整批完成状态与汇总数量。

提交前核对 `git diff --cached --numstat`，确保没有图片原图、模型权重、环境文件或生成目录；同步远端后运行受影响的 Python 和浏览器/JavaScript 检查。

`commit` 和 `push` 不等于服务器发布。服务器发布仍严格使用 `AGENTS.md` 规定的 `sudo bash scripts/deploy_release.sh [commit]`，并核对 `/health` 的版本指纹。
