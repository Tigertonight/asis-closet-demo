"""selfit onboarding 属性识别算法模块（大头照 → 肤色/脸型，全身照 → 身型）。

只提供纯算法函数，不绑定任何 HTTP 路由；后端任务负责把它包装成
`POST /api/v1/selfit/sessions/{id}/photos/{kind}` 协议响应。

设计约定（与 docs/SELFIT_BACKEND_INTEGRATION.md 对齐）：
- 「有效照片推断 + 用户手动纠正优先」：本模块的输出只做预选，用户永远可以改。
- 照片本身不满足识别条件时，通过 issues 报错并附重拍建议，不做沉默降级。
- 肤色、脸型、身型三个属性各自带 status，互不阻塞（例如刘海挡脸型不挡肤色）。

输出结构：
{
    "status": "pass" | "warn" | "fail",   # 照片级总状态（门禁失败 = fail）
    "confidence": float,
    "issues": [{"code", "message", "suggestion"}],   # 照片级问题汇总
    "suggestions": [str],
    "attributes": {
        "skin_tone": {"status", "label" | None, "confidence", "issues", "evidence"},
        "face_shape": {"status", "label" | None, "candidates", "confidence", "issues", "evidence"},
    },
    "evidence": {...},   # 门禁证据，供 QA / 调试
}

脸型输出已确认为 5 类：椭圆脸/圆脸/方脸/心形脸/菱形脸（长脸并入椭圆脸——
两者在特征空间只差长宽比一个维度）。长宽比 r 超过 FACE_ELONGATED_RATIO 时，
脸型属性额外输出 sub_label="偏修长"，供报告层补充建议，不改变主标签。
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

try:
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions, vision
except Exception:  # pragma: no cover - optional runtime dependency
    mp = None
    BaseOptions = None
    vision = None

from app.cv_pipeline import (
    _adaptive_skin_region_sample,
    _channel_cast_score,
    _clip_box,
    _detect_face_landmarks,
    _face_landmark_region_layout,
    _issue,
    _landmark_pixel_points,
    _primary_face,
    _skin_mask_rgb,
    colour_science,
    run_face_cv,
)

POSE_LANDMARKER_MODEL = Path(__file__).resolve().parent / "models" / "pose_landmarker_lite.task"
SELFIE_SEGMENTER_MODEL = Path(__file__).resolve().parent / "models" / "selfie_segmenter.tflite"
_MP_POSE_LANDMARKER: Any | None = None
_MP_SELFIE_SEGMENTER: Any | None = None

# ---------------------------------------------------------------------------
# 肤色 5 档（明度阶）
# 口径：自然色居中、左右各两档；最深的蜜糖色已并入小麦色
# （深色段过细对用户不友好，且深肤色用户不愿意选很黑的色号）。
# TODO(calibration): 阈值为文献先验初始值，需用内部标注集回归标定。
SKIN_TONE_LABELS = ["白皙色", "自然白", "自然色", "健康色", "小麦色"]
# L*(D65/2°) 下界：L* >= 下界[i] → SKIN_TONE_LABELS[i]，否则落入下一档。
SKIN_TONE_L_STAR_BOUNDS = [68.0, 65.0, 61.5, 57.5]

# 脸部光照门禁（HSV V 通道 0-100 口径）
FACE_TOO_DARK_V = 45.0
FACE_TOO_BRIGHT_V = 96.0
FACE_STRONG_CAST = 42.0

# ---------------------------------------------------------------------------
# 脸型门禁与规则
# TODO(calibration): 全部阈值待真实自拍标注集回归标定。
FACE_YAW_REJECT = 0.22          # 鼻部到左右外眼角距离差 / 脸宽，超过则判侧脸
BANGS_SKIN_RATIO_REJECT = 0.55  # 刘海检测：额区皮肤占比低于该值则判遮挡（无遮挡样本 ≥0.9，刘海样本 ≈0.33）
FACE_SHAPE_LABELS = ["椭圆脸", "圆脸", "方脸", "心形脸", "菱形脸"]
FACE_ELONGATED_RATIO = 1.48     # 长宽比超过该值时脸型附注「偏修长」（长脸并入椭圆脸后的子标签）


def _face_shape_rules(features: dict[str, float]) -> dict[str, float]:
    """数据驱动的脸型评分表，每类 0~1。features 见 _face_shape_features。"""
    r = features["length_width_ratio"]      # 脸长 / 颧骨宽
    jr = features["jaw_cheek_ratio"]        # 下颌宽 / 颧骨宽
    fr = features["forehead_cheek_ratio"]   # 额宽 / 颧骨宽
    jaw_angle = features["jaw_angle_deg"]   # 下颌角，小=方正
    chin_angle = features["chin_angle_deg"]  # 下巴夹角，小=尖

    square = (
        0.55 * _ramp(jr, 0.82, 0.92)
        + 0.45 * _ramp(135.0 - jaw_angle, 0.0, 20.0)
    ) * (0.7 + 0.3 * _ramp(1.5 - r, 0.0, 0.3))
    round_ = (
        0.5 * _ramp(1.28 - r, 0.0, 0.22)
        + 0.25 * _ramp(jr, 0.76, 0.88)
        + 0.25 * _ramp(chin_angle - 140.0, 0.0, 25.0)
    )
    heart = (
        0.4 * _ramp(fr, 0.80, 0.92)
        + 0.35 * _ramp(0.74 - jr, 0.0, 0.12)
        + 0.25 * _ramp(142.0 - chin_angle, 0.0, 25.0)
    )
    # 菱形 = 颧骨独宽：额与下颌同时窄于颧骨，下巴偏尖。与心形互补——心形要求额宽。
    diamond = (
        0.45 * _ramp(0.84 - fr, 0.0, 0.16)
        + 0.35 * _ramp(0.78 - jr, 0.0, 0.12)
        + 0.20 * _ramp(148.0 - chin_angle, 0.0, 28.0)
    )
    oval = (
        0.45 * (1.0 - _ramp(abs(r - 1.36), 0.04, 0.22))
        + 0.30 * (1.0 - _ramp(abs(jr - 0.79), 0.03, 0.12))
        + 0.25 * (1.0 - _ramp(abs(fr - 0.80), 0.04, 0.14))
    )
    return {
        "椭圆脸": _clamp01(oval),
        "圆脸": _clamp01(round_),
        "方脸": _clamp01(square),
        "心形脸": _clamp01(heart),
        "菱形脸": _clamp01(diamond),
    }


# ---------------------------------------------------------------------------
# 身型门禁与规则
# TODO(calibration): 全部阈值待真实全身照标注集回归标定。
BODY_SHAPE_LABELS = ["梨型", "倒三角型", "沙漏型", "矩型", "苹果型"]
BODY_MIN_VISIBILITY = 0.5
BODY_ANKLE_EDGE_MARGIN = 0.985     # 脚踝归一化 y 超过该值视为被裁切
BODY_SHOULDER_TILT_REJECT = 0.10   # 左右肩高度差 / 躯干长
BODY_HIP_TILT_REJECT = 0.12
BODY_LOOSE_HIP_FACTOR = 2.4        # 轮廓髋宽 / 骨骼髋宽超过该值视为裙装/宽松
PEAR_HIP_OVER_SHOULDER = 1.08      # 髋宽/肩宽 ≥ → 梨型
INVERTED_SHOULDER_OVER_HIP = 1.08  # 肩宽/髋宽 ≥ → 倒三角
HOURGLASS_WAIST_OVER_HIP = 0.78    # 腰/髋 ≤ → 沙漏
APPLE_WAIST_OVER_HIP = 0.95        # 腰/髋 ≥ → 苹果


def _classify_body_shape(measurements: dict[str, float]) -> dict[str, Any]:
    """measurements: shoulder_width / hip_width / waist_width（轮廓口径）。"""
    shoulder = measurements["shoulder_width"]
    hip = measurements["hip_width"]
    waist = measurements.get("waist_width")
    scores = {label: 0.0 for label in BODY_SHAPE_LABELS}

    hip_shoulder = hip / max(shoulder, 1e-6)
    shoulder_hip = shoulder / max(hip, 1e-6)
    scores["梨型"] = _ramp(hip_shoulder - PEAR_HIP_OVER_SHOULDER, 0.0, 0.12)
    scores["倒三角型"] = _ramp(shoulder_hip - INVERTED_SHOULDER_OVER_HIP, 0.0, 0.12)

    waist_reliable = waist is not None and waist > 0
    waist_hip = (waist / hip) if waist_reliable else None
    balanced = 1.0 - max(scores["梨型"], scores["倒三角型"])
    if waist_reliable:
        scores["沙漏型"] = balanced * _ramp(HOURGLASS_WAIST_OVER_HIP - waist_hip, 0.0, 0.10)
        scores["苹果型"] = balanced * _ramp(waist_hip - APPLE_WAIST_OVER_HIP, 0.0, 0.08)
        rectangle = _ramp(waist_hip - HOURGLASS_WAIST_OVER_HIP, 0.0, 0.06) * _ramp(APPLE_WAIST_OVER_HIP - waist_hip, 0.0, 0.06)
        scores["矩型"] = balanced * _clamp01(rectangle + 0.35 * _ramp(0.9 - abs(waist_hip - 0.86), 0.0, 0.9))
    else:
        # 腰测不到（手臂贴身等）：均衡体型里三者都给一点分，置信度自然低。
        scores["沙漏型"] = scores["矩型"] = scores["苹果型"] = balanced * 0.34

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    label, score = ranked[0]
    margin = score - ranked[1][1]
    return {
        "label": label if score > 0.05 else None,
        "scores": {key: round(value, 3) for key, value in scores.items()},
        "margin": round(margin, 3),
        "waist_reliable": waist_reliable,
        "ratios": {
            "hip_over_shoulder": round(hip_shoulder, 3),
            "shoulder_over_hip": round(shoulder_hip, 3),
            "waist_over_hip": round(waist_hip, 3) if waist_hip is not None else None,
        },
    }


# ---------------------------------------------------------------------------
# 对外入口：大头照
# ---------------------------------------------------------------------------

def analyze_face_photo(image: Image.Image) -> dict[str, Any]:
    """大头照 → 肤色 5 档 + 脸型 5 类。任何问题都通过 issues 显式返回。"""
    gate = run_face_cv(image)
    if gate["status"] == "fail":
        skipped = {
            "skin_tone": _attribute("unknown", 0.0, None, [], {"reason": "face_gate_failed"}),
            "face_shape": _attribute("unknown", 0.0, None, [], {"reason": "face_gate_failed"}),
        }
        return _photo_result("fail", 0.4, gate["issues"], skipped, {"face_gate": gate["evidence"]})

    face = _primary_face(gate, image.size)
    rgb = np.array(image.convert("RGB"))
    img_h, img_w = rgb.shape[:2]
    landmarks = _detect_face_landmarks(rgb)
    points = _landmark_pixel_points(landmarks, img_w, img_h) if landmarks else {}
    gate_issues = list(gate.get("issues", []))
    gate_evidence = {"face_gate": gate["evidence"]}

    skin_attr = _skin_tone_attribute(rgb, face, points)
    face_attr = _face_shape_attribute(rgb, face, points)

    attributes = {"skin_tone": skin_attr, "face_shape": face_attr}
    issues = gate_issues + skin_attr["issues"] + face_attr["issues"]
    statuses = [attr["status"] for attr in attributes.values()]
    status = "warn" if "warn" in statuses or gate["status"] == "warn" else "pass"
    if all(attr["status"] == "fail" for attr in attributes.values()):
        status = "fail"
    confidence = round(min(attr["confidence"] for attr in attributes.values()), 2)
    return _photo_result(status, confidence, issues, attributes, gate_evidence)


# ---------------------------------------------------------------------------
# 对外入口：全身照
# ---------------------------------------------------------------------------

def analyze_body_photo(image: Image.Image) -> dict[str, Any]:
    """全身照 → 身型 5 类。骨骼关键点与分割轮廓双路互验。"""
    rgb = np.array(image.convert("RGB"))
    img_h, img_w = rgb.shape[:2]
    pose = _detect_body_pose(rgb)
    if pose is None:
        issue = _issue("body.no_person", "没有识别到完整的人", "请上传一张单人正面全身照，头顶和脚踝都要入镜。")
        attr = _attribute("fail", 0.4, None, [issue], {"reason": "pose_not_found"})
        return _photo_result("fail", 0.4, [issue], {"body_shape": attr}, {"pose": "not_found"})

    issues: list[dict[str, str]] = []
    gate_issue = _body_gate_issues(pose, img_w, img_h)
    if gate_issue is not None:
        attr = _attribute("fail", 0.45, None, [gate_issue], {"reason": gate_issue["code"]})
        return _photo_result("fail", 0.45, [gate_issue], {"body_shape": attr}, {"pose": "found"})

    mask = _person_mask(rgb, pose)
    measurements, measure_meta = _measure_body_widths(mask, pose, img_w, img_h)
    if measurements is None:
        issue = _issue("body.silhouette_unclear", "身形轮廓提取不稳定", "请换背景简洁、全身入镜的正面照片重试。")
        attr = _attribute("fail", 0.42, None, [issue], measure_meta)
        return _photo_result("fail", 0.42, [issue], {"body_shape": attr}, measure_meta)

    if measure_meta.get("loose_clothing_suspect"):
        issues.append(_issue("body.loose_clothing", "衣服比较宽松，身形判断可能不准", "宽松衣物会遮住腰线；穿修身一些的照片会更准。"))
    if not measure_meta.get("waist_reliable", True):
        issues.append(_issue("body.arms_attached", "手臂和身体贴得太近，腰线量不准", "重新拍一张手臂微微张开、与身体留有缝隙的全身照会更准。"))

    classification = _classify_body_shape(measurements)
    if classification["label"] is None:
        issue = _issue("body.shape_ambiguous", "这张照片的身形特征不明显", "建议换一张正面、修身、手臂微张的全身照。")
        attr = _attribute("fail", 0.4, None, issues + [issue], {**measure_meta, "classification": classification})
        return _photo_result("fail", 0.4, issues + [issue], {"body_shape": attr}, measure_meta)

    confidence = 0.62 + min(0.2, classification["margin"])
    if not classification["waist_reliable"]:
        confidence -= 0.12
    if measure_meta.get("loose_clothing_suspect"):
        confidence -= 0.1
    status = "pass" if not issues else "warn"
    attr = _attribute(
        status,
        round(_clamp(confidence, 0.4, 0.85), 2),
        classification["label"],
        issues,
        {**measure_meta, "classification": classification, "measurements": {key: round(value, 1) for key, value in measurements.items()}},
    )
    return _photo_result(status, attr["confidence"], issues, {"body_shape": attr}, measure_meta)


# ---------------------------------------------------------------------------
# 肤色属性
# ---------------------------------------------------------------------------

def _skin_tone_attribute(rgb: np.ndarray, face: dict[str, Any], points: dict[int, tuple[int, int]]) -> dict[str, Any]:
    box = face["box"]
    crop = rgb[box["y"] : box["y"] + box["height"], box["x"] : box["x"] + box["width"]]
    if crop.size == 0:
        return _attribute("fail", 0.4, None, [_issue("photo.face_crop_empty", "脸部区域异常", "请重新上传一张正脸照。")], {})

    hsv = cv2.cvtColor(crop, cv2.COLOR_RGB2HSV)
    mean_v = float(np.mean(hsv[:, :, 2]) * 100 / 255)
    if mean_v < FACE_TOO_DARK_V:
        return _attribute(
            "fail", 0.45, None,
            [_issue("photo.insufficient_light", "照片光线偏暗，肤色读不准", "换到明亮的地方（比如窗边自然光）重新拍一张。")],
            {"face_mean_value": round(mean_v, 1)},
        )
    if mean_v > FACE_TOO_BRIGHT_V:
        return _attribute(
            "fail", 0.45, None,
            [_issue("photo.overexposed", "照片过曝，肤色读不准", "避开强光直射，重新拍一张亮度均匀的照片。")],
            {"face_mean_value": round(mean_v, 1)},
        )

    layout = _face_landmark_region_layout(rgb, face) if points else None
    regions = layout["skin_regions"] if layout else {}
    samples: list[np.ndarray] = []
    region_evidence = []
    for name, (x0, y0, x1, y1) in regions.items():
        patch = rgb[y0:y1, x0:x1]
        if patch.size == 0:
            continue
        sample = _adaptive_skin_region_sample(patch)
        if sample["stable"]:
            samples.append(np.median(sample["pixels"], axis=0))
            region_evidence.append({"name": name, "skin_ratio": sample["skin_ratio"], "stable": True})
        else:
            region_evidence.append({"name": name, "skin_ratio": sample["skin_ratio"], "stable": False})
    if not samples:
        return _attribute(
            "fail", 0.42, None,
            [_issue("skin.sample_failed", "无法稳定提取肤色区域", "请上传清晰、无遮挡的正脸照。")],
            {"regions": region_evidence},
        )

    median_rgb = np.median(np.array(samples), axis=0).astype(np.float64)
    lab = _srgb_to_lab(median_rgb)
    l_star = float(lab[0])
    ita = math.degrees(math.atan2(l_star - 50.0, max(float(lab[2]), 1e-6)))
    label, boundary_gap = _classify_skin_tone(l_star)

    issues: list[dict[str, str]] = []
    status = "pass"
    cast = _channel_cast_score(crop)
    if cast["cast_strength"] > FACE_STRONG_CAST:
        status = "warn"
        issues.append(_issue("photo.color_cast", "照片整体有偏色", "关闭滤镜、用自然光原图，肤色判断会更准。"))
    confidence = 0.6 + min(0.22, boundary_gap / 10.0) - (0.1 if status == "warn" else 0.0)
    evidence = {
        "method": "landmark_region_median_lab",
        "rgb": [int(round(v)) for v in median_rgb.tolist()],
        "lab_d65": [round(float(v), 2) for v in lab.tolist()],
        "l_star": round(l_star, 2),
        "ita_deg": round(ita, 1),
        "boundary_gap": round(boundary_gap, 2),
        "face_mean_value": round(mean_v, 1),
        "color_cast": cast,
        "regions": region_evidence,
    }
    return _attribute(status, round(_clamp(confidence, 0.4, 0.86), 2), label, issues, evidence)


def _classify_skin_tone(l_star: float) -> tuple[str, float]:
    """L* → 5 档标签 + 到最近分界的距离（距离越大置信越高）。"""
    for index, bound in enumerate(SKIN_TONE_L_STAR_BOUNDS):
        if l_star >= bound:
            gap = l_star - bound if index == 0 else min(l_star - bound, SKIN_TONE_L_STAR_BOUNDS[index - 1] - l_star)
            return SKIN_TONE_LABELS[index], float(gap)
    return SKIN_TONE_LABELS[-1], float(SKIN_TONE_L_STAR_BOUNDS[-1] - l_star)


def _srgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    """统一 colour-science D65/2° 口径；库不可用时回退 OpenCV 近似。"""
    if colour_science is not None:
        try:
            arr = np.clip(np.asarray(rgb, dtype=np.float64) / 255.0, 0.0, 1.0)
            return colour_science.XYZ_to_Lab(colour_science.sRGB_to_XYZ(arr))
        except Exception:  # pragma: no cover - defensive fallback
            pass
    lab = cv2.cvtColor(np.uint8([[np.clip(rgb, 0, 255)]]), cv2.COLOR_RGB2LAB)[0][0].astype(float)
    return np.array([lab[0] * 100 / 255, lab[1] - 128, lab[2] - 128])


# ---------------------------------------------------------------------------
# 脸型属性
# ---------------------------------------------------------------------------

def _face_shape_attribute(rgb: np.ndarray, face: dict[str, Any], points: dict[int, tuple[int, int]]) -> dict[str, Any]:
    if not points:
        return _attribute(
            "fail", 0.42, None,
            [_issue("face.landmark_missing", "面部关键点定位失败", "请换一张清晰、正对镜头的正脸照。")],
            {},
        )

    yaw = _face_yaw_ratio(points)
    if yaw > FACE_YAW_REJECT:
        return _attribute(
            "fail", 0.5, None,
            [_issue("face.side_pose", "脸部角度偏侧，脸型判断不准", "请正对镜头、不要转头，重新拍一张。")],
            {"yaw_ratio": round(yaw, 3)},
        )

    bangs = _bangs_forehead_ratio(rgb, points, face)
    if bangs is not None and bangs < BANGS_SKIN_RATIO_REJECT:
        return _attribute(
            "fail", 0.5, None,
            [_issue("face.bangs_forehead", "刘海遮住了额头，暂时判断不了脸型", "把刘海拨开、露出额头后重新拍一张。")],
            {"forehead_skin_ratio": round(bangs, 3)},
        )

    features = _face_shape_features(points)
    if features is None:
        return _attribute(
            "fail", 0.42, None,
            [_issue("face.landmark_missing", "脸部轮廓关键点不完整", "请换一张清晰、正对镜头的正脸照。")],
            {},
        )

    scores = _face_shape_rules(features)
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    label, score = ranked[0]
    margin = score - ranked[1][1]
    issues: list[dict[str, str]] = []
    status = "pass"
    if margin < 0.12:
        status = "warn"
        issues.append(_issue("face.shape_close", "脸型介于两种之间", f"更接近{label}，也可能偏{ranked[1][0]}；以你自己选的为准。"))
    confidence = 0.58 + min(0.24, margin) + min(0.08, score * 0.1)
    candidates = [
        {"label": name, "score": round(value, 3)}
        for name, value in ranked[:2]
    ]
    evidence = {
        "method": "face_oval_landmark_ratios",
        "yaw_ratio": round(yaw, 3),
        "forehead_skin_ratio": round(bangs, 3) if bangs is not None else None,
        "features": {key: round(value, 3) for key, value in features.items()},
        "scores": {key: round(value, 3) for key, value in scores.items()},
        "margin": round(margin, 3),
    }
    result = _attribute(status, round(_clamp(confidence, 0.4, 0.86), 2), label, issues, evidence, candidates=candidates)
    # 长脸并入椭圆脸：长宽比超阈值时保留「偏修长」子标签，供报告层补充建议。
    if features["length_width_ratio"] >= FACE_ELONGATED_RATIO:
        evidence["elongated"] = True
        result["sub_label"] = "偏修长"
    return result


def _face_yaw_ratio(points: dict[int, tuple[int, int]]) -> float:
    """鼻尖到左右外眼角距离差 / 脸宽，近似 yaw。0 = 完全正脸。"""
    needed = [4, 33, 263, 234, 454]
    if not all(index in points for index in needed):
        # 鼻尖 4 不存在时退回鼻根 1
        if 1 in points and all(index in points for index in [33, 263, 234, 454]):
            nose = points[1]
        else:
            return 0.0
    else:
        nose = points[4]
    left = _dist(nose, points[33])
    right = _dist(nose, points[263])
    width = max(_dist(points[234], points[454]), 1e-6)
    return abs(left - right) / width


def _bangs_forehead_ratio(rgb: np.ndarray, points: dict[int, tuple[int, int]], face: dict[str, Any]) -> float | None:
    """额区（眉上 → 发际）皮肤占比；过低说明被刘海/帽檐遮挡。无法定位时返回 None。"""
    needed = [10, 105, 334]
    if not all(index in points for index in needed):
        return None
    top_y = points[10][1]
    brow_y = min(points[105][1], points[334][1])
    if brow_y - top_y < 8:
        return None
    img_h, img_w = rgb.shape[:2]
    x_left = min(points[105][0], points[334][0])
    x_right = max(points[105][0], points[334][0])
    x0, y0, x1, y1 = _clip_box(x_left, top_y + 2, x_right, brow_y - 2, img_w, img_h)
    patch = rgb[y0:y1, x0:x1]
    if patch.size == 0:
        return None
    mask = _skin_mask_rgb(patch.reshape(-1, 3))
    return float(np.mean(mask))


# MediaPipe 脸部外轮廓关键索引
_FACE_OVAL_CHEEK_L, _FACE_OVAL_CHEEK_R = 234, 454
_FACE_OVAL_GONION_L, _FACE_OVAL_GONION_R = 172, 397
_FACE_OVAL_TOP, _FACE_OVAL_CHIN = 10, 152
_FOREHEAD_PAIRS = [(103, 332), (54, 284), (21, 251), (162, 389)]
_CHIN_SIDE_L, _CHIN_SIDE_R = 176, 400
_JAW_UP_L, _JAW_UP_R = 58, 288
_JAW_DOWN_L, _JAW_DOWN_R = 136, 365


def _face_shape_features(points: dict[int, tuple[int, int]]) -> dict[str, float] | None:
    needed = [_FACE_OVAL_CHEEK_L, _FACE_OVAL_CHEEK_R, _FACE_OVAL_GONION_L, _FACE_OVAL_GONION_R, _FACE_OVAL_TOP, _FACE_OVAL_CHIN, _CHIN_SIDE_L, _CHIN_SIDE_R, _JAW_UP_L, _JAW_UP_R, _JAW_DOWN_L, _JAW_DOWN_R]
    if not all(index in points for index in needed):
        return None
    cheek_w = _dist(points[_FACE_OVAL_CHEEK_L], points[_FACE_OVAL_CHEEK_R])
    if cheek_w <= 1:
        return None
    forehead_w = max((_dist(points[a], points[b]) for a, b in _FOREHEAD_PAIRS if a in points and b in points), default=0.0)
    jaw_w = _dist(points[_FACE_OVAL_GONION_L], points[_FACE_OVAL_GONION_R])
    face_len = _dist(points[_FACE_OVAL_TOP], points[_FACE_OVAL_CHIN])
    jaw_angle = (_angle_deg(points[_JAW_UP_L], points[_FACE_OVAL_GONION_L], points[_JAW_DOWN_L]) + _angle_deg(points[_JAW_UP_R], points[_FACE_OVAL_GONION_R], points[_JAW_DOWN_R])) / 2
    chin_angle = _angle_deg(points[_CHIN_SIDE_L], points[_FACE_OVAL_CHIN], points[_CHIN_SIDE_R])
    return {
        "length_width_ratio": face_len / cheek_w,
        "jaw_cheek_ratio": jaw_w / cheek_w,
        "forehead_cheek_ratio": forehead_w / cheek_w if forehead_w > 0 else 0.0,
        "jaw_angle_deg": jaw_angle,
        "chin_angle_deg": chin_angle,
    }


# ---------------------------------------------------------------------------
# 身型：姿态与分割
# ---------------------------------------------------------------------------

def _mediapipe_pose_landmarker() -> Any | None:
    global _MP_POSE_LANDMARKER
    if _MP_POSE_LANDMARKER is not None:
        return _MP_POSE_LANDMARKER
    if mp is None or BaseOptions is None or vision is None or not POSE_LANDMARKER_MODEL.exists():
        return None
    try:
        options = vision.PoseLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(POSE_LANDMARKER_MODEL)),
            running_mode=vision.RunningMode.IMAGE,
            num_poses=1,
        )
        _MP_POSE_LANDMARKER = vision.PoseLandmarker.create_from_options(options)
    except Exception:
        _MP_POSE_LANDMARKER = None
    return _MP_POSE_LANDMARKER


def _mediapipe_selfie_segmenter() -> Any | None:
    global _MP_SELFIE_SEGMENTER
    if _MP_SELFIE_SEGMENTER is not None:
        return _MP_SELFIE_SEGMENTER
    if mp is None or BaseOptions is None or vision is None or not SELFIE_SEGMENTER_MODEL.exists():
        return None
    try:
        options = vision.ImageSegmenterOptions(
            base_options=BaseOptions(model_asset_path=str(SELFIE_SEGMENTER_MODEL)),
            running_mode=vision.RunningMode.IMAGE,
            output_category_mask=True,
        )
        _MP_SELFIE_SEGMENTER = vision.ImageSegmenter.create_from_options(options)
    except Exception:
        _MP_SELFIE_SEGMENTER = None
    return _MP_SELFIE_SEGMENTER


def _detect_body_pose(rgb: np.ndarray) -> list[Any] | None:
    landmarker = _mediapipe_pose_landmarker()
    if mp is None or landmarker is None:
        return None
    try:
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
        results = landmarker.detect(image)
    except Exception:
        return None
    if not results.pose_landmarks:
        return None
    return list(results.pose_landmarks[0])


def _body_gate_issues(pose: list[Any], img_w: int, img_h: int) -> dict[str, str] | None:
    def visible(index: int) -> bool:
        return float(getattr(pose[index], "visibility", 1.0)) >= BODY_MIN_VISIBILITY

    if not all(visible(index) for index in [0, 11, 12]):
        return _issue("body.upper_incomplete", "上半身没有拍全", "请把镜头拿远一点，让头、肩都完整入镜。")
    if not (visible(27) and visible(28)):
        return _issue("body.not_full_body", "没有拍到脚踝，判断不了完整身型", "请拍全身照，头顶到脚踝都要在画面里。")
    for index in [27, 28]:
        if pose[index].y > BODY_ANKLE_EDGE_MARGIN:
            return _issue("body.not_full_body", "脚踝被画面裁掉了", "把脚也拍进来，头顶和脚踝都完整入镜。")
    shoulder_y_l, shoulder_y_r = pose[11].y * img_h, pose[12].y * img_h
    hip_y_l, hip_y_r = pose[23].y * img_h, pose[24].y * img_h
    torso_len = max(abs((hip_y_l + hip_y_r) / 2 - (shoulder_y_l + shoulder_y_r) / 2), 1e-6)
    if abs(shoulder_y_l - shoulder_y_r) / torso_len > BODY_SHOULDER_TILT_REJECT or abs(hip_y_l - hip_y_r) / torso_len > BODY_HIP_TILT_REJECT:
        return _issue("body.side_pose", "身体角度不正，身型判断不准", "请正面站立、双肩放平，重新拍一张。")
    return None


def _person_mask(rgb: np.ndarray, pose: list[Any]) -> np.ndarray | None:
    segmenter = _mediapipe_selfie_segmenter()
    if mp is None or segmenter is None:
        return None
    try:
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
        result = segmenter.segment(image)
        category = result.category_mask.numpy_view()
    except Exception:
        return None
    if category is None or category.size == 0:
        return None
    if category.ndim == 3:
        category = category[:, :, 0]
    category = cv2.resize(category, (rgb.shape[1], rgb.shape[0]), interpolation=cv2.INTER_NEAREST)
    # 不假设类别值约定（有的构建 0=人，有的 255=人）：
    # 用骨骼关键点所在像素的多数类别作为“人”的类别。
    h, w = category.shape
    votes: list[int] = []
    for index in [11, 12, 23, 24, 27, 28]:
        x = min(max(int(pose[index].x * w), 0), w - 1)
        y = min(max(int(pose[index].y * h), 0), h - 1)
        votes.append(int(category[y, x]))
    person_class = max(set(votes), key=votes.count)
    mask = category == person_class
    if float(np.mean(mask)) < 0.02:
        return None
    return mask


def _torso_run_width(mask_row: np.ndarray, spine_x: int) -> int:
    """mask_row 中 spine_x 所在的连续人体段宽度（手臂已被调用方预先挖除）。"""
    if mask_row.shape[0] == 0:
        return 0
    spine_x = int(min(max(spine_x, 0), mask_row.shape[0] - 1))
    if not mask_row[spine_x]:
        return 0
    left = spine_x
    while left > 0 and mask_row[left - 1]:
        left -= 1
    right = spine_x
    while right < mask_row.shape[0] - 1 and mask_row[right + 1]:
        right += 1
    return right - left + 1


def _arm_zones_at_row(pose: list[Any], img_w: int, img_h: int, y_px: float) -> list[tuple[float, float]]:
    """y_px 行上左右手臂（含手）占据的 x 区间，用肩-肘-腕骨骼折线外推。"""
    zones: list[tuple[float, float]] = []
    for shoulder_i, elbow_i, wrist_i in [(11, 13, 15), (12, 14, 16)]:
        shoulder = (pose[shoulder_i].x * img_w, pose[shoulder_i].y * img_h)
        elbow = (pose[elbow_i].x * img_w, pose[elbow_i].y * img_h)
        wrist = (pose[wrist_i].x * img_w, pose[wrist_i].y * img_h)
        # 手：沿前臂方向再延长 45%
        hand_end = (wrist[0] + (wrist[0] - elbow[0]) * 0.45, wrist[1] + (wrist[1] - elbow[1]) * 0.45)
        radius = max(10.0, 0.14 * _dist(elbow, wrist))
        for a, b in [(shoulder, elbow), (elbow, hand_end)]:
            if abs(b[1] - a[1]) <= 1:
                continue
            if min(a[1], b[1]) - radius <= y_px <= max(a[1], b[1]) + radius:
                t = min(max((y_px - a[1]) / (b[1] - a[1]), 0.0), 1.0)
                x = a[0] + (b[0] - a[0]) * t
                zones.append((x - radius, x + radius))
    return zones


def _measure_body_widths(mask: np.ndarray | None, pose: list[Any], img_w: int, img_h: int) -> tuple[dict[str, float] | None, dict[str, Any]]:
    """轮廓量肩/腰/髋三宽；手臂骨骼折线先挖除，避免垂臂污染宽度。

    手臂区间与骨骼躯干区间重叠的行（手臂贴身）记为不可靠：
    肩/髋可靠行不足时分别退回骨骼估计/失败，腰不可靠时只影响沙漏/矩型/苹果的分辨。
    """
    shoulder_l = (pose[11].x * img_w, pose[11].y * img_h)
    shoulder_r = (pose[12].x * img_w, pose[12].y * img_h)
    hip_l = (pose[23].x * img_w, pose[23].y * img_h)
    hip_r = (pose[24].x * img_w, pose[24].y * img_h)
    bone_shoulder = _dist(shoulder_l, shoulder_r)
    bone_hip = _dist(hip_l, hip_r)
    meta: dict[str, Any] = {
        "bone_shoulder_width": round(bone_shoulder, 1),
        "bone_hip_width": round(bone_hip, 1),
        "shoulder_source": None,
        "waist_reliable": False,
        "loose_clothing_suspect": False,
        "mask_available": mask is not None,
    }
    if mask is None or bone_shoulder <= 1 or bone_hip <= 1:
        return None, meta

    shoulder_y = (shoulder_l[1] + shoulder_r[1]) / 2
    hip_y = (hip_l[1] + hip_r[1]) / 2
    torso_h = max(hip_y - shoulder_y, 1e-6)
    spine_shoulder_x = (shoulder_l[0] + shoulder_r[0]) / 2
    spine_hip_x = (hip_l[0] + hip_r[0]) / 2

    def spine_x_at(y: float) -> int:
        return int(spine_shoulder_x + (spine_hip_x - spine_shoulder_x) * ((y - shoulder_y) / torso_h))

    def bone_torso_span_at(y: float) -> tuple[float, float]:
        """骨骼躯干区间（×1.15 血肉系数），用于判断手臂是否贴身。"""
        t = min(max((y - shoulder_y) / torso_h, 0.0), 1.4)
        half = (bone_shoulder + (bone_hip - bone_shoulder) * min(t, 1.0)) * 1.15 / 2
        center = spine_shoulder_x + (spine_hip_x - spine_shoulder_x) * min(t, 1.0)
        return center - half, center + half

    def clean_width(y: float) -> tuple[int, bool]:
        """挖除手臂区间后的躯干宽；(宽度, 该行是否可靠)。"""
        y_int = min(max(int(y), 0), img_h - 1)
        row = mask[y_int].copy()
        torso_lo, torso_hi = bone_torso_span_at(y)
        reliable = True
        for x0, x1 in _arm_zones_at_row(pose, img_w, img_h, y):
            if x0 < torso_hi and x1 > torso_lo:
                reliable = False  # 手臂与躯干骨骼区间重叠，挖除会误伤躯干
            row[max(0, int(x0)) : min(img_w, int(x1) + 1)] = False
        return _torso_run_width(row, spine_x_at(y)), reliable

    armpit_y = shoulder_y + 0.14 * torso_h
    bust_y = shoulder_y + 0.28 * torso_h
    waist_top, waist_bottom = bust_y, hip_y - 0.04 * torso_h
    hip_top, hip_bottom = hip_y - 0.05 * torso_h, hip_y + 0.22 * torso_h

    shoulder_w, shoulder_reliable = clean_width(armpit_y)
    if not shoulder_reliable or shoulder_w < bone_shoulder:
        # 腋下这行手臂贴着躯干，挖臂会误伤肩宽；退回骨骼估计。
        shoulder_w = 0.0
    waist_widths = []
    waist_reliable_rows = 0
    y = waist_top
    while y < waist_bottom:
        width, reliable = clean_width(y)
        if width > 0:
            waist_widths.append(width)
            waist_reliable_rows += 1 if reliable else 0
        y += 2
    hip_widths = []
    hip_reliable_rows = 0
    y = hip_top
    while y < hip_bottom:
        width, reliable = clean_width(y)
        if width > 0:
            hip_widths.append(width)
            hip_reliable_rows += 1 if reliable else 0
        y += 2

    if shoulder_w <= 0:
        shoulder_w = bone_shoulder * 1.15
        meta["shoulder_source"] = "bone_estimate"
    else:
        meta["shoulder_source"] = "silhouette"
    if not hip_widths:
        return None, meta

    hip_ratio_reliable = hip_reliable_rows / max(len(hip_widths), 1)
    if hip_ratio_reliable < 0.2:
        # 髋部各行都被手/手臂挡住，轮廓不可信
        return None, {**meta, "hip_reliable_row_ratio": round(hip_ratio_reliable, 3)}

    hip_w = float(np.percentile(hip_widths, 90))
    waist_ratio_reliable = waist_reliable_rows / max(len(waist_widths), 1)
    waist_reliable = bool(waist_widths) and waist_ratio_reliable >= 0.4
    waist_w = float(np.percentile(waist_widths, 10)) if waist_reliable else None
    if waist_w is not None and waist_w > hip_w * 1.15:
        waist_reliable = False  # 腰比髋还宽太多，多半是残留手臂或宽松衣物
    meta["waist_reliable"] = waist_reliable
    meta["waist_reliable_row_ratio"] = round(waist_ratio_reliable, 3) if waist_widths else 0.0
    meta["hip_reliable_row_ratio"] = round(hip_ratio_reliable, 3)
    meta["loose_clothing_suspect"] = hip_w > bone_hip * BODY_LOOSE_HIP_FACTOR
    measurements = {
        "shoulder_width": float(shoulder_w),
        "hip_width": hip_w,
    }
    if waist_reliable and waist_w is not None:
        measurements["waist_width"] = waist_w
    return measurements, meta


# ---------------------------------------------------------------------------
# 结果结构与工具函数
# ---------------------------------------------------------------------------

def _attribute(status: str, confidence: float, label: str | None, issues: list[dict[str, str]], evidence: dict[str, Any], candidates: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    result = {
        "status": status,
        "label": label,
        "confidence": round(float(confidence), 2),
        "issues": issues,
        "evidence": evidence,
    }
    if candidates is not None:
        result["candidates"] = candidates
    return result


def _photo_result(status: str, confidence: float, issues: list[dict[str, str]], attributes: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    deduped = list({issue["code"]: issue for issue in issues}.values())
    return {
        "status": status,
        "confidence": round(float(confidence), 2),
        "issues": deduped,
        "suggestions": [issue["suggestion"] for issue in deduped if issue.get("suggestion")],
        "attributes": attributes,
        "evidence": evidence,
    }


def _ramp(value: float, low: float, high: float) -> float:
    """value 从 low 到 high 线性升到 1 的饱和函数。"""
    if high <= low:
        return 1.0 if value >= high else 0.0
    return _clamp01((value - low) / (high - low))


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return float(math.hypot(float(a[0]) - float(b[0]), float(a[1]) - float(b[1])))


def _angle_deg(a: tuple[float, float], vertex: tuple[float, float], b: tuple[float, float]) -> float:
    va = (float(a[0]) - float(vertex[0]), float(a[1]) - float(vertex[1]))
    vb = (float(b[0]) - float(vertex[0]), float(b[1]) - float(vertex[1]))
    norm = math.hypot(*va) * math.hypot(*vb)
    if norm <= 1e-6:
        return 180.0
    cosine = max(-1.0, min(1.0, (va[0] * vb[0] + va[1] * vb[1]) / norm))
    return math.degrees(math.acos(cosine))


__all__ = [
    "analyze_face_photo",
    "analyze_body_photo",
    "SKIN_TONE_LABELS",
    "FACE_SHAPE_LABELS",
    "BODY_SHAPE_LABELS",
]
