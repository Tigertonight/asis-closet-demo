# 新女模特整套预设交接（2026-09-11）

## 当前结论：用户要求暂停

用户在北京时间 **2026-09-11 18:04:42** 要求：“暂停调用，然后把相关数据整理，todo也整理，便于其他合作者接着做”。后续 Nano 请求已停止，在途请求已保存回执，生成进程已退出，运行锁已释放。暂停后没有发起新请求。

**保持 `outputs/tryon-examples/female-nano-one-shot-20260911/STOP`。没有新的恢复指令时，只做本地检查与整理，不恢复生图或上传调用。** `run` 检测到 STOP 会直接返回，不发送请求。暂停证明在批次 `pause-receipt.json`。

暂停整理时的代码基线为 `demoApp` 分支的 `f223d4af35107bde512f6fa2d1d017e5b730dd47`。随后用户要求 commit 并 push，本次提交包含批处理代码、业务 JSON 和交接文档。原模特照片、生成过程、完整任务快照和凭据仍留本地，仅拉取远端无法得到这些受忽略文件。Git 提交不恢复图片调用，也不执行服务器发布。

## 范围与准确进度

采用 **本地 ADC → Vertex AI → Nano Banana 2（`gemini-3.1-flash-image`）**，每次请求同时生成整套衣服、鞋包及配饰。80 套女款报告搭配 + 16 套场景/趋势搭配，与三位新女模特组合，共 **288 张**。原有 16 张男模特预设保持不变；白 T 替换版属于其他批次。

| 状态 | 数量 | 含义 |
| --- | ---: | --- |
| `uploaded` | 17 | 已通过数值检查、逐张目检，上传七牛并回读核对 SHA-256，已登记索引 |
| `generated_local` | 2 | 数值检查通过，尚未目检；不可直接发布 |
| `failed_api` | 4 | 最近一次为 HTTP 429，未获得可用结果 |
| `failed_quality` | 1 | 最近图片面部差异超阈值 |
| `failed_visual` | 1 | 数值通过，但人工检查发现面部/领型变化 |
| `queued` | 263 | 尚未开始 |
| **总计** | **288** | **仍有 271 张尚未登记完成** |

共发起 71 次真实 API 请求，另复用 1 张用户已接受的试跑结果。`successfulImages=35` 包含失败中间图和复用图，**不是验收数量**。`apiSecondsTotal` 是各次调用耗时之和，也不是批次墙钟耗时。

当前索引保留尚未替换的历史女模特行，顶层旧 `counts` 和 `sourceSnapshot` 含历史批次信息。判断这次完成量应看 `femaleOneShotBatch`、本批各 `job.json` 和交接清单，不能把旧行算作新女模特的可用预设。

## 接手入口

- [待办与六项返工说明](FEMALE_NANO_PRESETS_TODO_20260911.md)
- [逐套、逐体型状态表](../outputs/tryon-examples/female-nano-one-shot-20260911/handoff/OUTFITS.md)：96 套的三体型状态，可跳转结果和 job。
- [交接数据清单](../outputs/tryon-examples/female-nano-one-shot-20260911/handoff/manifest.json)：暂停、统计、代码版本、验证证据和文件说明。
- [288 个任务摘要](../outputs/tryon-examples/female-nano-one-shot-20260911/handoff/jobs.json)：当前状态、尝试次数、素材绑定、结果、错误、修正提示词。
- [输入文件清单](../outputs/tryon-examples/female-nano-one-shot-20260911/handoff/inputs.json)：模特原图与全部参考图的本地路径及 SHA-256。
- [米白长裙待审核对比图](../outputs/tryon-examples/female-nano-one-shot-20260911/review-sheets/ease--outfits-04.jpg)：原搭配、匀称版、纤细版、丰满版失败结果。

这些链接指向本地受忽略目录；跨机器交接时需连同批次目录、输入清单中的素材文件及所需本地配置一起准备。**不能把 ADC 文件、`.env*`、SSH 私钥打包进交接材料或提交 Git。** 三张新女模特原图按既有要求只留本地，本次未上传原图。

