from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from app.selfit_recommend import ContentPool, recommend_outfits
from app.selfit_persona import PERSONAS
from scripts.migrate_selfit_content_pool_v2 import OUTPUT_POOL, build
from scripts.build_selfit_imagegen_queue import build as build_imagegen_queue
from scripts.prepare_selfit_garment_asset import prepare


ROOT = Path(__file__).resolve().parents[1]
PROMPTS = ROOT / "app/static/selfit/data/content-generation-prompts.v1.json"
CAPSULE = ROOT / "app/static/selfit/data/capsules/mute-01.json"


def test_generation_prompt_catalog_covers_all_personas_and_asset_modes() -> None:
    data = json.loads(PROMPTS.read_text(encoding="utf-8"))

    assert set(data["personas"]) == set(PERSONAS)
    assert set(data["assetTypes"]) == {"garment_cutout", "outfit_flatlay", "tryon_reference"}
    assert "genuinely transparent background" in data["assetTypes"]["garment_cutout"]["prompt"]
    assert "no person, mannequin, hanger" in data["assetTypes"]["garment_cutout"]["prompt"]
    jobs = build_imagegen_queue()
    assert len(jobs) == 80
    assert all(sum(job["persona"] == code for job in jobs) == 5 for code in PERSONAS)


def test_v2_migration_keeps_legacy_pool_and_adds_generated_capsule() -> None:
    pool, audit = build()

    assert pool["schemaVersion"] == "2.0"
    assert pool["status"] == "draft"
    assert len(pool["outfits"]) == 157
    assert len(pool["garments"]) == 4
    assert pool["outfits"][-1]["id"] == "outfit_mute_capsule_01"
    assert all(item["assets"]["alpha_verified"] for item in pool["garments"])
    assert audit["globalCoverage"]["garment_ids"] == 1
    assert audit["publishBlockers"]


def test_generated_cutouts_and_flatlay_have_expected_asset_properties(tmp_path: Path) -> None:
    capsule = json.loads(CAPSULE.read_text(encoding="utf-8"))
    for garment in capsule["garments"]:
        path = ROOT / "app" / garment["assets"]["image_url"].lstrip("/")
        image = Image.open(path).convert("RGBA")
        alpha = image.getchannel("A")
        assert image.size == (1200, 1200)
        assert alpha.getextrema() == (0, 255)
        assert alpha.getbbox() is not None

    outfit_path = ROOT / "app" / capsule["outfit"]["assets"]["image_url"].lstrip("/")
    assert Image.open(outfit_path).size == (1200, 1500)

    source = ROOT / "app/static/selfit/assets/content_v2/mute/garments/mute-tote-taupe-raw-v1.png"
    result = prepare(source, tmp_path / "prepared.png")
    assert result["passed"] is True
    assert min(result["margins"].values()) >= 0.095


def test_v2_draft_is_compatible_with_existing_recommendation_engine() -> None:
    pool = ContentPool(OUTPUT_POOL)
    outfits = recommend_outfits(
        pool,
        primary="MUTE",
        secondary="ICED",
        regional_style="韩系",
        primary_region="无倾向",
        compatible_regions=("日系", "韩系"),
        body_shape="矩型",
        rectangle_branch=None,
        skin="冷白肤",
        top_n=10,
    )

    assert len(outfits) == 10
    # Unreviewed generated capsules remain in the archive, not in production
    # recommendations; the migrated V1 baseline still provides ten results.
    assert not any(item["id"] == "outfit_mute_capsule_01" for item in outfits)
    assert any(item["id"] == "outfit_mute_capsule_01" for item in pool.all_outfits)
