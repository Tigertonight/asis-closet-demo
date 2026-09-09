# 80 套 × 3 女模特试穿示例

本批次读取 `app/data/styling-delivery.v1.json` 的 80 套拆款和 `tests/fixtures/tryon_models/manifest.json` 的 3 个启用女模特，生成 240 个唯一组合。所有套装均测试纤细型、沙漏型、丰满型，包括 16 套微胖版。

## 首轮执行结果

240 个组合均已处理，索引状态为 `completed_with_issues`，无待处理任务。231 张真实图片已保存在本地、上传七牛云并登记素材库；每张均完成上传后下载 SHA-256 核对。9 个工具审核拦截保留请求和错误记录，没有伪造图片。

| 模特 | 通过几何检查 | 质量失败图 | 工具拦截 | 本地及云端图片 |
| --- | ---: | ---: | ---: | ---: |
| 纤细型 | 69 | 10 | 1 | 79 |
| 沙漏型 | 63 | 11 | 6 | 74 |
| 丰满型 | 62 | 16 | 2 | 78 |
| 合计 | 194 | 37 | 9 | 231 |

通过几何检查的 194 条中，191 条完成服装、配饰两阶段，3 条 WABI 第四套按现有类别配置仅执行配饰阶段。质量失败图可能在服装阶段即停止，实际阶段数见各条记录。几何通过不代表单品细节或姿势已经完整核验。

首轮核验的 `allCasesProcessed` 为 `true`、`errors` 为空；`complete: false` 表示并非 240 条全部通过。8 项批处理和七牛云测试通过，另有独立只读审阅核对组合映射、状态和访问方式。首轮汇总与核验已分别保留为 `retry-round-01/baseline-completion-summary.json`、`retry-round-01/baseline-verification.json`；批次根目录的同名文件记录最新累计结果。

## 追加重试：retry-round-01

按用户追加要求，对首轮 37 个质量失败和 9 个工具拦截共 46 个组合各追加一轮。35 个从配饰阶段开始，11 个从服装阶段开始；服装阶段通过后，按原管线继续配饰阶段。每个需要生成的阶段仅允许一次新工具调用，任何质量失败或工具错误都结束本轮该组合，不自动追加质量重试。

新文件位于 `outputs/tryon-examples/20260909/retry-round-01/`，其中 `baseline-index.json` 保留完整首轮索引，`manifest.json` 固定 46 个目标，`examples.json`、`summary.json` 记录本轮进度。每个组合的 `generation-attempts` 用独占创建的 claim 防止重复调用，原请求和图片保持可追溯。所有首轮图片和原云端地址保留。

本轮 46 个组合已全部完成，共 51 次阶段调用，每个阶段仅一次。42 张新的结果图（含质量失败图）均已保存、上传七牛、登记素材库并完成下载哈希核对；4 个组合再次被工具审核拦截。服装等中间阶段图片另保存在各组合管线目录。

| 模特 | 本轮通过几何检查 | 本轮质量失败 | 本轮工具拦截 | 新结果图 |
| --- | ---: | ---: | ---: | ---: |
| 纤细型 | 0 | 10 | 1 | 10 |
| 沙漏型 | 4 | 11 | 2 | 15 |
| 丰满型 | 1 | 16 | 1 | 17 |
| 合计 | 5 | 37 | 4 | 42 |

5 个新增几何通过均来自首轮工具拦截：沙漏型 EDGE 第三套、MUTE 第四套、OOPS 第四套、VOID 第四套，以及丰满型 EDGE 第二套。首轮 37 个质量失败在本轮仍未通过；剩余拦截为 FLOU 第一套的三个模特，以及沙漏型 LOOP 微胖版第一套。

当前主索引累计为 **199 个几何通过、37 个质量失败、4 个工具拦截**，共 236 张当前结果图，所有 240 个组合均有终态。重试核验确认 51 个阶段调用记录合规、首轮 231 张图片未改变；主索引核验确认全部当前图片及上传记录一致，两份核验均无错误。46 份新目检记录和重试历史已写入索引，原先 194 个通过组合未改变。批处理、七牛及重试回归共覆盖 11 项通过测试。

沙漏型 OOPS 第四套虽在本轮通过几何检查，目检仍发现缺少金色包和红色心形墨镜。几何通过数量不能当作单品完整性通过数量，具体问题保留在 `visualReview`。

主索引的 `retryHistory` 保存前次与本次结果，`latestRetry` 标明本轮状态，顶层 `retryRounds` 和 `retryInProgress` 标明批次进度。新实际图片上传校验后会成为当前图片；本次无图而之前已有图片时保留之前图片，因此必须同时查看 `latestRetry`，不能把旧图理解成本轮重试出图。

```sh
.venv/bin/python scripts/retry_codex_tryon_examples.py status
.venv/bin/python scripts/retry_codex_tryon_examples.py publish --upload
.venv/bin/python scripts/retry_codex_tryon_examples.py verify
```

