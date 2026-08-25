# 04 · 光照归一化与特征改造（P0 工程实施文档）

> 优先级：**P0，冲刺期与工具改造并行（Day 1~3），必须先于大规模引流上线**。
> 理由：冷暖判断的本质是 Lab b\* 轴上几个单位的差异，室内暖光可造成 10 个以上 b\* 单位的漂移——不归一化，回收的用户照片和评分本身就是脏数据，后续所有阈值校准都是垃圾进垃圾出。
> 本文档到函数级改动点，可直接照着实施。

## 1. 问题量化

| 现象 | 量级 | 后果 |
| --- | --- | --- |
| 当前冷暖判定余量 | `warmth = b* − 0.35a*`，warm/cool 分界带宽度约 4 个 b\* 单位（阈值 8 / 4） | 余量极小 |
| 室内暖光（~2700K）对肤色的影响 | b\* 正向漂移可达 10~20 单位 | 冷皮被判暖皮，整个季节族翻转（夏冬↔春秋） |
| 屏幕冷光/阴天 | b\* 负向漂移 | 暖皮被判冷皮 |
| 净柔用的绝对 C\*、HSV 饱和度 | 随 illuminant 整体缩放 | 净/柔判断跟着光线走 |

结论：**无色卡路径（绝大多数真实用户）当前冷暖判断是在裸奔。**

## 2. 修正前情：眼白不能做白平衡锚点

早期提案「用眼白做白平衡参照」被否，原因：

1. 眼白颜色本身是净/柔诊断信号（净型眼白偏蓝白、柔/暖型偏柔白泛黄）。把眼白拉成纯白 = 先抹掉诊断特征再诊断，净/暖边界全乱。
2. 眼白有血管、结膜反射、眼睑阴影，不是朗伯体白；个体基线差异大，单点锚定对噪声极敏感。
3. 会制造系统性偏差：眼白偏黄的人（多为暖/柔型）被过度校正成冷调。

**眼白的正确角色**：校正**前**提取眼白颜色作为净柔/冷暖辅助特征保留；眼白明显过黄只作「可能暖光污染」弱证据 → 降置信，不作锚点。

## 3. 总体设计：三算法投票 + 保守部分校正

```mermaid
flowchart TD
    A[照片] --> B{色卡可用?}
    B -->|是| C[现有 ColorChecker 3x4 矩阵<br/>保持现状, 最可靠]
    B -->|否| D[illuminant 统计估计<br/>新增]
    D --> D1[GrayWorld<br/>排除人脸框/过曝/过暗]
    D --> D2[WhitePatch<br/>最亮1%像素<br/>排除眼区与V>250]
    D --> D3[ShadesOfGray p=4~6]
    D1 & D2 & D3 --> E{三估计投票}
    E -->|chroma角差≤15°<br/>且增益比≤1.3| F[对角增益校正<br/>von Kries per-channel gain]
    E -->|发散| G[放弃校正<br/>illuminant_uncertain flag + 降置信]
    F --> H{肤色保护检查<br/>校正后肤色仍在肤色先验范围内?}
    H -->|是| I[按强度 s≤0.3 部分混合<br/>rgb' = raw·(1-s) + corrected·s]
    H -->|否| J[降低 s 重试; 仍越界则放弃]
    I --> K[skin_tone 用校正后 RGB 采样]
    G --> L[skin_tone 用原图, 现状行为]
    M[眼白/牙齿] -.->|只作诊断特征与弱证据| N[特征层, 不参与校正]
```

设计要点：

