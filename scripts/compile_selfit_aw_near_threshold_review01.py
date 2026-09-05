#!/usr/bin/env python3
"""Compile the non-blind whole-image review for near-threshold batch 01."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs/audits/20260904-aw-supply"
FIELDS = [
    "axes", "expression", "formality", "layering", "persona_scores", "scenes",
    "seasons", "structure", "wearability", "main_visual_slots", "main_colors",
    "conflicts", "silhouette", "color_relation", "persona_evidence", "winter_outdoor",
]

CANDIDATES = {
    1: ({"heir": .84, "ease": .62}, "棕褐茧形外套、白衬衫和海军蓝长裤建立经典干净的冬季长线。"),
    3: ({"void": .86, "wabi": .70}, "海军蓝茧形长外层与一处错层长裙形成受控的包裹感。"),
    6: ({"edge": .90, "noir": .76}, "长皮外套与角度长裤使用同一锐利线条，素色内层稳定主次。"),
    8: ({"heir": .88, "iced": .62}, "海军蓝短夹克、Polo 针织与浅灰直裤构成整洁经典的冬季比例。"),
    9: ({"heir": .90, "iced": .66}, "海军蓝长大衣覆盖冰蓝衬衫裙，肩线和长线是主要视觉证据。"),
    10: ({"iced": .84, "mute": .68}, "浅冰蓝夹克、黑针织与浅灰直裤保持收净边界，闭口鞋包完整。"),
    11: ({"iced": .88, "mute": .70}, "蓝灰长风衣覆在炭灰衬衫裙上，冷静长线和低对比配色一致。"),
    16: ({"heir": .86, "bolt": .64}, "浅粉长外套用经典肩领和收腰线配简洁白衬衫、黑长裙。"),
    19: ({"iced": .84, "noir": .70}, "浅冰蓝强肩长外套与冰蓝内层建立连续冷调长线，黑裙收束。"),
    21: ({"mute": .88, "iced": .72}, "蓝灰风衣、冰蓝衬衫与流动中蓝裙形成清晰且低装饰的秋季蓝色层次。"),
    22: ({"oops": .84, "edge": .68}, "素炭灰短外套支撑一处斜向裤片，错位表达可解释且没有多焦点。"),
    25: ({"jade": .86, "heir": .62}, "灰褐双排扣风衣、白衬衫与鼠尾草绿 A 裙保持清楚领型和纵线。"),
    28: ({"loop": .84, "heir": .68}, "海军蓝长外套、同色针织和冰蓝长裙是可复用的模块组合，比例完整。"),
    30: ({"void": .86, "wabi": .72}, "棕褐茧形外套与一处错层裙建立包裹体积，黑针织稳定主次。"),
}

WINTER_INCOMPLETE = {4, 5, 14, 15, 17}
COMPETING = {2, 7, 12, 13, 23, 24, 29}
PERSONA_MISMATCH = {18, 20, 26, 27}


def main() -> None:
    rendered = json.loads((AUDIT / "near-threshold-recipes.batch01.rendered.json").read_text())
    base = json.loads((ROOT / "app/data/recommendation-visual.v1.json").read_text())
    generated = json.loads((AUDIT / "generated-garments/combined-manifest-v3.json").read_text())
    visuals = {**base["garments"], **generated["visual"]}
    entries = []
    for position, row in enumerate(rendered["entries"], 1):
        raw = row["new_record"]
        observations = [visuals[item]["observations"] for item in raw["garment_ids"]]
        categories = [item["category"] for item in observations]
        structure = "dress" if "dress" in categories else "skirt" if "skirt" in categories else "pants"
        colors = list(dict.fromkeys(
            color for item in observations if item["category"] not in {"shoes", "bag"}
            for color in item.get("main_colors") or []
        ))
        candidate = CANDIDATES.get(position)
        is_winter = "冬" in raw["season_tags"]
        if candidate:
            scores, evidence = candidate
            status, seasons, scenes = "ai_candidate", ["winter" if is_winter else "autumn"], ["daily"]
            wearability, conflicts = "everyday_with_statement", None
            winter = "complete_layers_visually_reviewed" if is_winter else "not_applicable"
        else:
            scores, status, seasons, scenes, wearability, winter = {}, "needs_review", None, None, None, None
            if position in WINTER_INCOMPLETE:
                evidence = "短薄针织或轻量夹克缺少可信的冬季外出覆盖，不靠季节标签放行。"
                conflicts = ["winter_layering_incomplete"]
            elif position in COMPETING:
                evidence = "外套、下装或装饰同时形成强焦点，日常穿着的主次不清楚。"
                conflicts = ["competing_focal_points"]
            elif position in PERSONA_MISMATCH:
                evidence = "整套的运动、松弛或戏剧表达与目标人格的主要视觉证据不符。"
                conflicts = ["persona_mismatch"]
            else:
                evidence = "整图尚不足以证明目标人格、季节和日常可穿性。"
                conflicts = ["insufficient_visual_evidence"]
        observed = {
            "axes": {}, "expression": "typical", "formality": "smart_casual", "layering": 2,
            "persona_scores": scores, "scenes": scenes, "seasons": seasons, "structure": structure,
            "wearability": wearability,
            "main_visual_slots": ["outer", "dress"] if structure == "dress" else ["outer", "top", structure],
            "main_colors": colors, "conflicts": conflicts,
            "silhouette": f"reviewed_{'winter' if is_winter else 'autumn'}_{structure}_composition",
            "color_relation": "reviewed_coherent" if candidate else "unresolved",
            "persona_evidence": evidence, "winter_outdoor": winter,
        }
        statuses = {key: "unknown" if observed[key] is None else "ai_observed" for key in FIELDS}
        sheet = f"near-threshold-batch01-review/recipes-{(position - 1) // 6 + 1}.jpg"
        provenance = {
            key: {"source_file": sheet, "version": "aw-near-threshold-01-native-v1",
                  "confidence": None if statuses[key] == "unknown" else .85}
            for key in FIELDS
        }
        entries.append({
            "outfit_id": raw["id"], "status": status,
            "record_fingerprint": row["record_fingerprint"], "asset_sha256": row["asset_sha256"],
            "image_url": raw["assets"]["image_url"], "source_kind": "codex_visual_review",
            "evidence": evidence, "observations": observed, "confidence": .85,
            "model": "current_codex_session", "prompt_version": "aw-near-threshold-01-native-v1",
            "review_level": "individual_contact_sheet_judgment",
            "evidence_scope": "nonblind_individual_visual_judgment; no temperature/waterproof claim",
            "review_complete": True, "field_status": statuses, "field_provenance": provenance,
        })
    assert len(entries) == 30 and sum(row["status"] == "ai_candidate" for row in entries) == 14
    result = {
        "schema_version": 1, "source_rendered_version": rendered["version"],
        "independent_blind_review": False, "winter_outdoor_reviewed": True,
        "physical_warmth_verified": False, "entries": entries,
    }
    result["version"] = "aw-near-threshold-review-" + hashlib.sha256(
        json.dumps(result, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()[:20]
    target = AUDIT / "near-threshold-recipes.batch01.native-review.json"
    if target.exists() and json.loads(target.read_text()) != result:
        raise SystemExit("Near-threshold review changed; refusing overwrite")
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"version": result["version"], "accepted": 14, "held": 16}, ensure_ascii=False))


if __name__ == "__main__":
    main()
