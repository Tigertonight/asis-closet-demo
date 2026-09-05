"""Render new recipes around reviewed unused main garments as immutable drafts."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.closet import selfit_content_pool
from app.outfit_layout import render_outfit_preview, outfit_preview_url
from app.recommendation_visual import asset_sha, load_visual, valid_observation
from app.selfit_content_quality import record_fingerprint


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("spec", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Rendered recomposition exists; refusing overwrite")
    spec = json.loads(args.spec.read_text())
    assert len(spec["recipes"]) <= 48
    idle = json.loads((ROOT / "docs/audits/20260904-aw-supply/idle-main-review/native-review.json").read_text())
    assert spec["source_idle_review"] == idle["version"]
    reusable = {r["token"] for r in idle["entries"] if r["decision"] == "direct_autumn_recompose"}
    visual = load_visual()
    pool = selfit_content_pool()
    garments = {r["id"]: r for r in pool.garments}
    token_to_id = {r["token"]: gid for gid, r in visual["garments"].items()}
    results = []
    for index, recipe in enumerate(spec["recipes"], 1):
        assert recipe["hero"] in reusable and recipe["hero"] in recipe["items"]
        ids = [token_to_id[token] for token in recipe["items"]]
        assert len(ids) == len(set(ids))
        items = [garments[gid] for gid in ids]
        assert all(valid_observation(g, visual["garments"][g["id"]], g["assets"]["image_url"], "garments") for g in items)
        url = outfit_preview_url(items)
        target = ROOT / "app" / url.lstrip("/")
        if target.exists():
            qa = json.loads(target.with_suffix(".qa.json").read_text())
            assert {p["garment_id"] for p in qa["placements"]} == set(ids)
        else:
            qa = render_outfit_preview(items, ROOT)
        outfit_id = f"outfit_{recipe['persona'].lower()}_{spec['batch_id']}_{index:02d}"
        roles = {gid: ("hero" if gid == token_to_id[recipe["hero"]] else "support") for gid in ids}
        record = {
            "id": outfit_id, "kind": "master", "parent_outfit_id": None,
            "recipe_version": spec["batch_id"], "title": f"{recipe['persona']} 秋季日常重组 {index:02d}",
            "description": recipe["intent"], "primary_persona": recipe["persona"],
            "secondary_personas": [], "persona_affinity": {}, "regional_styles": [], "body_types": [],
            "scene_tags": ["日常"], "season_tags": ["秋"], "weather_tags": [],
            "presentation": ["feminine"], "intensity": "entry", "formality": 3,
            "garment_ids": ids, "visible_slots": [g["category"] for g in items],
            "layer_graph": [], "slot_roles": roles,
            "replacement_rules": {"same_slot": True, "match_season": True, "match_scene": True,
                                  "max_formality_delta": 1, "preserve_color_harmony": True},
            "structure": {"visual_weight": "未判断", "waistline": "未判断", "tummy_space": "未判断", "line_direction": "未判断"},
            "color": {"temperature": "未判断", "lightness": "未判断", "saturation": "未判断", "harmony": "未判断", "palette": []},
            "assets": {"image_url": qa["image_url"], "width": 1200, "height": 1500,
                       "rights_status": "owned", "layout_version": qa["layout_version"]},
            "annotation": {"status": "draft", "source": "designer_recomposition", "confidence": None,
                           "review_notes": ["season and persona are design targets pending native review"]}
        }
        results.append({"hero": recipe["hero"], "new_record": record,
                        "record_fingerprint": record_fingerprint(record),
                        "asset_sha256": asset_sha(record["assets"]["image_url"]),
                        "layout_qa": qa, "status": "pending_native_review", "review": None})
    output = {"schema_version": 1, "batch_id": spec["batch_id"], "source_idle_review": idle["version"],
              "source_visual_version": visual["version"], "entries": results}
    output["version"] = "aw-recompose-rendered-" + digest(output)[:20]
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"version": output["version"], "recipes": len(results)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
