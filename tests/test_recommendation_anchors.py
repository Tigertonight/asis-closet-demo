import json

from app.recommendation_anchors import PERSONAS, adapt_released_anchor, approved_anchor_pool, validate_manifest
from app.selfit_content_quality import GATES, record_fingerprint


def _four_gate_review(record):
    fingerprint = record_fingerprint(record)
    return {
        "record_fingerprint": fingerprint,
        **{
            gate: {"status": "passed", "reviewer": f"reviewer-{gate}", "evidence": f"evidence/{gate}.json"}
            for gate in GATES
        },
    }


def release_fixture():
    raw, catalog, anchors = [], [], []
    structures = ["pants", "skirt", "dress", "pants", "skirt", "dress", "pants", "skirt", "dress", "pants"]
    expressions = ["easy"] * 4 + ["typical"] * 4 + ["explore"] * 2
    for persona in sorted(PERSONAS):
        for index, (structure, expression) in enumerate(zip(structures, expressions), 1):
            oid = f"look-{persona}-{index:02d}"
            gid = f"garment-{persona}-{index:02d}"
            record = {
                "id": oid,
                "title": f"日常灵感 {index}",
                "primary_persona": persona.upper(),
                "garment_ids": [gid],
                "slot_roles": {gid: "hero"},
                "layer_graph": [],
                "parent_outfit_id": oid,
            }
            record["quality_review"] = _four_gate_review(record)
            raw.append(record)
            catalog.append({
                "outfit_id": oid,
                "primary_persona": persona.upper(),
                "parent_outfit_id": oid,
                "items": [{"item_id": gid, "category": "dress", "style_family_id": f"item:{gid}"}],
                "visual": {"structure": structure, "expression": expression, "layering": 1},
            })
            anchors.append({
                "outfit_id": oid,
                "persona": persona,
                "expression": expression,
                "structure": structure,
                "user_title": f"日常灵感 {index}",
                "record_fingerprint": record_fingerprint(record),
            })
    package_id = "blind-package-v1"
    manifest = {
        "schema_version": 1,
        "status": "approved",
        "version": "anchors-v1",
        "content_version": "content-v1",
        "visual_version": "visual-v1",
        "family_registry_sha256": "family-v1",
        "blind_review_package_id": package_id,
        "anchors": anchors,
    }
    blind = {
        "package_id": package_id,
        "reviewer": "independent-reviewer",
        "identity_verification": "declaration_only",
        "independent": True, "labels_hidden": True,
        "samples": 160,
        "top1_accuracy": .8,
        "top2_accuracy": 1.0,
        "by_persona": {
            persona: {"samples": 10, "top1_hits": 8, "top2_hits": 10}
            for persona in PERSONAS
        },
        "decisions": [{
            "token": f"sample-{i}", "outfit_id": anchor["outfit_id"],
            "expected_persona": anchor["persona"],
            "record_fingerprint": anchor["record_fingerprint"],
            "top1": anchor["persona"] if i % 10 < 8 else next(p for p in sorted(PERSONAS) if p != anchor["persona"]),
            "top2": next(p for p in sorted(PERSONAS) if p != anchor["persona"]) if i % 10 < 8 else anchor["persona"],
            "reason": "visible garment structure", "issues": [], "verdict": "accept",
        } for i, anchor in enumerate(anchors)],
    }
    return raw, catalog, manifest, blind


def test_complete_revision_bound_anchor_release_passes():
    raw, catalog, manifest, blind = release_fixture()
    result = validate_manifest(
        manifest, catalog, raw,
        content_version="content-v1", visual_version="visual-v1", family_registry_sha256="family-v1", blind_result=blind,
    )
    assert result["valid"] is True
    assert result["errors"] == []
    assert set(result["counts"]) == PERSONAS
    assert set(result["counts"].values()) == {10}


def test_blind_release_recomputes_scores_and_checks_sample_identity():
    from copy import deepcopy
    from app.recommendation_anchors import blind_review_errors
    _, _, manifest, original = release_fixture()
    for field, value in (("top1_accuracy", float("nan")), ("top2_accuracy", "invalid"),
                         ("independent", False)):
        result = deepcopy(original)
        result[field] = value
        assert blind_review_errors(result, manifest["blind_review_package_id"], manifest["anchors"])
    result = deepcopy(original)
    result["decisions"][1] = deepcopy(result["decisions"][0])
    errors = blind_review_errors(result, manifest["blind_review_package_id"], manifest["anchors"])
    assert any("duplicate" in error for error in errors)
    result = deepcopy(original)
    result["decisions"][0]["record_fingerprint"] = "old"
    assert any("stale" in error for error in blind_review_errors(
        result, manifest["blind_review_package_id"], manifest["anchors"]))
    result = deepcopy(original)
    result["top1_accuracy"] = 1.0
    assert any("summary does not match" in error for error in blind_review_errors(
        result, manifest["blind_review_package_id"], manifest["anchors"]))