`verify` 核对首轮 231 张图片未改变、重试目标、阶段 claim 次数、原失败阶段请求不变及新输出来源；当前主索引的图片和云端记录另由原批次的 `verify` 完整核对。

## 再次重试拦截项：retry-round-02

按用户要求，仅对仍被审核拦截的 4 个组合追加一轮：FLOU 第一套的三个模特从服装阶段重试；沙漏型 LOOP 微胖版第一套复用上一轮服装图，从配饰阶段重试。4 次调用均保持原提示词、参照图和质量门槛，每个阶段仅一次。

4 个请求均再次被工具输出审核拦截，没有新图，也没有新的上传。本批当前结果仍为 199 个几何通过、37 个质量失败、4 个无最终图的工具拦截，共 236 张当前结果图。

本轮真实错误、服务请求 UUID、目检记录及检查点保存在 `outputs/tryon-examples/20260909/retry-round-02/`；主索引的对应 4 条保留两轮 `retryHistory`。本轮核验确认 4 次调用记录完整、原有 236 张当前图片未改动；其余 236 个组合的记录未改动。主索引及重试核验均无错误。

脚本支持 `--round retry-round-02` 选择轮次，初始化时用 `--only-blocked` 限定拦截项，目标清单一旦建立即冻结。本轮增加了筛选冻结、有效前置阶段保留及多轮历史保留的回归检查，4 项重试测试均通过。

图片汇总目录 `outputs/试穿图片汇总-20260909/` 已同步本轮状态：仍为 559 张去重生成图（236 当前结果、37 历史结果、231 中间阶段、55 历史尝试），新一轮复制的前置阶段图按内容去重，未重复导出。

## 提示词及穿法调整版：prompt-adjusted-01

在用户追加授权后，为上述四个组合准备明确改变服装覆盖的日常外穿版本。FLOU 的蕾丝上衣要求增加同色完整不透内衬；LOOP 微胖版将裙摆调整到大腿中段、斜襟闭合、袜层改为黑色不透明。统一按模特原站姿安排单品，移除坐姿、台阶摆包等冲突穿法。

`scripts/adjust_codex_tryon_examples.py` 在独立测试上下文中将两阶段改为整套一次生成，仍使用项目参考板、编辑区域和原几何检查。源拆款和生产 provider 不变；每个组合只调用一次内置 image_gen。新索引在 `outputs/tryon-examples/20260909/prompt-adjusted-01/examples.json`，完整变更说明在同目录 `ADJUSTMENTS.md`，每例保留原始计划、调整计划、最终提示词与参照路径。

这些结果通过主索引的 `adjustedVariants` 关联，并标记 `originalRequestEquivalent: false`。它们不替换原四条拦截状态，不计作原请求已成功。图片汇总文件夹中以 `05调整版结果` 前缀单独展示，是否落实覆盖与全部单品细节需查看 `visualReview`，不能只看几何检查。

本轮 4 次单步调用已全部完成：FLOU 沙漏型、FLOU 丰满型和 LOOP 微胖版沙漏型共 3 张调整版出图并通过原几何检查，FLOU 纤细型仍被工具审核拦截。3 张图均已保存、上传七牛并下载校验，素材库及主索引关联已完成。本轮核验无错误，确认原 240 条结果和原图未改变；3 项调整逻辑测试通过。

目检限制：两张 FLOU 图的蕾丝底层颜色偏米白，不能确认完全落实同色不透内衬；LOOP 袜层仍有棕灰透肤观感，未确认达到所要求的均匀不透明。新图不标为完整语义通过。汇总目录现有 562 张去重图片，其中 `05调整版结果` 为新增 3 张。

## 文件位置

- 业务索引：`app/data/tryon-examples.v1.json`
- 本地图：`outputs/tryon-examples/20260909/<modelId>/<templateId>--<noteId>/result.png`
- 任务检查点：同目录 `job.json`
- 完整管线结果：同目录 `pipeline-result.json`
- 原始请求、提示词、参照板、遮罩、每步出图及回填凭据：同目录 `pipeline/<tryonId>/stage_*/`
- 云端回执及下载校验：同目录 `upload.json`
- 素材注册表：`app/data/material-assets.v1.json`

索引的 `examples` 以套装与模特组合唯一对应，保留人格/笔记绑定、原始拆款单品 ID、模特体型和输入哈希、provider、生成步骤、质量检查及本地/云端图片。

## 生成方式

使用 Codex 内置 `image_gen` 工具，实际执行项目 `run_try_on_from_outfit_plan` 的服装、配饰分组请求。原管线只为非空分组生成阶段，多数套装有服装、配饰两步；具体步骤以每条记录的 `imageEdit.evidence.stages` 和 `pipeline-result.json` 为准。批处理脚本仅导出请求、接收原始生图结果、复跑检查，不调用另一家生图 API，也不修改正式 provider。

