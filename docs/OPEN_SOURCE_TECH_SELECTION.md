# AI 色彩测试开源技术选型

这份文档记录当前 MVP 后续算法迭代的开源技术判断。结论是：个人四季/12 季色彩诊断没有看到足够成熟、活跃、可直接替换生产逻辑的开源项目；更可靠的开源资产集中在色彩科学、ColorChecker 检测/校正、肤色提取等底层模块。

## 总体结论

- 不建议直接引入某个开源 personal color 项目作为最终诊断引擎。
- 建议保留当前阶段化 pipeline 和 `result_summary` 出参，逐段替换底层模块。
- `face_landmarks` 已接入本地 MediaPipe Face Landmarker 模型，用于把肤色和眼部采样从人脸框比例区域升级为关键点定位区域。
- `color_card_cv` 已开始接入 `colour-checker-detection`，当前采用“官方 segmentation 检测 + 位置/形态校验 + OpenCV 回退”的混合适配器。
- `color_correction` 已用 `colour-science` 输出 CIE 2000 DeltaE 指标，保留 RGB 距离字段兼容旧消费方。
- `feature_contrast` 已从整块固定区域亮度差升级为“非肤色暗像素”自适应采样，减少背景、发际线边缘和浅色样本被误判为高对比。
- `seasonal_result` 暂时保留可解释规则，后续需要真实标注数据后再升级为分类/排序模型。

## 分层选型

| 模块 | 当前实现 | 推荐开源方向 | 成熟度判断 | 接入优先级 |
| --- | --- | --- | --- | --- |
| `face_cv` | MediaPipe face detection + Haar fallback | InsightFace / 人脸姿态模型 | 已有检测兜底；后续主要补姿态、多人、遮挡和质量细分 | P1 |
| `face_landmarks` | MediaPipe Face Landmarker 本地模型 | face parsing / skin parsing | 已用于肤色和五官采样区域定位；模型失败时回退人脸框比例区域 | P0 |
| `color_card_cv` | `colour-checker-detection` segmentation + OpenCV 回退 | 继续评估 template/YOLOv8 inference 路径 | segmentation 已接入；YOLOv8 路径还需额外依赖和模型治理 | P0 |
| `color_correction` | 24 色 patch 线性 RGB 校正 + CIE 2000 DeltaE 评估 | ColorChecker 校正模型、OpenCV mcc | 已接入 `colour-science` 标准指标，后续可继续升级校正模型 | P0 |
| `skin_tone` | Face Landmarker 区域 + HSV/YCrCb/RGB 自适应肤色 mask | `SkinToneClassifier`、`SonyResearch/skin-tone-extraction`、face parsing | 已从比例框升级为关键点区域，并输出 `region_source` / `sample_quality`；后续可升级 skin parsing | P1 |
| `feature_contrast` | Face Landmarker 眼部/发际区域 + 非肤色暗像素自适应采样 | face parsing / hair segmentation | 已减少固定区域对背景和边缘暗点的敏感性；后续补 hair segmentation | P1 |
| `vl_review` | 本地 CV 风险初筛 + fixture 标注 | 正式 VL API | 用于妆容、滤镜、截图、二次元、商品图、遮挡语义审核 | P1 |
| `seasonal_result` | 冷暖、深浅、净柔三段诊断 + 虚拟色布排序 | 自研标注集 + 可校准排序模型 | 开源四季分类项目不够成熟，建议自研数据驱动 | P2 |

## 可参考项目

### 1. `colour-science/colour`

用途：标准颜色空间转换、色差、色彩科学计算。

当前状态：

- 已接入 `colour-science`，在 `color_correction.evidence` 中输出 `delta_e_2000_before/after/improvement`。
- 保留旧 `delta_e_before/after` 字段作为 RGB 距离兼容，同时新增 `rgb_distance_*` 明确语义。
- 新增 `correction_quality`，用于 QA 判断校正后仍然偏弱的样本。

建议用途：

- 替换当前手写的 RGB/Lab/HSV 中部分颜色空间转换。
- 引入标准 DeltaE 指标评估校正前后误差。
- 后续统一使用标准 illuminant / observer / white point 口径。

接入方式：

- 先以 optional dependency 或 adapter 引入，不直接改动 `result_summary`。
- 新增 `color_correction.evidence.delta_e_*` 等标准指标，兼容当前字段。

### 2. `colour-science/colour-checker-detection`

用途：ColorChecker 检测。

当前状态：

- 已通过 `ColourScienceColorCardDetector` 接入 segmentation 路径。
- 默认 `HybridColorCardDetector` 会先尝试官方库，再做位置/形态校验，不合格时回退到本地 OpenCV 检测。
- 当前不启用 inference 路径，因为它还需要额外的 `ultralytics` 依赖和模型文件治理。

建议用途：

