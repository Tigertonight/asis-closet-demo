"""Render bounded, explicitly designed AW recipes as immutable review drafts."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.closet import selfit_content_pool
from app.outfit_layout import outfit_preview_url, render_outfit_preview
from app.recommendation_visual import asset_sha, load_visual, valid_observation
from app.selfit_content_quality import record_fingerprint
from app.recommendation_diversity import MAIN_SLOTS, main_recipe_signature


def digest(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("spec", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Rendered recipe batch exists; refusing overwrite")
    spec = json.loads(args.spec.read_text())
    assert spec["schema_version"] == 1 and len(spec["recipes"]) <= 48
    assert len(spec.get("new_garments") or []) <= 24

    visual = deepcopy(load_visual())
    pool = selfit_content_pool()
    assert spec["source_visual_version"] == visual["version"]
    garments = {row["id"]: row for row in pool.garments}
    token_to_id = {row["token"]: gid for gid, row in visual["garments"].items()}
    if spec.get("new_garment_manifest"):
        manifest_path = (args.spec.parent / spec["new_garment_manifest"]).resolve()
        if not manifest_path.is_relative_to(ROOT / "docs/audits"):
            raise ValueError("New garment manifest must stay in the internal audit tree")
        manifest = json.loads(manifest_path.read_text())
        if (manifest.get("schema_version") != 1 or manifest.get("production_approved") is not False
                or manifest.get("version") != spec.get("new_garment_version")):
            raise ValueError("Invalid or stale new garment manifest")
        if len(manifest.get("garments") or []) > 24:
            raise ValueError("Generated garment batch exceeds the review cap")
        for row in manifest["garments"]:
            observation = manifest.get("visual", {}).get(row["id"])
            image_url = row["assets"]["image_url"]
            if row["id"] in garments or not valid_observation(row, observation, image_url, "garments"):
                raise ValueError(f"Invalid generated garment candidate: {row['id']}")
            token = observation["token"]
            if token in token_to_id:
                raise ValueError(f"Duplicate generated garment token: {token}")
            garments[row["id"]] = row
            visual["garments"][row["id"]] = observation
            token_to_id[token] = row["id"]
    results = []
    for index, recipe in enumerate(spec["recipes"], 1):
        assert recipe["season"] in {"autumn", "winter"}
        ids = [token_to_id[token] for token in recipe["items"]]
        assert len(ids) == len(set(ids))
        items = [garments[gid] for gid in ids]
        assert all(valid_observation(item, visual["garments"][item["id"]],
                                     item["assets"]["image_url"], "garments") for item in items)
        categories = [item["category"] for item in items]
        if recipe["season"] == "winter":
            assert "outer" in categories and "shoes" in categories
            assert ("dress" in categories) ^ ("top" in categories and bool({"bottom", "skirt"} & set(categories)))
        url = outfit_preview_url(items)
        target = ROOT / "app" / url.lstrip("/")
        if target.exists():
            qa = json.loads(target.with_suffix(".qa.json").read_text())
            assert {placement["garment_id"] for placement in qa["placements"]} == set(ids)
        else:
            qa = render_outfit_preview(items, ROOT)
        outfit_id = f"outfit_{recipe['persona'].lower()}_{spec['batch_id']}_{index:02d}"
        hero_id = token_to_id[recipe["hero"]]
        if hero_id not in ids or garments[hero_id]["category"] not in MAIN_SLOTS:
            raise ValueError("Recipe hero must be one of its main garments")
        signature = main_recipe_signature({"items": [
            {"item_id": item["id"], "category": item["category"]} for item in items
        ]})
        parent_id = "main-recipe-" + digest(signature)[:24]
        record = {
            "id": outfit_id, "kind": "master", "parent_outfit_id": parent_id,
            "recipe_version": spec["batch_id"],
            "title": f"{recipe['persona']} {recipe['season']} 日常设计 {index:02d}",
            "description": recipe["intent"], "primary_persona": recipe["persona"],
            "secondary_personas": [], "persona_affinity": {}, "regional_styles": [], "body_types": [],
            "scene_tags": ["日常"], "season_tags": ["冬"] if recipe["season"] == "winter" else ["秋"],
            "weather_tags": [], "presentation": ["feminine"], "intensity": recipe.get("expression", "entry"),
            "formality": 3, "garment_ids": ids, "visible_slots": categories, "layer_graph": [],
            "slot_roles": {gid: ("hero" if gid == hero_id else "support") for gid in ids},
            "replacement_rules": {"same_slot": True, "match_season": True, "match_scene": True,
                                  "max_formality_delta": 1, "preserve_color_harmony": True},
            "structure": {"visual_weight": "未判断", "waistline": "未判断", "tummy_space": "未判断", "line_direction": "未判断"},
            "color": {"temperature": "未判断", "lightness": "未判断", "saturation": "未判断", "harmony": "未判断", "palette": []},
            "assets": {"image_url": qa["image_url"], "width": 1200, "height": 1500,
                       "rights_status": "owned", "layout_version": qa["layout_version"]},
            "annotation": {"status": "draft", "source": "designer_recomposition", "confidence": None,
                           "review_notes": ["season, palette and persona are design targets pending whole-image review"]},
        }
        results.append({
            "target_palette": recipe["palette"], "hero": recipe["hero"], "new_record": record,
            "record_fingerprint": record_fingerprint(record), "asset_sha256": asset_sha(record["assets"]["image_url"]),
            "layout_qa": qa, "status": "pending_native_review", "review": None,
        })
    output = {
        "schema_version": 1, "batch_id": spec["batch_id"], "source_visual_version": visual["version"],
        "entries": results, "production_approved": False,
    }
    output["version"] = "aw-designed-rendered-" + digest(output)[:20]
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"version": output["version"], "recipes": len(results)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
