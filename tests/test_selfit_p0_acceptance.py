import importlib.util
import json
from pathlib import Path

from tests.test_recommendation_anchors import release_fixture


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/audit_selfit_p0_release.py"
SPEC = importlib.util.spec_from_file_location("audit_selfit_p0_release", SCRIPT)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)
BLIND_SCRIPT = Path(__file__).resolve().parents[1] / "scripts/selfit_p0_blind_review.py"
BLIND_SPEC = importlib.util.spec_from_file_location("selfit_p0_blind_review", BLIND_SCRIPT)
blind = importlib.util.module_from_spec(BLIND_SPEC)
BLIND_SPEC.loader.exec_module(blind)
PREPARE_SCRIPT = Path(__file__).resolve().parents[1] / "scripts/prepare_selfit_p0_anchors.py"
PREPARE_SPEC = importlib.util.spec_from_file_location("prepare_selfit_p0_anchors", PREPARE_SCRIPT)
prepare = importlib.util.module_from_spec(PREPARE_SPEC)
PREPARE_SPEC.loader.exec_module(prepare)
BACKLOG_SCRIPT = Path(__file__).resolve().parents[1] / "scripts/build_selfit_p0_production_backlog.py"
BACKLOG_SPEC = importlib.util.spec_from_file_location("build_selfit_p0_production_backlog", BACKLOG_SCRIPT)
backlog = importlib.util.module_from_spec(BACKLOG_SPEC)
BACKLOG_SPEC.loader.exec_module(backlog)


def test_p0_anchor_titles_use_current_product_persona_names():
    root = Path(__file__).resolve().parents[1]
    templates = json.loads(
        (root / "app/static/selfit/data/personality-report-templates.v1.json").read_text(encoding="utf-8")
    )["types"]
    assert prepare.PERSONA_NAMES == {
        persona: templates[persona]["metadata"]["name"]
        for persona in prepare.PERSONA_NAMES
    }


def test_p0_backlog_structure_allocator_covers_all_structures_and_respects_cap():
    allocated = backlog.allocate_structures(
        backlog.Counter({"pants": 2, "skirt": 3}), 5
    )
    final = backlog.Counter({"pants": 2, "skirt": 3})
    final.update(allocated)
    assert sum(final.values()) == 10
    assert set(final) == {"pants", "skirt", "dress"}
    assert max(final.values()) <= 5


def test_candidate_selection_excludes_accessory_duplicates_and_wrong_scene():
    def row(oid, garment, scenes):
        return {
            "outfit_id": oid, "parent_outfit_id": oid,
            "items": [{"item_id": garment, "category": "dress"},
                      {"item_id": "bag-" + oid, "category": "bag"}],
            "visual": {"expression": "easy", "structure": "dress",
                       "wearability": "everyday", "scenes": scenes},
            "_raw": {"slot_roles": {garment: "hero"}},
        }
    selected, _ = prepare.select_persona([
        row("first", "dress-one", ["daily"]),
        row("second", "dress-one", ["daily"]),
        row("occasion", "dress-two", ["party"]),
        row("third", "dress-three", ["daily"]),
    ], excluded_recipes={tuple(["dress-three"])})
    assert [item["outfit_id"] for item in selected] == ["first"]


def test_full_numeric_quota_still_reports_missing_structure():
    rows = [{"visual": {"expression": expression,
                        "structure": "pants" if index < 5 else "skirt"}}
            for index, expression in enumerate(["easy"] * 4 + ["typical"] * 4 + ["explore"] * 2)]
    gap = prepare.selection_gap("wabi", rows, {})
    assert gap["selected"] == 10
    assert gap["missing"] == 0
    assert gap["missing_structures"] == ["dress"]
    assert gap["replacement_required"] is True
    rows[-1]["visual"]["structure"] = "dress"
    assert prepare.selection_gap("wabi", rows, {}) is None
    rows[0]["visual"]["expression"] = "typical"
    assert prepare.selection_gap("wabi", rows, {})["missing_by_expression"]["easy"] == 1