- **为什么是投票而不是单算法**：自拍里人脸+黑发占比大、背景复杂，灰世界假设（场景均值=中性灰）常被肤色/发色/彩色背景拉偏；白块法被高光/白墙骗。三算法互相矛盾说明照片不适合校正——**放弃校正比错误校正安全**。
- **为什么是对角增益而不是 3×4 矩阵**：统计法估计的置信度远低于色卡，只允许 per-channel gain（von Kries 模型），不引入 hue 旋转和自由度更高的仿射——防止过校正引入新偏差。
- **肤色保护检查**：肤色先验（skin mask 像素在 YCrCb 的已知范围）本来可用来估计 illuminant，但那会形成「用肤色定光照、再用光照改肤色」的循环论证，把真实冷暖差异拉平。所以肤色先验**只用作校正后 sanity check**，不作估计输入。

## 4. 函数级改动点（照此实施）

### 4.1 不新增 pipeline stage

关键决策：统计法校正**塞进现有 `color_correction` stage** 作为 `method="statistical_illuminant"` 变体，不动 `PIPELINE_STAGES`。这样评估协议（`expected_stage_status`）、`/qa` 页面、issue/置信度体系（`correction.*` 系列）零改动兼容。

### 4.2 `app/cv_pipeline.py` 新增

```python
def estimate_illuminant_gains(rgb: np.ndarray, face: dict, layout: dict | None) -> dict:
    """无色卡路径的 illuminant 估计。返回对角增益 + 置信度，或不可用标记。"""

    # 1) 构造估计用 mask：排除人脸框(外扩10%)、眼区(用 layout 的 feature_regions)、
    #    过曝(V>250)、过暗(V<20)
    # 2) 三个算法在该 mask 上分别估计 illuminant 色度方向与增益:
    #    - gray_world:   gain_c = mean_gray / mean_c,  c ∈ {r,g,b}
    #    - white_patch:  取 V 最高 1% 像素的均值作为白点
    #    - shades_gray:  (mean(I_c^p))^(1/p), p=5
    # 3) 投票: 两两 chromaticity 角差 ≤15° 且 gain 极值比 ≤1.3 → 取三者中位数
    #    否则 → {"usable": False, "reason": "estimators_diverged"}
    # 4) 增益裁剪: 每通道 gain 限制在 [0.75, 1.33](±约 1300K 等效)
    #    超出 → 降置信并裁剪
    # 返回 {"usable": True, "gains": [gr,gg,gb], "confidence": 0.3~0.55,
    #       "estimator_agreement": {...}}
```

### 4.3 `run_color_correction` 扩展（分支逻辑）

```python
def run_color_correction(image, color_card_stage):
    if 色卡可用:                    # 现状分支, 不动
        ... 现有矩阵逻辑
    else:                           # 新增分支
        est = estimate_illuminant_gains(...)
        if not est["usable"]:
            return 现状 no_card_fallback（额外挂 illuminant_uncertain flag）
        return _stage("pass", est["confidence"], {
            "method": "statistical_illuminant_voting",
            "diag_gain_rgb": est["gains"],      # 与 matrix_rgb_3x4 并存的新字段
            "estimator_agreement": est["estimator_agreement"],
            ...
        }, [])
```

### 4.4 `run_skin_tone` 适配（极小改动）

`_apply_rgb_correction` 当前只认 `matrix_rgb_3x4`。扩展为：

```python
def _apply_rgb_correction(rgb, color_correction_stage):
    ev = color_correction_stage.get("evidence", {})
    if ev.get("matrix_rgb_3x4"):        # 色卡路径, 现状
        ...
    if ev.get("diag_gain_rgb"):         # 统计法路径, 新增
        gains = np.array(ev["diag_gain_rgb"], dtype=np.float32)
        return np.clip(rgb.astype(np.float32) * gains, 0, 255)
    return np.clip(rgb, 0, 255)
```

`_skin_correction_strength` 增加按方法分档：色卡路径保持 0.22~0.45；**统计法路径上限 0.3**，且置信度越低强度越低（`s = min(0.3, confidence × 0.6)`）。

### 4.5 净柔特征改造（`_layered_color_diagnosis` 的 clarity_test）

现状：`clear_score` 由绝对 C\* 和 HSV 饱和度构成——随 illuminant 漂移。改为相对结构特征为主：

