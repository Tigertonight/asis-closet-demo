import copy
import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from scripts.selfit_persona_review import PRODUCER, grade, select_anchors
from app.selfit_content_quality import record_fingerprint
from app.closet import selfit_content_pool


def fixture(tmp_path):
    image = tmp_path / "cover.jpg"
    image.write_bytes(b"fixture image")
    outfits = {oid: {"id": oid, "garment_ids": ["g"]} for oid in ("o1", "o2")}
    garments = {"g": {"id": "g"}}
    keys = {oid: {"outfit_id": oid, "primary_persona": code, "record_fingerprint": record_fingerprint(outfits[oid]),
                  "cover_path": "cover.jpg", "cover_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
                  "garment_fingerprints": {"g": record_fingerprint(garments["g"])}} for oid, code in (("o1", "loop"), ("o2", "mute"))}
    key = {"package_id": "test", "producer": PRODUCER, "keys": keys}
    answer = {"package_id": "test", "reviewer": "independent-fixture", "independent": True, "labels_hidden": True,
              "answers": [{"token": oid, "top1": code, "top2": alt, "reason": "fixture visual evidence", "verdict": "accept", "issues": []}
                          for oid, code, alt in (("o1", "loop", "mute"), ("o2", "mute", "loop"))]}
    return key, answer, outfits, garments


def test_grading_is_evidence_bound_and_does_not_publish(tmp_path):
    key, answer, outfits, garments = fixture(tmp_path)
    original = copy.deepcopy(outfits)
    result = grade(key, answer, outfits, garments, tmp_path)
    assert result["top1_accuracy"] == result["top2_accuracy"] == 1
    assert result["catalog_mutated"] is False and outfits == original
    assert result["identity_verification"] == "declaration_only"
    outfits["o1"]["changed"] = True
    with pytest.raises(ValueError, match="Stale outfit"):
        grade(key, answer, outfits, garments, tmp_path)


@pytest.mark.parametrize("field,value", [("independent", False), ("labels_hidden", False), ("reviewer", PRODUCER), ("reviewer", ""), ("package_id", "wrong")])
def test_self_review_or_missing_declaration_is_rejected(tmp_path, field, value):
    key, answer, outfits, garments = fixture(tmp_path)
    answer[field] = value
    with pytest.raises(ValueError):
        grade(key, answer, outfits, garments, tmp_path)


def test_missing_duplicate_answers_and_stale_image_are_rejected(tmp_path):
    key, answer, outfits, garments = fixture(tmp_path)
    answer["answers"][0]["verdict"] = "pending"
    with pytest.raises(ValueError, match="Incomplete"):
        grade(key, answer, outfits, garments, tmp_path)
    answer["answers"][0]["verdict"] = "accept"
    answer["answers"].append(answer["answers"][0])
    with pytest.raises(ValueError, match="exactly once"):
        grade(key, answer, outfits, garments, tmp_path)
    answer["answers"].pop()
    (tmp_path / "cover.jpg").write_bytes(b"changed")
    with pytest.raises(ValueError, match="Stale image"):
        grade(key, answer, outfits, garments, tmp_path)


def test_live_anchors_are_stratified_and_unique_recipes():
    from collections import Counter
    selected = select_anchors(selfit_content_pool().outfits)
    assert len(selected) == 160
    assert set(Counter(o["primary_persona"] for o in selected).values()) == {10}
    assert len({o.get("parent_outfit_id") or o["id"] for o in selected}) == 160
    for code in {o["primary_persona"] for o in selected}:
        assert Counter(o["intensity"] for o in selected if o["primary_persona"] == code) == {"entry": 4, "signature": 4, "experimental": 2}
