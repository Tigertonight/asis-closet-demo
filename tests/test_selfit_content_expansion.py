from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from app import closet
import app.selfit_recommend as selfit_recommend
from app.selfit_recommend import ContentPool, _incremental_v2_ready, _published_v2_ready, recommend_outfits
from scripts.publish_selfit_content_pool_incremental import build as build_incremental_pool
from scripts.publish_selfit_content_pool_v2 import build as build_published_pool


ROOT = Path(__file__).resolve().parents[1]
REFERENCE_LIBRARY = ROOT / "app/static/selfit/data/reference-looks.internal.json"
PRODUCTION_PLAN = ROOT / "app/static/selfit/data/content-production-plan.v2.json"
SCHEMA = ROOT / "app/static/selfit/data/content-pool.schema.v2.json"
PERSONAS = {"MUTE", "ICED", "HEIR", "EASE", "MELT", "WABI", "FLOU", "NEON", "EDGE", "BOLT", "FILM", "JADE", "LOOP", "NOIR", "VOID", "OOPS"}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_reference_library_is_complete_and_strictly_non_publishable() -> None:
    data = _load(REFERENCE_LIBRARY)
    records = data["reference_looks"]
    unlabeled = data["unlabeled_assets"]

    assert len(records) == 366
    assert len(unlabeled) == 11
    assert len({item["id"] for item in records}) == 366
    assert len({item["file_name"] for item in records}) == 366
    assert all(item["rights_status"] == "source_recorded" and item["publishable"] is False for item in records)
    assert all(item["status"] == "unlabeled" and item["publishable"] is False for item in unlabeled)
    assert data["summary"]["personaCounts"]["EASE"] == 126
    assert data["summary"]["personaCounts"]["NOIR"] == 1
    assert "LOOP" not in data["summary"]["personaCounts"]
    assert "OOPS" not in data["summary"]["personaCounts"]


def test_production_plan_has_exact_garment_and_outfit_quotas() -> None:
    data = _load(PRODUCTION_PLAN)
    jobs = data["garmentJobs"]
    masters = data["masterOutfits"]
    variants = data["variantOutfits"]

    assert len(jobs) == 600
    assert Counter(item["tier"] for item in jobs) == {"shared": 240, "variant": 240, "signature": 120}
    assert Counter(item["category"] for item in jobs) == {
        "top": 120, "outer": 80, "bottom": 70, "skirt": 70, "dress": 60,
        "shoes": 70, "bag": 60, "hat": 30, "scarf": 20, "accessory": 20,
    }
    assert len(masters) == 480
    assert len(variants) == 720
    assert Counter(item["primary_persona"] for item in masters) == {persona: 30 for persona in PERSONAS}
    assert Counter(item["primary_persona"] for item in variants) == {persona: 45 for persona in PERSONAS}


def test_every_persona_master_matrix_matches_product_quota() -> None:
    masters = _load(PRODUCTION_PLAN)["masterOutfits"]
    for persona in PERSONAS:
        items = [item for item in masters if item["primary_persona"] == persona]
        assert Counter(item["scene_tags"][0] for item in items) == {
            "通勤": 6, "日常": 6, "约会社交": 5, "正式活动": 4, "旅行": 4, "创意表达": 5,
        }
        assert Counter(item["season_tags"][0] for item in items) == {"春": 7, "夏": 8, "秋": 8, "冬": 7}
        assert Counter(item["intensity"] for item in items) == {"entry": 12, "signature": 12, "experimental": 6}
        assert Counter(item["presentation"][0] for item in items) == {"feminine": 21, "neutral": 9}


def test_variants_replace_only_one_same_category_slot() -> None:
    data = _load(PRODUCTION_PLAN)
    garment_category = {job["record_template"]["id"]: job["category"] for job in data["garmentJobs"]}
    masters = {item["id"]: item for item in data["masterOutfits"]}
    for variant in data["variantOutfits"]:
        parent = masters[variant["parent_outfit_id"]]
        changes = [(before, after) for before, after in zip(parent["garment_ids"], variant["garment_ids"], strict=True) if before != after]
        assert len(changes) == 1
        before, after = changes[0]
        assert garment_category[before] == garment_category[after]
        assert variant["replacement_rules"] == {
            "same_slot": True, "match_season": True, "match_scene": True,
            "max_formality_delta": 1, "preserve_color_harmony": True,
        }


