# AI 色彩测试 MVP 验证交接

这份文档用于交接当前“色彩诊断入口”MVP。目标不是证明算法已经生产可用，而是证明验证期链路已经能稳定跑通：上传照片、质量门禁、色卡状态、肤色与对比度提取、季节型推理、用户侧分层、QA 回归和演示入口。

## 当前状态

- MVP 状态页：`http://127.0.0.1:8000/mvp`
- 产品 Demo：`http://127.0.0.1:8000/demo`
- QA 面板：`http://127.0.0.1:8000/qa`
- 机器状态：`http://127.0.0.1:8000/mvp/status`
- 门禁规则：`http://127.0.0.1:8000/mvp/rules`

当前回归集共 53 张样本，最新验收分布：

- 标准可用：9 张
- 可用但轻提示：24 张
- 低可信初步：8 张
- 建议重拍：12 张

本轮新增真实用户灰区覆盖：复杂海报墙无色卡、室内暖光、屏幕冷光、透明眼镜轻微反光、刘海遮额头、帽檐阴影、手托脸自拍。除强环境光进入低可信外，其余均保持可分析并只给轻提示，避免误伤用户觉得“明明能看清脸”的照片。

`/mvp/status` 返回 `status=ready` 时，表示测试集、关键验收门槛和 QA 物料均可用于验证期演示。

## 如何启动

```bash
. .venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

如果需要重新生成测试物料：

```bash
. .venv/bin/activate
python scripts/generate_qa_artifacts.py
pytest -q
```

启动服务后，可以用一条 smoke 命令快速确认演示链路：

```bash
python scripts/smoke_mvp.py
```

运行后会生成 `tests/results/smoke_mvp_results.json`，服务启动时也可通过 `http://127.0.0.1:8000/qa-artifacts/smoke_mvp_results.json` 查看。

## 演示路径

优先打开：

```text
http://127.0.0.1:8000/mvp
```

页面里有 12 个代表样本，点击后会打开 `/demo?case=...` 并自动跑产品结果：

- `season_spring_bright`：标准可用
- `card_missing`：无色卡轻提示
- `card_fake_grid`：伪色卡低可信
- `real_social_screenshot_auto_crop`：App 截图自动裁脸
- `real_colorful_poster_no_card`：彩色背景无色卡
- `real_busy_poster_wall_no_card`：海报墙无色卡
- `real_warm_indoor_light_no_card`：室内暖光低可信
- `real_screen_cool_light_no_card`：屏幕冷光低可信
- `real_clear_glasses`：普通透明眼镜可测
- `real_bangs_forehead`：刘海遮额头轻提示
- `real_hand_near_face`：手托脸轻提示
- `portrait_sunglasses`：遮挡需重拍

这些样本覆盖了当前最核心的用户路径：好图直接给结果、无色卡继续分析、伪色卡降低可信度、严重遮挡不展示误导性结果，以及真实用户常见的截图、复杂背景、环境光、眼镜、刘海和手托脸灰区。

也可以直接分享单个样本链接：

```text
http://127.0.0.1:8000/demo?case=real_screen_cool_light_no_card
```

有效 `case` 会自动进入结果页；无效 `case` 会停在上传页并提示“这个样本链接暂不可用”，不会误报成上传失败。

## 用户侧门禁口径

### 必须重拍

只覆盖照片本身已经无法稳定判断的情况：

- 非人像或无法识别人脸
- 多人脸且无法明确主脸
- 墨镜、口罩、下半脸或眼部严重遮挡
- 严重过曝、欠曝、强模糊
- 脸部严重裁切或自动裁剪后仍无法取稳定肤色区域

### 可测，轻提示

照片仍然可以给结果，但需要提示用户“更规范会更准”：

- 无色卡
- 普通色卡不可用、色卡轻微倾斜、轻微反光或距离较远
- 脸小但已自动裁剪
- 轻微贴边、轻微模糊、轻微姿态异常
- 轻微美颜、口红、腮红、刘海、彩瞳等局部风险

### 可测，低可信

照片仍可给初步结果，但存在会直接影响肤色判断的因素：

- 明显滤镜偏色
- 浓妆、厚粉底
- 疑似伪色卡或色卡校正失败
- 大角度侧脸
- 脸部区域偏糊但仍能勉强提取肤色

## 色卡策略

色卡不是上传硬门槛。当前规则是：

