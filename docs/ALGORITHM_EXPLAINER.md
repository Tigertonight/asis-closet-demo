# AI 色彩测试算法说明

这份文档用于解释当前 MVP 验证版的真实判断逻辑。它不是生产算法承诺，而是便于产品、测试和算法同学理解“现在到底是谁在做判断”。

## 总体链路

1. `input_quality`：检查格式、尺寸、比例、曝光和清晰度。
2. `face_cv`：MediaPipe Face Detector 优先，OpenCV Haar 兜底，判断单人脸、脸部占比、清晰度、裁切和明显遮挡。
3. `color_card_cv`：`colour-checker-detection` segmentation 优先，OpenCV 色块网格兜底，识别 24 色 ColorChecker 候选。
4. `color_correction`：有可用色卡时计算线性 RGB 校正矩阵，并用 `colour-science` 输出 CIE 2000 DeltaE 指标。
5. `skin_tone`：MediaPipe Face Landmarker 定位额头、双颊、下颌候选区，再用 HSV/YCrCb/RGB 肤色 mask 提取稳定肤色。
6. `feature_contrast`：MediaPipe Face Landmarker 定位眼部和发际候选区，再采样非肤色暗像素估算眼发与肤色对比。
7. `vl_review`：fixture 使用 Codex 辅助标注；真实上传先用本地 CV 识别妆容、滤镜、美颜等软风险。
8. `seasonal_result`：先做冷暖、深浅、净柔三段诊断，再用 12 季虚拟色布画像做候选排序。

## 当前真实模型

- MediaPipe Face Detector：人脸检测。
- MediaPipe Face Landmarker：关键点定位，驱动肤色和五官采样区域。
- `colour-checker-detection`：ColorChecker 候选检测。
- `colour-science`：CIE 2000 DeltaE 等标准色彩指标。
- OpenCV：图像基础处理、Haar 兜底、人脸/色块/清晰度/颜色空间计算。

当前没有让 VL 模型直接输出春夏秋冬；季节型结果来自本地 CV 指标、三段诊断和可解释候选排序。

## 核心维度

### 冷暖

肤色先转 Lab，当前用 `b* - 0.35 * a*` 得到暖感分数：

- `>= 8`：warm
- `<= 4`：cool
- 中间：neutral

`neutral` 会降低置信度，并进入相邻季节候选。

### 明度

使用 Lab 的 `L*`：

- `>= 67`：light
- `<= 52`：deep
- 中间：medium

### 彩度

使用 `sqrt(a*² + b*²)` 并结合 HSV saturation：

- 彩度值 `>= 25` 或 saturation `>= 34`：bright
- 彩度值 `<= 16` 且 saturation `<= 24`：muted
- 中间：medium

### 对比度

使用肤色亮度减去眼发区域暗色特征亮度：

- `>= 78`：high
- `<= 38`：low
- 中间：medium

眼发区域优先采样非肤色暗像素，避免背景边缘把浅色类型误判为高对比。

## 三段诊断

当前不再用单条 if/else 直接从“冷暖 + 明度 + 彩度 + 对比度”跳到春夏秋冬，而是先把照片转换成三组可比较分数：

- 冷暖测试：warm / cool / neutral。Lab 暖感分数越高，warm 分越高；接近中间时 neutral 分变高。
- 深浅测试：light / medium / deep。主要使用 Lab L*，用于区分浅春/浅夏、暖秋/深秋等。
- 净柔测试：clear / balanced / soft。主要使用肤色彩度和 HSV saturation，对比度只作为辅助，不再让黑发高对比直接决定 bright_spring。

## 虚拟色布排序

每个 12 季结果都有一个简化的“色布画像”，例如：

- bright_spring：warm + light + clear，并要求 bright chroma 或 high contrast 共同支持。
- light_spring：warm + light + balanced。
- light_summer：cool + light + soft。
- soft_summer：cool + medium + soft。
- soft_autumn：warm + medium + soft。
- warm_autumn：warm + medium + balanced/clear。
- deep_autumn：warm + deep，或 medium-deep 且对比更强。
- clear_winter：cool + medium + clear。
- deep_winter：cool + deep + clear。

系统会对所有 12 季候选打分，输出 Top-2 候选。这样做的目的，是让“肤色深浅变化”和“净柔变化”真实参与排序，避免亚洲黑发样本因为高对比被统一推到明亮春型。

## 24 季命名

当前 24 季是派生命名，不是独立模型：

```text
{season_12}_{brightness}_{chroma}_{contrast}
```

例如：

```text
light_summer_light_muted_medium
```

## 色卡策略

- 有完整可用色卡时，参与色彩校正并提升可信度。
- 无色卡、色卡太远、反光、裁切、遮挡、伪色卡时，不阻断分析。
- 色卡不可用会设置 warning，并引导用户补拍带色卡照片。

## 置信度策略

置信度不是模型概率，而是当前照片条件和算法稳定性的综合评分：

- 可用色卡和校正成功会加分。
- 无色卡、校正不可用、肤色冷暖中性、脸部软糊、妆容/滤镜风险会降分。
- 验证期还会对用户展示置信度做上限保护，避免把规则结果包装成绝对判断。

## QA 验证口径

当前 QA 重点看：

- 回归集是否 `53/53` 通过。
- 可分析样本是否仍进入 `analyzed`。
- 严重异常是否进入 `needs_retake`。
- 季节型金标 Top-1 是否 `>=70%`，Top-2 是否 `>=85%`。
- 关键点采样覆盖率是否足够高。
- 采样区域图是否符合肉眼直觉。

相关入口：

- `/qa`：QA 面板。
- `/qa-artifacts/region_overlay_sheet.jpg`：采样区域总览图。
- `/qa-artifacts/overlays/{case_id}.jpg`：单张样本采样图。
- `/mvp/status`：当前验收状态 JSON。

## 不要误解

- 当前不是端到端深度学习季节型分类器。
- 当前没有使用 VL 直接判断春夏秋冬。
- 当前 24 季是解释型派生结果，不是经过 24 类训练的模型输出。
- 无色卡可以分析，但应标记为初步结果。
- 用户侧应该表达为“初步诊断/更适合复核”，不要表达成绝对结论。