def test_no_persona_sequence_repeats_one_hero_more_than_twice_in_ten() -> None:
    data = _load(PRODUCTION_PLAN)
    for section in ("masterOutfits", "variantOutfits"):
        for persona in PERSONAS:
            rows = [item for item in data[section] if item["primary_persona"] == persona]
            heroes = [
                next(garment_id for garment_id, role in item["slot_roles"].items() if role == "hero")
                for item in rows
            ]
            for start in range(len(heroes) - 9):
                assert max(Counter(heroes[start:start + 10]).values()) <= 2


def test_publish_gate_rejects_planned_or_missing_assets(tmp_path: Path) -> None:
    incomplete = _load(PRODUCTION_PLAN)
    incomplete["garmentJobs"][0]["status"] = "planned"
    plan = tmp_path / "incomplete-plan.json"
    plan.write_text(json.dumps(incomplete), encoding="utf-8")
    with pytest.raises(ValueError, match="publish gates failed"):
        build_published_pool(plan)


def test_incremental_publish_merges_stable_baseline_and_only_reviewed_v2_assets() -> None:
    pool = build_incremental_pool()
    publication = pool["publication"]

    assert pool["releaseMode"] == "incremental"
    assert publication["baselineOutfitCount"] == 156
    assert publication["incrementalGarmentCount"] == 600
    assert publication["incrementalOutfitCount"] == 1169
    assert len(publication["incrementalOutfitIds"]) == 1169
    assert len(pool["outfits"]) == 1325
    assert "outfit_neon_master_01" not in publication["incrementalOutfitIds"]
    assert all(item["assets"]["rights_status"] == "owned" for item in pool["garments"])
    assert all(item["production"]["qa_status"] == "approved" for item in pool["garments"])
    added = next(item for item in pool["outfits"] if item["id"] == "outfit_ease_master_16")
    assert added["imageUrl"] == added["assets"]["image_url"]
    assert set(added["garment_ids"]) <= set(publication["incrementalGarmentIds"])


def test_incremental_loader_rejects_tampered_manifest(tmp_path: Path) -> None:
    pool = build_incremental_pool()
    pool["publication"]["incrementalGarmentIds"].pop()
    path = tmp_path / "incremental.json"
    path.write_text(json.dumps(pool), encoding="utf-8")
    assert _incremental_v2_ready(path) is False


def test_v2_loader_requires_full_published_pool(tmp_path: Path) -> None:
    path = tmp_path / "pool.json"
    path.write_text(json.dumps({"schemaVersion": "2.0", "status": "published", "garments": [], "outfits": []}), encoding="utf-8")
    assert _published_v2_ready(path) is False


