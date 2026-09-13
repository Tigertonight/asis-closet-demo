from copy import deepcopy
import json

import pytest

from scripts import female_nano_user_acceptance as acceptance


def test_user_quality_decision_preserves_automatic_failure_and_rejects_other_failures():
    original = {"status": "fail", "issues": [{"code": "quality.face_changed", "message": "face differs"}],
                "suggestions": ["retry"], "evidence": {"face_diff": 49.26, "protected_region_diff": 2.45}}
    before = deepcopy(original)
    accepted = acceptance.accepted_quality(original, {"id": "confirmed"})
    assert accepted["status"] == "pass" and accepted["automatedStatus"] == "fail"
    assert accepted["evidence"]["face_diff"] == 49.26 and accepted["acceptedIssues"] == original["issues"]
    assert original == before
    for changed in [dict(original, issues=[{"code": "quality.background_changed"}]),
                    dict(original, evidence={"face_diff": 49.26, "protected_region_diff": 19})]:
        with pytest.raises(ValueError):
            acceptance.accepted_quality(changed, {"id": "confirmed"})


def test_confirmation_rejects_different_result_model_outfit_items_or_missing_report(tmp_path, monkeypatch):
    monkeypatch.setattr(acceptance, "ROOT", tmp_path)
    path = tmp_path / "acceptances.json"
    monkeypatch.setattr(acceptance, "APPROVALS", path)
    row = {"id": "job", "modelId": "model", "key": "key", "outfitId": "outfit", "sourceAssetId": "source",
           "itemIds": ["item"], "inputAssetIds": ["input"], "selectedAttempt": "attempts/01",
           "model": {"sha256": "original"}, "result": {"sha256": "shown-result"}}
    entry = {k: v for k, v in row.items() if k not in {"model", "result"}}
    entry.update(modelSha256="original", resultSha256="shown-result")
    path.write_text(json.dumps({"rule": acceptance.RULE, "reviewer": "user", "userMessage": "通过", "confirmedAt": "now", "entries": [entry]}))
    _, confirmation = acceptance.approval_for(row)
    assert confirmation["resultSha256"] == "shown-result"
    for field, value in [("id", "unconfirmed"), ("outfitId", "other"), ("sourceAssetId", "other"),
                         ("model", {"sha256": "other"}), ("result", {"sha256": "another-attempt"}),
                         ("itemIds", ["other"]), ("inputAssetIds", ["other"]), ("selectedAttempt", "attempts/02")]:
        changed = deepcopy(row); changed[field] = value
        with pytest.raises(ValueError):
            acceptance.approval_for(changed)
    with pytest.raises(ValueError):
        acceptance.validate_user_acceptance(dict(row, userAcceptance=confirmation), {}, {})
