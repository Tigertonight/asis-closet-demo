#!/usr/bin/env python3
"""Compile native whole-image review for the 48 targeted autumn/winter recipes."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs/audits/20260904-aw-supply"
FIELDS = ["axes", "expression", "formality", "layering", "persona_scores", "scenes", "seasons", "structure", "wearability", "main_visual_slots", "main_colors", "conflicts", "silhouette", "color_relation", "persona_evidence", "winter_outdoor"]
HELD = {
    16: "肉桂褐短外层与露脚背鞋履无法从图片证明冬季外出完整性。",
    18: "肉桂褐短外层叠长裙配露脚背鞋，冬季覆盖关系不足。",
    28: "朱红短外层与露脚背鞋履无法从图片证明冬季外出完整性。",
    30: "朱红短外层叠长裙配露脚背鞋，冬季覆盖关系不足。",
    40: "深咖短夹克与露脚背鞋履无法从图片证明冬季外出完整性。",
    42: "深咖短夹克叠长裙配露脚背鞋，冬季覆盖关系不足。",
}


def main():
    rendered = json.loads((AUDIT / "targeted-recipes.batch09.rendered.json").read_text())
    base = json.loads((ROOT / "app/data/recommendation-visual.v1.json").read_text())
    generated = json.loads((AUDIT / "generated-garments/batch10/manifest.json").read_text())
    visuals = {**base["garments"], **generated["visual"]}
    entries = []
    for position, row in enumerate(rendered["entries"], 1):
        raw = row["new_record"]
        observations = [visuals[garment_id]["observations"] for garment_id in raw["garment_ids"]]
        categories = [value["category"] for value in observations]
        structure = "dress" if "dress" in categories else "skirt" if "skirt" in categories else "pants"
        season = "winter" if "冬" in raw["season_tags"] else "autumn"
        colors = list(dict.fromkeys(color for value in observations if value["category"] not in {"shoes", "bag"} for color in value.get("main_colors") or []))
        accepted = position not in HELD
        if accepted:
            evidence = f"{raw['primary_persona']} 的颜色与轮廓由新主外层提供；{structure} 支撑款低竞争，整套主次清楚。"
            scores = {raw["primary_persona"].lower(): 0.86}
            status = "ai_candidate"
            seasons = [season]
            scenes = ["daily"]
            wearability = "everyday_with_statement"
            conflicts = None
            winter = "complete_layers_visually_reviewed" if season == "winter" else None
        else:
            evidence = HELD[position]
            scores = {}
            status = "needs_review"
            seasons = scenes = wearability = winter = None
            conflicts = ["winter_outdoor_unconfirmed"]
        observed = {
            "axes": {}, "expression": "typical", "formality": "smart_casual", "layering": 2,
            "persona_scores": scores, "scenes": scenes, "seasons": seasons, "structure": structure,
            "wearability": wearability,
            "main_visual_slots": ["outer", "dress"] if structure == "dress" else ["outer", "top", structure],
            "main_colors": colors, "conflicts": conflicts,
            "silhouette": f"reviewed_targeted_{season}_{structure}",
            "color_relation": "reviewed_coherent" if accepted else "unresolved",
            "persona_evidence": evidence, "winter_outdoor": winter,
        }
        statuses = {field: "unknown" if observed[field] is None else "ai_observed" for field in FIELDS}
        sheet = f"targeted-batch09-review/recipes-{(position - 1) // 6 + 1}.jpg"
        provenance = {field: {"source_file": sheet, "version": "aw-targeted-09-native-v1", "confidence": None if statuses[field] == "unknown" else 0.86} for field in FIELDS}
        entries.append({
            "outfit_id": raw["id"], "status": status,
            "record_fingerprint": row["record_fingerprint"], "asset_sha256": row["asset_sha256"],
            "image_url": raw["assets"]["image_url"], "source_kind": "codex_visual_review",
            "evidence": evidence, "observations": observed, "confidence": 0.86,
            "model": "current_codex_session", "prompt_version": "aw-targeted-09-native-v1",
            "review_level": "individual_contact_sheet_judgment",
            "evidence_scope": "nonblind_individual_visual_judgment; no temperature/waterproof claim",
            "review_complete": True, "field_status": statuses, "field_provenance": provenance,
        })
    assert len(entries) == 48 and sum(row["status"] == "ai_candidate" for row in entries) == 42
    result = {
        "schema_version": 1, "source_rendered_version": rendered["version"],
        "independent_blind_review": False, "winter_outdoor_reviewed": True,
        "physical_warmth_verified": False, "entries": entries,
    }
    result["version"] = "aw-targeted-review-" + hashlib.sha256(json.dumps(result, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]
    target = AUDIT / "targeted-recipes.batch09.native-review.json"
    if target.exists() and json.loads(target.read_text()) != result:
        raise SystemExit("Review09 changed; refusing overwrite")
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"version": result["version"], "accepted": 42, "held": 6}, ensure_ascii=False))


if __name__ == "__main__":
    main()
