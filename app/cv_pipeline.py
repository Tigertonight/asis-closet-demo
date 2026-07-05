from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageFilter, ImageStat

try:
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions, vision
except Exception:  # pragma: no cover - optional runtime dependency
    mp = None
    BaseOptions = None
    vision = None

try:
    import colour_checker_detection as ccd
except Exception:  # pragma: no cover - optional runtime dependency
    ccd = None

try:
    import colour as colour_science
except Exception:  # pragma: no cover - optional runtime dependency
    colour_science = None


FACE_DETECTOR_MODEL = Path(__file__).resolve().parent / "models" / "blaze_face_short_range.tflite"
FACE_LANDMARKER_MODEL = Path(__file__).resolve().parent / "models" / "face_landmarker.task"
_MP_FACE_DETECTOR: Any | None = None
_MP_FACE_LANDMARKER: Any | None = None
ColorCardCandidate = tuple[int, int, int, int, float, float, str, dict[str, Any]]


class ColorCardDetector:
    name = "base"

    def detect(self, bgr: np.ndarray) -> ColorCardCandidate | None:
        raise NotImplementedError


class OpenCVColorCardDetector(ColorCardDetector):
    name = "opencv_contour_grid"

    def detect(self, bgr: np.ndarray) -> ColorCardCandidate | None:
        return _find_card_candidate(bgr)


class ColourScienceColorCardDetector(ColorCardDetector):
    name = "colour_science_segmentation"

    def detect(self, bgr: np.ndarray) -> ColorCardCandidate | None:
        if ccd is None:
            return None
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        detections = ccd.detect_colour_checkers_segmentation(rgb, additional_data=True)
        candidates = [_colour_science_detection_to_candidate(detection, bgr.shape) for detection in detections]
        candidates = [candidate for candidate in candidates if candidate is not None]
        if not candidates:
            return None
        return max(candidates, key=lambda candidate: candidate[4])


class HybridColorCardDetector(ColorCardDetector):
    name = "colour_science_segmentation_with_opencv_fallback"

    def __init__(self) -> None:
        self.colour_science_detector = ColourScienceColorCardDetector()
        self.opencv_detector = OpenCVColorCardDetector()

    def detect(self, bgr: np.ndarray) -> ColorCardCandidate | None:
        candidate = self.colour_science_detector.detect(bgr)
        if candidate is not None:
            return candidate
        return self.opencv_detector.detect(bgr)


_DEFAULT_COLOR_CARD_DETECTOR = HybridColorCardDetector()


def run_face_cv(image: Image.Image) -> dict[str, Any]:
    bgr = _pil_to_bgr(image)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    detections = _detect_face_candidates(bgr, gray)
    h, w = gray.shape[:2]
    raw_faces = []
    faces = []
    rejected = []
    for x, y, fw, fh, detector in detections:
        area_ratio = round(float((fw * fh) / (w * h)), 4)
        box = {"x": int(x), "y": int(y), "width": int(fw), "height": int(fh)}
        detector_is_semantic = detector.startswith("mediapipe")
        eye_count = 2 if detector_is_semantic else _eye_count(gray, box)
        face_item = {"box": box, "area_ratio": area_ratio, "detector": detector, "eye_like_count": eye_count}
        if area_ratio < 0.08 and eye_count == 0 and not detector_is_semantic:
            rejected.append({**face_item, "reason": "small_candidate_without_eye_structure"})
            continue
        raw_faces.append(face_item)
        if area_ratio >= 0.03:
            faces.append(face_item)

    if not faces:
        if raw_faces:
            return _stage("fail", 0.82, {"face_count": len(raw_faces), "faces": raw_faces, "rejected_candidates": rejected}, [_issue("face.too_small", "脸部占比过小", "请靠近一些拍摄，让脸部更清晰。")])
        message = "未检测到可用人像" if rejected else "未检测到可用正脸"
        suggestion = "请上传一张单人正脸自拍。" if rejected else "请重新拍摄正脸单人照。"
        return _stage("fail", 0.86, {"face_count": 0, "rejected_candidates": rejected}, [_issue("face.no_face", message, suggestion)])
    faces = _keep_dominant_face_if_clear(faces)
    if len(faces) > 1:
        return _stage("fail", 0.88, {"face_count": len(faces), "faces": faces}, [_issue("face.multiple_faces", "检测到多人脸", "请只保留本人单人正脸。")])

    face = faces[0]
    box = face["box"]
    ratio = face["area_ratio"]
    if ratio < 0.08:
        return _stage("fail", 0.84, {"face_count": 1, "primary_face": face}, [_issue("face.too_small", "脸部占比过小", "请靠近一些拍摄，让脸部更清晰。")])

    crop_issue = _face_crop_issue(box, w, h)
    if crop_issue and crop_issue["blocking"]:
        return _stage("fail", 0.82, {"face_count": 1, "primary_face": face, "cropped": True, "crop_edges": crop_issue["edges"]}, [crop_issue["issue"]])

    crop = gray[box["y"] : box["y"] + box["height"], box["x"] : box["x"] + box["width"]]
    sharpness = _sharpness(crop)
    # Smooth skin, compressed social posters, and beauty-camera selfies can have a low Laplacian
    # score inside the face box even when the face is clear enough for a consumer MVP result.
    if sharpness < 18:
        return _stage("fail", 0.8, {"face_count": 1, "primary_face": face, "face_sharpness": sharpness}, [_issue("face.blurry", "脸部区域偏糊", "请保持手机稳定后重拍。")])
    blur_issue = None
    if sharpness < 110:
        blur_issue = _issue("face.soft_detail", "脸部细节略软，已继续分析", "这张照片可以先测；更清晰的原图会让结果更稳定。")

    occlusion_issue = _face_occlusion_issue(bgr, box)
    if occlusion_issue:
        return _stage(
            "fail",
            0.78,
            {
                "model": "opencv_haar_frontal_profile_eye_checked",
                "face_count": 1,
                "primary_face": face,
                "face_sharpness": sharpness,
                "occlusion_evidence": occlusion_issue["evidence"],
            },
            [occlusion_issue["issue"]],
        )

    issues = [issue for issue in [crop_issue["issue"] if crop_issue else None, blur_issue] if issue]
    return _stage(
        "warn" if issues else "pass",
        0.74 if blur_issue else 0.78 if crop_issue else 0.86,
        {
            "model": "mediapipe_face_detection_with_haar_fallback",
            "face_count": 1,
            "primary_face": face,
            "face_sharpness": sharpness,
            **({"crop_edges": crop_issue["edges"]} if crop_issue else {}),
        },
        issues,
    )


def run_color_card_cv(image: Image.Image, detector: ColorCardDetector | None = None) -> dict[str, Any]:
    detector = detector or _DEFAULT_COLOR_CARD_DETECTOR
    detector_name = getattr(detector, "name", detector.__class__.__name__)
    bgr = _pil_to_bgr(image)
    h, w = bgr.shape[:2]
    try:
        candidate = detector.detect(bgr)
    except Exception as exc:
        return _missing_card_stage(
            detector_name,
            0.32,
            "detector_error",
            {
                "detector_error": str(exc),
            },
        )
    if candidate is None:
        return _missing_card_stage(detector_name)

    x, y, cw, ch, area_ratio, angle, method, grid_score = candidate
    aspect_ratio = cw / ch if ch else 0
    evidence = {
        "detected": True,
        "detector_adapter": detector_name,
        "card_type": "colorchecker_24_candidate",
        "detection_method": method,
        "card_box": {"x": x, "y": y, "width": cw, "height": ch},
        "area_ratio": round(area_ratio, 4),
        "aspect_ratio": round(aspect_ratio, 3),
        "angle": round(angle, 2),
        "grid_score": grid_score,
    }

    if area_ratio < 0.055:
        return _unusable_card_stage(evidence, "card.too_far", "色卡距离较远，本次不使用色卡校正", "已先用原图继续分析；想更准时可补拍一张色卡更近的照片。")
    if y + ch > h * 0.985 or x <= 2 or x + cw >= w - 2:
        return _unusable_card_stage(evidence, "card.cropped", "色卡不完整，本次不使用色卡校正", "已先用原图继续分析；想更准时可补拍完整色卡照片。")
    tilted_issue = None
    if abs(angle) > 8:
        tilted_issue = _issue("card.tilted", "色卡有一定倾斜，但完整可用", "后续建议尽量让色卡正对镜头。")

    crop = bgr[y : y + ch, x : x + cw]
    patch_stats = _sample_card_patches(crop)
    profile = _colorchecker_patch_profile(crop)
    evidence["patch_count"] = len(patch_stats)
    evidence["colorfulness"] = round(float(np.mean([p["saturation"] for p in patch_stats])), 2) if patch_stats else 0
    evidence["glare_ratio"] = round(_white_ratio(crop), 4)
    evidence["skin_occlusion_ratio"] = round(_skin_ratio(crop), 4)
    evidence["colorchecker_profile"] = profile

    if evidence["glare_ratio"] > 0.1:
        return _unusable_card_stage(evidence, "card.glare", "色卡反光明显，本次不使用色卡校正", "已先用原图继续分析；想更准时可避开反光后补拍色卡。")
    if evidence["skin_occlusion_ratio"] > 0.34:
        return _unusable_card_stage(evidence, "card.occluded", "色卡遮挡较明显，本次不使用色卡校正", "已先用原图继续分析；想更准时可避免手指遮挡色块。")
    if evidence["colorfulness"] > 140:
        return _unusable_card_stage(evidence, "card.fake", "疑似非标准色卡，本次不使用色卡校正", "已先用原图继续分析；想更准时可使用标准 24 色 ColorChecker。")
    if aspect_ratio < 1.2:
        code = "card.fake" if evidence["colorfulness"] > 90 else "card.wrong_lighting"
        message = "疑似非标准色卡，本次不使用色卡校正" if code == "card.fake" else "色卡状态不稳定，本次不使用色卡校正"
        suggestion = "已先用原图继续分析；想更准时可使用标准 24 色 ColorChecker。" if code == "card.fake" else "已先用原图继续分析；想更准时请让色卡和脸处在同一片均匀光线下。"
        return _unusable_card_stage(evidence, code, message, suggestion)
    if evidence["skin_occlusion_ratio"] > 0.22 and evidence["colorfulness"] > 100:
        evidence["usable_for_correction"] = False
        evidence["fallback"] = "uncorrected_image_inference"
        return _stage("warn", 0.62, evidence, [_issue("card.occluded", "色卡局部可能有遮挡", "本次会继续分析；如需更准，请避免手指遮挡色块。")])
    if evidence["colorfulness"] < 28:
        return _unusable_card_stage(evidence, "card.fake", "色卡色块特征不足，本次不使用色卡校正", "已先用原图继续分析；想更准时可使用标准 24 色 ColorChecker。")

    evidence["usable_for_correction"] = True
    evidence["same_lighting_as_face"] = True
    if tilted_issue:
        return _stage("warn", 0.72, evidence, [tilted_issue])
    return _stage("pass", 0.84, evidence, [])


def run_color_correction(image: Image.Image, color_card_stage: dict[str, Any]) -> dict[str, Any]:
    if color_card_stage["status"] not in {"pass", "warn"}:
        return _stage(
            "unknown",
            0.0,
            {"skipped": True, "reason": "color_card_cv_not_pass"},
            [],
        )
    evidence = color_card_stage.get("evidence", {})
    if not evidence.get("detected") or not evidence.get("usable_for_correction", False) or "card_box" not in evidence:
        return _stage(
            "warn",
            0.35,
            {"skipped": True, "reason": "color_card_unavailable", "fallback": "uncorrected_image_inference"},
            [_issue("correction.no_card_fallback", "未使用色卡校正，已使用原图继续推理", "建议下次加入标准 24 色卡，以提升肤色校正和季节型判断稳定性。")],
        )

    bgr = _pil_to_bgr(image)
    box = evidence["card_box"]
    crop = bgr[box["y"] : box["y"] + box["height"], box["x"] : box["x"] + box["width"]]
    patches = _sample_card_patches(crop)
    if len(patches) < 18:
        return _card_correction_fallback(
            "correction.patch_count_low",
            "色卡可用色块不足，已改用原图继续推理",
            "这张照片仍可分析；想要更准时，可以补拍一张完整清晰的色卡照。",
            {"patch_count": len(patches)},
        )

    observed = np.array([p["rgb"] for p in patches], dtype=np.float32)
    target = _reference_colorchecker_rgb()[: len(observed)].astype(np.float32)
    rgb_before = _mean_rgb_distance(observed, target)
    corrected, matrix = _linear_color_correct(observed, target)
    rgb_after = _mean_rgb_distance(corrected, target)
    delta_e_before = _mean_delta_e_2000(observed, target)
    delta_e_after = _mean_delta_e_2000(corrected, target)
    if not np.isfinite(rgb_after):
        return _card_correction_fallback(
            "correction.solve_failed",
            "色卡校正不稳定，已改用原图继续推理",
            "这张照片仍可分析；想要更准时，可以在均匀自然光下补拍带色卡照片。",
            {"delta_e_before": round(rgb_before, 2), "rgb_distance_before": round(rgb_before, 2)},
        )

    standard_metric_available = np.isfinite(delta_e_before) and np.isfinite(delta_e_after)
    improved = delta_e_after < delta_e_before if standard_metric_available else rgb_after < rgb_before
    status = "pass" if improved else "warn"
    issues = [] if status == "pass" else [_issue("correction.not_improved", "色彩校正改善有限", "建议在更均匀光线下重拍。")]
    correction_quality = _correction_quality(delta_e_after if standard_metric_available else rgb_after, standard_metric_available)
    return _stage(
        status,
        0.78 if status == "pass" else 0.58,
        {
            "method": "linear_rgb_matrix_with_colour_science_delta_e",
            "patch_count": len(patches),
            "delta_e_before": round(rgb_before, 2),
            "delta_e_after": round(rgb_after, 2),
            "improvement": round(rgb_before - rgb_after, 2),
            "rgb_distance_before": round(rgb_before, 2),
            "rgb_distance_after": round(rgb_after, 2),
            "rgb_distance_improvement": round(rgb_before - rgb_after, 2),
            "delta_e_2000_before": round(delta_e_before, 2) if np.isfinite(delta_e_before) else None,
            "delta_e_2000_after": round(delta_e_after, 2) if np.isfinite(delta_e_after) else None,
            "delta_e_2000_improvement": round(delta_e_before - delta_e_after, 2) if standard_metric_available else None,
            "delta_e_method": "CIE 2000" if standard_metric_available else "unavailable",
            "correction_quality": correction_quality,
            "matrix_rgb_3x4": [[round(float(value), 6) for value in row] for row in matrix.T.tolist()],
        },
        issues,
    )