| 新特征 | 公式 | 稳定性依据 |
| --- | --- | --- |
| 区域色度离散度 `region_dispersion` | std(C\*额, C\*左颊, C\*右颊, C\*颌) / mean(四者) | illuminant 对各区域同向漂移，离散度近似不变；「柔=蒙灰雾感」即低离散度 |
| ab 平面分布面积 `ab_spread` | 肤色像素在 (a\*,b\*) 平面 PCA 的 √(λ1·λ2) | 分布形状比位置稳；净=集中，柔=弥散 |
| 肤发眼对比 `feature_deltaE` | ΔE2000(skin, hair) + ΔE2000(skin, eye)（colour-science 已装） | 相对差值对对角变换鲁棒 |
| 纹理对比 `texture`（复用 `_skin_texture_score`，校正前灰度计算） | 皮肤区 Laplacian 方差 | 不受色温影响；柔=磨砂低纹理 |

`clarity_test` 新公式（初始等权，回流数据回归校准）：

```
clear_score = 0.35·norm(region_dispersion) + 0.25·norm(ab_spread)
            + 0.25·norm(feature_deltaE)   + 0.15·contrast_bonus   # 现状对比度辅助保留
soft_score  = 镜像构造
绝对 C* 与饱和度降级为弱辅助(≤0.15 权重)且按校正强度重标定阈值
```

### 4.6 色彩口径统一（顺手做）

肤色侧从 OpenCV 8bit Lab 切到 `colour-science` 的 `sRGB_to_XYZ → XYZ_to_Lab`（D65/2°），与色卡侧统一；旧字段保留一个版本周期用于对照回归。

## 5. 验证方案（上线前必做）

| 实验 | 构造 | 通过标准 |
| --- | --- | --- |
| E1 合成色温漂移 | 对现有 8 个季节金标 + 全部 real_upload fixture 施加已知色温 tint（按通道增益模拟 2700K 暖灯 / 6500K 阴天 / 屏幕冷光三档） | 校正后 warmth 回到 tint 前 ±2 单位内的样本 ≥80%；季节金标 Top-1 全部保持 |
| E2 投票发散场景 | 彩色背景、大面积红衣、海报墙 fixture | 估计器正确放弃校正（usable=False），不误校 |
| E3 回归不破 | 53 fixture 全量 | 现有回归全绿；无色卡样本置信度封顶逻辑仍生效 |
| E4 净柔对照 | 金标 + 回流样本 | 新旧 clarity 分数并行输出，观察净春/净冬 vs 柔夏/柔秋的分离度是否提升 |
| E5（引流后）回流消融 | 带评分样本按「校正开/关」双跑 | 校正组低分率显著更低；「冷暖判反」归因占比下降 |

## 6. 风险与回退

| 风险 | 缓解 |
| --- | --- |
| 统计法在纯色背景自拍上完全失效 | 投票发散即放弃校正；E2 覆盖 |
| 校正把真实暖皮拉向中性（肤色保护被绕过） | 强度上限 0.3 + 校正后肤色先验检查 + E1 验证 |
| 净柔新特征在深色肤色上信噪比低 | 按 Monk 肤阶分组评估（长期标注集到位后）；当前保留旧特征弱权重兜底 |
| 改动破坏现有回归 | 色卡路径逻辑完全不动；新分支默认仅无色卡时进入 |

## 7. 实施时间表（P0，与工具改造并行）

| 时间 | 交付 |
| --- | --- |
| Day 1 下午 | `estimate_illuminant_gains` + `run_color_correction` 新分支 + skin_tone 适配 |
| Day 2 上午 | E1/E2/E3 实验跑通，fixture 回归全绿 |
| Day 2 下午 | 净柔新特征接入（新旧并行输出，不切主流） |
| Day 3 | 随工具页一起上线；E4/E5 待回流数据 |