- 继续并联当前 `run_color_card_cv` 中的 OpenCV 轮廓检测。
- 对 24 色 ColorChecker 做更稳定的定位、透视矫正和 patch 顺序识别。
- 降低彩色衣服、海报墙、UI 截图被误判为色卡的概率。

注意：

- 其 YOLOv8 inference 路径涉及额外模型和依赖，需单独评估许可证、包体积和部署复杂度。
- 第一阶段可先接 segmentation/template 路径，失败时回退当前实现。

### 3. `SkinToneClassifier`

用途：肤色区域检测、肤色分类和调试报告。

建议用途：

- 参考其 skin mask 和 dominant skin tone 抽取方式。
- 用作 `skin_tone` 的对照实验，不直接替代季节型结果。
- 可帮助构建 QA report，显示采样区域是否合理。

注意：

- 它输出的是肤色类别，不是春夏秋冬。
- 需要确认与我们当前 Lab/HSV 维度口径的转换关系。

### 4. `SonyResearch/skin-tone-extraction`

用途：从 facial skin mask 中提取 skin tone。

建议用途：

- 参考其对 mask 输入、肤色提取和批处理评估的设计。
- 后续如果引入 face parsing / skin segmentation，可作为 skin extraction baseline。

注意：

- 更偏研究工具链，需要提供稳定 mask。
- 不直接解决色彩季节分类。

### 5. `deep-seasonal-color-analysis-system`

用途：自拍到 palette，再做服装检索的完整课程项目。

建议用途：

- 参考 pipeline 结构、palette 推荐和服装检索思路。
- 不建议直接作为生产算法依赖。

### 6. `SeasonalColourClassification`

用途：12 类 seasonal color classifier 研究项目。

建议用途：

- 参考训练任务定义和 12 类分类建模方式。
- 等我们有真实标注样本后，可参考其训练结构做自研模型。

注意：

- 项目成熟度低，作者也说明仍在寻找可靠模型方案。
- 不适合当前 MVP 直接接入。

## 建议迭代顺序

### Phase A：色卡检测与校正增强

目标：让“有色卡”真正显著提升稳定性。

- 已新增 `ColorCardDetector` adapter 接口。
- 已并联当前 OpenCV 检测和 `colour-checker-detection` segmentation 检测。
- 对比 `patch_count`、检测框、透视矫正后的 patch 顺序。
- 新增 QA 样本：色卡倾斜、远近、局部反光、手机屏幕截图彩色块、海报墙伪色卡。
- 验收：无色卡仍可测；伪色卡不误阻断；标准色卡校正后肤色波动下降。

### Phase B：标准颜色科学指标

目标：让校正质量有可解释、可比较的指标。

- 已引入 `colour-science` 做 Lab/XYZ/DeltaE。
- 已新增标准 `delta_e_2000_before/after`，并保留旧 `delta_e_before/after` 兼容字段。
- 已输出 `color_correction.evidence.correction_quality`。
- 验收：同一人不同光线下，带色卡校正后的 Lab 差异小于无色卡版本。

### Phase C：肤色区域提取升级

目标：减少口红、腮红、刘海、手托脸对肤色区域的污染。

- 已将额头、双颊、下颌从固定比例框，升级为 MediaPipe Face Landmarker 关键点区域；关键点失败时保留比例框回退。
- 已输出 `skin_tone.evidence.region_source`、`sample_quality` 和每个区域的 `skin_ratio/selection_method/stable`，方便 QA 看采样是否合理。
- 后续继续引入 skin segmentation，把候选区域从关键点框升级为皮肤解析 mask。
- 验收：刘海、手托脸、口红、腮红样本继续分析但采样区域不被明显污染。

### Phase D：季节型模型化

目标：从当前三段诊断 + 虚拟色布排序继续升级为可校准的学习排序模型。

- 建立真实用户标注集，每张照片至少包含 4 季、12 季、可信度、风险标签。
- 保留当前规则模型作为 baseline。
- 训练 Top-2 排序模型，而不是只做 Top-1 硬分类。
- 验收：Top-1 >= 70%，Top-2 >= 85%，并按无色卡/有色卡、光线、妆容分组查看。

## 接口约束

无论替换哪个模块，都必须保持：

- `/analyze` 出参结构兼容。
- 每个 pipeline stage 仍返回 `status/confidence/evidence/issues/suggestions`。
- `result_summary.available=false` 时不能展示季节型结果。
- 无色卡不阻断，只影响 `capture.color_card_state` 和可信度。
- 严重非人像、多人脸、墨镜/口罩、严重模糊仍必须进入 `needs_retake`。

## 当前不建议做的事

- 不建议直接使用开源 seasonal color classifier 替换当前规则模型。
- 不建议让 VL 模型直接输出最终春夏秋冬并覆盖 CV 结果。
- 不建议把“无色卡”作为失败条件。
- 不建议为了追求一次性准确率而移除可解释中间指标。
