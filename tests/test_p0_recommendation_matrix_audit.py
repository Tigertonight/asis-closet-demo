"""Candidate diagnostics must never manufacture formal recommendation evidence."""
import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.test_recommendation_anchors import release_fixture


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/audit_selfit_p0_recommendation_matrix.py"
SPEC = importlib.util.spec_from_file_location("p0_matrix_audit", SCRIPT)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


@pytest.fixture
def matrix(monkeypatch):
    # Deliberately perfect components: coverage gaps must be caught by the
    # audit itself, independently of production ranking and selection tests.
    monkeypatch.setattr(audit, "rank_candidates", lambda rows, *args: (rows, []))
    monkeypatch.setattr(audit, "select_sequence", lambda rows, *args, **kwargs: (rows[:10], []))
    _, catalog, manifest, _ = release_fixture()
    return manifest, catalog


def test_complete_offline_matrix_is_not_formal_acceptance(matrix):
    result = audit.diagnose_matrix(*matrix)
    assert result["status"] == "diagnostic_pass"
    assert result["errors"] == []
    assert result["formal_acceptance"] is False
    assert set(result["personas"]) == audit.PERSONAS
    assert len(result["cases"]) == 14
    assert set(result["cases"].values()) == {"Not Run"}
    assert "pagination and cursor snapshots" in result["unverified"]


@pytest.mark.parametrize("count", [0, 10, 150, 159])
def test_missing_personas_cannot_disappear_from_matrix(matrix, count):
    manifest, catalog = matrix
    manifest["anchors"] = manifest["anchors"][:count]
    result = audit.diagnose_matrix(manifest, catalog)
    assert result["status"] == "diagnostic_fail"
    assert len(result["personas"]) == 16
    assert "anchor count must be exactly 160" in result["errors"]
    assert any("anchor count must be 10" in error for error in result["errors"])
    assert set(result["cases"].values()) == {"Not Run"}


@pytest.mark.parametrize("bad_row", [None, {}, {"outfit_id": " "},
    {"outfit_id": "look", "persona": "not-a-persona"},
    {"outfit_id": "look", "persona": []}])
def test_malformed_anchor_fails_closed(matrix, bad_row):
    manifest, catalog = matrix
    manifest["anchors"][0] = bad_row
    result = audit.diagnose_matrix(manifest, catalog)
    assert result["status"] == "diagnostic_fail"


def test_duplicate_ids_are_not_silently_collapsed(matrix):
    manifest, catalog = matrix
    manifest["anchors"][1] = copy.deepcopy(manifest["anchors"][0])
    result = audit.diagnose_matrix(manifest, catalog)
    assert any("duplicate anchor ID" in error for error in result["errors"])


def test_missing_catalog_row_fails_even_with_full_manifest(matrix):
    manifest, catalog = matrix
    result = audit.diagnose_matrix(manifest, catalog[1:])
    assert any("absent from candidate catalog" in error for error in result["errors"])


def test_adaptation_must_not_hide_persona_mismatch(matrix):
    manifest, catalog = matrix
    catalog[0]["primary_persona"] = "VOID"
    result = audit.diagnose_matrix(manifest, catalog)
    assert any("catalog persona does not match manifest" in error for error in result["errors"])


def test_duplicate_catalog_row_is_reported(matrix):
    manifest, catalog = matrix
    result = audit.diagnose_matrix(manifest, catalog + [copy.deepcopy(catalog[0])])
    assert any("duplicate catalog ID" in error for error in result["errors"])


def test_structure_failure_is_diagnostic_not_fake_rec_execution(matrix):
    manifest, catalog = matrix
    for row in catalog[:10]:
        row["visual"]["structure"] = "pants"
    result = audit.diagnose_matrix(manifest, catalog)
    assert any("structure coverage/cap failed" in error for error in result["errors"])
    assert set(result["cases"].values()) == {"Not Run"}


@pytest.fixture
def cli(matrix, monkeypatch, tmp_path):
    manifest, catalog = matrix
    raw, _, _, _ = release_fixture()
    family = tmp_path / "families.json"
    family.write_text("{}")
    manifest["family_registry_sha256"] = audit.sha(family)
    manifest["staging_version"] = "staging-test"
    anchor = tmp_path / "anchors.json"
    anchor.write_text(json.dumps(manifest))
    staging = tmp_path / "staging.json"
    staging.write_text(json.dumps({"version": "staging-test", "entries": []}))
    output = tmp_path / "matrix.json"
    monkeypatch.setattr(audit, "FAMILY_PATH", family)
    monkeypatch.setattr(audit.closet, "selfit_content_pool", lambda: SimpleNamespace(
        garments=[], outfits=raw, metadata={"contentVersion": "content-v1"}))
    monkeypatch.setattr(audit.closet, "_published_catalog_outfits", lambda: catalog)
    monkeypatch.setattr(audit, "load_visual", lambda: {"version": "visual-v1"})
    monkeypatch.setattr(audit, "attach_visual", lambda rows, *args: (rows, []))
    monkeypatch.setattr(audit.sys, "argv", [str(SCRIPT), "--anchor-manifest", str(anchor),
        "--staging", str(staging), "--output", str(output)])
    return anchor, staging, output


def test_cli_writes_only_diagnostic_status_and_refuses_overwrite(cli):
    _, _, output = cli
    assert audit.main() == 0
    result = json.loads(output.read_text())
    assert result["status"] == "diagnostic_pass"
    assert set(result["cases"].values()) == {"Not Run"}
    with pytest.raises(ValueError, match="overwrite"):
        audit.main()


@pytest.mark.parametrize("change", ["content_version", "visual_version", "family_registry_sha256", "fingerprint"])
def test_cli_rejects_stale_evidence(cli, change):
    anchor, _, output = cli
    manifest = json.loads(anchor.read_text())
    if change == "fingerprint":
        manifest["anchors"][0]["record_fingerprint"] = "stale"
    else:
        manifest[change] = "stale"
    anchor.write_text(json.dumps(manifest))
    assert audit.main() == 2
    result = json.loads(output.read_text())
    assert any("stale candidate" in error for error in result["errors"])


def test_cli_detects_input_changed_during_diagnosis(cli, monkeypatch):
    anchor, _, output = cli
    original = audit.diagnose_matrix
    def change_input(*args):
        result = original(*args)
        anchor.write_text("{}")
        return result
    monkeypatch.setattr(audit, "diagnose_matrix", change_input)
    assert audit.main() == 2
    result = json.loads(output.read_text())
    assert "input changed during diagnosis" in result["errors"]
    assert result["anchor_manifest_sha256"] != audit.sha(anchor)


def test_cli_rejects_stale_staged_raw_record(cli):
    _, staging, _ = cli
    raw, catalog, _, _ = release_fixture()
    staging.write_text(json.dumps({"version": "staging-test", "entries": [{
        "raw_record": raw[0], "catalog_record": catalog[0], "record_fingerprint": "stale"}]}))
    with pytest.raises(ValueError, match="Staging contains"):
        audit.main()
