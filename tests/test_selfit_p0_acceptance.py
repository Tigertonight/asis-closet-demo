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


def test_evidence_gate_requires_all_cases_and_revision_binding():
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

    complete = audit.evidence_gate({
        "schema_version": 1,
        "anchor_manifest_sha256": "anchor-sha",
        "cases": {case_id: {"status": "Pass"} for case_id in required},
    }, required, "anchor-sha")
    assert complete["status"] == "Pass"


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
