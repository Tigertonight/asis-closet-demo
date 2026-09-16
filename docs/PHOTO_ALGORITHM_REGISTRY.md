# 照片算法版本注册表（photo algorithm registry）

> 建立：2026-09-15，肤色事故复盘后。回答三个问题：「旧版本对这批照片怎么判的」、
> 「新版到底改了哪些照片的结果」、「用户报告出问题时用哪个版本复现」。

## 机制

- **代码快照**：`app/photo_algorithm_registry.py` 在服务启动时检测
  `PHOTO_ALGORITHM_VERSION` 无快照则自动把 `app/attribute_pipeline.py` +
  `app/cv_pipeline.py` 字节级拷贝到 `outputs/photo_algorithms/<version>/`。
  代码即真相：任意历史版本可动态加载（import 重写 + 模型路径 patch），
  不依赖服务器上的 git 历史。
- **全量跑批**：新版本快照后自动对全量存量照片跑批，报告写入
  `outputs/photo_algorithm_reports/<version>/reports.jsonl`（photo_id 去重，
  重跑覆盖）。存量 = 用户 accepted/rejected 照片（含 mirror）+ qa_photos 素材。
- **新照片补跑**：上传链路（accepted 与 rejected）异步把照片补跑进所有
  已注册版本的报告（`_registry_record_photo`，串行低优先级 executor）。
- **版本对比**：`compare_reports(a, b)` 输出标签变化矩阵 + 逐照片明细
  （label 变化 / L* 变化 ≥1 / 新增 issue）。

## 管理后台

`/admin` → 「算法版本」tab：

- 版本列表（快照时间、报告照片数、标签分布 tag 列表）；
- 任意两版本对比（下拉选择 → 变化矩阵 + 明细表）；
- 单版本手动重算（后台串行执行，force 默认覆盖）。

## 智能评测页（QA）「算法版本」tab

`/qa/onboarding-attributes?tab=algorithms`——交互式跑批与对比（推荐入口）：

1. **选照片**：按来源分组（内置 / App 拍照 / 镜子拍照 / 管理员上传）可折叠勾选，
   组级全选 + 单张缩略图勾选，顶部全选/清空；
2. **跑批**：选一个版本 × 勾选的照片执行（可选覆盖旧结果），实时进度轮询；
3. **版本对比**：勾选两个以上版本，对勾选照片（未勾选则全部）出对比矩阵——
   每张照片一张卡片：缩略图 + 各版本结果并排（标签/状态/置信度/L*/提示），
   与基准版本不同的卡片高亮，「只看有变化的」默认开启。

API（管理员鉴权，JSON，`app/qa_onboarding.py`）：

| 路由 | 功能 |
|---|---|
| `GET /qa/algorithms/versions` | 版本列表 + 报告统计 |
| `POST /qa/algorithms/run` | 提交跑批 `{version, photo_ids, force}` → job_id |
| `GET /qa/algorithms/job/{job_id}` | 跑批进度 `{status, total, done, failed}` |
| `POST /qa/algorithms/matrix` | 多版本结果矩阵 `{versions, photo_ids}` |

照片口径：QA 页只列 qa_photos 素材（含用户上传归档副本 user_*.jpg）；
session 内的 asset 照片由上传链路自动补跑进各版本报告，不在 QA 页重复展示。

API（管理员鉴权，`app/photo_algorithm_admin.py`）：

| 路由 | 功能 |
|---|---|
| `GET /admin/api/photo-algorithms` | 版本列表 + 报告统计 |
| `GET /admin/api/photo-algorithms/compare?from=&to=` | 两版本 diff |
| `GET /admin/api/photo-algorithms/{version}/photos?label=&changed_from=` | 报告明细 |
| `POST /admin/api/photo-algorithms/{version}/rerun` | 触发重算 |## 版本号写入位置（追溯链）

| 数据 | 字段 | 写入点 |
|---|---|---|
| session.photos[kind] | `algorithm_version` | `_process_session_photo` accepted 路径 |
| user_photos（跨会话索引） | `algorithm_version` | `_index_user_photo` 透传 |
| rejected_photos | `algorithm_version` | `_save_rejected_photo_record`（原有） |
| reports（用户报告） | `photo_algorithm_versions` | `_run_report_job` 快照当时各照片版本 |
| qa_photos/_results.json | 缓存键含版本 | `_analyze_all` 版本变更即失效重算 |
| 注册表报告行 | `algorithm_version` | 每行自带 |

## 算法变更流程（在 attribute_pipeline.py 既有约定之上）

1. 修改算法 → `PHOTO_ALGORITHM_VERSION` 递增 → 测试通过 → commit + push；
2. 服务器 `scripts/deploy_release.sh` 发布，服务启动时注册表自动快照 + 后台跑批；
3. 管理后台「算法版本」tab 核对新旧版本 diff（预期内的变化 + 有无意外误伤）；
4. 历史版本问题复现：`load_algorithm(version)` 直接调用当时的
   `analyze_face_photo / analyze_body_photo`。

## 已知边界

- 快照只在版本**运行过**的服务器上生成：本地新版本未部署前，服务器上没有它的快照
  （部署即生成）。git 历史版本可手工提取快照（参考 photo-v1.1 的
  `git show <commit>:app/attribute_pipeline.py` 方式）。
- 远程资产存储（OSS/S3）下新照片补跑会跳过（拿不到本地文件路径）；
  全量跑批同样只覆盖本地可见照片。demo 部署为 LocalAssetStore，不受影响。
- 算法模块每版本各持一套 mediapipe 模型实例（进程内缓存，内存代价可控）。
