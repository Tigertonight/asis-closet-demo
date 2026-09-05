from copy import deepcopy

import pytest

from app.selfit_content_quality import record_fingerprint, review_is_current
from scripts.stage_selfit_p0_persona_revisions import revise


def test_persona_correction_preserves_source_and_invalidates_approval():
    raw = {"id": "source", "primary_persona": "MUTE", "garment_ids": ["top"],
           "quality_review": {"status": "old"}, "curation": {"status": "approved"}}
    before = deepcopy(raw)
    catalog = {"outfit_id": "source", "parent_outfit_id": "original-parent",
               "primary_persona": "MUTE", "visual": {"persona_scores": {"iced": .8}},
               "items": [{"item_id": "top", "category": "top"}]}
    anchor = {"outfit_id": "source", "persona": "iced", "record_fingerprint": record_fingerprint(raw)}
    replacement, entry = revise(anchor, raw, catalog)
    assert raw == before
    assert replacement["outfit_id"] != raw["id"]
    assert entry["raw_record"]["primary_persona"] == "ICED"
    assert entry["raw_record"]["parent_outfit_id"] == "original-parent"
    assert not review_is_current(entry["raw_record"])
    assert entry["catalog_record"]["visual"] == catalog["visual"]
    assert replacement["record_fingerprint"] != anchor["record_fingerprint"]


def test_persona_correction_rejects_stale_source_or_missing_signal():
    raw = {"id": "source", "primary_persona": "MUTE"}
    anchor = {"persona": "iced", "record_fingerprint": "stale"}
    with pytest.raises(ValueError, match="stale"):
        revise(anchor, raw, {})
    anchor["record_fingerprint"] = record_fingerprint(raw)
    with pytest.raises(ValueError, match="evidence"):
        revise(anchor, raw, {})
