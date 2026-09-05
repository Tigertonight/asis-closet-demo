"""Native grouping is explicit, complete for the queue, and never activates QA."""
import csv
import json
from copy import deepcopy
from pathlib import Path

import pytest

from app.closet import selfit_content_pool
from app.recommendation_diversity import style_family_map
from scripts.compile_selfit_family_review import compile_review, read_rows
from scripts.audit_selfit_personal_home_supply import sequence_diagnostics
from scripts.summarize_selfit_family_supply import summarize

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "docs/audits/20260903-personal-home-visual/family-review"


@pytest.fixture
def inputs():
    read = lambda p: json.loads(p.read_text())
    notes = []
    for path in sorted(DIRECTORY.parent.glob("codex-family-observations-*.tsv")):
        with path.open() as handle:
            notes.extend({**r, "source_file": path.name} for r in csv.DictReader(handle, delimiter="\t"))
    return [read(ROOT / "app/data/recommendation-visual.v1.json"),
            {"garments": deepcopy(selfit_content_pool().garments)}, read(DIRECTORY / "manifest.json"),
            read_rows(DIRECTORY), read(DIRECTORY / "methods.json"), notes,
            read(DIRECTORY.parent / "full-native-audit-summary.json")["family_governance"]["strict_descriptor_candidates"]]


def test_native_queue_complete_draft_only_and_qa_unchanged(inputs):
    original = deepcopy(inputs[0])
    registry_path = ROOT / "app/data/garment-style-families.v1.json"
    production_bytes = registry_path.read_bytes()
    registry, report = compile_review(*inputs)
    assert report["counts"]["machine_pairs"] == 443
    assert report["counts"]["reviewed_members"] == 299
    assert report["counts"]["draft_families"] == 68
    assert len(report["member_ledger"]) + len(report["not_in_comparison_set"]) == 600
    assert report["machine_pairs_all_adjudicated"] is True
    assert report["registry_activated"] is False and registry["production_approved"] is False
    assert report["exhaustive_all_pairs_recall"] is None
    assert inputs[0] == original and registry_path.read_bytes() == production_bytes
    row = next(r for r in report["member_ledger"] if r["token"] == "g0354")
    assert row["qa_status_unchanged"] == "needs_review" and row["family_id"]
    assert len(style_family_map(inputs[1]["garments"], registry)) == 204


def test_connected_machine_candidates_do_not_automatically_merge(inputs):
    _, report = compile_review(*inputs)
    counts = report["counts"]["pair_decisions"]
    assert counts == {"same_visual_family": 78, "distinct_visual_family": 365}
    members = {r["token"]: r for r in report["member_ledger"]}
    assert members["g0248"]["group_id"] != members["g0250"]["group_id"]  # Mary Jane / penny loafer
    assert members["g0085"]["group_id"] != members["g0109"]["group_id"]  # pullover / cardigan
    assert members["g0512"]["group_id"] == members["g0528"]["group_id"] != members["g0592"]["group_id"]
    assert members["g0402"]["group_id"] == members["g0418"]["group_id"]


@pytest.mark.parametrize("kind", ["duplicate", "missing", "unknown", "unviewed"])
def test_invalid_or_unseen_assignments_rejected(inputs, kind):
    if kind == "duplicate":
        inputs[3].append(deepcopy(inputs[3][0]))
    elif kind == "missing":
        inputs[3].pop(0)
    elif kind == "unknown":
        inputs[3][0]["member_tokens"] += ",g9999"
    else:
        inputs[3][0]["source_sheets"] = "unviewed.jpg"
    with pytest.raises(AssertionError):
        compile_review(*inputs)


@pytest.mark.parametrize("kind", ["version", "fingerprint", "asset", "duplicate_pair"])
def test_stale_or_duplicated_evidence_rejected(inputs, kind):
    if kind == "version":
        inputs[2]["visual_version"] = "stale"
    elif kind in {"fingerprint", "asset"}:
        inputs[2]["members"][0]["record_fingerprint" if kind == "fingerprint" else "asset_sha256"] = "stale"
    else:
        inputs[2]["pairs"].append(inputs[2]["pairs"][0])
    with pytest.raises(AssertionError):
        compile_review(*inputs)


def test_historical_and_descriptor_candidates_have_explicit_reconciliation(inputs):
    _, report = compile_review(*inputs)
    assert len(report["historical_reconciliation"]) == 10
    assert len(report["descriptor_reconciliation"]) == 6
    assert sum(r["outcome"].startswith("split") for r in report["historical_reconciliation"]) == 2
    assert all(r["decisions"] for r in report["descriptor_reconciliation"])


def test_sequence_diagnostics_do_not_hide_small_samples_or_violations():
    assert sequence_diagnostics([])["mean_pairwise_main_family_jaccard"] is None
    rows = [{"outfit_id": str(i), "parent_outfit_id": "same_parent", "visual": {"structure": "pants"},
             "items": [{"item_id": "top", "category": "top", "style_family_id": "same_family"}]} for i in range(3)]
    result = sequence_diagnostics(rows)
    assert result["mean_pairwise_main_family_jaccard"] == 1
    assert {v["type"] for v in result["constraint_violations"]} == {"main", "family", "parent"}
    assert result["highest_color_appearance_share"] is None


def test_supply_artifacts_cover_seasons_and_do_not_equate_zero_violations_with_success():
    read = lambda path: json.loads(path.read_text())
    family = read(DIRECTORY / "native-family-review.json")
    baseline = read(DIRECTORY.parent / "effective-coverage-autumn.json")
    seasons = {s: read(DIRECTORY / f"effective-coverage-{s}.json") for s in ("spring", "summer", "autumn", "winter")}
    global_review = read(DIRECTORY.parent / "full-native-audit-summary.json")
    report = summarize(family, baseline, seasons, global_review)
    assert report["total_conditions_checked"] == 384
    assert report["constraint_violations"] == 0
    assert report["season_results"]["winter"]["counts"]["qualified_first_ten"] == 0
    assert len(report["autumn_supply_requirements"]) == 82
    assert len(report["autumn_changed_conditions"]) == 23
    assert len(report["unused_main_garment_candidates"]) == 35
    assert report["production_approved"] is False
    seasons["winter"]["family_registry"] = "stale"
    with pytest.raises(AssertionError, match="Stale family supply"):
        summarize(family, baseline, seasons, global_review)
