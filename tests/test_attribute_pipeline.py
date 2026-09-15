"""app/attribute_pipeline.py 的单元测试与 fixture 冒烟测试。

- 分类纯函数（肤色 6 档 / 脸型 4 类 / 身型 5 类）用合成特征确定性验证；
- 门禁函数用伪造关键点验证；
- 真实 fixture 只做宽松断言（不崩溃、输出结构完整、已知场景触发对应 issue），
  具体标签的正确性留给内部标注集标定后回归。
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest
from PIL import Image

from app import attribute_pipeline as ap

FIXTURE_IMAGES = __import__("pathlib").Path(__file__).resolve().parent / "fixtures"


class _FakePoseLandmark:
    def __init__(self, x: float, y: float, visibility: float = 1.0) -> None:
        self.x = x
        self.y = y
        self.visibility = visibility


def _fake_frontal_pose(img_w: int = 1000, img_h: int = 2000) -> list[_FakePoseLandmark]:
    """构造一个正面站立、全身完整的 33 点姿态。"""
    pose = [_FakePoseLandmark(0.5, 0.5) for _ in range(33)]
    pose[0] = _FakePoseLandmark(0.5, 0.05)                      # 鼻
    pose[11] = _FakePoseLandmark(0.4, 0.22)                     # 左肩
    pose[12] = _FakePoseLandmark(0.6, 0.22)                     # 右肩
    pose[23] = _FakePoseLandmark(0.43, 0.5)                     # 左髋
    pose[24] = _FakePoseLandmark(0.57, 0.5)                     # 右髋
    pose[27] = _FakePoseLandmark(0.46, 0.92)                    # 左踝
    pose[28] = _FakePoseLandmark(0.54, 0.92)                    # 右踝
    return pose


# ---------------------------------------------------------------------------
# 肤色 6 类（明度 × 底调）
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "l_star,a_star,b_star,expected,exp_lightness,exp_undertone",
    [
        # 白皙档：底调分冷白 / 暖白
        (72.0, 5.0, 10.0, "冷白肤", "白皙", "冷调"),
        (70.0, 10.0, 25.0, "暖白肤", "白皙", "暖调"),
        (66.5, 8.0, 13.0, "冷白肤", "白皙", "冷调"),   # 白皙下限 + 冷/暖边界
        (66.5, 8.0, 14.0, "暖白肤", "白皙", "暖调"),
        # 自然中等档：底调分中性 / 暖黄 / 橄榄
        (64.0, 15.0, -1.0, "中性自然肤", "自然中等", "中性"),
        (63.0, 14.0, 13.0, "中性自然肤", "自然中等", "中性"),
        (58.0, 20.0, 23.0, "暖黄肤", "自然中等", "暖调"),
        (56.0, 16.0, 26.0, "暖黄肤", "自然中等", "暖调"),
        (60.0, 6.0, 10.0, "橄榄肤", "自然中等", "橄榄调"),  # a*低+b*低 → 偏青灰
        # 深肤档：不强判底调
        (50.0, 13.0, 12.0, "小麦色", "深肤", "未判断"),
        (32.0, 13.0, 12.0, "小麦色", "深肤", "未判断"),
    ],
)
def test_classify_skin_tone_labels(
    l_star: float, a_star: float, b_star: float, expected: str, exp_lightness: str, exp_undertone: str
) -> None:
    label, gap, lightness, undertone = ap._classify_skin_tone(l_star, a_star, b_star)
    assert label == expected
    assert lightness == exp_lightness
    assert undertone == exp_undertone
    assert gap >= 0


def test_classify_skin_tone_labels_cover_six() -> None:
    """6 类枚举都被分类函数覆盖到（无死枚举）。"""
    reachable = set()
    for l_star in (70.0, 60.0, 45.0):
        for a_star in (5.0, 15.0):
            for b_star in (-2.0, 11.0, 16.0, 25.0):
                reachable.add(ap._classify_skin_tone(l_star, a_star, b_star)[0])
    assert reachable == set(ap.SKIN_TONE_LABELS)


def test_classify_skin_tone_boundary_gap_nonnegative() -> None:
    """边界两侧 gap 均非负（gap 语义为到最近决策边界距离）。"""
    for l_star in (52.0 - 0.5, 52.0 + 0.5, 66.0 - 0.5, 66.0 + 0.5):
        _, gap, _, _ = ap._classify_skin_tone(l_star, 12.0, 15.0)
        assert gap >= 0


# ---------------------------------------------------------------------------
# 偏色告警分通道口径（2026-09 标定）
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "cast,expected",
    [
        # 红主导 = 暖肤天然底色（R−B 普遍 40~80），只拦极端暖光
        ({"cast_strength": 58.0, "dominant_channel": "red"}, False),   # 正常暖肤，不告警
        ({"cast_strength": 65.0, "dominant_channel": "red"}, False),   # 边界值不触发
        ({"cast_strength": 70.0, "dominant_channel": "red"}, True),    # 极端暖光
        # 蓝/绿主导 = 冷调滤镜/屏幕光特征，对齐 demo 链路从严
        ({"cast_strength": 12.0, "dominant_channel": "blue"}, False),
        ({"cast_strength": 25.0, "dominant_channel": "blue"}, True),
        ({"cast_strength": 25.0, "dominant_channel": "green"}, True),
        ({"cast_strength": 0.0, "dominant_channel": "none"}, False),   # 空 crop 兜底
    ],
)
def test_cast_suspect_channel_thresholds(cast: dict[str, object], expected: bool) -> None:
    assert ap._cast_suspect(cast) is expected


# ---------------------------------------------------------------------------
# 脸型 4 类
# ---------------------------------------------------------------------------

def _face_features(r: float, jr: float, fr: float, jaw_angle: float, chin_angle: float) -> dict[str, float]:
    return {
        "length_width_ratio": r,
        "jaw_cheek_ratio": jr,
        "forehead_cheek_ratio": fr,
        "jaw_angle_deg": jaw_angle,
        "chin_angle_deg": chin_angle,
    }


@pytest.mark.parametrize(
    "features,expected",
    [
        (_face_features(1.36, 0.79, 0.80, 150, 150), "椭圆脸"),
        (_face_features(1.08, 0.86, 0.90, 160, 165), "圆脸"),
        (_face_features(1.30, 0.95, 0.88, 115, 160), "方脸"),
        (_face_features(1.35, 0.62, 0.95, 150, 120), "心形脸"),
        (_face_features(1.42, 0.68, 0.72, 150, 126), "菱形脸"),
    ],
)
def test_face_shape_rules_pick_expected_label(features: dict[str, float], expected: str) -> None:
    scores = ap._face_shape_rules(features)
    assert max(scores, key=scores.get) == expected
    assert set(scores) == set(ap.FACE_SHAPE_LABELS)


def test_face_shape_rules_scores_bounded() -> None:
    scores = ap._face_shape_rules(_face_features(1.2, 0.8, 0.85, 140, 145))
    assert all(0.0 <= value <= 1.0 for value in scores.values())


# ---------------------------------------------------------------------------
# 身型 5 类
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "measurements,expected",
    [
        ({"shoulder_width": 200.0, "hip_width": 250.0, "waist_width": 180.0}, "梨型"),
        ({"shoulder_width": 260.0, "hip_width": 200.0, "waist_width": 170.0}, "倒三角型"),
        ({"shoulder_width": 220.0, "hip_width": 220.0, "waist_width": 160.0}, "沙漏型"),
        ({"shoulder_width": 220.0, "hip_width": 220.0, "waist_width": 192.0}, "矩型"),
        ({"shoulder_width": 210.0, "hip_width": 200.0, "waist_width": 196.0}, "苹果型"),
    ],
)
def test_classify_body_shape_labels(measurements: dict[str, float], expected: str) -> None:
    result = ap._classify_body_shape(measurements)
    assert result["label"] == expected
    assert result["waist_reliable"] is True


def test_classify_body_shape_without_waist_still_classifies_hip_shoulder() -> None:
    result = ap._classify_body_shape({"shoulder_width": 200.0, "hip_width": 260.0})
    assert result["label"] == "梨型"
    assert result["waist_reliable"] is False
    assert result["ratios"]["waist_over_hip"] is None


# ---------------------------------------------------------------------------
# 身型门禁（伪造关键点，不跑模型）
# ---------------------------------------------------------------------------

def test_body_gate_passes_frontal_full_body() -> None:
    assert ap._body_gate_issues(_fake_frontal_pose(), 1000, 2000) is None


def test_body_gate_passes_when_ankles_out_of_frame() -> None:
    # 产品口径（内测定版）：露到大腿即可，脚踝不在画面不再拦截。
    pose = _fake_frontal_pose()
    pose[27] = _FakePoseLandmark(0.46, 0.92, visibility=0.1)
    pose[28] = _FakePoseLandmark(0.54, 0.92, visibility=0.1)
    assert ap._body_gate_issues(pose, 1000, 2000) is None


def test_body_gate_passes_when_ankle_cropped_by_frame() -> None:
    pose = _fake_frontal_pose()
    pose[27] = _FakePoseLandmark(0.46, 0.999)
    assert ap._body_gate_issues(pose, 1000, 2000) is None


def test_body_gate_rejects_missing_hips() -> None:
    pose = _fake_frontal_pose()
    pose[23] = _FakePoseLandmark(0.43, 0.5, visibility=0.1)
    pose[24] = _FakePoseLandmark(0.57, 0.5, visibility=0.1)
    issue = ap._body_gate_issues(pose, 1000, 2000)
    assert issue is not None and issue["code"] == "body.upper_incomplete"


def test_body_gate_rejects_side_pose() -> None:
    pose = _fake_frontal_pose()
    pose[12] = _FakePoseLandmark(0.6, 0.28)  # 右肩明显低于左肩
    issue = ap._body_gate_issues(pose, 1000, 2000)
    assert issue is not None and issue["code"] == "body.side_pose"


def test_arm_zones_cover_hanging_arms() -> None:
    pose = _fake_frontal_pose()
    pose[13] = _FakePoseLandmark(0.36, 0.35)  # 左肘
    pose[15] = _FakePoseLandmark(0.34, 0.48)  # 左腕
    zones = ap._arm_zones_at_row(pose, 1000, 2000, 0.42 * 2000)
    assert zones, "垂臂在腰际行应该产生手臂区间"
    assert any(x0 < 350 < x1 for x0, x1 in zones)


# ---------------------------------------------------------------------------
# 真实 fixture 冒烟（宽松断言）
# ---------------------------------------------------------------------------

def _load_fixture(name: str) -> Image.Image:
    return Image.open(FIXTURE_IMAGES / "images" / name)


def test_face_photo_bangs_returns_label_with_warn() -> None:
    # 产品口径（2026-09 更新）：刘海照不拦截上传，仍照常给出脸型标签，
    # 降为 warn + 扣减置信度，并提示识别可能不准（用户可手动修改）。
    result = ap.analyze_face_photo(_load_fixture("real_bangs_forehead.jpg"))
    face_shape = result["attributes"]["face_shape"]
    assert face_shape["status"] == "warn"
    assert face_shape["label"] in ap.FACE_SHAPE_LABELS
    assert any(issue["code"] == "face.bangs_forehead" for issue in face_shape["issues"])
    assert result["attributes"]["skin_tone"]["status"] in {"pass", "warn"}
    assert result["status"] in {"pass", "warn"}


def test_face_photo_clear_frontal_returns_labels() -> None:
    result = ap.analyze_face_photo(_load_fixture("real_warm_indoor_light_no_card.jpg"))
    assert result["status"] in {"pass", "warn"}
    assert result["attributes"]["skin_tone"]["label"] in ap.SKIN_TONE_LABELS
    assert result["attributes"]["face_shape"]["label"] in ap.FACE_SHAPE_LABELS
    candidates = result["attributes"]["face_shape"]["candidates"]
    assert 1 <= len(candidates) <= 2


def test_face_photo_non_person_fails_with_issue() -> None:
    result = ap.analyze_face_photo(_load_fixture("portrait_non_person.png"))
    assert result["status"] == "fail"
    assert result["issues"], "失败必须带用户可见 issue"
    for attr in result["attributes"].values():
        assert attr["label"] is None


def test_face_photo_too_dark_fails() -> None:
    result = ap.analyze_face_photo(_load_fixture("input_too_dark.jpg"))
    assert result["status"] == "fail"


def test_face_photo_noise_does_not_crash() -> None:
    noise = Image.fromarray(np.random.default_rng(7).integers(0, 255, (480, 640, 3), dtype=np.uint8))
    result = ap.analyze_face_photo(noise)
    assert result["status"] == "fail"
    assert result["attributes"]["skin_tone"]["status"] == "unknown"


def _load_body_fixture(name: str) -> Image.Image:
    return Image.open(FIXTURE_IMAGES / "tryon_models" / name)


def test_body_photo_full_body_returns_label() -> None:
    result = ap.analyze_body_photo(_load_body_fixture("female_slim_1.png"))
    body = result["attributes"]["body_shape"]
    assert result["status"] in {"pass", "warn"}
    assert body["label"] in ap.BODY_SHAPE_LABELS
    measurements = body["evidence"]["measurements"]
    assert measurements["shoulder_width"] > 0
    assert measurements["hip_width"] > 0


def test_body_photo_hands_on_hip_falls_back_to_bone_hip() -> None:
    """叉腰全身照（内测实录，photo-v1 前被误拒为 body_unclear）。

    手腕贴髋使髋部量测行全部不可靠，髋宽退回骨骼估计
    （hip_source=bone_estimate），照片通过并给出分型，
    置信度因骨骼兜底小幅下调。
    """

    result = ap.analyze_body_photo(_load_body_fixture("female_hands_on_hip_1.png"))
    body = result["attributes"]["body_shape"]
    # 不再因轮廓「不稳定」拒绝
    assert result["status"] in {"pass", "warn"}
    assert not any(issue["code"] == "body.silhouette_unclear" for issue in result["issues"])
    assert body["label"] in ap.BODY_SHAPE_LABELS
    evidence = body["evidence"]
    assert evidence["hip_source"] == "bone_estimate"
    measurements = evidence["measurements"]
    assert measurements["hip_width"] > 0
    # 骨骼兜底的髋宽 = 骨骼髋距 × 1.15
    assert abs(measurements["hip_width"] - evidence["bone_hip_width"] * 1.15) < 0.5
    # 手臂贴身提示保留（warn 级，不拦截）
    assert any(issue["code"] == "body.arms_attached" for issue in result["issues"])


def test_body_photo_face_only_fails_with_no_person() -> None:
    result = ap.analyze_body_photo(_load_fixture("real_clear_glasses.jpg"))
    body = result["attributes"]["body_shape"]
    assert result["status"] == "fail"
    assert any(issue["code"] in {"body.no_person", "body.not_full_body", "body.upper_incomplete"} for issue in result["issues"])
    assert body["label"] is None


def test_body_photo_noise_does_not_crash() -> None:
    noise = Image.fromarray(np.random.default_rng(11).integers(0, 255, (800, 600, 3), dtype=np.uint8))
    result = ap.analyze_body_photo(noise)
    assert result["status"] == "fail"
    assert any(issue["code"] == "body.no_person" for issue in result["issues"])


# ---------------------------------------------------------------------------
# 输出结构契约（供后端包装成 photos/{kind} 响应）
# ---------------------------------------------------------------------------

def test_photo_result_contract_shape() -> None:
    result = ap.analyze_face_photo(_load_fixture("real_warm_indoor_light_no_card.jpg"))
    assert set(result) >= {"status", "confidence", "issues", "suggestions", "attributes", "evidence"}
    for issue in result["issues"]:
        assert {"code", "message", "suggestion"} <= set(issue)
    for attr in result["attributes"].values():
        assert {"status", "label", "confidence", "issues", "evidence"} <= set(attr)


# ---------------------------------------------------------------------------
# 光照鲁棒三防线（photo-v1.2，2026-09 内测事故复盘）
# 合成布局绕过 mediapipe，直接验证分区 L* / 矛盾区 / 眼白锚点 / 削顶逻辑。
# ---------------------------------------------------------------------------

_LIGHT_SKIN = (192, 150, 130)      # L*≈65.5 b*≈16.6 → 中性自然肤
_DARK_SKIN = (135, 95, 82)         # L*≈44.2 → 阴影里的暗肤读数
_DEEP_SUSPECT_SKIN = (150, 107, 92)  # L*≈49.2 b*≈15.2，事故照片实测色：L* 判深 + b* 健康
_BLOWN_SKIN = (252, 220, 205)      # L*≈90 高光削顶（R≥250）→ 严重过曝
_SCLERA_GRAY = (200, 198, 195)     # 中性眼白 R−B=5
_SCLERA_BLUE = (165, 163, 200)     # 冷窗光眼白 R−B=−35

_TEST_REGIONS = {
    "forehead": (80, 40, 160, 80),
    "left_cheek": (30, 110, 100, 160),
    "right_cheek": (140, 110, 210, 160),
    "jaw": (90, 180, 150, 220),
}


def _fake_face_rgb(
    region_fills: dict[str, tuple[int, int, int]],
    background: tuple[int, int, int] = _LIGHT_SKIN,
    size: int = 240,
) -> tuple[np.ndarray, dict[str, Any]]:
    rgb = np.zeros((size, size, 3), dtype=np.uint8)
    rgb[:, :] = background
    for name, fill in region_fills.items():
        x0, y0, x1, y1 = _TEST_REGIONS[name]
        rgb[y0:y1, x0:x1] = fill
    return rgb, {"box": {"x": 0, "y": 0, "width": size, "height": size}}


def _patch_layout(monkeypatch: pytest.MonkeyPatch, feature_regions: dict[str, Any] | None = None) -> None:
    def fake_layout(rgb: np.ndarray, face: dict[str, Any]) -> dict[str, Any]:
        return {
            "source": "test",
            "skin_regions": _TEST_REGIONS,
            "feature_regions": feature_regions or {},
        }

    monkeypatch.setattr(ap, "_face_landmark_region_layout", fake_layout)


def _eye_box(rgb: np.ndarray, box: tuple[int, int, int, int], sclera: tuple[int, int, int]) -> None:
    """眼眶框：四周眼睑皮肤 + 中心巩膜块（真实眼眶 80%+ 是皮肤）。"""
    x0, y0, x1, y1 = box
    rgb[y0:y1, x0:x1] = _LIGHT_SKIN
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    rgb[cy - 4 : cy + 4, cx - 10 : cx + 10] = sclera


def test_skin_shadow_regions_select_bright_side_and_warn(monkeypatch: pytest.MonkeyPatch) -> None:
    """半张脸埋阴影（两区亮两区暗）→ 只用亮区采样，label 恢复亮侧读数并告警。"""
    _patch_layout(monkeypatch)
    rgb, face = _fake_face_rgb(
        {"forehead": _LIGHT_SKIN, "right_cheek": _LIGHT_SKIN, "left_cheek": _DARK_SKIN, "jaw": _DARK_SKIN}
    )
    result = ap._skin_tone_attribute(rgb, face, {10: (120, 120)})
    assert result["label"] == "中性自然肤"
    assert result["status"] == "warn"
    assert any(issue["code"] == "skin.face_shadow" for issue in result["issues"])
    evidence = result["evidence"]
    assert evidence["shadow_suspect"] is True
    assert evidence["selected_regions"] == ["forehead", "right_cheek"]
    assert evidence["l_star"] > 60.0  # 亮区读数，而非被暗区拉到边界


def test_skin_uniform_regions_stay_clean(monkeypatch: pytest.MonkeyPatch) -> None:
    """光照均匀的好照片：三防线全部静默，不产生任何光照告警。"""
    _patch_layout(monkeypatch)
    rgb, face = _fake_face_rgb({name: _LIGHT_SKIN for name in _TEST_REGIONS})
    result = ap._skin_tone_attribute(rgb, face, {10: (120, 120)})
    assert result["label"] == "中性自然肤"
    assert result["status"] == "pass"
    assert result["issues"] == []
    assert result["evidence"]["shadow_suspect"] is False


def test_skin_deep_reading_with_healthy_b_compensates_and_warns(monkeypatch: pytest.MonkeyPatch) -> None:
    """L* 判深肤但 b* 健康（事故照片实测色）→ 补偿到自然中等并明确告知。

    真深肤黑色素会同步压低 b*（qa_photos 唯一真深肤样本 b*=7.6）；
    b* 仍 15 的"深肤"读数是暗光压暗 → 按更亮的读数给估算色号，
    低置信度 + 提示可重拍或手动修改。
    """
    _patch_layout(monkeypatch)
    rgb, face = _fake_face_rgb({name: _DEEP_SUSPECT_SKIN for name in _TEST_REGIONS})
    result = ap._skin_tone_attribute(rgb, face, {10: (120, 120)})
    assert result["label"] == "中性自然肤"  # 补偿后：小麦色 → 自然中等
    assert result["status"] == "warn"
    assert any(issue["code"] == "skin.dim_light_suspect" for issue in result["issues"])
    message = next(issue["message"] for issue in result["issues"] if issue["code"] == "skin.dim_light_suspect")
    assert "已按更亮的肤色估算" in message
    assert result["confidence"] <= 0.55  # 估算值低置信度
    evidence = result["evidence"]
    assert evidence["shadow_compensated"] is True
    assert evidence["raw_l_star"] < 52.0 <= evidence["l_star"]  # raw 保留供 QA 回看


def test_skin_true_deep_tone_stays_uncompensated(monkeypatch: pytest.MonkeyPatch) -> None:
    """真深肤（黑色素双压：L* 低且 b* 低）不做补偿——qa_photos face_01 实测特征。

    b*=7.6 低于 SKIN_DEEP_SUSPECT_B=14，矛盾区校验不触发，照常给小麦色。
    """
    _patch_layout(monkeypatch)
    true_deep = (112, 78, 66)  # L*≈35 b*≈8：黑色素双压的真深肤
    rgb, face = _fake_face_rgb({name: true_deep for name in _TEST_REGIONS})
    result = ap._skin_tone_attribute(rgb, face, {10: (120, 120)})
    assert result["label"] == "小麦色"
    evidence = result["evidence"]
    assert evidence["shadow_compensated"] is False
    assert evidence["raw_l_star"] == evidence["l_star"]
    assert not any(issue["code"] == "skin.dim_light_suspect" for issue in result["issues"])


def test_skin_severe_overexposure_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """高光大面积削顶（clip_ratio≥0.35）→ 肤色信息物理丢失，直接拒绝。"""
    _patch_layout(monkeypatch)
    rgb, face = _fake_face_rgb(
        {"forehead": _BLOWN_SKIN, "left_cheek": _BLOWN_SKIN, "right_cheek": _BLOWN_SKIN, "jaw": _DEEP_SUSPECT_SKIN},
        background=(230, 230, 230),  # 非皮肤背景拉低均值 V，躲开 96 的旧门禁，考验新削顶判定
    )
    result = ap._skin_tone_attribute(rgb, face, {10: (120, 120)})
    assert result["status"] == "fail"
    assert result["label"] is None
    assert any(issue["code"] == "photo.overexposed_severe" for issue in result["issues"])
    assert result["evidence"]["clip_ratio"] >= 0.35


def test_overexposed_clip_ratio_unit() -> None:
    """削顶占比只统计皮肤像素，白色背景不误判。"""
    crop = np.zeros((10, 10, 3), dtype=np.uint8)
    crop[:5] = _BLOWN_SKIN          # 皮肤 + 削顶
    crop[5:] = (200, 160, 140)      # 皮肤未削顶
    assert 0.4 < ap._overexposed_clip_ratio(crop) < 0.6
    white_bg = np.zeros((10, 10, 3), dtype=np.uint8)
    white_bg[:5] = _BLOWN_SKIN
    white_bg[5:] = (250, 250, 250)  # 白色非皮肤：不算过曝，也不稀释皮肤占比
    assert ap._overexposed_clip_ratio(white_bg) == 1.0
    dark = np.full((10, 10, 3), _DEEP_SUSPECT_SKIN, dtype=np.uint8)
    assert ap._overexposed_clip_ratio(dark) == 0.0


def test_sclera_tint_detects_mixed_light(monkeypatch: pytest.MonkeyPatch) -> None:
    """两眼眼白色相差大（暖灯+冷窗混光）→ 混光告警。"""
    feature_regions = {"left_eye": (20, 60, 60, 80), "right_eye": (180, 60, 220, 80)}
    _patch_layout(monkeypatch, feature_regions)
    rgb, face = _fake_face_rgb({name: _LIGHT_SKIN for name in _TEST_REGIONS})
    _eye_box(rgb, feature_regions["left_eye"], _SCLERA_GRAY)
    _eye_box(rgb, feature_regions["right_eye"], _SCLERA_BLUE)
    sclera = ap._sclera_tint(rgb, {"feature_regions": feature_regions})
    assert sclera is not None
    assert sclera["mixed_light"] is True
    assert abs(sclera["eye_warm_rb"][0] - sclera["eye_warm_rb"][1]) > 35
    result = ap._skin_tone_attribute(rgb, face, {10: (120, 120)})
    assert any(issue["code"] == "skin.mixed_light" for issue in result["issues"])


def test_sclera_tint_neutral_eyes_no_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    """中性眼白（好照片）→ 不触发暖光/混光告警。"""
    feature_regions = {"left_eye": (20, 60, 60, 80), "right_eye": (180, 60, 220, 80)}
    _patch_layout(monkeypatch, feature_regions)
    rgb, face = _fake_face_rgb({name: _LIGHT_SKIN for name in _TEST_REGIONS})
    for box in feature_regions.values():
        _eye_box(rgb, box, _SCLERA_GRAY)
    result = ap._skin_tone_attribute(rgb, face, {10: (120, 120)})
    assert result["status"] == "pass"
    codes = {issue["code"] for issue in result["issues"]}
    assert "skin.warm_illuminant" not in codes
    assert "skin.mixed_light" not in codes
    assert result["evidence"]["sclera_tint"]["warm_rb"] < 25


def test_sclera_tint_returns_none_without_eyes() -> None:
    """眼白像素不足（闭眼/墨镜/低分辨率）→ 不做判定，绝不误报。"""
    assert ap._sclera_tint(np.zeros((10, 10, 3), dtype=np.uint8), None) is None
    assert ap._sclera_tint(np.zeros((10, 10, 3), dtype=np.uint8), {"feature_regions": {}}) is None