## 数据与脚本职责

| 路径 | 职责 |
| --- | --- |
| `app/data/tryon-examples.v1.json` | 实际消费的原套装预设索引，本批只登记 17 张已验收结果 |
| `app/data/material-assets.v1.json` | 七牛素材注册表；包含其他任务改动，不能整表回退或用交接子集覆盖 |
| `scripts/batch_female_nano_presets.py` | 初始化、断点续跑、状态、复用试跑；每次尝试从原模特及整套参考重新生图 |
| `scripts/review_female_nano_presets.py` | 列出待审图、制作对比图、登记绑定结果 SHA 的人工验收 |
| `scripts/publish_female_nano_presets.py` | 发布已验收图；`verify` 核对登记；`finalize` 仅全量完成时可用 |
| `app/selfit_tryon_presets.py` | 完整配方与当前模特匹配；新增场景/趋势原套装支持和单次整套目检约束 |
| `tests/test_selfit_tryon_presets.py` | 原套装匹配、不同照片/部分组合拒绝、场景/趋势与历史保存验证 |
| `tests/test_female_nano_prompt.py` | 去除来源人物姿势而保留服装构造与配饰穿法的回归测试 |

批次根目录为 `outputs/tryon-examples/female-nano-one-shot-20260911/`：

- `source-snapshot.json`：96 套精确输入快照；恢复时禁止无提示替换成新资料。
- `catalog/<套装 key>/catalog.json`：原 look、执行 plan、图像引用及**本批修正后的 itemContext**。必须保留这些提示词修正。
- `<modelId>/<套装 key>/job.json`：每个任务的唯一状态来源。
- `attempts/NN/`：请求元数据、完整提示词、真实响应、原生图、规范画幅图、数值报告及上传回执。失败尝试不覆盖、不删除。
- `visual-review.json`：当前明确目检结论；通过记录绑定结果 SHA 和完整单品 ID。
- `baseline-tryon-examples.v1.json`、`before-publication/`：原索引与发布前备份，供核对和恢复，不可直接覆盖当前数据。
- `run.log`、`run-v2.log`、`run-v3.log`、`run-v4.log`：历次运行日志；最后一次为单并发，现已退出。
- `publish-01.log` 至 `publish-07.log`：已完成的分批发布。
- `handoff/`：本次暂停后的稳定交接快照；恢复后以实际 job 和业务索引为准，需更新快照。

## 输入与调用约束

三张模型原图都是 1792 × 2400 的 PNG。身份分别是匀称型 `female_medium_1`、纤细型 `female_slim_1`、丰满型 `female_plus_1`，默认匀称型。

| 模特 | 原图 SHA-256 |
| --- | --- |
| `female_medium_1` | `637cb742b8d5447b11e1f53509f6279b15fe0a023facaca0b15769eae940bc87` |
| `female_slim_1` | `8dedd0555421d14026ffbea8b4102ce58a042d6c6d737c44d359668e685b0501` |
| `female_plus_1` | `365001c4e926a8bb8747a2ada7afeda8e5471cc439bfc5741b6c11fc8dc058e7` |

文件在 `tests/fixtures/tryon_models/<modelId>.png`，有效配置由 `load_model_manifest()` 读取 `manifest.json` + 与原图 SHA 一致的 `manifest.local.json` 覆盖。**不要改用同名旧 WebP 或旧共享照片**；没有同一原图的环境应正常拒绝本批预设。

- 项目：`gen-lang-client-0606324711`；位置：`global`；模型：`gemini-3.1-flash-image`。
- ADC 在运行者本地 `~/.config/gcloud/application_default_credentials.json`；交接只记录路径，不复制凭据内容。
- 每次完整套装一张图，3:4、2K；目标画幅 1792 × 2400。保留原生字节，必要时仅规范画幅，禁止事后拼脸掩盖质量问题。
- 图 1 为唯一模特身份/姿势依据，图 2 为原套装关系，后续为单品图。超过参考数量限制的两套只合并小配饰参考板，单品不省略。
- 数值阈值保持 `face_diff <= 28`、`protected_region_diff <= 18`；人工检查必须覆盖完整单品、构造/叠穿、脸、手机、手臂和脚位。合法遮挡与轻微自然差异写入 observations，不能把未看过的图登记为通过。
- 常见返工：来源笔记“插袋/坐姿/双手提包”带偏动作、长裙使双脚靠拢、墨镜/头巾改变面部、领型和袋盖简化。过滤姿势、详细单品描述、脚位约束、EASE 发饰及衬衫下摆修正均已保存于代码和 catalog。

