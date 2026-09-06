import json

from scripts import audit_selfit_p0_final_batch as audit


def test_batch19_completes_all_quantitative_and_repetition_constraints():
    root = audit.ROOT / "docs/audits/20260904-p0-acceptance"
    result = audit.build_audit(
        root / "anchor-candidates.v41.json",
        root / "p0-gap-staging.v30.json",
        root / "gap-recipes.visual-evidence.batch19.rendered.json",
        root / "gap-recipes.visual-evidence.batch19.visual-review.json",
        root / "generated-garments/batch11/manifest.json",
    )
    assert result["constraints_pass"] is True
    assert result["resulting_anchor_count"] == 160
    assert result["violations"] == []
    assert len(result["personas"]) == 16
    for row in result["personas"].values():
        assert row["count"] == 10
        assert row["expressions"] == {"easy": 4, "explore": 2, "typical": 4}
        assert set(row["structures"]) == {"dress", "pants", "skirt"}
        assert max(row["structures"].values()) <= 5
        assert row["selection_gap"] is None
        assert row["parent_over_cap"] == {}
        assert row["main_item_over_cap"] == {}
        assert row["family_over_cap"] == {}


def test_batch19_review_remains_explicitly_nonformal():
    path = audit.ROOT / "docs/audits/20260904-p0-acceptance/gap-recipes.visual-evidence.batch19.visual-review.json"
    review = json.loads(path.read_text())
    assert review["independent_blind_review"] is False
    assert review["four_gate_editorial_review"] is False
    assert review["formal_acceptance"] is False