def test_version_switch_can_force_v1_and_v2_still_falls_back_safely(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    v1 = tmp_path / "v1.json"
    incomplete_v2 = tmp_path / "v2.json"
    v1.write_text(json.dumps({"outfits": [{"id": "stable-v1"}]}), encoding="utf-8")
    incomplete_v2.write_text(json.dumps({"schemaVersion": "2.0", "status": "published", "garments": [], "outfits": []}), encoding="utf-8")
    monkeypatch.setattr(selfit_recommend, "BUNDLED_CONTENT_POOL_PATH", v1)
    monkeypatch.setattr(selfit_recommend, "BUNDLED_CONTENT_POOL_V2_PATH", incomplete_v2)
    monkeypatch.setattr(selfit_recommend, "BUNDLED_CONTENT_POOL_V2_INCREMENTAL_PATH", tmp_path / "missing-incremental.json")
    monkeypatch.setattr(selfit_recommend, "DEFAULT_CONTENT_POOL_PATH", tmp_path / "missing.json")
    monkeypatch.delenv("SELFIT_CONTENT_POOL_PATH", raising=False)

    for version in ("v1", "v2", "auto"):
        monkeypatch.setenv("SELFIT_CONTENT_POOL_VERSION", version)
        selfit_recommend.reset_content_pool_cache()
        assert selfit_recommend.content_pool().outfits == [{"id": "stable-v1"}]


def test_auto_loader_prefers_incremental_but_v1_can_still_be_forced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    v1 = tmp_path / "v1.json"
    incremental = tmp_path / "incremental.json"
    v1.write_text(json.dumps({"outfits": [{"id": "stable-v1"}]}), encoding="utf-8")
    pool = build_incremental_pool()
    incremental.write_text(json.dumps(pool), encoding="utf-8")
    monkeypatch.setattr(selfit_recommend, "BUNDLED_CONTENT_POOL_PATH", v1)
    monkeypatch.setattr(selfit_recommend, "BUNDLED_CONTENT_POOL_V2_PATH", tmp_path / "missing-full-v2.json")
    monkeypatch.setattr(selfit_recommend, "BUNDLED_CONTENT_POOL_V2_INCREMENTAL_PATH", incremental)
    monkeypatch.setattr(selfit_recommend, "DEFAULT_CONTENT_POOL_PATH", tmp_path / "missing.json")
    monkeypatch.delenv("SELFIT_CONTENT_POOL_PATH", raising=False)

    monkeypatch.setenv("SELFIT_CONTENT_POOL_VERSION", "auto")
    selfit_recommend.reset_content_pool_cache()
    assert any(item["id"] == "outfit_ease_master_16" for item in selfit_recommend.content_pool().outfits)

    monkeypatch.setenv("SELFIT_CONTENT_POOL_VERSION", "v1")
    selfit_recommend.reset_content_pool_cache()
    assert selfit_recommend.content_pool().outfits == [{"id": "stable-v1"}]


def test_incremental_outfit_is_available_to_main_app_and_tryon() -> None:
    selfit_recommend.reset_content_pool_cache()
    catalog = closet._published_catalog_outfits()
    outfit = next(item for item in catalog if item["outfit_id"] == "outfit_ease_master_16")

    assert outfit["source"] == "published_content_v2"
    assert outfit["tryon_ready"] is True
    assert [item["category"] for item in outfit["items"]] == ["top", "skirt", "shoes", "bag"]
    assert closet._closet_disk_path(outfit["cover_path"]).exists()
    plan, resolved = closet.outfit_as_tryon_plan(outfit["outfit_id"])
    assert resolved["content_version"] == "2026.09-v2-published1"
    assert [item["slot"] for item in plan["items"]] == ["top", "skirt", "shoes", "bag"]
    recommendation = closet._score_outfit_for_persona(
        outfit,
        {"typeId": "ease", "metadata": {"code": "EASE", "name": "松弛讲究"}},
    )
    assert recommendation["score"] >= 100
    assert recommendation["primary_reason"] == "呼应你的人格风格"


def test_context_and_main_item_diversity_are_applied(tmp_path: Path) -> None:
    outfits = []
    for index in range(8):
        outfits.append({
            "id": f"outfit-{index}", "primary_persona": "MUTE", "secondary_personas": [],
            "scene_tags": ["通勤" if index < 6 else "旅行"], "season_tags": ["秋"], "weather_tags": ["晴"],
            "visible_slots": ["top", "bottom"], "garment_ids": ["same-hero" if index < 4 else f"hero-{index}", f"bottom-{index}"],
            "slot_roles": {"same-hero" if index < 4 else f"hero-{index}": "hero"},
            "structure": {}, "color": {}, "assets": {"image_url": f"/{index}.webp"},
        })
    path = tmp_path / "pool.json"
    path.write_text(json.dumps({"outfits": outfits}), encoding="utf-8")
    result = recommend_outfits(
        ContentPool(path), primary="MUTE", secondary=None, regional_style=None, primary_region="无倾向",
        compatible_regions=(), body_shape=None, rectangle_branch=None, skin=None, top_n=6,
        scene="通勤", season="秋", weather="晴", visible_slots=("top",), recently_exposed_ids=("outfit-0",),
    )
    assert sum(item["garment_ids"][0] == "same-hero" for item in result) <= 2
    assert all(item["recommendation_reasons"] for item in result)


def test_schema_exposes_production_and_recipe_contracts() -> None:
    schema = _load(SCHEMA)
    garment = schema["$defs"]["garment"]["properties"]
    outfit = schema["$defs"]["outfit"]["properties"]
    assert "production" in garment
    assert {"parent_outfit_id", "recipe_version", "slot_roles", "replacement_rules"} <= set(outfit)
