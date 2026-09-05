from __future__ import annotations

import copy
import json
from collections import Counter
from pathlib import Path

import pytest
from PIL import Image

from app import closet
from app.selfit_content_quality import apply_curation, load_curation, record_fingerprint, review_is_current, publication_status
from app.selfit_recommend import ContentPool, BUNDLED_CONTENT_POOL_V2_PATH, body_structure_score, skin_color_score, _published_v2_ready
from scripts.build_selfit_content_expansion import _merge_progress
from scripts.build_selfit_outfit_flatlay import build_from_plan
from scripts.curate_selfit_content import build, measure_color, AUDIT


@pytest.fixture(scope="module")
def raw_pool():
    return json.loads(BUNDLED_CONTENT_POOL_V2_PATH.read_text())


def test_curation_keeps_assets_but_removes_duplicates_and_confirmed_issues(raw_pool):
    source = copy.deepcopy(raw_pool)
    reviewed = apply_curation(raw_pool)
    pool = ContentPool(BUNDLED_CONTENT_POOL_V2_PATH)
    assert raw_pool == source  # editorial layer never mutates the production archive
    assert len(pool.all_outfits) == 1200
    assert len(pool.outfits) == 1169
    assert len(pool.garments) == 600
    counts = Counter(row["curation"]["status"] for row in reviewed["outfits"])
    assert counts == {"legacy_allowed": 1169, "hold": 18, "alias": 13}
    sets = [tuple(sorted(row["garment_ids"])) for row in pool.outfits]
    assert len(sets) == len(set(sets))
    assert min(Counter(row["primary_persona"] for row in pool.outfits).values()) >= 10
    excluded = {row["id"] for row in pool.all_outfits} - {row["id"] for row in pool.outfits}
    assert {"outfit_neon_master_01", "outfit_bolt_master_16", "outfit_heir_master_27_v1", "outfit_noir_master_29"} <= excluded
    assert {"outfit_neon_master_01_v1", "outfit_neon_master_01_v2"} <= excluded


def test_review_only_conflicts_are_not_mass_rejected():
    pool = ContentPool(BUNDLED_CONTENT_POOL_V2_PATH)
    assert sum("scene_tags_need_review" in row["curation"]["review_flags"] for row in pool.outfits) > 350
    assert sum("winter_layering_context_unknown" in row["curation"]["review_flags"] for row in pool.outfits) > 170


def test_historical_detail_is_available_but_not_in_default_catalog(monkeypatch):
    monkeypatch.setattr(closet, "_ensure_outfit_manifest", lambda: {"outfits": []})
    pool = ContentPool(BUNDLED_CONTENT_POOL_V2_PATH)
    monkeypatch.setattr(closet, "selfit_content_pool", lambda: pool)
    assert "outfit_neon_master_01" not in {row["outfit_id"] for row in closet._published_catalog_outfits()}
    detail = closet.get_outfit("outfit_neon_master_01")
    assert detail["curation"]["status"] == "hold"
    assert detail["items"]


@pytest.mark.parametrize("field,value", [("garment_ids", ["different"]), ("scene_tags", ["旅行"]), ("primary_persona", "VOID"), ("recipe_version", "new")])
def test_changed_recipe_cannot_inherit_audited_release(raw_pool, field, value):
    row = copy.deepcopy(raw_pool["outfits"][0])
    row[field] = value
    assert publication_status(row) == "pending"
    patched = apply_curation({"outfits": [row]})["outfits"][0]
    assert patched["curation"]["status"] == "pending"


def test_missing_overlay_fails_closed_for_v2_but_does_not_filter_v1(raw_pool):
    generated = copy.deepcopy(raw_pool["outfits"][0])
    rows = apply_curation({"outfits": [generated, {"id": "legacy", "imageUrl": "/old.jpg"}]}, {})["outfits"]
    assert rows[0]["curation"]["status"] == "pending"
    assert "curation" not in rows[1]


def test_raw_count_does_not_mask_unavailable_curated_content(tmp_path, raw_pool):
    changed = copy.deepcopy(raw_pool)
    for row in changed["outfits"]:
        row["recipe_version"] = "unreviewed-rebuild"
    path = tmp_path / "changed.json"
    path.write_text(json.dumps(changed))
    assert _published_v2_ready(path) is False


def test_curated_runtime_records_still_validate_against_schema():
    from jsonschema import Draft202012Validator
    schema = json.loads((BUNDLED_CONTENT_POOL_V2_PATH.parent / "content-pool.schema.v2.json").read_text())
    data = ContentPool(BUNDLED_CONTENT_POOL_V2_PATH)._load()
    assert list(Draft202012Validator(schema).iter_errors(data)) == []