def _unusable_card_stage(evidence: dict[str, Any], code: str, message: str, suggestion: str) -> dict[str, Any]:
    return _stage(
        "warn",
        0.5,
        {
            **evidence,
            "detected": True,
            "usable_for_correction": False,
            "fallback": "uncorrected_image_inference",
        },
        [_issue(code, message, suggestion)],
    )


def _missing_card_stage(
    detector_name: str,
    confidence: float = 0.42,
    detection_method: str = "color_grid_rejected_or_missing",
    extra_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _stage(
        "warn",
        confidence,
        {
            "detected": False,
            "usable_for_correction": False,
            "detector_adapter": detector_name,
            "detection_method": detection_method,
            **(extra_evidence or {}),
        },
        [_issue("card.missing", "未检测到标准色卡", "本次会先使用原图继续分析；想要更准时可补拍带标准色卡的照片。")],
    )


def _card_correction_fallback(code: str, message: str, suggestion: str, evidence: dict[str, Any]) -> dict[str, Any]:
    return _stage(
        "warn",
        0.36,
        {
            **evidence,
            "skipped": True,
            "reason": code,
            "fallback": "uncorrected_image_inference",
        },
        [_issue(code, message, suggestion)],
    )


def run_skin_tone(image: Image.Image, face_stage: dict[str, Any], color_correction_stage: dict[str, Any]) -> dict[str, Any]:
    face = _primary_face(face_stage, image.size)
    if face is None:
        return _stage("unknown", 0.0, {"reason": "face_box_missing"}, [])

    rgb = np.array(image.convert("RGB"))
    box = face["box"]
    layout = _face_landmark_region_layout(rgb, face)
    regions = layout["skin_regions"] if layout else _skin_regions(box, rgb.shape[1], rgb.shape[0])
    region_source = layout["source"] if layout else "face_box_ratio"
    landmark_keypoints = layout.get("keypoints", {}) if layout else {}
    stable_samples = []
    fallback_samples = []
    region_evidence = []
    for name, region in regions.items():
        x0, y0, x1, y1 = region
        patch = rgb[y0:y1, x0:x1]
        if patch.size == 0:
            continue
        sample = _adaptive_skin_region_sample(patch)
        median_rgb = np.median(sample["pixels"], axis=0)
        if sample["stable"]:
            stable_samples.append(median_rgb)
        else:
            fallback_samples.append(median_rgb)
        region_evidence.append(
            {
                "name": name,
                "box": {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0},
                "source": region_source,
                "skin_pixels": sample["skin_pixels"],
                "skin_ratio": sample["skin_ratio"],
                "selection_method": sample["method"],
                "stable": sample["stable"],
                **({"selected_window": sample["selected_window"]} if sample.get("selected_window") else {}),
            }
        )

    samples = stable_samples or fallback_samples
    if not samples:
        return _stage("fail", 0.56, {"regions": region_evidence}, [_issue("skin.sample_failed", "无法稳定提取肤色区域", "请上传清晰正脸照。")])

    raw_median = np.median(np.array(samples), axis=0).astype(np.float32)
    full_corrected_median = _apply_rgb_correction(raw_median, color_correction_stage)
    correction_strength = _skin_correction_strength(raw_median, full_corrected_median, color_correction_stage)
    corrected_median = raw_median * (1.0 - correction_strength) + full_corrected_median * correction_strength
    median = corrected_median.astype(np.uint8)
    raw_uint8 = np.clip(raw_median, 0, 255).astype(np.uint8)
    full_corrected_uint8 = np.clip(full_corrected_median, 0, 255).astype(np.uint8)
    correction_applied = bool(color_correction_stage.get("evidence", {}).get("matrix_rgb_3x4"))
    lab = cv2.cvtColor(np.uint8([[median]]), cv2.COLOR_RGB2LAB)[0][0].astype(float)
    hsv = cv2.cvtColor(np.uint8([[median]]), cv2.COLOR_RGB2HSV)[0][0].astype(float)
    l_star = float(round(float(lab[0] * 100 / 255), 2))
    a_star = float(round(float(lab[1] - 128), 2))
    b_star = float(round(float(lab[2] - 128), 2))
    hue = float(round(float(hsv[0] * 2), 2))
    saturation = float(round(float(hsv[1] * 100 / 255), 2))
    value = float(round(float(hsv[2] * 100 / 255), 2))

    warmth_score = round(b_star - 0.35 * a_star, 2)
    temperature = "warm" if warmth_score >= 8 else "cool" if warmth_score <= 4 else "neutral"
    brightness = "light" if l_star >= 67 else "deep" if l_star <= 52 else "medium"
    chroma_value = float(np.sqrt(a_star**2 + b_star**2))
    chroma = "bright" if chroma_value >= 25 or saturation >= 34 else "muted" if chroma_value <= 16 and saturation <= 24 else "medium"

    correction_status = color_correction_stage.get("status")
    confidence = 0.72
    if correction_status == "pass":
        confidence += 0.08
    elif correction_status == "warn":
        confidence -= 0.08
    if face_stage.get("status") == "warn":
        confidence -= 0.06
    confidence = round(max(0.42, min(0.86, confidence)), 2)

    issues = []
    status = "pass"
    if temperature == "neutral":
        status = "warn"
        issues.append(_issue("skin.temperature_ambiguous", "肤色冷暖接近中性", "建议结合更多照片或色卡提高判断稳定性。"))

    return _stage(
        status,
        confidence,
        {
            "method": "adaptive_skin_mask_region_median_rgb_lab_hsv",
            "region_source": region_source,
            **({"landmark_keypoints": landmark_keypoints} if landmark_keypoints else {}),
            "regions": region_evidence,
            "sample_quality": {
                "stable_region_count": len(stable_samples),
                "fallback_region_count": len(fallback_samples),
                "used_stable_regions": bool(stable_samples),
            },
            "color_values": {
                "rgb": [int(v) for v in median.tolist()],
                "raw_rgb": [int(v) for v in raw_uint8.tolist()],
                "full_corrected_rgb": [int(v) for v in full_corrected_uint8.tolist()],
                "lab": [l_star, a_star, b_star],
                "hsv": [hue, saturation, value],
                "correction_applied": correction_applied,
                "correction_strength": round(correction_strength, 2),
            },
            "scores": {
                "warmth": warmth_score,
                "chroma": round(chroma_value, 2),
            },
            "dimensions": {
                "temperature": temperature,
                "brightness": brightness,
                "chroma": chroma,
                "undertone": temperature,
            },
        },
        issues,
    )


def run_feature_contrast(image: Image.Image, face_stage: dict[str, Any], skin_stage: dict[str, Any]) -> dict[str, Any]:
    face = _primary_face(face_stage, image.size)
    if face is None or skin_stage.get("status") not in {"pass", "warn"}:
        return _stage("unknown", 0.0, {"reason": "missing_face_or_skin"}, [])

    rgb = np.array(image.convert("RGB"))
    box = face["box"]
    x, y, w, h = [int(box[k]) for k in ["x", "y", "width", "height"]]
    img_h, img_w = rgb.shape[:2]
    layout = _face_landmark_region_layout(rgb, face)
    regions = layout["feature_regions"] if layout else {
        "hair": _clip_box(x + int(w * 0.12), y - int(h * 0.18), x + int(w * 0.88), y + int(h * 0.16), img_w, img_h),
        "left_eye": _clip_box(x + int(w * 0.22), y + int(h * 0.34), x + int(w * 0.43), y + int(h * 0.48), img_w, img_h),
        "right_eye": _clip_box(x + int(w * 0.57), y + int(h * 0.34), x + int(w * 0.78), y + int(h * 0.48), img_w, img_h),
    }
    region_source = layout["source"] if layout else "face_box_ratio"
    landmark_keypoints = layout.get("keypoints", {}) if layout else {}

    luminance = {}
    region_evidence = {}
    for name, region in regions.items():
        x0, y0, x1, y1 = region
        patch = rgb[y0:y1, x0:x1]
        if patch.size == 0:
            continue
        sample = _feature_luminance_sample(patch, "hair" if name == "hair" else "eye")
        luminance[name] = sample["luminance"]
        region_evidence[name] = {
            "x": x0,
            "y": y0,
            "width": x1 - x0,
            "height": y1 - y0,
            "source": region_source,
            "selection_method": sample["method"],
            "dark_pixel_ratio": sample["dark_pixel_ratio"],
            "skin_pixel_ratio": sample["skin_pixel_ratio"],
            "sample_pixels": sample["sample_pixels"],
            "stable": sample["stable"],
        }

    skin_rgb = np.array(skin_stage["evidence"]["color_values"]["rgb"], dtype=np.uint8)
    skin_luma = float(cv2.cvtColor(np.uint8([[skin_rgb]]), cv2.COLOR_RGB2GRAY)[0][0])
    feature_luma_values = list(luminance.values()) or [skin_luma]
    feature_luma = min(feature_luma_values)
    delta = skin_luma - feature_luma
    contrast = "high" if delta >= 78 else "low" if delta <= 38 else "medium"
    eye_luma = np.mean([v for k, v in luminance.items() if "eye" in k]) if any("eye" in k for k in luminance) else feature_luma
    hair_luma = luminance.get("hair", feature_luma)

    return _stage(
        "pass",
        0.7,
        {
            "method": "adaptive_feature_luminance_contrast",
            "region_source": region_source,
            **({"landmark_keypoints": landmark_keypoints} if landmark_keypoints else {}),
            "regions": region_evidence,
            "sample_quality": {
                "stable_region_count": sum(1 for item in region_evidence.values() if item["stable"]),
                "fallback_region_count": sum(1 for item in region_evidence.values() if not item["stable"]),
            },
            "luminance": {
                "skin": round(skin_luma, 2),
                "hair": round(hair_luma, 2),
                "eyes": round(float(eye_luma), 2),
                "delta": round(delta, 2),
            },
            "eye_color": _tone_label(float(eye_luma)),
            "hair_color": _tone_label(float(hair_luma)),
            "overall_contrast": contrast,
        },
        [],
    )


def available_color_card_detectors() -> list[dict[str, str]]:
    return [
        {
            "name": _DEFAULT_COLOR_CARD_DETECTOR.name,
            "role": "default",
            "status": "active",
            "description": "优先尝试 colour-science 官方色卡检测，未通过位置/形态校验时回退到本地 OpenCV 检测器",
        },
        {
            "name": "colour_checker_detection",
            "role": "primary_adapter",
            "status": "active" if ccd is not None else "missing_dependency",
            "description": "colour-science 的 ColorChecker segmentation 检测能力",
        },
        {
            "name": OpenCVColorCardDetector.name,
            "role": "fallback_adapter",
            "status": "active",
            "description": "本地 OpenCV 色块网格/轮廓检测器",
        },
    ]


def run_local_visual_risk_review(image: Image.Image, face_stage: dict[str, Any]) -> dict[str, Any]:
    face = _primary_face(face_stage, image.size)
    if face is None:
        return _stage(
            "unknown",
            0.0,
            {"source": "local_cv_visual_risk", "reason": "face_box_missing"},
            [],
        )

    rgb = np.array(image.convert("RGB"))
    img_h, img_w = rgb.shape[:2]
    box = face["box"]
    x, y, w, h = [int(box[k]) for k in ["x", "y", "width", "height"]]
    regions = {
        "forehead": _clip_box(x + int(w * 0.35), y + int(h * 0.18), x + int(w * 0.65), y + int(h * 0.32), img_w, img_h),
        "left_cheek": _clip_box(x + int(w * 0.18), y + int(h * 0.50), x + int(w * 0.42), y + int(h * 0.68), img_w, img_h),
        "right_cheek": _clip_box(x + int(w * 0.58), y + int(h * 0.50), x + int(w * 0.82), y + int(h * 0.68), img_w, img_h),
        "eye_band": _clip_box(x + int(w * 0.16), y + int(h * 0.30), x + int(w * 0.84), y + int(h * 0.50), img_w, img_h),
        "mouth": _clip_box(x + int(w * 0.33), y + int(h * 0.62), x + int(w * 0.67), y + int(h * 0.80), img_w, img_h),
        "face_center": _clip_box(x + int(w * 0.18), y + int(h * 0.24), x + int(w * 0.82), y + int(h * 0.82), img_w, img_h),
        "right_lower_edge": _clip_box(x + int(w * 0.78), y + int(h * 0.55), x + int(w * 1.12), y + int(h * 0.92), img_w, img_h),
        "left_lower_edge": _clip_box(x - int(w * 0.12), y + int(h * 0.55), x + int(w * 0.22), y + int(h * 0.92), img_w, img_h),
    }

    stats = {name: _region_color_stats(rgb, region) for name, region in regions.items()}
    mask_stats = {name: _region_mask_stats(rgb, region) for name, region in regions.items()}
    cheek_redness = float(np.mean([stats["left_cheek"]["redness"], stats["right_cheek"]["redness"]]))
    cheek_saturation = float(np.mean([stats["left_cheek"]["saturation"], stats["right_cheek"]["saturation"]]))
    cheek_skin = float(np.mean([mask_stats["left_cheek"]["skin_ratio"], mask_stats["right_cheek"]["skin_ratio"]]))
    forehead_redness = stats["forehead"]["redness"]
    forehead_darkness = mask_stats["forehead"]["dark_ratio"]
    mouth_redness = stats["mouth"]["redness"]
    mouth_saturation = stats["mouth"]["saturation"]
    eye_glare = mask_stats["eye_band"]["bright_low_sat_ratio"]
    side_skin = max(mask_stats["left_lower_edge"]["skin_ratio"], mask_stats["right_lower_edge"]["skin_ratio"])
    face_center = rgb[regions["face_center"][1] : regions["face_center"][3], regions["face_center"][0] : regions["face_center"][2]]
    skin_texture = _skin_texture_score(face_center)
    channel_cast = _channel_cast_score(rgb)
    forehead_shadow_like = forehead_darkness > 0.28 or (cheek_redness - forehead_redness > 24 and cheek_saturation > 20)

    issues = []
    if (mouth_redness - cheek_redness > 16 and mouth_saturation > 42) or (mouth_redness >= 90 and mouth_saturation > 45 and mouth_redness - cheek_redness >= 3):
        issues.append(_issue("vl.lipstick", "检测到唇部颜色偏明显", "口红不影响基础肤色采样，本次会继续分析并降低一点可信度。"))
    if not forehead_shadow_like and cheek_redness - forehead_redness > 9 and cheek_saturation > 28:
        issues.append(_issue("vl.blush", "脸颊颜色偏红，可能有腮红或局部泛红", "已尽量结合额头和下颌区域；自然光淡妆或素颜照会更稳。"))
    if channel_cast["dominant_channel"] in {"blue", "green"} and channel_cast["cast_strength"] > 18:
        issues.append(_issue("vl.color_filter", "照片整体颜色有偏色倾向", "本次结果可作为初步参考；关闭滤镜、使用自然光原图会更准。"))
    elif channel_cast["cast_strength"] > 42 and channel_cast["dominant_channel"] in {"red", "blue", "green"}:
        issues.append(_issue("vl.color_filter", "照片整体颜色有偏色倾向", "本次结果可作为初步参考；关闭滤镜、使用自然光原图会更准。"))
    if skin_texture < 18 and face_stage.get("evidence", {}).get("face_sharpness", 0) > 160:
        issues.append(_issue("vl.beauty_filter", "脸部纹理过于平滑，可能有轻微美颜", "美颜可能改变肤色表现，本次会降低一点可信度。"))
    if forehead_shadow_like:
        issues.append(_issue("vl.hat_bangs", "刘海或帽檐可能影响额头区域", "本次会优先参考脸颊和下颌；下次露出额头会更稳定。"))
    if side_skin > 0.7 and cheek_redness >= 52 and 260 <= skin_texture <= 900:
        issues.append(_issue("vl.hand_near_face", "手部靠近脸颊或下巴", "本次会避开受影响区域继续分析。"))

    evidence = {
        "source": "local_cv_visual_risk",
        "semantic_review_available": False,
        "method": "face_region_color_texture_heuristics",
        "scores": {
            "mouth_redness": round(mouth_redness, 2),
            "mouth_saturation": round(mouth_saturation, 2),
            "cheek_redness": round(cheek_redness, 2),
            "forehead_redness": round(forehead_redness, 2),
            "cheek_saturation": round(cheek_saturation, 2),
            "skin_texture": round(skin_texture, 2),
            "forehead_darkness": round(forehead_darkness, 3),
            "eye_glare": round(eye_glare, 3),
            "side_skin": round(side_skin, 3),
            **channel_cast,
        },
        "risk_codes": [issue["code"] for issue in issues],
    }
    if not issues:
        return _stage("pass", 0.58, evidence, [])
    return _stage(
        "warn",
        0.56,
        evidence,
        issues,
    )


def run_seasonal_result(skin_stage: dict[str, Any], feature_stage: dict[str, Any], color_card_stage: dict[str, Any], color_correction_stage: dict[str, Any]) -> dict[str, Any]:
    if skin_stage.get("status") not in {"pass", "warn"} or feature_stage.get("status") not in {"pass", "warn"}:
        return _stage("unknown", 0.0, {"reason": "missing_skin_or_contrast"}, [])

    dims = skin_stage["evidence"]["dimensions"]
    temperature = dims["temperature"]
    brightness = dims["brightness"]
    chroma = dims["chroma"]
    contrast = feature_stage["evidence"]["overall_contrast"]
    layered = _layered_color_diagnosis(skin_stage, feature_stage)
    ranking = _seasonal_drape_ranking(layered, brightness, chroma, contrast)
    ranking = _ranking_with_probabilities(ranking)
    primary = ranking[0]
    season_4 = primary["season_4"]
    season_12 = primary["season_12"]
    season_24 = f"{season_12}_{brightness}_{chroma}_{contrast}"
    confidence = 0.62
    confidence += 0.08 if color_card_stage.get("status") == "pass" else -0.04
    confidence += 0.06 if color_correction_stage.get("status") == "pass" else -0.04
    confidence += min(0.08, max(0.0, skin_stage.get("confidence", 0.0) - 0.68))
    confidence += 0.03 if feature_stage.get("confidence", 0.0) >= 0.7 else 0
    if temperature == "neutral":
        confidence -= 0.06
    confidence = round(max(0.38, min(0.88, confidence)), 2)

    ambiguous = [item["season_12"] for item in ranking[1:3] if primary["score"] - item["score"] <= 0.12]
    if not ambiguous:
        ambiguous = _adjacent_seasons(season_12, temperature, brightness, chroma, contrast)
    top_candidates = _top_season_candidates_from_ranking(ranking, brightness, chroma, contrast, confidence)
    uncertainty_flags = _seasonal_uncertainty_flags(
        layered,
        color_card_stage,
        color_correction_stage,
        primary,
        ranking,
        brightness,
        chroma,
        contrast,
    )
    issues = []
    status = "pass"
    if confidence < 0.58:
        status = "warn"
        issues.append(_issue("seasonal.low_confidence", "季节型判断置信度较低", "建议补充自然光正脸照或标准色卡照复核。"))

    return _stage(
        status,
        confidence,
        {
            "method": "layered_lab_hsv_virtual_drape_ranking",
            "season_4": season_4,
            "season_12": season_12,
            "season_24": season_24,
            "confidence": confidence,
            "probability": primary.get("probability"),
            "probability_percent": primary.get("probability_percent"),
            "ambiguous_between": ambiguous,
            "top_candidates": top_candidates,
            "layered_diagnosis": layered,
            "virtual_drape_ranking": ranking,
            "uncertainty_flags": uncertainty_flags,
            "why": [
                f"肤色温度为 {temperature}",
                f"明度为 {brightness}",
                f"彩度为 {chroma}",
                f"整体对比度为 {contrast}",
                f"虚拟色布评分最高为 {season_12}，主倾向概率约 {primary.get('probability_percent')}%",
            ],
            "suitable_colors": _suitable_colors(season_4, season_12),
            "avoid_colors": _avoid_colors(season_4, season_12),
        },
        issues,
    )


def _primary_face(face_stage: dict[str, Any], image_size: tuple[int, int]) -> dict[str, Any] | None:
    evidence = face_stage.get("evidence", {})
    face = evidence.get("primary_face")
    if face and "box" in face:
        return face
    faces = evidence.get("faces") or []
    if len(faces) == 1 and "box" in faces[0]:
        return faces[0]
    width, height = image_size
    if face_stage.get("status") == "warn" and "face.auto_cropped" in evidence.get("auto_preprocessing", []):
        side = int(min(width, height) * 0.46)
        return {
            "box": {
                "x": int((width - side) / 2),
                "y": int(height * 0.22),
                "width": side,
                "height": side,
            },
            "area_ratio": round((side * side) / (width * height), 4),
            "estimated": True,
        }
    return None


def _detect_face_candidates(bgr: np.ndarray, gray: np.ndarray) -> list[tuple[int, int, int, int, str]]:
    candidates: list[tuple[int, int, int, int, str]] = []
    candidates.extend(_detect_mediapipe_face_candidates(bgr))
    frontal = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    profile = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_profileface.xml")

    for x, y, w, h in frontal.detectMultiScale(gray, scaleFactor=1.08, minNeighbors=4, minSize=(80, 80)):
        candidates.append((int(x), int(y), int(w), int(h), "haar_frontal"))
    for x, y, w, h in profile.detectMultiScale(gray, scaleFactor=1.08, minNeighbors=4, minSize=(80, 80)):
        candidates.append((int(x), int(y), int(w), int(h), "haar_profile"))

    flipped = cv2.flip(gray, 1)
    image_width = gray.shape[1]
    for x, y, w, h in profile.detectMultiScale(flipped, scaleFactor=1.08, minNeighbors=4, minSize=(80, 80)):
        candidates.append((int(image_width - x - w), int(y), int(w), int(h), "haar_profile_flipped"))

    return _dedupe_face_candidates(candidates)


def _detect_mediapipe_face_candidates(bgr: np.ndarray) -> list[tuple[int, int, int, int, str]]:
    detector = _mediapipe_face_detector()
    if mp is None or detector is None:
        return []
    h, w = bgr.shape[:2]
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    candidates: list[tuple[int, int, int, int, str]] = []
    try:
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        results = detector.detect(image)
    except Exception:
        return []
    for detection in results.detections:
        score = float(detection.categories[0].score) if detection.categories else 0.0
        box = detection.bounding_box
        x = int(box.origin_x)
        y = int(box.origin_y)
        bw = int(box.width)
        bh = int(box.height)
        pad_x = int(bw * 0.08)
        pad_top = int(bh * 0.12)
        pad_bottom = int(bh * 0.18)
        x0 = max(0, x - pad_x)
        y0 = max(0, y - pad_top)
        x1 = min(w, x + bw + pad_x)
        y1 = min(h, y + bh + pad_bottom)
        cw = x1 - x0
        ch = y1 - y0
        if cw <= 0 or ch <= 0:
            continue
        candidates.append((x0, y0, cw, ch, f"mediapipe_tasks_{score:.2f}"))
    return candidates


def _mediapipe_face_detector() -> Any | None:
    global _MP_FACE_DETECTOR
    if _MP_FACE_DETECTOR is not None:
        return _MP_FACE_DETECTOR
    if mp is None or BaseOptions is None or vision is None or not FACE_DETECTOR_MODEL.exists():
        return None
    try:
        options = vision.FaceDetectorOptions(
            base_options=BaseOptions(model_asset_path=str(FACE_DETECTOR_MODEL)),
            min_detection_confidence=0.5,
            min_suppression_threshold=0.3,
        )
        _MP_FACE_DETECTOR = vision.FaceDetector.create_from_options(options)
    except Exception:
        _MP_FACE_DETECTOR = None
    return _MP_FACE_DETECTOR


def _mediapipe_face_landmarker() -> Any | None:
    global _MP_FACE_LANDMARKER
    if _MP_FACE_LANDMARKER is not None:
        return _MP_FACE_LANDMARKER
    if mp is None or BaseOptions is None or vision is None or not FACE_LANDMARKER_MODEL.exists():
        return None
    try:
        options = vision.FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(FACE_LANDMARKER_MODEL)),
            running_mode=vision.RunningMode.IMAGE,
            num_faces=1,
        )
        _MP_FACE_LANDMARKER = vision.FaceLandmarker.create_from_options(options)
    except Exception:
        _MP_FACE_LANDMARKER = None
    return _MP_FACE_LANDMARKER