def test_backlog_creates_replacement_without_inflating_anchor_target(tmp_path):
    rows = [{"outfit_id": f"wabi-{index}", "persona": "wabi",
             "expression": expression, "structure": "pants" if index < 5 else "skirt"}
            for index, expression in enumerate(["easy"] * 4 + ["typical"] * 4 + ["explore"] * 2)]
    gap = prepare.selection_gap("wabi", [{"visual": row} for row in rows], {})
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"anchors": rows, "readiness": {"gaps": [gap]}}))
    templates = tmp_path / "templates.json"
    templates.write_text(json.dumps({"types": {"wabi": {"metadata": {"name": "WABI"}}}}))
    result = backlog.build(manifest, templates)
    assert result["summary"]["addition_tasks"] == 0
    assert result["summary"]["replacement_tasks"] == 1
    task = result["tasks"][0]
    assert task["structure"] == "dress"
    old = next(row for row in rows if row["outfit_id"] == task["replaces_outfit_id"])
    assert task["expression"] == old["expression"]
    final = [row for row in rows if row != old] + [task]
    assert len(final) == 10
    assert prepare.selection_gap("wabi", [{"visual": row} for row in final], {}) is None


def test_selector_covers_actual_structures_after_conflicting_dress_branch():
    rows = []
    for index, expression in enumerate(["explore"] * 2 + ["typical"] * 4 + ["easy"] * 4):
        oid = f"row-{index}"
        rows.append({
            "outfit_id": oid, "parent_outfit_id": oid,
            "items": [{"item_id": oid, "category": "top"}],
            "visual": {"expression": expression,
                       "structure": "pants" if index < 5 else "skirt",
                       "wearability": "everyday", "scenes": ["daily"]},
            "_raw": {"slot_roles": {oid: "hero"}},
        })
    # This high-ranked dress steals the parent needed by a mandatory easy row.
    # Visiting it and backtracking must not leave phantom dress coverage.
    import copy
    conflict = copy.deepcopy(rows[0])
    conflict.update(outfit_id="a-conflict", parent_outfit_id="row-9", _target_persona_score=1)
    conflict["items"] = [{"item_id": "conflict-dress", "category": "dress"}]
    conflict["visual"]["structure"] = "dress"
    selected, supply = prepare.select_persona([conflict, *rows])
    assert prepare.selection_gap("wabi", selected, supply) is not None
    valid = copy.deepcopy(conflict)
    valid.update(outfit_id="valid-dress", parent_outfit_id="valid-dress")
    valid["items"] = [{"item_id": "valid-dress", "category": "dress"}]
    selected, supply = prepare.select_persona([conflict, valid, *rows])
    assert len(selected) == 10
    assert {row["visual"]["structure"] for row in selected} == prepare.STRUCTURES
    assert prepare.selection_gap("wabi", selected, supply) is None


def test_evidence_gate_requires_all_cases_and_revision_binding(tmp_path):
    required = {"CASE-001", "CASE-002"}
    missing = audit.evidence_gate({}, required, "anchor-sha")
    assert missing["status"] == "Not Run"

    stale = audit.evidence_gate({
        "schema_version": 1,
        "anchor_manifest_sha256": "old-sha",
        "cases": {case_id: "Pass" for case_id in required},
    }, required, "anchor-sha")
    assert stale["status"] == "Fail"
    assert any("not bound" in error for error in stale["errors"])

    artifact = tmp_path / "run.log"
    artifact.write_text("observed actual execution results")
    record = {"status": "Pass", "executor": "qa", "executed_at": "2026-09-05T12:00:00Z",
              "actual_result": "Assertions matched recorded observations",
              "artifacts": [{"path": str(artifact), "sha256": audit.sha256(artifact)}]}
    evidence = {
        "schema_version": 1,
        "anchor_manifest_sha256": "anchor-sha",
        "cases": {case_id: dict(record) for case_id in required},
    }
    complete = audit.evidence_gate(evidence, required, "anchor-sha")
    assert complete["status"] == "Pass"
    artifact.write_text("changed after acceptance")
    assert audit.evidence_gate(evidence, required, "anchor-sha")["status"] == "Fail"


