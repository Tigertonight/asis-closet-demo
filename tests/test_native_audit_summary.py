"""An aggregate must preserve uncertainty and not activate family candidates."""
import json
from copy import deepcopy
from pathlib import Path

import pytest

from scripts.summarize_selfit_native_visual_audit import aggregate, markdown

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs/audits/20260903-personal-home-visual"


@pytest.fixture
def inputs():
    read = lambda p: json.loads(p.read_text())
    return [read(ROOT / "app/data/recommendation-visual.v1.json"),
            read(ROOT / "app/static/selfit/data/content-pool.v2.published.json"),
            read(AUDIT / "effective-coverage-autumn.json"),
            read(ROOT / "app/data/garment-style-families.v1.json"), [], []]


def test_summary_accounts_for_full_review_and_does_not_modify_registry(inputs):
    original_registry = deepcopy(inputs[3])
    report = aggregate(*inputs)
    assert sum(r["outfits"] for r in report["persona_supply"]) == 1169
    assert len(report["persona_evidence_ledger"]) == 1169
    assert len(report["problem_outfits"]) == report["effective_coverage"]["held_outfits"]
    assert report["independent_top1"] is report["independent_top2"] is None
    assert report["publish_approval"] is False
    assert report["family_governance"]["activated_by_this_report"] is False
    assert report["family_governance"]["machine_pairs_all_reviewed"] is False
    assert inputs[3] == original_registry
    assert "不是每套均做原尺寸检查" in markdown(report)


def test_summary_preserves_ties_and_unknown_persona_score(inputs):
    oid = next(iter(inputs[0]["outfits"]))
    inputs[0]["outfits"][oid]["observations"]["persona_scores"] = {"oops": .8, "neon": .8}
    report = aggregate(*inputs)
    item = next(r for r in report["persona_evidence_ledger"] if r["outfit_id"] == oid)
    assert item["strongest_observed_personas"] == ["neon", "oops"]
    assert item["catalog_persona_visual_score"] is None
    row = next(r for r in report["persona_supply"] if r["persona"] == item["catalog_persona"])
    assert row["declared_score_unknown"] >= 1
    assert row["observed_persona_confusion"]["neon / oops"] >= 1


def test_summary_rejects_stale_coverage_and_incomplete_native_review(inputs):
    inputs[2]["visual_version"] = "obsolete"
    with pytest.raises(AssertionError, match="Stale coverage"):
        aggregate(*inputs)
    inputs[2]["visual_version"] = inputs[0]["version"]
    next(iter(inputs[0]["garments"].values()))["review_complete"] = False
    with pytest.raises(AssertionError, match="Incomplete native audit"):
        aggregate(*inputs)


def test_summary_shared_descriptors_are_not_family_approval(inputs):
    report = aggregate(*inputs)
    groups = report["family_governance"]["strict_descriptor_candidates"]
    assert groups
    for group in groups:
        assert group["status"] == "candidate_only_requires_pairwise_visual_review"
        assert "main_colors" not in group["dimensions"]
        assert len(group["members"]) >= 2
        assert all(r["asset_sha256"] and r["source_file"] for r in group["members"])


def test_summary_requires_exact_queue_and_revision_for_completed_families(inputs):
    read = lambda name: json.loads((AUDIT / "family-review" / name).read_text())
    review = read("native-family-review.json")
    draft = read("effective-coverage-autumn.json")
    inputs[5] = [p["machine_candidate"] for p in review["machine_pair_decisions"]]
    report = aggregate(*inputs, review, draft)
    assert report["family_governance"]["machine_pairs_all_reviewed"] is True
    assert report["family_governance"]["activated_by_this_report"] is False
    assert "68个多成员家族" in markdown(report)
    review["machine_pair_decisions"].pop()
    with pytest.raises(AssertionError, match="Incomplete family queue"):
        aggregate(*inputs, review, draft)


def test_summary_rejects_wrong_draft_family_version(inputs):
    read = lambda name: json.loads((AUDIT / "family-review" / name).read_text())
    review = read("native-family-review.json")
    inputs[5] = [p["machine_candidate"] for p in review["machine_pair_decisions"]]
    draft = read("effective-coverage-autumn.json")
    draft["family_registry"] = "obsolete"
    with pytest.raises(AssertionError, match="Stale draft coverage"):
        aggregate(*inputs, review, draft)