def test_accessory_variants_cannot_impersonate_distinct_anchor_recipes():
    raw, catalog, manifest, blind = release_fixture()
    catalog[1]["items"] = [dict(catalog[0]["items"][0]),
                           {"item_id": "different-bag", "category": "bag"}]
    result = validate_manifest(
        manifest, catalog, raw, content_version="content-v1",
        visual_version="visual-v1", family_registry_sha256="family-v1", blind_result=blind,
    )
    assert not result["valid"]
    assert any("accessory changes are not distinct parents" in error for error in result["errors"])


def test_missing_four_gate_review_and_stale_anchor_fail_closed():
    raw, catalog, manifest, blind = release_fixture()
    raw[0].pop("quality_review")
    raw[0]["description"] = "changed after review"
    result = validate_manifest(
        manifest, catalog, raw,
        content_version="content-v1", visual_version="visual-v1", family_registry_sha256="family-v1", blind_result=blind,
    )
    assert result["valid"] is False
    assert any("record fingerprint is stale" in error for error in result["errors"])
    assert any("four-gate review is missing" in error for error in result["errors"])


def test_blind_thresholds_are_global_and_per_persona_hard_gates():
    raw, catalog, manifest, blind = release_fixture()
    blind["by_persona"]["wabi"] = {"samples": 10, "top1_hits": 5, "top2_hits": 7}
    result = validate_manifest(
        manifest, catalog, raw,
        content_version="content-v1", visual_version="visual-v1", family_registry_sha256="family-v1", blind_result=blind,
    )
    assert result["valid"] is False
    assert "wabi: blind Top-1 is below 60%" in result["errors"]
    assert "wabi: blind Top-2 is below 80%" in result["errors"]


def test_reject_or_uncertain_blind_decision_blocks_release():
    raw, catalog, manifest, blind = release_fixture()
    blind["decisions"][10]["verdict"] = "uncertain"
    result = validate_manifest(
        manifest, catalog, raw,
        content_version="content-v1", visual_version="visual-v1", family_registry_sha256="family-v1", blind_result=blind,
    )
    assert result["valid"] is False
    assert "blind review contains reject or unresolved uncertain decisions" in result["errors"]


def test_structure_expression_family_and_user_copy_are_hard_gates():
    raw, catalog, manifest, blind = release_fixture()
    target = next(row for row in manifest["anchors"] if row["persona"] == "mute")
    target["expression"] = "experimental"
    catalog_by_id = {row["outfit_id"]: row for row in catalog}
    catalog_by_id[target["outfit_id"]]["visual"]["expression"] = "experimental"
    target["user_title"] = "MUTE pipeline 01"
    result = validate_manifest(
        manifest, catalog, raw,
        content_version="content-v1", visual_version="visual-v1", family_registry_sha256="family-v1", blind_result=blind,
    )
    assert result["valid"] is False
    assert any("expression must be" in error for error in result["errors"])
    assert any("expression mix must be" in error for error in result["errors"])
    assert any("internal code" in error for error in result["errors"])


def test_configured_release_returns_empty_pool_when_manifest_is_stale(tmp_path, monkeypatch):
    raw, catalog, manifest, blind = release_fixture()
    manifest["content_version"] = "old-content"
    manifest_path = tmp_path / "anchors.json"
    blind_path = tmp_path / "blind.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    blind_path.write_text(json.dumps(blind), encoding="utf-8")
    monkeypatch.setenv("SELFIT_P0_ANCHOR_MANIFEST", str(manifest_path))
    monkeypatch.setenv("SELFIT_P0_BLIND_REVIEW", str(blind_path))
    rows, result = approved_anchor_pool(
        catalog, raw, content_version="content-v1", visual_version="visual-v1"
    )
    assert rows == []
    assert result["valid"] is False
    assert "anchor manifest content version is stale" in result["errors"]
    assert result["manifest_sha256"]
    assert result["blind_result_sha256"]


def test_release_backed_persona_supersedes_ai_candidate_score_without_mutating_source():
    source = {"outfit_id": "look-1", "title": "internal", "visual": {
        "persona_scores": {"mute": .2}, "scenes": ["social"],
    }}
    released = adapt_released_anchor(source, {"persona": "mute", "user_title": "安静有序"})
    assert released["title"] == "安静有序"
    assert released["visual"]["persona_scores"]["mute"] == 1.0
    assert released["visual"]["scenes"] == ["daily", "social"]
    assert source["visual"]["persona_scores"]["mute"] == .2
