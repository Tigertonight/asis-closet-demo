"""Account for an explicitly worn hat without treating it as a face change."""
from copy import deepcopy
import re

import numpy as np

HEADWEAR_RULE = "worn_hat_unexpanded_face_box_v1"
HEADWEAR_FEATURES_RULE = "worn_hat_fixed_visible_features_v2"
HEADWEAR_RULES = {HEADWEAR_RULE, HEADWEAR_FEATURES_RULE}
FIXED_FACE_BOX = {"x": 834, "y": 225, "width": 216, "height": 216}
# Visually checked on all three hash-bound 1792x2400 batch model originals:
# y=270 is above BOTH eyebrows; the bottom still includes the full chin.
# Only the upper forehead where the intended cap brim can sit is excluded.
FIXED_FEATURE_BOX = {"x": 834, "y": 270, "width": 216, "height": 171}


def worn_hat_ids(items):
    return [item["name"] for item in items
            if "帽" in item.get("name", "")
            and re.search(r"戴|罩在头部", item.get("wearing_method", ""))
            and not re.search(r"未戴|不戴|未佩戴|没有戴|未穿戴|未罩|不罩|没有罩", item["wearing_method"])]


def review_worn_hat(original, result, quality, items, box, *, allow_forehead_occlusion=False):
    """Keep the 28/18 limits; exclude the old 18% margin containing hat/hair/collar.

    This only rechecks a face-only failure for an explicitly worn hat. The entire
    original face box, including eyes/nose/mouth/chin, remains in the v1 metric.
    The explicit fixed-model opt-in also accounts for upper-forehead occlusion,
    using a prevalidated region that still includes both eyebrows and all features.
    Unworn hats, sunglasses, hair ties and unrelated failures never get this rule.
    """
    hats = worn_hat_ids(items)
    codes = {issue["code"] for issue in quality.get("issues", [])}
    if not hats or codes != {"quality.face_changed"}:
        return deepcopy(quality)
    if original.size != result.size or quality["evidence"].get("protected_region_diff", 255) > 18:
        return deepcopy(quality)
    x, y, w, h = (box[k] for k in ("x", "y", "width", "height"))
    crop = (x, y, x + w, y + h)
    assert 0 <= x < x + w <= original.width and 0 <= y < y + h <= original.height
    a = np.asarray(original.crop(crop).convert("RGB"), dtype=np.float32)
    b = np.asarray(result.crop(crop).convert("RGB"), dtype=np.float32)
    core_diff = round(float(np.abs(a - b).mean()), 2)
    checked = deepcopy(quality)
    checked["evidence"].update(
        face_diff=core_diff, face_metric=HEADWEAR_RULE,
        face_expanded_diff=quality["evidence"]["face_diff"], face_box=deepcopy(box),
        worn_headwear=hats, face_threshold=28, protected_region_threshold=18,
        face_margin_exclusion_reason="The 18% outer margin includes intentionally replaced hat/hair and shirt collar.")
    if core_diff <= 28:
        checked.update(status="pass", confidence=.82, issues=[], suggestions=[])
    elif allow_forehead_occlusion and original.size == (1792, 2400) and box == FIXED_FACE_BOX:
        # Opt-in for these fixed model originals only. Never locate a convenient
        # region from the result or exclude eyes, nose, mouth, or chin. Old v1
        # receipts continue to recompute with the default opt-out behavior.
        fx, fy, fw, fh = (FIXED_FEATURE_BOX[k] for k in ("x", "y", "width", "height"))
        feature_crop = (fx, fy, fx + fw, fy + fh)
        a = np.asarray(original.crop(feature_crop).convert("RGB"), dtype=np.float32)
        b = np.asarray(result.crop(feature_crop).convert("RGB"), dtype=np.float32)
        features_diff = round(float(np.abs(a - b).mean()), 2)
        checked["evidence"].update(
            face_diff=features_diff, face_metric=HEADWEAR_FEATURES_RULE,
            face_unexpanded_diff=core_diff, protected_feature_box=deepcopy(FIXED_FEATURE_BOX),
            excluded_forehead_box={"x": x, "y": y, "width": w, "height": fy - y},
            face_forehead_exclusion_reason="Explicitly worn hat may cover upper forehead; fixed region retains both eyebrows, eyes, nose, mouth and full chin. Visual inspection remains required.")
        if features_diff <= 28:
            checked.update(status="pass", confidence=.82, issues=[], suggestions=[])
    return checked