def test_status_only_and_duplicate_evidence_cannot_pass():
    evidence = {"schema_version": 1, "anchor_manifest_sha256": "sha",
                "cases": {"CASE-001": "Pass"}}
    result = audit.evidence_gate(evidence, {"CASE-001"}, "sha")
    assert result["status"] == "Fail"
    assert any("execution record" in error for error in result["errors"])
    evidence["cases"] = [{"id": "CASE-001", "status": "Fail"},
                         {"id": "CASE-001", "status": "Pass"}]
    result = audit.evidence_gate(evidence, {"CASE-001"}, "sha")
    assert "duplicate case IDs" in result["errors"]


def test_gate_case_matrix_matches_all_94_documented_cases():
    import re
    spec = (audit.ROOT / "docs/SELFIT_P0_ACCEPTANCE_20260904.md").read_text()
    documented = set(re.findall(r"^\| ([A-Z][A-Z0-9]*-\d{3}) \|", spec, re.MULTILINE))
    required = set().union(*audit.GATE_CASES.values())
    assert len(documented) == 94
    assert required == documented
    assert {"PERF-007", "PERF-008"} <= audit.PERF_CASES


def test_non_pass_case_blocks_evidence_gate():
    result = audit.evidence_gate({
        "schema_version": 1,
        "anchor_manifest_sha256": "anchor-sha",
        "cases": {"CASE-001": "Blocked"},
    }, {"CASE-001"}, "anchor-sha")
    assert result["status"] == "Fail"
    assert "CASE-001" in result["errors"][0]


def test_structural_fixture_remains_compatible_with_auditor_contract():
    raw, catalog, manifest, blind = release_fixture()
    result = audit.validate_manifest(
        manifest, catalog, raw,
        content_version="content-v1", visual_version="visual-v1",
        family_registry_sha256="family-v1", require_release=False,
    )
    assert result["valid"] is True
    assert audit.blind_review_errors(blind, manifest["blind_review_package_id"]) == []


def test_current_staging_bundle_produces_160_structurally_valid_anchors():
    root = Path(__file__).resolve().parents[1]
    report = json.loads((root / "docs/audits/20260904-p0-acceptance/release-report.v8.json").read_text())
    manifest = json.loads((root / "docs/audits/20260904-p0-acceptance/anchor-candidates.v11.json").read_text())
    staging = json.loads((root / "docs/audits/20260904-p0-acceptance/p0-gap-staging.v4.json").read_text())
    assert len(manifest["anchors"]) == 160
    assert len(staging["entries"]) == 7
    assert report["inventory"]["anchor_rows"] == 160
    assert report["gates"]["G3_anchor_completeness"] == {"status": "Pass", "errors": []}
    assert report["gates"]["G2_content_admission"]["status"] == "Fail"
    assert all(entry["four_gate_status"] == "pending" for entry in staging["entries"])


def test_blind_package_is_blocked_until_every_editorial_gate_passes():
    _, _, manifest, _ = release_fixture()
    manifest_sha = "manifest-sha"
    reviews = [{
        "outfit_id": row["outfit_id"],
        "record_fingerprint": row["record_fingerprint"],
        "final_decision": "approved",
        "gates": {gate: {"status": "passed", "reviewer": "editor", "evidence": "evidence.json"}
                  for gate in ("technical", "aesthetic", "persona", "context")},
    } for row in manifest["anchors"]]
    editorial = {"anchor_manifest_sha256": manifest_sha, "reviews": reviews}
    assert blind.editorial_errors(manifest, editorial, manifest_sha) == []
    reviews[0]["gates"]["persona"]["status"] = "needs_review"
    errors = blind.editorial_errors(manifest, editorial, manifest_sha)
    assert any("persona gate is incomplete" in error for error in errors)