def test_labels_are_measured_or_unknown_not_persona_templates():
    pool = ContentPool(BUNDLED_CONTENT_POOL_V2_PATH)
    assert all(row["color"]["palette"] for row in pool.garments)
    assert all(row["color_evidence"]["asset_sha256"] for row in pool.garments)
    assert all(row["materials"] == [] and row["fit"] == "未判断" for row in pool.garments)
    assert all(row["semantic_review"]["status"] == "pending" for row in pool.garments)
    assert all(not row["body_types"] for row in pool.outfits)
    assert body_structure_score(pool.outfits[0], "苹果型", None) is None
    assert skin_color_score({"color": {"temperature": "未判断"}}, "冷白肤") is None


def test_transparent_background_does_not_count_as_garment_color(tmp_path):
    image = Image.new("RGBA", (120, 120), (0, 255, 0, 0))
    image.paste((255, 0, 0, 255), (40, 40, 80, 80))
    path = tmp_path / "red.png"
    image.save(path)
    measured = measure_color(path)
    assert measured["color"]["palette"] == ["#ff0000"]
    assert measured["color"]["saturation"] == "高饱和"
    assert measured["color"]["temperature"] == "未判断"


def test_overlay_decisions_are_reproducible(raw_pool):
    audit = json.loads(AUDIT.read_text())
    result, summary = build(raw_pool, audit, measure=False)
    assert summary["outfit_status_counts"] == {"legacy_allowed": 1169, "hold": 18, "alias": 13}
    for oid, entry in result["outfits"].items():
        assert entry["status"] == load_curation()["outfits"][oid]["status"]


def test_cli_flag_cannot_fake_designer_review(tmp_path):
    with pytest.raises(ValueError, match="cannot certify"):
        build_from_plan(tmp_path / "missing.json", designer_approved=True)


def test_rerender_is_versioned_and_invalidates_review(tmp_path, monkeypatch):
    import scripts.build_selfit_outfit_flatlay as flatlay
    monkeypatch.setattr(flatlay, "_asset_path", lambda value: Path(value))
    garment_path = tmp_path / "garment.png"
    image = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    image.paste((100, 130, 170, 255), (20, 20, 80, 80))
    image.save(garment_path)
    old_path = tmp_path / "outfit.webp"
    old_path.write_bytes(b"old version must stay")
    plan = {"garmentJobs": [{"record_template": {"id": "g", "category": "top", "assets": {"image_url": str(garment_path)}}}],
            "masterOutfits": [{"id": "test", "garment_ids": ["g"], "assets": {"image_url": str(old_path)},
                               "quality_review": {"old": "review"}}]}
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan))
    result = build_from_plan(path)
    row = json.loads(path.read_text())["masterOutfits"][0]
    assert result["passed"]
    assert old_path.read_bytes() == b"old version must stay"
    assert row["assets"]["image_url"] != str(old_path)
    assert Path(row["assets"]["image_url"]).is_file()
    assert "quality_review" not in row
    assert row["annotation"]["status"] == "machine_draft"
    qa = json.loads(Path(row["assets"]["image_url"]).with_suffix(".qa.json").read_text())
    assert qa["designer_reviewed"] is False
    assert qa["checks"]["within_canvas"] is True
    assert qa["checks"]["bag_hat_shoes_complete"] is None


def test_regeneration_does_not_copy_review_to_changed_recipe(tmp_path, raw_pool):
    old = copy.deepcopy(raw_pool["outfits"][0])
    path = tmp_path / "old.json"
    path.write_text(json.dumps({"masterOutfits": [old]}))
    changed = copy.deepcopy(old)
    changed["garment_ids"][0] = "replacement"
    changed["annotation"] = {"status": "machine_draft"}
    result = _merge_progress({"masterOutfits": [changed]}, path)
    assert result["masterOutfits"][0]["annotation"]["status"] == "machine_draft"


def test_four_reviews_must_match_current_recipe(raw_pool):
    row = copy.deepcopy(raw_pool["outfits"][0])
    assert not review_is_current(row)
    row["quality_review"] = {"record_fingerprint": record_fingerprint(row), **{
        gate: {"status": "passed", "reviewer": "test-only", "evidence": ["fixture evidence"]}
        for gate in ("technical", "aesthetic", "persona", "context")}}
    assert review_is_current(row)
    row["intensity"] = "experimental"
    assert not review_is_current(row)