## 恢复流程（收到新的恢复指令后再执行）

1. 先阅读 TODO、检查本地输入哈希与当前模型覆盖；保持同一批次输入。当前暂停时有 2 张本地图可以先目检，无需调用 API。
2. 查看 `status`、`pending` 和对比图。通过需保存真实 observations、`resultSha256`；失败保存明确 correction。不要直接改 status 为 uploaded。
3. 恢复生图时将 STOP **改名归档**，保留用户暂停记录。末轮单并发；2 并发曾连续出现 8 次 429，当前没有足够证据证明限流已消失。客户端响应等待已从 240 秒提高为 600 秒，采用指数退避。
4. `--max-attempts` 是每个任务**累计尝试上限**，不是新增次数。五个已有 4 次尝试的失败任务，用 4 无法再跑。可先用 `--max-attempts 5 --limit 1` 小步重试，并查看实际被选中的任务；`--limit` 限制任务数，不限制该任务内部尝试数。新任务可继续用较小上限。
5. 逐张目检后再 publish。用户此前已明确授权本批 **288 张中验收通过的结果上传七牛 selfit 私有空间并登记**，无需重复索取同一上传授权；但当前暂停要求优先。
6. 全部结果就绪后运行 verify、实际预设命中检查与测试；最后才 finalize，核对 288 新女模特 + 原 16 男模特 = 304 条已登记可用结果。

只读/本地整理命令（项目根目录执行）：

```bash
.venv/bin/python scripts/batch_female_nano_presets.py status
.venv/bin/python scripts/review_female_nano_presets.py pending
.venv/bin/python scripts/review_female_nano_presets.py sheets --keys ease--outfits-04
.venv/bin/python scripts/publish_female_nano_presets.py verify
.venv/bin/python -m pytest -q tests/test_female_nano_prompt.py tests/test_selfit_tryon_presets.py
```

恢复后使用的命令（当前不要执行上传/生图）：

```bash
# 先按新的恢复指令归档 STOP，再单并发、小批量观察。
.venv/bin/python scripts/batch_female_nano_presets.py run --concurrency 1 --max-attempts 5 --limit 1
.venv/bin/python scripts/review_female_nano_presets.py record --file /path/to/reviews.json
.venv/bin/python scripts/publish_female_nano_presets.py preflight
.venv/bin/python scripts/publish_female_nano_presets.py publish
# 只有 288 张全部登记后才可执行：
.venv/bin/python scripts/publish_female_nano_presets.py finalize
```

## 已做验证与交接边界

- 29 项相关测试通过，日志在 `handoff-tests.log`；仅有 Starlette/AnyIO 弃用提示。
- `publication-validation.json` 已核对 17 个登记行的当前模型、素材、结果、上传回执和本地缓存，原 16 条男模特数据完全一致。
- 首批实际预设匹配验证在 `publication-validation-partial.json`；新图需最终补做全量实际命中验证，不能只依赖测试夹具。
- STOP 防护已实际执行验证，API 请求总数保持 71；无运行 job，锁可获取。
- 没有新增定时任务、后台自动续跑或后续外部调用。

暂停时的完整工作区状态保留在本地 `handoff/git-status.txt`；这是提交前的历史快照。本次一并提交此前已完成的灵感素材引用、白 T 补图数据与相关说明。三张女模特原图继续保留为本地修改，不进入提交；生成目录、凭据和模型权重也不进入本次提交。服务器发布仍必须先 commit + push，再在服务器执行项目规定的 `sudo bash scripts/deploy_release.sh [commit]` 并核对 health 指纹。