生成图片保持原始像素和尺寸；保留几何质量门槛。语义检查明确标记 `pending`，不会把未完成的人工核验伪装成通过。已有 BOLT 第一套、沙漏型示例经请求哈希和输出 SHA-256 验证后复用。

## 续跑

```sh
.venv/bin/python scripts/batch_codex_tryon_examples.py init
.venv/bin/python scripts/batch_codex_tryon_examples.py prepare --model female_slim_1 --limit 4
```

读取返回的请求文件，将 `prompt` 与 `referenced_image_paths` 交给内置工具。使用工具前查看编辑目标；完成后查看原图结果，再回填：

```sh
.venv/bin/python scripts/batch_codex_tryon_examples.py ingest --model female_slim_1 --key bolt--outfits-01 --stage stage_1_visible_clothing --result /absolute/path/to/generated.png
```

回填会自动检查并准备配饰阶段；最后状态为 `generated_local`。失败可用 `retry --model ... --key ... --stage ...` 留存旧输出并重试该步。三个执行者各自只操作对应模特目录，每人最多 4 个独立生图请求并发，总计最多 12 个；同一组合的配饰阶段须等待服装阶段完成。每个请求完成即回填，无需等待同组其他请求。

质量失败最多再做两次针对性重试；仍失败时使用 `finalize-failure --model ... --key ...` 将实际图保存为 `quality-failed.png`，索引用独立 `failedResult`、`status: failed_quality`、`qualityPassed: false` 表达。失败图同样上传、下载核对哈希，回执为 `quality-failed.upload.json`，不计入通过检查的 `uploaded` 数量。工具审核拦截标记 `blocked_moderation`，记录 request ID 和错误，不伪造图片或 URL。

协调者负责上传和汇总：

```sh
.venv/bin/python scripts/batch_codex_tryon_examples.py publish --upload
.venv/bin/python scripts/batch_codex_tryon_examples.py watch
.venv/bin/python scripts/batch_codex_tryon_examples.py verify
```

`watch` 每 30 秒检查新结果并上传，全部 240 个组合已有终态后退出；连续 5 次上传失败也会退出。需中止时创建 `outputs/tryon-examples/20260909/stop-upload-watcher`。

上传到既有七牛云 `selfit` 桶的 `selfit/tryon-examples/20260909/` 前缀，凭据只读取本地 `.env.qiniu`。对象以内容哈希命名，可重试去重。每张上传成功后重新下载、核对 SHA-256，才标记 `uploaded`。JSON 保存 unsigned URL、storage 与 `contentUrl`，不写有时效的 token；项目展示优先使用素材 `contentUrl`。

`status: complete` 仅表示所有 240 个组合有经过下载校验的云端图；单品细节是否完成核验须独立查看 `semanticReview`。待生成任务没有虚构结果 URL。

如果所有组合都已执行，但包含质量失败或工具拦截，索引状态为 `completed_with_issues`，不能称为 240 张成功出图。`generated`/`uploaded` 只统计通过原几何检查的图，`failedImages`/`failedUploaded` 单独统计实际失败图，`blocked` 统计无图的工具拦截。

执行者另存的 `visual-review.json` 会作为 `visualReview` 汇入索引，记录可见问题或遮挡；这不替代原始管线里的自动语义核验状态。`verify` 检查 240 个组合、本地尺寸与 SHA-256、每步请求/输入/输出对应关系、素材库和上传回执，结果保存到本批目录 `verification.json`。

## 已观察到的效果限制

- WABI 第四套现有拆款将连衣裙归入 accessory，四件单品全部落入配饰分组，实际只有 `stage_1_visible_accessories`，管线同时报告缺少上装和下装/裙装。这是冻结输入中的分类问题，本批保留原配置和真实输出，未中途更改分类；后续应复核该套单品类别再单独回归。不能把这条样例描述为已执行两个阶段。
- 部分戴帽结果触发 `quality.face_changed`，例如 FILM 微胖版第一、二套。检查依据是人脸区域像素差；帽檐覆盖上额或发际可能影响结果，不能仅凭这个数值认定身份发生改变。原阈值保持不变，实际图与观察同时保留。
- 部分 EASE、HEIR 结果把原模特的手部姿势改为插袋或身前提包。通过几何检查不代表姿势完全一致。
- 有的结果遗漏帽子或只显示包侧面。具体问题保存在每个组合的目检记录中；自动逐件语义检查未启用，不能把几何通过当作单品完整性已验证。
- 目检记录还发现额外单品、颜色和细节变化：例如沙漏型 MELT 第三套多出袜子，丰满型 LOOP 第三套腰间针织衫颜色变化，丰满型 VOID 微胖版第三套上衣斜边银扣改变。
- 丰满型 OOPS 第四套虽通过几何检查，目检记录指出金色包和红色心形墨镜缺失；部分 VOID 微胖版带白边，沙漏型 MUTE 第二套背景出现竖条。筛选可用示例时需要同时查看 `visualReview`。

这些是已生成样例的观察，不能代替对剩余样例的检查，也不与未运行的原 API 做质量对照。
