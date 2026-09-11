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
4. 生成白 T 图使用 `scripts/batch_female_white_tee_presets.py` 或 `scripts/batch_white_tee_presets.py` 准备请求。脚本不调用图片模型；原生图片工具返回后再 `ingest`，检查人物、完整单品、画幅与输入绑定。
5. `publish` 只处理经过程序检查和逐张目检的结果，上传后回读校验，合并预设索引。失败或被工具拦截的结果保留本地记录，不登记为可用图片。
6. 预设必须匹配当前模特字节、当前白 T/拆款配方，以及用户实际保存的完整单品组合。输入变动、部分单品和自己的照片不会误用固定预设。

## 当前白 T 批次

女款批次 `white-tee-female-selfie-20260911` 已生成并上传 177 张：59 套方案 × 三位女模特。另有「柔性薄荷」一套的 3 张被图片工具拦截，因此索引保留 180 张目标数量，不宣称全部完成。男款 12 张已上传并保留，合计 189 张可用白 T 预设。

批次 `REVIEW.md` 提供逐张查看链接，`local-validation.json` 检查输入和图片完整性、实际保存后的命中，以及试穿历史。预设命中后保持约三秒 loading；生成 API 不会再次被调用。

新女款预设绑定本地自拍原图，其他环境没有同一张原图时不会命中，按现有流程正常生成。测试同时验证有对应原图时命中和未配原图时拒绝，避免把本地素材视为代码发布的一部分。

## 提交与发布

提交前核对 `git diff --cached --numstat`，确保没有图片原图、模型权重、环境文件或生成目录；同步远端后运行受影响的 Python 和浏览器/JavaScript 检查。

`commit` 和 `push` 不等于服务器发布。服务器发布仍严格使用 `AGENTS.md` 规定的 `sudo bash scripts/deploy_release.sh [commit]`，并核对 `/health` 的版本指纹。
