from PIL import Image

from scripts.female_nano_quality import HEADWEAR_RULE, review_worn_hat
from scripts.female_nano_quality import HEADWEAR_FEATURES_RULE, FIXED_FACE_BOX, FIXED_FEATURE_BOX

BOX = {"x": 40, "y": 40, "width": 80, "height": 80}
HAT = [{"name": "米色棒球帽", "wearing_method": "正向戴在头部"}]


def failure():
    return {"status": "fail", "confidence": .62,
            "evidence": {"face_diff": 40, "protected_region_diff": 5},
            "issues": [{"code": "quality.face_changed"}], "suggestions": ["retry"]}


def test_hat_outside_face_does_not_fail_identity_but_raw_evidence_is_kept():
    original = Image.new("RGB", (160, 160), "black")
    result = original.copy()
    result.paste("white", (20, 20, 140, 40))
    raw = failure()
    checked = review_worn_hat(original, result, raw, HAT, BOX)
    assert checked["status"] == "pass"
    assert checked["evidence"]["face_diff"] == 0
    assert checked["evidence"]["face_expanded_diff"] == 40
    assert checked["evidence"]["face_metric"] == HEADWEAR_RULE
    assert raw == failure()


def test_hat_does_not_exempt_changed_face_or_background():
    original = Image.new("RGB", (160, 160), "black")
    changed = original.copy()
    changed.paste((80, 80, 80), (40, 40, 120, 120))
    checked = review_worn_hat(original, changed, failure(), HAT, BOX)
    assert checked["status"] == "fail" and checked["evidence"]["face_diff"] == 80
    background = failure()
    background["issues"].append({"code": "quality.background_changed"})
    background["evidence"]["protected_region_diff"] = 19
    assert review_worn_hat(original, original, background, HAT, BOX) == background


def test_unworn_hat_and_other_accessories_keep_original_gate():
    original = Image.new("RGB", (160, 160), "black")
    for item in [
        {"name": "草帽", "wearing_method": "未戴在头上，放在身侧"},
        {"name": "草帽", "wearing_method": "未佩戴，放地面"},
        {"name": "太阳镜", "wearing_method": "佩戴于眼部"},
        {"name": "发圈", "wearing_method": "戴在后脑"},
    ]:
        assert review_worn_hat(original, original, failure(), [item], BOX) == failure()


def test_hood_explicitly_covering_head_uses_same_face_gate():
    original = Image.new("RGB", (160, 160), "black")
    hood = {"name": "黑色灰帽机能短外套", "wearing_method": "穿在黑色内搭外层，灰色连帽罩在头部"}
    checked = review_worn_hat(original, original, failure(), [hood], BOX)
    assert checked["status"] == "pass"
    assert checked["evidence"]["face_threshold"] == 28
    changed = original.copy()
    changed.paste((80, 80, 80), (40, 40, 120, 120))
    assert review_worn_hat(original, changed, failure(), [hood], BOX)["status"] == "fail"
    for method in ["连帽未罩在头部，垂在背后", "连帽不罩在头部", "连帽没有罩在头部", "连帽垂在背后"]:
        hood["wearing_method"] = method
        assert review_worn_hat(original, original, failure(), [hood], BOX) == failure()


def test_fixed_hat_forehead_occlusion_preserves_old_receipts_and_requires_opt_in():
    original = Image.new("RGB", (1792, 2400), "black")
    result = original.copy()
    result.paste("white", (834, 225, 1050, 270))
    raw = failure()
    assert review_worn_hat(original, result, raw, HAT, FIXED_FACE_BOX)["status"] == "fail"
    checked = review_worn_hat(original, result, raw, HAT, FIXED_FACE_BOX, allow_forehead_occlusion=True)
    assert checked["status"] == "pass"
    assert checked["evidence"]["face_metric"] == HEADWEAR_FEATURES_RULE
    assert checked["evidence"]["face_diff"] == 0
    assert checked["evidence"]["face_unexpanded_diff"] > 28
    assert checked["evidence"]["protected_feature_box"] == FIXED_FEATURE_BOX
    assert checked["evidence"]["face_threshold"] == 28
    assert raw == failure()


def test_fixed_hat_still_checks_brows_eyes_nose_mouth_chin_and_background():
    original = Image.new("RGB", (1792, 2400), "black")
    for y in (270, 295, 330, 370, 416):
        changed = original.copy()
        changed.paste("white", (834, 225, 1050, 270))
        changed.paste("white", (834, y, 1050, y + 25))
        checked = review_worn_hat(original, changed, failure(), HAT, FIXED_FACE_BOX, allow_forehead_occlusion=True)
        assert checked["status"] == "fail"
        assert checked["evidence"]["face_diff"] > 28
    background = failure()
    background["issues"].append({"code": "quality.background_changed"})
    background["evidence"]["protected_region_diff"] = 19
    assert review_worn_hat(original, original, background, HAT, FIXED_FACE_BOX, allow_forehead_occlusion=True) == background


def test_fixed_hat_opt_in_does_not_apply_to_other_models_or_accessories():
    original = Image.new("RGB", (1792, 2400), "black")
    result = original.copy()
    result.paste("white", (834, 225, 1050, 270))
    for item in [
        {"name": "草帽", "wearing_method": "未戴在头上，放在身侧"},
        {"name": "太阳镜", "wearing_method": "佩戴于眼部"},
        {"name": "头巾", "wearing_method": "包覆头顶"},
    ]:
        assert review_worn_hat(original, result, failure(), [item], FIXED_FACE_BOX, allow_forehead_occlusion=True) == failure()
    wrong_box = {**FIXED_FACE_BOX, "y": 226}
    checked = review_worn_hat(original, result, failure(), HAT, wrong_box, allow_forehead_occlusion=True)
    assert checked["status"] == "fail" and checked["evidence"]["face_metric"] == HEADWEAR_RULE