def _dedupe_face_candidates(candidates: list[tuple[int, int, int, int, str]]) -> list[tuple[int, int, int, int, str]]:
    deduped: list[tuple[int, int, int, int, str]] = []
    for candidate in sorted(candidates, key=lambda item: item[2] * item[3], reverse=True):
        if all(not _same_face_candidate(candidate[:4], existing[:4]) for existing in deduped):
            deduped.append(candidate)
    return deduped


def _same_face_candidate(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    return _box_iou(a, b) >= 0.35 or _smaller_box_coverage(a, b) >= 0.62


def _keep_dominant_face_if_clear(faces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(faces) <= 1:
        return faces
    ranked = sorted(faces, key=lambda face: float(face.get("area_ratio", 0.0)), reverse=True)
    largest = float(ranked[0].get("area_ratio", 0.0))
    second = float(ranked[1].get("area_ratio", 0.0))
    if largest >= max(second * 3.0, 0.12) and second < 0.06:
        dominant = dict(ranked[0])
        dominant["suppressed_secondary_faces"] = ranked[1:]
        return [dominant]
    return ranked


def _face_crop_issue(box: dict[str, int], image_width: int, image_height: int) -> dict[str, Any] | None:
    x, y, w, h = [int(box[k]) for k in ["x", "y", "width", "height"]]
    margin_x = w * 0.08
    margin_y = h * 0.08
    edges = {
        "left": x < margin_x,
        "top": y < margin_y,
        "right": x + w > image_width - margin_x,
        "bottom": y + h > image_height - margin_y,
    }
    touched = [edge for edge, value in edges.items() if value]
    if not touched:
        return None

    border_touch = x <= 2 or y <= 2 or x + w >= image_width - 2 or y + h >= image_height - 2
    blocking = border_touch or any(edge in touched for edge in ["bottom"]) or len(touched) >= 2
    if blocking:
        return {
            "blocking": True,
            "edges": edges,
            "issue": _issue("face.cropped", "脸部不完整", "请换一张脸颊和下巴都完整入镜的单人正脸照。"),
        }
    return {
        "blocking": False,
        "edges": edges,
        "issue": _issue("face.edge_close", "脸部略贴近画面边缘，已继续分析", "这张照片可以继续测；下次可以把手机拿远一点，让脸部更完整。"),
    }


def _box_iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ax1, ay1, bx1, by1 = ax + aw, ay + ah, bx + bw, by + bh
    ix0, iy0 = max(ax, bx), max(ay, by)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    intersection = (ix1 - ix0) * (iy1 - iy0)
    union = aw * ah + bw * bh - intersection
    return float(intersection / union) if union else 0.0


def _smaller_box_coverage(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ax1, ay1, bx1, by1 = ax + aw, ay + ah, bx + bw, by + bh
    ix0, iy0 = max(ax, bx), max(ay, by)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    intersection = (ix1 - ix0) * (iy1 - iy0)
    smaller = min(aw * ah, bw * bh)
    return float(intersection / smaller) if smaller else 0.0


def _eye_count(gray: np.ndarray, box: dict[str, int]) -> int:
    x, y, w, h = [int(box[k]) for k in ["x", "y", "width", "height"]]
    roi = gray[y : y + h, x : x + w]
    if roi.size == 0:
        return 0
    eye = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_eye.xml")
    min_size = (max(10, w // 12), max(8, h // 16))
    detections = eye.detectMultiScale(roi, scaleFactor=1.08, minNeighbors=3, minSize=min_size)
    return int(len(detections))


def _face_occlusion_issue(bgr: np.ndarray, box: dict[str, int]) -> dict[str, Any] | None:
    x, y, w, h = [int(box[k]) for k in ["x", "y", "width", "height"]]
    crop = bgr[y : y + h, x : x + w]
    if crop.size == 0:
        return None

    def region_stats(region: np.ndarray) -> dict[str, float]:
        if region.size == 0:
            return {"skin": 0.0, "dark": 0.0, "bright_low_sat": 0.0, "mean_v": 0.0, "mean_s": 0.0}
        hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
        gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
        hue, sat, value = cv2.split(hsv)
        skin = (hue < 25) & (sat > 30) & (sat < 140) & (value > 90) & (value < 245)
        dark = gray < 55
        bright_low_sat = (value > 150) & (sat < 45)
        return {
            "skin": round(float(np.mean(skin)), 3),
            "dark": round(float(np.mean(dark)), 3),
            "bright_low_sat": round(float(np.mean(bright_low_sat)), 3),
            "mean_v": round(float(np.mean(value)), 1),
            "mean_s": round(float(np.mean(sat)), 1),
        }

    eye_region = crop[int(0.22 * h) : int(0.48 * h), int(0.08 * w) : int(0.92 * w)]
    lower_region = crop[int(0.55 * h) : int(0.9 * h), int(0.18 * w) : int(0.82 * w)]
    cheek_region = crop[int(0.42 * h) : int(0.72 * h), int(0.1 * w) : int(0.9 * w)]
    eye = region_stats(eye_region)
    lower = region_stats(lower_region)
    cheek = region_stats(cheek_region)
    evidence = {"eye_region": eye, "lower_face_region": lower, "cheek_region": cheek}

    eye_much_darker_than_face = eye["mean_v"] < min(lower["mean_v"] - 70, cheek["mean_v"] - 45)
    low_saturation_dark_cover = eye["mean_s"] < 68 and eye["dark"] > 0.52
    if low_saturation_dark_cover and eye["skin"] < 0.48 and eye["mean_v"] < 118 and eye_much_darker_than_face:
        return {
            "issue": _issue("face.eye_occluded", "眼部有明显遮挡", "请摘下墨镜或避免眼部大面积遮挡后再拍。"),
            "evidence": evidence,
        }
    if lower["skin"] < 0.45 and cheek["skin"] > 0.45 and (lower["bright_low_sat"] > 0.55 or lower["dark"] > 0.35):
        return {
            "issue": _issue("face.lower_occluded", "下半脸有明显遮挡", "请摘下口罩，并保证脸颊、下巴区域清晰可见。"),
            "evidence": evidence,
        }
    return None


def _skin_regions(box: dict[str, int], image_width: int, image_height: int) -> dict[str, tuple[int, int, int, int]]:
    x, y, w, h = [int(box[k]) for k in ["x", "y", "width", "height"]]
    regions = {
        "forehead": (x + int(w * 0.36), y + int(h * 0.18), x + int(w * 0.64), y + int(h * 0.31)),
        "left_cheek": (x + int(w * 0.18), y + int(h * 0.48), x + int(w * 0.40), y + int(h * 0.67)),
        "right_cheek": (x + int(w * 0.60), y + int(h * 0.48), x + int(w * 0.82), y + int(h * 0.67)),
        "jaw": (x + int(w * 0.38), y + int(h * 0.70), x + int(w * 0.62), y + int(h * 0.84)),
    }
    return {name: _clip_box(*region, image_width, image_height) for name, region in regions.items()}


def _face_landmark_region_layout(rgb: np.ndarray, face: dict[str, Any]) -> dict[str, Any] | None:
    landmarks = _detect_face_landmarks(rgb)
    if not landmarks:
        return None
    image_height, image_width = rgb.shape[:2]
    points = _landmark_pixel_points(landmarks, image_width, image_height)
    if not points:
        return None

    xs = [point[0] for point in points.values()]
    ys = [point[1] for point in points.values()]
    lx0, ly0, lx1, ly1 = min(xs), min(ys), max(xs), max(ys)
    landmark_box = (lx0, ly0, max(1, lx1 - lx0), max(1, ly1 - ly0))
    face_box = face.get("box", {})
    if {"x", "y", "width", "height"}.issubset(face_box):
        primary_box = (int(face_box["x"]), int(face_box["y"]), int(face_box["width"]), int(face_box["height"]))
        if _box_iou(landmark_box, primary_box) < 0.12:
            return None

    face_w = max(24, landmark_box[2])
    face_h = max(24, landmark_box[3])
    skin_regions = {
        "forehead": _landmark_center_box(points, [10, 67, 109, 338, 297, 151], face_w, face_h, 0.18, 0.08, image_width, image_height, y_shift=-0.01),
        "left_cheek": _landmark_center_box(points, [50, 101, 118, 123, 187, 205], face_w, face_h, 0.18, 0.12, image_width, image_height),
        "right_cheek": _landmark_center_box(points, [280, 330, 347, 352, 411, 425], face_w, face_h, 0.18, 0.12, image_width, image_height),
        "jaw": _landmark_center_box(points, [17, 18, 199, 200, 152], face_w, face_h, 0.16, 0.09, image_width, image_height, y_shift=-0.01),
    }
    feature_regions = {
        "hair": _clip_box(
            lx0 + int(face_w * 0.16),
            max(0, ly0 - int(face_h * 0.18)),
            lx1 - int(face_w * 0.16),
            ly0 + int(face_h * 0.10),
            image_width,
            image_height,
        ),
        "left_eye": _landmark_bounds_box(points, [33, 133, 159, 145, 160, 144, 158, 153], face_w, face_h, image_width, image_height, 0.06, 0.04),
        "right_eye": _landmark_bounds_box(points, [362, 263, 386, 374, 387, 373, 385, 380], face_w, face_h, image_width, image_height, 0.06, 0.04),
    }
    keypoint_indices = {
        "forehead": 10,
        "chin": 152,
        "nose": 1,
        "left_cheek": 205,
        "right_cheek": 425,
        "left_eye_outer": 33,
        "right_eye_outer": 263,
        "mouth_center": 13,
    }
    return {
        "source": "mediapipe_face_landmarker",
        "skin_regions": skin_regions,
        "feature_regions": feature_regions,
        "landmark_box": {"x": lx0, "y": ly0, "width": landmark_box[2], "height": landmark_box[3]},
        "keypoints": {
            name: {"x": points[index][0], "y": points[index][1]}
            for name, index in keypoint_indices.items()
            if index in points
        },
    }


def _detect_face_landmarks(rgb: np.ndarray) -> list[Any]:
    landmarker = _mediapipe_face_landmarker()
    if mp is None or landmarker is None:
        return []
    try:
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
        results = landmarker.detect(image)
    except Exception:
        return []
    if not results.face_landmarks:
        return []
    return list(results.face_landmarks[0])


def _landmark_pixel_points(landmarks: list[Any], image_width: int, image_height: int) -> dict[int, tuple[int, int]]:
    points: dict[int, tuple[int, int]] = {}
    for index, landmark in enumerate(landmarks):
        x = int(round(float(landmark.x) * image_width))
        y = int(round(float(landmark.y) * image_height))
        if -image_width * 0.05 <= x <= image_width * 1.05 and -image_height * 0.05 <= y <= image_height * 1.05:
            points[index] = (
                max(0, min(image_width - 1, x)),
                max(0, min(image_height - 1, y)),
            )
    return points


def _landmark_center_box(
    points: dict[int, tuple[int, int]],
    indices: list[int],
    face_width: int,
    face_height: int,
    width_ratio: float,
    height_ratio: float,
    image_width: int,
    image_height: int,
    y_shift: float = 0.0,
) -> tuple[int, int, int, int]:
    selected = [points[index] for index in indices if index in points]
    if not selected:
        return _clip_box(0, 0, 1, 1, image_width, image_height)
    cx = int(round(float(np.mean([point[0] for point in selected]))))
    cy = int(round(float(np.mean([point[1] for point in selected])) + face_height * y_shift))
    half_w = max(4, int(face_width * width_ratio / 2))
    half_h = max(4, int(face_height * height_ratio / 2))
    return _clip_box(cx - half_w, cy - half_h, cx + half_w, cy + half_h, image_width, image_height)


def _landmark_bounds_box(
    points: dict[int, tuple[int, int]],
    indices: list[int],
    face_width: int,
    face_height: int,
    image_width: int,
    image_height: int,
    pad_width_ratio: float,
    pad_height_ratio: float,
) -> tuple[int, int, int, int]:
    selected = [points[index] for index in indices if index in points]
    if not selected:
        return _clip_box(0, 0, 1, 1, image_width, image_height)
    xs = [point[0] for point in selected]
    ys = [point[1] for point in selected]
    pad_x = max(3, int(face_width * pad_width_ratio))
    pad_y = max(3, int(face_height * pad_height_ratio))
    return _clip_box(min(xs) - pad_x, min(ys) - pad_y, max(xs) + pad_x, max(ys) + pad_y, image_width, image_height)


def _clip_box(x0: int, y0: int, x1: int, y1: int, image_width: int, image_height: int) -> tuple[int, int, int, int]:
    x0 = max(0, min(int(x0), image_width - 1))
    x1 = max(x0 + 1, min(int(x1), image_width))
    y0 = max(0, min(int(y0), image_height - 1))
    y1 = max(y0 + 1, min(int(y1), image_height))
    return x0, y0, x1, y1


def _skin_mask_rgb(pixels: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(pixels.reshape(-1, 1, 3).astype(np.uint8), cv2.COLOR_RGB2HSV).reshape(-1, 3)
    ycrcb = cv2.cvtColor(pixels.reshape(-1, 1, 3).astype(np.uint8), cv2.COLOR_RGB2YCrCb).reshape(-1, 3)
    h = hsv[:, 0].astype(float) * 2
    s = hsv[:, 1].astype(float) * 100 / 255
    v = hsv[:, 2].astype(float) * 100 / 255
    cr = ycrcb[:, 1].astype(float)
    cb = ycrcb[:, 2].astype(float)
    r = pixels[:, 0].astype(float)
    g = pixels[:, 1].astype(float)
    b = pixels[:, 2].astype(float)
    hsv_skin = (
        ((h <= 58) | (h >= 330))
        & (s >= 8)
        & (s <= 64)
        & (v >= 25)
    )
    ycrcb_skin = (cr >= 132) & (cr <= 180) & (cb >= 82) & (cb <= 142)
    rgb_skin = (
        (r > 55)
        & (g > 40)
        & (b > 30)
        & (r >= g * 0.82)
        & (r >= b * 0.78)
        & ((np.maximum.reduce([r, g, b]) - np.minimum.reduce([r, g, b])) >= 8)
    )
    return (hsv_skin & rgb_skin) | (ycrcb_skin & rgb_skin)


def _adaptive_skin_region_sample(patch: np.ndarray) -> dict[str, Any]:
    pixels = patch.reshape(-1, 3)
    if pixels.size == 0:
        return {
            "pixels": np.zeros((1, 3), dtype=np.uint8),
            "skin_pixels": 0,
            "skin_ratio": 0.0,
            "method": "empty_region",
            "stable": False,
        }

    mask = _skin_mask_rgb(pixels)
    skin_pixels = int(np.sum(mask))
    skin_ratio = float(skin_pixels / max(1, pixels.shape[0]))
    if skin_pixels >= 24 and skin_ratio >= 0.12:
        return {
            "pixels": pixels[mask],
            "skin_pixels": skin_pixels,
            "skin_ratio": round(skin_ratio, 3),
            "method": "region_skin_mask",
            "stable": True,
        }

    window_sample = _best_skin_window_sample(patch)
    if window_sample is not None:
        return window_sample

    return {
        "pixels": pixels[mask] if skin_pixels >= 12 else pixels,
        "skin_pixels": skin_pixels,
        "skin_ratio": round(skin_ratio, 3),
        "method": "fallback_region_skin_mask" if skin_pixels >= 12 else "fallback_full_region",
        "stable": False,
    }


def _best_skin_window_sample(patch: np.ndarray) -> dict[str, Any] | None:
    height, width = patch.shape[:2]
    if height < 8 or width < 8:
        return None
    best: dict[str, Any] | None = None
    window_width = max(6, int(width * 0.5))
    window_height = max(6, int(height * 0.5))
    x_positions = sorted(set([0, max(0, (width - window_width) // 2), max(0, width - window_width)]))
    y_positions = sorted(set([0, max(0, (height - window_height) // 2), max(0, height - window_height)]))
    for y0 in y_positions:
        for x0 in x_positions:
            window = patch[y0 : y0 + window_height, x0 : x0 + window_width]
            pixels = window.reshape(-1, 3)
            if pixels.size == 0:
                continue
            mask = _skin_mask_rgb(pixels)
            skin_pixels = int(np.sum(mask))
            skin_ratio = float(skin_pixels / max(1, pixels.shape[0]))
            score = skin_pixels * skin_ratio
            if best is None or score > best["score"]:
                best = {
                    "pixels": pixels[mask] if skin_pixels else pixels,
                    "skin_pixels": skin_pixels,
                    "skin_ratio": round(skin_ratio, 3),
                    "score": score,
                    "selected_window": {"x": x0, "y": y0, "width": window_width, "height": window_height},
                }
    if best is None or best["skin_pixels"] < 16 or best["skin_ratio"] < 0.16:
        return None
    return {
        "pixels": best["pixels"],
        "skin_pixels": best["skin_pixels"],
        "skin_ratio": best["skin_ratio"],
        "method": "adaptive_window_skin_mask",
        "stable": True,
        "selected_window": best["selected_window"],
    }


def _feature_luminance_sample(patch: np.ndarray, kind: str) -> dict[str, Any]:
    pixels = patch.reshape(-1, 3)
    if pixels.size == 0:
        return {
            "luminance": 255.0,
            "method": "empty_region",
            "dark_pixel_ratio": 0.0,
            "skin_pixel_ratio": 0.0,
            "sample_pixels": 0,
            "stable": False,
        }

    gray = cv2.cvtColor(patch, cv2.COLOR_RGB2GRAY).reshape(-1).astype(float)
    skin_mask = _skin_mask_rgb(pixels)
    dark_threshold = 118 if kind == "hair" else 135
    dark_mask = gray <= dark_threshold
    feature_mask = dark_mask & ~skin_mask
    feature_count = int(np.sum(feature_mask))
    dark_ratio = float(np.mean(dark_mask))
    skin_ratio = float(np.mean(skin_mask))
    min_pixels = max(12, int(pixels.shape[0] * (0.025 if kind == "hair" else 0.035)))
    stable_ratio = dark_ratio >= 0.35 if kind == "hair" else dark_ratio >= 0.08
    if feature_count >= min_pixels and stable_ratio:
        percentile = 35 if kind == "hair" else 45
        return {
            "luminance": float(np.percentile(gray[feature_mask], percentile)),
            "method": "dark_non_skin_pixels",
            "dark_pixel_ratio": round(dark_ratio, 3),
            "skin_pixel_ratio": round(skin_ratio, 3),
            "sample_pixels": feature_count,
            "stable": True,
        }

    percentile = 25 if kind == "hair" else 35
    return {
        "luminance": float(np.percentile(gray, percentile)),
        "method": "fallback_region_percentile",
        "dark_pixel_ratio": round(dark_ratio, 3),
        "skin_pixel_ratio": round(skin_ratio, 3),
        "sample_pixels": int(pixels.shape[0]),
        "stable": False,
    }


def _apply_rgb_correction(rgb: np.ndarray, color_correction_stage: dict[str, Any]) -> np.ndarray:
    matrix = color_correction_stage.get("evidence", {}).get("matrix_rgb_3x4")
    if not matrix:
        return np.clip(rgb, 0, 255)
    transform = np.array(matrix, dtype=np.float32)
    if transform.shape != (3, 4):
        return np.clip(rgb, 0, 255)
    vector = np.array([float(rgb[0]), float(rgb[1]), float(rgb[2]), 1.0], dtype=np.float32)
    corrected = transform @ vector
    return np.clip(corrected, 0, 255)


def _skin_correction_strength(raw_rgb: np.ndarray, corrected_rgb: np.ndarray, color_correction_stage: dict[str, Any]) -> float:
    if color_correction_stage.get("status") != "pass":
        return 0.0
    if not color_correction_stage.get("evidence", {}).get("matrix_rgb_3x4"):
        return 0.0
    delta = float(np.linalg.norm(np.clip(corrected_rgb, 0, 255) - np.clip(raw_rgb, 0, 255)))
    if delta <= 18:
        return 0.45
    if delta <= 36:
        return 0.32
    return 0.22


def _region_color_stats(rgb: np.ndarray, region: tuple[int, int, int, int]) -> dict[str, float]:
    x0, y0, x1, y1 = region
    patch = rgb[y0:y1, x0:x1]
    if patch.size == 0:
        return {"redness": 0.0, "saturation": 0.0, "value": 0.0}
    pixels = patch.reshape(-1, 3)
    mask = _skin_mask_rgb(pixels)
    selected = pixels[mask] if int(np.sum(mask)) >= 20 else pixels
    red = selected[:, 0].astype(float)
    green = selected[:, 1].astype(float)
    blue = selected[:, 2].astype(float)
    hsv = cv2.cvtColor(selected.reshape(-1, 1, 3).astype(np.uint8), cv2.COLOR_RGB2HSV).reshape(-1, 3)
    return {
        "redness": float(np.median(red - (green + blue) / 2)),
        "saturation": float(np.median(hsv[:, 1]) * 100 / 255),
        "value": float(np.median(hsv[:, 2]) * 100 / 255),
    }


def _region_mask_stats(rgb: np.ndarray, region: tuple[int, int, int, int]) -> dict[str, float]:
    x0, y0, x1, y1 = region
    patch = rgb[y0:y1, x0:x1]
    if patch.size == 0:
        return {"skin_ratio": 0.0, "dark_ratio": 0.0, "bright_low_sat_ratio": 0.0}
    pixels = patch.reshape(-1, 3)
    hsv = cv2.cvtColor(pixels.reshape(-1, 1, 3).astype(np.uint8), cv2.COLOR_RGB2HSV).reshape(-1, 3)
    gray = cv2.cvtColor(patch, cv2.COLOR_RGB2GRAY).reshape(-1)
    skin = _skin_mask_rgb(pixels)
    bright_low_sat = (hsv[:, 2] > 205) & (hsv[:, 1] < 60)
    return {
        "skin_ratio": round(float(np.mean(skin)), 4),
        "dark_ratio": round(float(np.mean(gray < 70)), 4),
        "bright_low_sat_ratio": round(float(np.mean(bright_low_sat)), 4),
    }


def _skin_texture_score(region_rgb: np.ndarray) -> float:
    if region_rgb.size == 0:
        return 0.0
    pixels = region_rgb.reshape(-1, 3)
    mask = _skin_mask_rgb(pixels).reshape(region_rgb.shape[:2])
    gray = cv2.cvtColor(region_rgb, cv2.COLOR_RGB2GRAY)
    if int(np.sum(mask)) >= 80:
        gray = np.where(mask, gray, np.median(gray[mask])).astype(np.uint8)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _channel_cast_score(rgb: np.ndarray) -> dict[str, Any]:
    if rgb.size == 0:
        return {"cast_strength": 0.0, "dominant_channel": "none"}
    sample = rgb.reshape(-1, 3).astype(float)
    median = np.median(sample, axis=0)
    names = ["red", "green", "blue"]
    max_idx = int(np.argmax(median))
    min_idx = int(np.argmin(median))
    return {
        "cast_strength": round(float(median[max_idx] - median[min_idx]), 2),
        "dominant_channel": names[max_idx],
    }


def _tone_label(luma: float) -> str:
    if luma < 70:
        return "dark"
    if luma > 150:
        return "light"
    return "medium"


SEASON_DRAPE_PROFILES: list[dict[str, Any]] = [
    {"season_12": "light_spring", "season_4": "spring", "temperature": "warm", "depth": "light", "clarity": "balanced"},
    {"season_12": "warm_spring", "season_4": "spring", "temperature": "warm", "depth": "light", "clarity": "balanced"},
    {"season_12": "bright_spring", "season_4": "spring", "temperature": "warm", "depth": "light", "clarity": "clear"},
    {"season_12": "light_summer", "season_4": "summer", "temperature": "cool", "depth": "light", "clarity": "soft"},
    {"season_12": "soft_summer", "season_4": "summer", "temperature": "cool", "depth": "medium", "clarity": "soft"},
    {"season_12": "cool_summer", "season_4": "summer", "temperature": "cool", "depth": "medium", "clarity": "balanced"},
    {"season_12": "soft_autumn", "season_4": "autumn", "temperature": "warm", "depth": "medium", "clarity": "soft"},
    {"season_12": "warm_autumn", "season_4": "autumn", "temperature": "warm", "depth": "medium", "clarity": "balanced"},
    {"season_12": "deep_autumn", "season_4": "autumn", "temperature": "warm", "depth": "deep", "clarity": "balanced"},
    {"season_12": "clear_winter", "season_4": "winter", "temperature": "cool", "depth": "medium", "clarity": "clear"},
    {"season_12": "cool_winter", "season_4": "winter", "temperature": "cool", "depth": "medium", "clarity": "balanced"},
    {"season_12": "deep_winter", "season_4": "winter", "temperature": "cool", "depth": "deep", "clarity": "clear"},
]


def _bounded(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _score_from_label(label: str, scores: dict[str, float], neutral_key: str | None = None) -> float:
    if label == "neutral" and neutral_key:
        return scores.get(neutral_key, 0.0)
    return scores.get(label, 0.0)


def _layered_color_diagnosis(skin_stage: dict[str, Any], feature_stage: dict[str, Any]) -> dict[str, Any]:
    skin_evidence = skin_stage.get("evidence", {})
    scores = skin_evidence.get("scores", {})
    values = skin_evidence.get("color_values", {})
    dims = skin_evidence.get("dimensions", {})
    lab = values.get("lab") or [0.0, 0.0, 0.0]
    hsv = values.get("hsv") or [0.0, 0.0, 0.0]
    l_value = float(lab[0]) if lab else 0.0
    warmth = float(scores.get("warmth", 6.0))
    chroma_score = float(scores.get("chroma", 20.0))
    saturation = float(hsv[1]) if len(hsv) > 1 else 0.0
    feature_evidence = feature_stage.get("evidence", {})
    contrast_label = feature_evidence.get("overall_contrast", "medium")
    feature_luminance = feature_evidence.get("luminance", {})
    hair_luma = float(feature_luminance.get("hair", 128.0) or 128.0)
    eye_luma = float(feature_luminance.get("eyes", 128.0) or 128.0)
    feature_delta = float(feature_luminance.get("delta", 0.0) or 0.0)

    warm_score = _bounded((warmth - 3.0) / 8.0)
    cool_score = _bounded((8.5 - warmth) / 8.0)
    neutral_score = _bounded(1.0 - abs(warmth - 5.8) / 4.8)

    hair_dark_score = _bounded((115.0 - hair_luma) / 82.0)
    eye_dark_score = _bounded((118.0 - eye_luma) / 82.0)
    both_dark_score = min(hair_dark_score, eye_dark_score)
    feature_depth_score = _bounded(0.58 * both_dark_score + 0.28 * eye_dark_score + 0.14 * hair_dark_score)
    contrast_depth_bonus = {"high": 0.13, "medium": 0.04, "low": -0.06}.get(contrast_label, 0.0)

    light_score = _bounded((l_value - 52.0) / 24.0 - 0.24 * feature_depth_score - (0.08 if contrast_label == "high" else 0.0))
    deep_score = _bounded((68.0 - l_value) / 24.0 + 0.35 * feature_depth_score + contrast_depth_bonus)
    medium_score = _bounded(1.0 - abs(l_value - 61.0) / 18.0 + 0.20 * feature_depth_score)

    contrast_clear_bonus = {"high": 0.16, "medium": 0.06, "low": -0.06}.get(contrast_label, 0.0)
    clear_score = _bounded(((chroma_score - 16.0) / 18.0) + ((saturation - 24.0) / 60.0) + contrast_clear_bonus)
    soft_score = _bounded(((24.0 - chroma_score) / 18.0) + ((34.0 - saturation) / 70.0) - (0.08 if contrast_label == "high" else 0.0))
    balanced_score = _bounded(1.0 - abs(chroma_score - 22.0) / 18.0 + (0.04 if contrast_label == "medium" else 0.0))

    temperature_scores = {"warm": round(warm_score, 3), "cool": round(cool_score, 3), "neutral": round(neutral_score, 3)}
    depth_scores = {"light": round(light_score, 3), "medium": round(medium_score, 3), "deep": round(deep_score, 3)}
    clarity_scores = {"clear": round(clear_score, 3), "balanced": round(balanced_score, 3), "soft": round(soft_score, 3)}

    return {
        "temperature_test": {
            "winner": max(temperature_scores, key=temperature_scores.get),
            "scores": temperature_scores,
            "source_dimension": dims.get("temperature"),
            "evidence": {"warmth_score": round(warmth, 2)},
        },
        "depth_test": {
            "winner": max(depth_scores, key=depth_scores.get),
            "scores": depth_scores,
            "source_dimension": dims.get("brightness"),
            "evidence": {
                "lab_l": round(l_value, 2),
                "hair_luminance": round(hair_luma, 2),
                "eye_luminance": round(eye_luma, 2),
                "skin_feature_luminance_delta": round(feature_delta, 2),
                "hair_dark_score": round(hair_dark_score, 3),
                "eye_dark_score": round(eye_dark_score, 3),
                "both_dark_score": round(both_dark_score, 3),
                "feature_depth_score": round(feature_depth_score, 3),
            },
        },
        "clarity_test": {
            "winner": max(clarity_scores, key=clarity_scores.get),
            "scores": clarity_scores,
            "source_dimension": dims.get("chroma"),
            "evidence": {
                "chroma_score": round(chroma_score, 2),
                "hsv_saturation": round(saturation, 2),
                "feature_contrast": contrast_label,
            },
        },
    }


def _seasonal_drape_ranking(layered: dict[str, Any], brightness: str, chroma: str, contrast: str) -> list[dict[str, Any]]:
    temperature_scores = layered["temperature_test"]["scores"]
    depth_scores = layered["depth_test"]["scores"]
    clarity_scores = layered["clarity_test"]["scores"]
    temperature_evidence = layered["temperature_test"].get("evidence", {})
    depth_evidence = layered["depth_test"].get("evidence", {})
    clarity_evidence = layered["clarity_test"].get("evidence", {})
    l_value = float(depth_evidence.get("lab_l", 0.0) or 0.0)
    warmth = float(temperature_evidence.get("warmth_score", 6.0) or 6.0)
    chroma_score = float(clarity_evidence.get("chroma_score", 20.0) or 20.0)
    neutral_score = float(temperature_scores.get("neutral", 0.0) or 0.0)
    cool_score = float(temperature_scores.get("cool", 0.0) or 0.0)
    both_dark_score = float(depth_evidence.get("both_dark_score", 0.0) or 0.0)
    eye_dark_score = float(depth_evidence.get("eye_dark_score", 0.0) or 0.0)
    hair_dark_score = float(depth_evidence.get("hair_dark_score", 0.0) or 0.0)
    feature_delta = float(depth_evidence.get("skin_feature_luminance_delta", 0.0) or 0.0)

    ranking = []
    for profile in SEASON_DRAPE_PROFILES:
        temp_score = _score_from_label(profile["temperature"], temperature_scores, "neutral")
        if profile["temperature"] in {"warm", "cool"}:
            # Neutral-looking skin is common in corrected selfies. Keep both warm/cool families eligible,
            # then let depth, clarity, and feature contrast separate summer/winter/spring/autumn.
            temp_score = max(temp_score, float(temperature_scores.get("neutral", 0.0)) * 0.72)
        depth_score = depth_scores.get(profile["depth"], 0.0)
        clarity_score = clarity_scores.get(profile["clarity"], 0.0)
        score = temp_score * 0.42 + depth_score * 0.34 + clarity_score * 0.24

        if profile["season_12"] == "bright_spring":
            if brightness != "light":
                score -= 0.12
            if chroma != "bright":
                score -= 0.10
            if contrast != "high":
                score -= 0.04
            if chroma == "bright":
                score += 0.08
            if warmth >= 8.5 and both_dark_score >= 0.55 and l_value < 78:
                score -= 0.18
            if warmth >= 8.0 and both_dark_score >= 0.78 and contrast == "high":
                score -= 0.18
        elif profile["season_12"] == "clear_winter":
            if contrast == "high" or chroma == "bright":
                score += 0.04
            if contrast == "high" and eye_dark_score >= 0.55 and warmth <= 7.0:
                score += 0.16
            if l_value >= 78 and contrast == "high" and eye_dark_score >= 0.75:
                score += 0.24
            if l_value >= 78 and contrast == "high" and both_dark_score >= 0.82 and chroma != "bright":
                score += 0.08
            if neutral_score >= 0.35 and contrast == "high" and eye_dark_score >= 0.82 and 0.18 <= both_dark_score < 0.62 and feature_delta >= 145:
                score += 0.30
        elif profile["season_12"] == "deep_autumn":
            if brightness == "deep":
                score += 0.11
            elif brightness == "medium" and contrast == "high":
                score += 0.05
            if warmth >= 8.0 and both_dark_score >= 0.62 and l_value <= 70:
                score += 0.24
        elif profile["season_12"] == "warm_autumn":
            if brightness == "medium" and chroma in {"medium", "bright"}:
                score += 0.06
            if contrast == "low":
                score -= 0.08
            if warmth >= 8.5 and both_dark_score >= 0.55 and 69 < l_value <= 77:
                score += 0.22
        elif profile["season_12"] == "soft_autumn":
            if brightness == "medium" and chroma != "bright":
                score += 0.05
            if contrast == "low":
                score += 0.10
            if warmth >= 7.5 and both_dark_score >= 0.55 and l_value > 76 and chroma_score < 34:
                score += 0.36
            if both_dark_score >= 0.92 and feature_delta >= 175:
                score -= 0.18
        elif profile["season_12"] == "light_spring":
            if brightness == "light" and chroma != "bright":
                score += 0.06
            if warmth >= 8.0 and 0.18 <= both_dark_score <= 0.55 and chroma != "bright":
                score += 0.08
            if both_dark_score >= 0.55 and contrast == "high":
                score -= 0.14
            if both_dark_score >= 0.82 and feature_delta >= 160:
                score -= 0.24
            if chroma == "bright":
                score -= 0.05
        elif profile["season_12"] == "light_summer":
            if brightness == "light" and chroma == "muted":
                score += 0.07
            if contrast == "high" and eye_dark_score >= 0.55 and l_value < 79:
                score -= 0.14
            if contrast == "high" and both_dark_score >= 0.82:
                score -= 0.24
            if contrast == "high" and neutral_score >= 0.35 and eye_dark_score >= 0.82 and feature_delta >= 145:
                score -= 0.18
            if l_value >= 78 and eye_dark_score < 0.48:
                score += 0.06
        elif profile["season_12"] == "soft_summer":
            if chroma == "muted":
                score += 0.07
            if chroma == "muted" and 68 <= l_value < 75:
                score += 0.16
        elif profile["season_12"] == "deep_winter":
            if brightness == "deep":
                score += 0.10
            if contrast == "high" and both_dark_score >= 0.68 and warmth <= 7.5:
                score += 0.18
            if contrast == "high" and both_dark_score >= 0.82 and feature_delta >= 165:
                score += 0.24 if warmth <= 7.0 and l_value >= 78 else 0.48
            if warmth >= 7.0 and contrast == "high" and both_dark_score >= 0.92 and feature_delta >= 175:
                score += 0.30
        elif profile["season_12"] == "cool_winter":
            if contrast == "high" and eye_dark_score >= 0.60 and warmth <= 7.0:
                score += 0.14
            if l_value >= 76 and chroma != "bright" and hair_dark_score >= 0.65:
                score += 0.24
            if neutral_score >= 0.35 and l_value >= 78 and contrast == "high" and both_dark_score >= 0.82 and chroma != "bright":
                score += 0.26
            if chroma == "muted" and l_value < 79 and cool_score >= 0.7:
                score -= 0.08
        elif profile["season_12"] == "warm_spring":
            if warmth >= 8.0 and chroma != "bright" and both_dark_score < 0.58:
                score += 0.12
            if both_dark_score >= 0.62 and contrast == "high":
                score -= 0.18
            if both_dark_score >= 0.82 and feature_delta >= 160:
                score -= 0.18
        elif profile["season_12"] == "cool_summer":
            if chroma == "muted" and eye_dark_score >= 0.55 and l_value >= 74:
                score += 0.15
            if chroma == "muted" and l_value < 79 and cool_score >= 0.7:
                score += 0.16

        ranking.append(
            {
                "season_4": profile["season_4"],
                "season_12": profile["season_12"],
                "score": round(_bounded(score, 0.0, 1.0), 3),
                "components": {
                    "temperature": round(temp_score, 3),
                    "depth": round(depth_score, 3),
                    "clarity": round(clarity_score, 3),
                },
                "reason": _drape_reason(profile["season_12"], profile["temperature"], profile["depth"], profile["clarity"]),
            }
        )
    return sorted(ranking, key=lambda item: item["score"], reverse=True)


def _ranking_with_probabilities(ranking: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not ranking:
        return []
    scores = np.asarray([float(item.get("score", 0.0)) for item in ranking], dtype=np.float64)
    # A low temperature makes close candidates visible while keeping the Top-1 decisive enough for C-end copy.
    temperature = 0.16
    shifted = (scores - float(np.max(scores))) / temperature
    exp_scores = np.exp(shifted)
    probabilities = exp_scores / max(float(np.sum(exp_scores)), 1e-9)
    result = []
    for item, probability in zip(ranking, probabilities):
        next_item = dict(item)
        next_item["probability"] = round(float(probability), 4)
        next_item["probability_percent"] = int(round(float(probability) * 100))
        result.append(next_item)
    return result


def _seasonal_uncertainty_flags(
    layered: dict[str, Any],
    color_card_stage: dict[str, Any],
    color_correction_stage: dict[str, Any],
    primary: dict[str, Any],
    ranking: list[dict[str, Any]],
    brightness: str,
    chroma: str,
    contrast: str,
) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    no_card = color_card_stage.get("status") != "pass" or color_correction_stage.get("status") != "pass"
    depth_scores = layered.get("depth_test", {}).get("scores", {})
    sorted_depth = sorted((float(value), key) for key, value in depth_scores.items())
    depth_gap = sorted_depth[-1][0] - sorted_depth[-2][0] if len(sorted_depth) >= 2 else 1.0
    if no_card:
        flags.append(
            {
                "code": "no_card_reference",
                "label": "未使用色卡",
                "message": "本次基于原图推理，色彩深浅和冷暖会更受光线影响。",
            }
        )
    if no_card and brightness == "light":
        flags.append(
            {
                "code": "no_card_depth_risk",
                "label": "深浅可能偏浅",
                "message": "未使用色卡且照片读数偏亮，深浅判断可能被自然光、美颜或曝光推浅。",
            }
        )
    if depth_gap < 0.12:
        flags.append(
            {
                "code": "depth_uncertain",
                "label": "深浅接近",
                "message": "浅/中/深分数接近，建议用自然光或带色卡照片复核。",
            }
        )
    if len(ranking) > 1 and float(primary.get("probability", 0.0)) - float(ranking[1].get("probability", 0.0)) < 0.08:
        flags.append(
            {
                "code": "close_candidates",
                "label": "候选接近",
                "message": "主结果和备选结果分差较小，本次更适合看作倾向排序。",
            }
        )
    if chroma == "medium" and contrast == "high":
        flags.append(
            {
                "code": "asian_high_contrast_risk",
                "label": "高对比辅助判断",
                "message": "黑发带来的高对比只作为辅助，不应单独决定明亮型或冬季型。",
            }
        )
    return flags


def _drape_reason(season_12: str, temperature: str, depth: str, clarity: str) -> str:
    return f"该候选要求{temperature}调、{depth}明度、{clarity}净柔度，和当前照片的三段测试接近。"


def _top_season_candidates_from_ranking(
    ranking: list[dict[str, Any]],
    brightness: str,
    chroma: str,
    contrast: str,
    confidence: float,
) -> list[dict[str, Any]]:
    candidates = []
    for index, item in enumerate(ranking[:3], start=1):
        candidate_confidence = confidence if index == 1 else round(max(0.34, min(0.72, confidence - max(0.08, ranking[0]["score"] - item["score"]))), 2)
        candidates.append(
            {
                "rank": index,
                "season_4": item["season_4"],
                "season_12": item["season_12"],
                "season_24": f"{item['season_12']}_{brightness}_{chroma}_{contrast}",
                "confidence": candidate_confidence,
                "score": item.get("score"),
                "probability": item.get("probability"),
                "probability_percent": item.get("probability_percent"),
                "reason": item["reason"] if index == 1 else "这是相邻候选，适合用自然光或带色卡照片复核。",
            }
        )
    return candidates


def _season4(temperature: str, brightness: str, chroma: str, contrast: str) -> str:
    if temperature == "warm":
        if brightness == "deep":
            return "autumn"
        if brightness == "light" or chroma == "bright":
            return "spring"
        return "autumn"
    if chroma == "muted":
        return "summer"
    if brightness == "deep":
        return "winter"
    if contrast == "high" or chroma == "bright":
        return "winter"
    return "summer"


def _season12(season_4: str, brightness: str, chroma: str, contrast: str) -> str:
    if season_4 == "spring":
        if chroma == "bright" or contrast == "high":
            return "bright_spring"
        if brightness == "light":
            return "light_spring"
        return "warm_spring"
    if season_4 == "summer":
        if brightness == "light":
            return "light_summer"
        if chroma == "muted" or contrast == "low":
            return "soft_summer"
        return "cool_summer"
    if season_4 == "autumn":
        if brightness == "deep" or contrast == "high":
            return "deep_autumn"
        if chroma in {"muted", "medium"} or contrast in {"low", "medium"}:
            return "soft_autumn"
        return "warm_autumn"
    if contrast == "high" or chroma == "bright":
        return "clear_winter"
    if brightness == "deep":
        return "deep_winter"
    return "cool_winter"


def _adjacent_seasons(season_12: str, temperature: str, brightness: str, chroma: str, contrast: str) -> list[str]:
    adjacent = []
    if temperature == "neutral":
        adjacent.append("soft_summer" if "spring" in season_12 or "autumn" in season_12 else "soft_autumn")
    if chroma == "medium":
        adjacent.append("soft_summer" if season_12 == "soft_autumn" else season_12.replace("bright", "warm").replace("soft", "cool"))
        if season_12 == "warm_autumn":
            adjacent.append("soft_autumn")
    if contrast == "medium":
        adjacent.append(season_12.replace("clear", "cool").replace("deep", "cool"))
        if season_12 == "warm_autumn":
            adjacent.append("soft_autumn")
    return [item for item in dict.fromkeys(adjacent) if item and item != season_12]


def _top_season_candidates(
    season_4: str,
    season_12: str,
    brightness: str,
    chroma: str,
    contrast: str,
    confidence: float,
    ambiguous: list[str],
) -> list[dict[str, Any]]:
    alternatives = list(ambiguous)
    if not alternatives:
        alternatives.append(_fallback_adjacent_season(season_12, brightness, chroma, contrast))
    alternatives = [item for item in dict.fromkeys(alternatives) if item and item != season_12]

    secondary = alternatives[0] if alternatives else season_12
    secondary_confidence = round(max(0.34, min(0.72, confidence - (0.1 if ambiguous else 0.16))), 2)
    candidates = [
        {
            "rank": 1,
            "season_4": season_4,
            "season_12": season_12,
            "season_24": f"{season_12}_{brightness}_{chroma}_{contrast}",
            "confidence": confidence,
            "reason": "当前照片中肤色冷暖、明度、彩度和五官对比最接近这一类。",
        },
        {
            "rank": 2,
            "season_4": _season4_from12(secondary),
            "season_12": secondary,
            "season_24": f"{secondary}_{brightness}_{chroma}_{contrast}",
            "confidence": secondary_confidence,
            "reason": "这是相邻候选，适合用自然光或带色卡照片复核。",
        },
    ]
    return candidates


def _fallback_adjacent_season(season_12: str, brightness: str, chroma: str, contrast: str) -> str:
    if season_12 == "light_spring":
        return "light_summer"
    if season_12 == "bright_spring":
        return "clear_winter" if contrast == "high" or chroma == "bright" else "warm_spring"
    if season_12 == "warm_spring":
        return "warm_autumn"
    if season_12 == "light_summer":
        return "light_spring"
    if season_12 == "soft_summer":
        return "soft_autumn"
    if season_12 == "cool_summer":
        return "cool_winter"
    if season_12 == "soft_autumn":
        return "soft_summer"
    if season_12 == "warm_autumn":
        return "warm_spring"
    if season_12 == "deep_autumn":
        return "deep_winter"
    if season_12 == "clear_winter":
        return "bright_spring"
    if season_12 == "cool_winter":
        return "cool_summer"
    if season_12 == "deep_winter":
        return "deep_autumn"
    return "light_summer" if brightness == "light" else "soft_summer"


def _season4_from12(season_12: str) -> str:
    if "spring" in season_12:
        return "spring"
    if "summer" in season_12:
        return "summer"
    if "autumn" in season_12:
        return "autumn"
    return "winter"


def _suitable_colors(season_4: str, season_12: str) -> list[str]:
    if season_4 == "spring":
        return ["ivory", "coral", "teal"]
    if season_4 == "summer":
        return ["rose", "lavender", "soft_blue"]
    if season_4 == "autumn":
        return ["cream", "terracotta", "olive"]
    return ["white", "fuchsia", "cobalt"]


def _avoid_colors(season_4: str, season_12: str) -> list[str]:
    if season_4 == "spring":
        return ["muddy_gray", "black_brown", "icy_blue"]
    if season_4 == "summer":
        return ["orange", "neon_green", "black"]
    if season_4 == "autumn":
        return ["icy_pink", "pure_white", "neon_purple"]
    return ["mustard", "muddy_orange", "beige"]


def _colour_science_detection_to_candidate(detection: Any, image_shape: tuple[int, ...]) -> ColorCardCandidate | None:
    h, w = image_shape[:2]
    quadrilateral = np.asarray(getattr(detection, "quadrilateral", []), dtype=np.float32)
    swatches = np.asarray(getattr(detection, "swatch_colours", []), dtype=np.float32)
    if quadrilateral.shape != (4, 2) or swatches.shape[0] < 18:
        return None

    x0 = int(max(0, np.floor(np.min(quadrilateral[:, 0]))))
    y0 = int(max(0, np.floor(np.min(quadrilateral[:, 1]))))
    x1 = int(min(w, np.ceil(np.max(quadrilateral[:, 0]))))
    y1 = int(min(h, np.ceil(np.max(quadrilateral[:, 1]))))
    cw = x1 - x0
    ch = y1 - y0
    if cw <= 0 or ch <= 0:
        return None

    center_y_ratio = float((y0 + ch / 2) / h)
    aspect_ratio = cw / ch if ch else 0.0
    if center_y_ratio < 0.38 or not (0.95 <= aspect_ratio <= 2.35):
        return None

    swatches_255 = swatches * 255 if float(np.nanmax(swatches)) <= 1.5 else swatches
    swatches_255 = np.clip(swatches_255, 0, 255).astype(np.uint8)
    hsv = cv2.cvtColor(swatches_255.reshape(-1, 1, 3), cv2.COLOR_RGB2HSV).reshape(-1, 3).astype(float)
    saturation = hsv[:, 1]
    value = hsv[:, 2]
    top_sat = saturation[:18] if len(saturation) >= 18 else saturation
    bottom_sat = saturation[18:24] if len(saturation) >= 24 else saturation[-6:]
    bottom_value = value[18:24] if len(value) >= 24 else value[-6:]
    top_hues = hsv[:18, 0][top_sat > 45] if len(hsv) >= 18 else hsv[:, 0][saturation > 45]
    profile = {
        "patch_count": int(swatches.shape[0]),
        "colored_top_patches": int(np.sum(top_sat > 45)),
        "neutral_bottom_patches": int(np.sum(bottom_sat < 72)) if len(bottom_sat) else 0,
        "bottom_value_span": round(float(np.max(bottom_value) - np.min(bottom_value)), 2) if len(bottom_value) else 0.0,
        "top_hue_bins": len(set((top_hues // 15).astype(int).tolist())) if len(top_hues) else 0,
        "mean_saturation": round(float(np.mean(saturation)), 2) if len(saturation) else 0.0,
        "is_colorchecker_like": True,
        "is_fake_card_like": False,
    }
    rect = cv2.minAreaRect(quadrilateral.astype(np.float32))
    angle = rect[-1]
    if angle < -45:
        angle += 90
    grid_score = {
        "source": "colour_checker_detection",
        "swatch_count": int(swatches.shape[0]),
        "quadrilateral": [[round(float(point[0]), 2), round(float(point[1]), 2)] for point in quadrilateral],
        "center_y_ratio": round(center_y_ratio, 3),
        "colorchecker_profile": profile,
    }
    area_ratio = float((cw * ch) / max(1, w * h))
    return x0, y0, cw, ch, area_ratio, float(angle), "colour_science_segmentation", grid_score


def _find_card_candidate(bgr: np.ndarray) -> ColorCardCandidate | None:
    h, w = bgr.shape[:2]
    grid_candidate = _find_color_grid_candidate(bgr)
    if grid_candidate is not None:
        return grid_candidate

    masks = []
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    masks.append(cv2.inRange(hsv, np.array([0, 0, 0]), np.array([180, 100, 100])))
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    masks.append(cv2.inRange(gray, 0, 115))

    best = None
    for mask in masks:
        mask[: int(h * 0.5), :] = 0
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            area = cv2.contourArea(contour)
            x, y, cw, ch = cv2.boundingRect(contour)
            if ch == 0:
                continue
            aspect = cw / ch
            area_ratio = area / (w * h)
            if area_ratio < 0.012 or not (1.15 <= aspect <= 2.8):
                continue
            crop = bgr[y : y + ch, x : x + cw]
            grid_score = _score_card_grid(crop)
            patch_stats = _sample_card_patches(crop)
            colorfulness = float(np.mean([p["saturation"] for p in patch_stats])) if patch_stats else 0.0
            profile = _colorchecker_patch_profile(crop)
            if not (profile["is_colorchecker_like"] or profile["is_fake_card_like"]):
                continue
            grid_score = {**grid_score, "sampled_patch_colorfulness": round(colorfulness, 2), "colorchecker_profile": profile}
            rect = cv2.minAreaRect(contour)
            angle = rect[-1]
            if angle < -45:
                angle += 90
            candidate = (x, y, cw, ch, area_ratio, angle, "dark_frame_verified_grid", grid_score)
            if best is None or area_ratio > best[4]:
                best = candidate
    return best


def _find_color_grid_candidate(bgr: np.ndarray) -> tuple[int, int, int, int, float, float, str, dict[str, Any]] | None:
    h, w = bgr.shape[:2]
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    hue, sat, value = cv2.split(hsv)
    mask = ((sat > 58) & (value > 38) & (value < 252)).astype(np.uint8) * 255
    mask[: int(h * 0.48), :] = 0
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    patch_boxes = []
    image_area = w * h
    for contour in contours:
        area = cv2.contourArea(contour)
        x, y, cw, ch = cv2.boundingRect(contour)
        if cw < 8 or ch < 8:
            continue
        area_ratio = area / image_area
        aspect = cw / ch if ch else 0
        if not (0.35 <= aspect <= 2.25):
            continue
        if not (0.00005 <= area_ratio <= 0.04):
            continue
        patch_boxes.append((x, y, cw, ch, area))

    if len(patch_boxes) < 8:
        return None

    clusters = _cluster_patch_boxes(patch_boxes)
    best = None
    for cluster in clusters:
        if len(cluster) < 8:
            continue
        xs = [box[0] for box in cluster]
        ys = [box[1] for box in cluster]
        x2s = [box[0] + box[2] for box in cluster]
        y2s = [box[1] + box[3] for box in cluster]
        raw_x0, raw_y0, raw_x1, raw_y1 = min(xs), min(ys), max(x2s), max(y2s)
        raw_w = raw_x1 - raw_x0
        raw_h = raw_y1 - raw_y0
        if raw_w <= 0 or raw_h <= 0:
            continue
        raw_aspect = raw_w / raw_h
        if not (1.1 <= raw_aspect <= 2.8):
            continue

        avg_patch = float(np.median([(box[2] + box[3]) / 2 for box in cluster]))
        centers_x = [box[0] + box[2] / 2 for box in cluster]
        centers_y = [box[1] + box[3] / 2 for box in cluster]
        col_bins = _count_bins(centers_x, max(8.0, avg_patch * 0.72))
        row_bins = _count_bins(centers_y, max(8.0, avg_patch * 0.72))
        if not (3 <= row_bins <= 5 and 5 <= col_bins <= 8):
            continue

        left_pad = int(max(avg_patch * 0.55, raw_w * 0.08))
        right_pad = int(max(avg_patch * 0.55, raw_w * 0.08))
        top_pad = int(max(avg_patch * 0.55, raw_h * 0.08))
        bottom_pad = int(max(avg_patch * 0.65, raw_h * (0.12 if row_bins >= 4 else 0.46)))
        x0 = max(0, raw_x0 - left_pad)
        y0 = max(0, raw_y0 - top_pad)
        x1 = min(w, raw_x1 + right_pad)
        y1 = min(h, raw_y1 + bottom_pad)
        cw = x1 - x0
        ch = y1 - y0
        if cw <= 0 or ch <= 0:
            continue

        aspect = cw / ch
        area_ratio = (cw * ch) / image_area
        if not (0.95 <= aspect <= 2.35) or area_ratio < 0.012:
            continue

        points = np.array([[box[0] + box[2] / 2, box[1] + box[3] / 2] for box in cluster], dtype=np.float32)
        rect = cv2.minAreaRect(points)
        angle = rect[-1]
        if angle < -45:
            angle += 90
        crop = bgr[y0:y1, x0:x1]
        score = _score_card_grid(crop)
        profile = _colorchecker_patch_profile(crop)
        if not (profile["is_colorchecker_like"] or profile["is_fake_card_like"]):
            continue
        score.update(
            {
                "colored_patch_count": len(cluster),
                "colored_row_bins": row_bins,
                "colored_col_bins": col_bins,
                "raw_color_grid_box": {"x": raw_x0, "y": raw_y0, "width": raw_w, "height": raw_h},
                "colorchecker_profile": profile,
            }
        )
        candidate = (x0, y0, cw, ch, area_ratio, angle, "colored_patch_grid", score)
        if best is None or (row_bins, col_bins, len(cluster), area_ratio) > (
            best[7]["colored_row_bins"],
            best[7]["colored_col_bins"],
            best[7]["colored_patch_count"],
            best[4],
        ):
            best = candidate
    return best


def _cluster_patch_boxes(patch_boxes: list[tuple[int, int, int, int, float]]) -> list[list[tuple[int, int, int, int, float]]]:
    boxes = sorted(patch_boxes, key=lambda box: box[4], reverse=True)[:40]
    clusters: list[list[tuple[int, int, int, int, float]]] = []
    for seed in boxes:
        sx, sy, sw, sh, _ = seed
        scx = sx + sw / 2
        scy = sy + sh / 2
        cluster = []
        for box in boxes:
            x, y, bw, bh, _ = box
            cx = x + bw / 2
            cy = y + bh / 2
            if abs(cx - scx) <= max(sw, bw) * 8.5 and abs(cy - scy) <= max(sh, bh) * 6.5:
                cluster.append(box)
        clusters.append(cluster)
    return clusters


def _score_card_grid(crop: np.ndarray) -> dict[str, Any]:
    if crop.size == 0:
        return {"patch_like_count": 0, "row_bins": 0, "col_bins": 0}
    h, w = crop.shape[:2]
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1]
    value = hsv[:, :, 2]
    mask = (((sat > 45) & (value > 40) & (value < 250)) | (value < 70)).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    centers_x = []
    centers_y = []
    patch_sizes = []
    for contour in contours:
        area = cv2.contourArea(contour)
        x, y, cw, ch = cv2.boundingRect(contour)
        if cw < max(4, w * 0.035) or ch < max(4, h * 0.035):
            continue
        aspect = cw / ch if ch else 0
        area_ratio = area / max(1, w * h)
        if 0.42 <= aspect <= 2.1 and 0.0012 <= area_ratio <= 0.12:
            centers_x.append(x + cw / 2)
            centers_y.append(y + ch / 2)
            patch_sizes.append((cw + ch) / 2)
    threshold = max(5.0, float(np.median(patch_sizes)) * 0.72) if patch_sizes else 8.0
    return {
        "patch_like_count": len(patch_sizes),
        "row_bins": _count_bins(centers_y, threshold),
        "col_bins": _count_bins(centers_x, threshold),
    }


def _colorchecker_patch_profile(crop: np.ndarray) -> dict[str, Any]:
    patches = _sample_card_patches(crop)
    if len(patches) != 24:
        return {
            "patch_count": len(patches),
            "is_colorchecker_like": False,
            "is_fake_card_like": False,
        }

    rgb = np.array([patch["rgb"] for patch in patches], dtype=np.uint8).reshape(24, 1, 3)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV).reshape(24, 3).astype(float)
    hue = hsv[:, 0]
    sat = hsv[:, 1]
    value = hsv[:, 2]
    top_sat = sat[:18]
    top_value = value[:18]
    bottom_sat = sat[18:]
    bottom_value = value[18:]

    colored_top = int(np.sum((top_sat > 45) & (top_value > 45) & (top_value < 245)))
    neutral_bottom = int(np.sum(bottom_sat < 72))
    bottom_value_span = float(np.max(bottom_value) - np.min(bottom_value)) if len(bottom_value) else 0.0
    top_hues = hue[:18][top_sat > 45]
    hue_bins = len(set((top_hues // 15).astype(int).tolist())) if len(top_hues) else 0
    saturation_gap = float(np.median(top_sat) - np.median(bottom_sat)) if len(bottom_sat) else 0.0
    mean_saturation = float(np.mean(sat))

    stable_neutral_row = neutral_bottom >= 4 or (neutral_bottom >= 3 and bottom_value_span >= 120 and hue_bins >= 8)
    is_colorchecker_like = (
        colored_top >= 11
        and stable_neutral_row
        and bottom_value_span >= 60
        and hue_bins >= 6
        and 38 <= mean_saturation <= 138
    )
    is_fake_card_like = (
        colored_top >= 14
        and hue_bins >= 7
        and mean_saturation > 138
    )
    return {
        "patch_count": len(patches),
        "colored_top_patches": colored_top,
        "neutral_bottom_patches": neutral_bottom,
        "bottom_value_span": round(bottom_value_span, 2),
        "top_hue_bins": hue_bins,
        "saturation_gap": round(saturation_gap, 2),
        "mean_saturation": round(mean_saturation, 2),
        "stable_neutral_row": stable_neutral_row,
        "is_colorchecker_like": is_colorchecker_like,
        "is_fake_card_like": is_fake_card_like,
    }


def _count_bins(values: list[float], min_gap: float) -> int:
    if not values:
        return 0
    bins = [sorted(values)[0]]
    for value in sorted(values)[1:]:
        if value - bins[-1] >= min_gap:
            bins.append(value)
        else:
            bins[-1] = (bins[-1] + value) / 2
    return len(bins)


def _sample_card_patches(crop: np.ndarray) -> list[dict[str, Any]]:
    if crop.size == 0:
        return []
    h, w = crop.shape[:2]
    patches = []
    for row in range(4):
        for col in range(6):
            x0 = int((col + 0.18) * w / 6)
            x1 = int((col + 0.82) * w / 6)
            y0 = int((row + 0.18) * h / 4)
            y1 = int((row + 0.82) * h / 4)
            patch = crop[y0:y1, x0:x1]
            if patch.size == 0:
                continue
            rgb = cv2.cvtColor(patch, cv2.COLOR_BGR2RGB).reshape(-1, 3)
            hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV).reshape(-1, 3)
            patches.append(
                {
                    "rgb": [float(v) for v in np.median(rgb, axis=0)],
                    "saturation": float(np.median(hsv[:, 1])),
                }
            )
    return patches


def _reference_colorchecker_rgb() -> np.ndarray:
    # Approximate sRGB values for the classic 24-patch ColorChecker layout.
    return np.array(
        [
            [115, 82, 68], [194, 150, 130], [98, 122, 157], [87, 108, 67], [133, 128, 177], [103, 189, 170],
            [214, 126, 44], [80, 91, 166], [193, 90, 99], [94, 60, 108], [157, 188, 64], [224, 163, 46],
            [56, 61, 150], [70, 148, 73], [175, 54, 60], [231, 199, 31], [187, 86, 149], [8, 133, 161],
            [243, 243, 242], [200, 200, 200], [160, 160, 160], [122, 122, 121], [85, 85, 85], [52, 52, 52],
        ],
        dtype=np.float32,
    )


def _linear_color_correct(observed: np.ndarray, target: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    a = np.concatenate([observed, np.ones((observed.shape[0], 1), dtype=np.float32)], axis=1)
    matrix, *_ = np.linalg.lstsq(a, target, rcond=None)
    corrected = a @ matrix
    return np.clip(corrected, 0, 255), matrix


def _mean_rgb_distance(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.mean(np.linalg.norm(a - b, axis=1)))


def _mean_delta_e_2000(a: np.ndarray, b: np.ndarray) -> float:
    if colour_science is None:
        return float("nan")
    try:
        a_rgb = np.clip(a.astype(np.float64) / 255.0, 0.0, 1.0)
        b_rgb = np.clip(b.astype(np.float64) / 255.0, 0.0, 1.0)
        a_lab = colour_science.XYZ_to_Lab(colour_science.sRGB_to_XYZ(a_rgb))
        b_lab = colour_science.XYZ_to_Lab(colour_science.sRGB_to_XYZ(b_rgb))
        delta = colour_science.delta_E(a_lab, b_lab, method="CIE 2000")
        return float(np.mean(delta))
    except Exception:
        return float("nan")


def _correction_quality(metric_after: float, is_delta_e: bool) -> str:
    if not np.isfinite(metric_after):
        return "unknown"
    if is_delta_e:
        if metric_after <= 8:
            return "excellent"
        if metric_after <= 14:
            return "good"
        if metric_after <= 22:
            return "usable"
        return "weak"
    if metric_after <= 18:
        return "good"
    if metric_after <= 32:
        return "usable"
    return "weak"


def _white_ratio(bgr: np.ndarray) -> float:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    return float(np.mean(gray > 238))


def _skin_ratio(bgr: np.ndarray) -> float:
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)
    mask = (h < 25) & (s > 30) & (s < 140) & (v > 90) & (v < 245)
    return float(np.mean(mask))


def _sharpness(gray_crop: np.ndarray) -> float:
    return round(float(cv2.Laplacian(gray_crop, cv2.CV_64F).var()), 2)


def _pil_to_bgr(image: Image.Image) -> np.ndarray:
    rgb = np.array(image.convert("RGB"))
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def _stage(status: str, confidence: float, evidence: dict[str, Any], issues: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "status": status,
        "confidence": confidence,
        "evidence": evidence,
        "issues": issues,
        "suggestions": [issue["suggestion"] for issue in issues if issue.get("suggestion")],
    }


def _issue(code: str, message: str, suggestion: str) -> dict[str, str]:
    return {"code": code, "message": message, "suggestion": suggestion}
