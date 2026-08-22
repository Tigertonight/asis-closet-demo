"""app/attribute_pipeline.py 的单元测试与 fixture 冒烟测试。

- 分类纯函数（肤色 6 档 / 脸型 4 类 / 身型 5 类）用合成特征确定性验证；
- 门禁函数用伪造关键点验证；
- 真实 fixture 只做宽松断言（不崩溃、输出结构完整、已知场景触发对应 issue），
  具体标签的正确性留给内部标注集标定后回归。
"""

from __future__ import annotations

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
# 肤色 6 档
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "l_star,expected",
    [
        (72.0, "白皙色"),
        (68.0, "白皙色"),
        (66.5, "自然白"),
        (63.0, "自然色"),
        (59.0, "健康色"),
        (55.0, "小麦色"),
        (50.0, "蜜糖色"),
    ],
)
def test_classify_skin_tone_labels(l_star: float, expected: str) -> None:
    label, gap = ap._classify_skin_tone(l_star)
    assert label == expected
    assert gap >= 0


def test_classify_skin_tone_boundary_gap_is_symmetric() -> None:
    _, below_gap = ap._classify_skin_tone(65.0 - 0.5)
    _, above_gap = ap._classify_skin_tone(65.0 + 0.5)
    assert below_gap == pytest.approx(above_gap, abs=1e-6)


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


def test_body_gate_rejects_missing_ankles() -> None:
    pose = _fake_frontal_pose()
    pose[27] = _FakePoseLandmark(0.46, 0.92, visibility=0.1)
    pose[28] = _FakePoseLandmark(0.54, 0.92, visibility=0.1)
    issue = ap._body_gate_issues(pose, 1000, 2000)
    assert issue is not None and issue["code"] == "body.not_full_body"


def test_body_gate_rejects_ankle_cropped() -> None:
    pose = _fake_frontal_pose()
    pose[27] = _FakePoseLandmark(0.46, 0.999)
    issue = ap._body_gate_issues(pose, 1000, 2000)
    assert issue is not None and issue["code"] == "body.not_full_body"


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


def test_face_photo_bangs_blocks_face_shape_but_not_skin() -> None:
    result = ap.analyze_face_photo(_load_fixture("real_bangs_forehead.jpg"))
    face_shape = result["attributes"]["face_shape"]
    assert face_shape["status"] == "fail"
    assert any(issue["code"] == "face.bangs_forehead" for issue in face_shape["issues"])
    assert result["attributes"]["skin_tone"]["status"] in {"pass", "warn"}


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