- 有可用 24 色卡时，优先做色彩校正。
- 无色卡时，继续基于原图推理，标记 `color_card_state=not_used`。
- 伪色卡、严重光线不一致或校正失败时，不阻断，但进入低可信。
- 单纯色卡问题不要求用户重拍；只有未检测到色卡或色卡不可用时，才通过 `retake_with_card` 引导补拍更准的照片。完整可用但轻微倾斜的色卡只做轻提示。

## 用户提示优先级

用户侧提示优先解释“这张照片真正影响判断的地方”，色卡只作为增准建议，不抢主提示：

- 强暖光、屏幕冷光或滤镜偏色：优先提示光线/色调会影响肤色判断，下一步优先建议自然光原图复核。
- 脸部偏小但可自动裁剪：优先提示“已帮你放大脸部区域继续分析”，再说明带色卡会更稳定。
- 伪色卡：提示“照片里有类似色卡的彩色块，但暂时不能用于校准”，不使用“错误色卡”这类指责感表达。
- 普通无色卡：提示本次为初步结果，建议补拍带色卡照片；不把无色卡直接说成低可信错误。
- 普通眼镜、刘海、手托脸：只提示已尽量避开局部不稳定区域，不要求重拍。

## 核心接口

```bash
curl http://127.0.0.1:8000/mvp/status
curl http://127.0.0.1:8000/mvp/rules
curl http://127.0.0.1:8000/analyze/contract
curl http://127.0.0.1:8000/self-test/cached-results
```

单样本分析：

```bash
curl http://127.0.0.1:8000/fixtures/season_spring_bright/analyze
curl http://127.0.0.1:8000/fixtures/card_missing/analyze
curl http://127.0.0.1:8000/fixtures/card_fake_grid/analyze
curl http://127.0.0.1:8000/fixtures/portrait_sunglasses/analyze
```

真实上传：

```bash
curl -X POST "http://127.0.0.1:8000/analyze" \
  -F "image=@/absolute/path/to/photo.jpg"
```

## 后续替换点

当前已经把规则写成阶段化结构，后续可以逐段替换：

- `face_cv`：替换为更稳定的人脸检测、关键点、姿态和遮挡模型。
- `color_card_cv`：当前已接入 `colour-checker-detection` segmentation，并保留 OpenCV 回退；后续继续评估 template/YOLOv8 inference 与透视校正。
- `color_correction`：当前已用 `colour-science` 输出 CIE 2000 DeltaE 和 `correction_quality`；后续继续升级为更完整的色彩管理/校正模型。
- `face_landmarks`：当前已接入本地 MediaPipe Face Landmarker，把肤色和五官采样区域从人脸框比例区域升级为关键点定位区域。
- `skin_tone`：当前已从固定区域中位数升级为 Face Landmarker 区域 + HSV/YCrCb/RGB 自适应肤色 mask 采样，并输出 `region_source` 和 `sample_quality`；后续继续评估 skin parsing。
- `vl_review`：接入正式 VL API，用于妆容、滤镜、截图、遮挡和非人像语义审核。
- `seasonal_result`：从启发式规则升级为有标注数据的分类/排序模型。

替换时应保持 `result_summary`、`decision`、`pipeline` 的出参兼容，前端优先消费 `result_summary`。

更详细的开源技术选型、成熟度判断和分阶段替换路线见 `docs/OPEN_SOURCE_TECH_SELECTION.md`。当前判断是：个人四季/12 季最终分类暂无足够成熟的高星开源方案，优先接入成熟的底层能力；其中 MediaPipe Face Landmarker 已用于关键点区域定位，`colour-checker-detection` 已作为混合检测适配器接入，`colour-science` 已用于标准 DeltaE 校正指标，`skin_tone` 已升级为自适应肤色 mask 采样，`feature_contrast` 已升级为非肤色暗像素自适应采样，后续继续参考肤色提取/skin parsing 工具校准 `seasonal_result`。

## 验收底线

每次改动后至少确认：

- `pytest -q` 通过。
- `python scripts/smoke_mvp.py` 通过。
- `/mvp/status` 返回 `ready`。
- `/mvp` 12 个代表样本都能打开并自动跑结果。
- `/demo?case=<case_id>` 有效样本链接能自动进入结果页；无效样本链接给出友好提示。
- `needs_retake` 样本不展示季节型结果。
- 无色卡样本仍可分析。
- 伪色卡进入低可信但不阻断。
