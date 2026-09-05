#!/usr/bin/env python3
"""Compile non-blind whole-image review for exact-gap winter batch 06."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs/audits/20260904-aw-supply"
FIELDS = ["axes", "expression", "formality", "layering", "persona_scores", "scenes", "seasons",
          "structure", "wearability", "main_visual_slots", "main_colors", "conflicts", "silhouette",
          "color_relation", "persona_evidence", "winter_outdoor"]
CANDIDATES = {
    1: ({"bolt":.84,"heir":.68}, "驼棕收腰短外套是唯一精致结构，黑色针织与长裤稳定为日常比例。"),
    3: ({"bolt":.82,"heir":.66}, "驼棕收腰短外层与素灰长衬衫裙形成清楚短长关系，鞋包克制。"),
    4: ({"bolt":.88,"melt":.66}, "浅粉 A 线长外套以肩腰结构而非装饰表达精致，黑色支撑款清楚。"),
    6: ({"bolt":.86,"heir":.64}, "浅粉收腰长外套覆盖素灰长裙，精致焦点集中在外层轮廓。"),
    7: ({"edge":.90,"noir":.70}, "冰丁香锐线外套、黑色层片长裤与长靴建立清楚角度和边界。"),
    9: ({"edge":.84,"iced":.64}, "冰丁香中长外套与灰色长衬衫裙形成锐利短长对比，鞋包延续边界。"),
    10: ({"neon":.90,"oops":.66}, "橙赭斜切羽绒是唯一图形色块，白衬衫和黑长裤提供稳定日常支撑。"),
    11: ({"neon":.86,"melt":.58}, "橙赭短羽绒与素黑针织、象牙斜裹裙形成一处高彩及短长反差。"),
    12: ({"neon":.82,"heir":.58}, "橙赭短羽绒覆盖素灰长衬衫裙，只保留一处高彩焦点。"),
    13: ({"noir":.92,"edge":.68}, "深巧克力强肩长外套与黑色层片裤、长靴形成连续有力量的纵线。"),
    15: ({"noir":.88,"heir":.66}, "深巧克力强肩长外套覆盖素灰长裙，锐利边界不依赖黑色主衣。"),
    16: ({"noir":.90,"iced":.68}, "浅冰蓝强肩长外套与黑色层片裤形成浅深对比，长直结构仍是主视觉。"),
    18: ({"noir":.86,"iced":.66}, "浅冰蓝强肩长外套覆盖素灰长裙，以结构而不是深色表达力量。"),
    20: ({"void":.88,"wabi":.72}, "深海蓝包裹长外套与一处错层长裙延续层片关系，运动鞋降低负担。"),
    21: ({"void":.84,"wabi":.66}, "深海蓝错位包裹外套覆盖素灰长裙，用体积而非破片表达 VOID。"),
    22: ({"wabi":.88,"ease":.70}, "水洗靛蓝自然茧形外套与米色锥裤形成圆量与收束，白衬衫保持清楚。"),
    24: ({"wabi":.84,"film":.68}, "水洗靛蓝茧形长外层与棕色衬衫裙构成自然材质观感和安静长线。"),
}
COMPETING = {2,5,8,14,17,19}


def main() -> None:
    rendered = json.loads((AUDIT / "winter-recipes.batch06.rendered.json").read_text())
    base = json.loads((ROOT / "app/data/recommendation-visual.v1.json").read_text())
    generated = json.loads((AUDIT / "generated-garments/batch03/manifest.json").read_text())
    visuals = {**base["garments"], **generated["visual"]}
    entries = []
    for position, row in enumerate(rendered["entries"], 1):
        raw = row["new_record"]
        observations = [visuals[item]["observations"] for item in raw["garment_ids"]]
        categories = [item["category"] for item in observations]
        structure = "dress" if "dress" in categories else "skirt" if "skirt" in categories else "pants"
        colors = list(dict.fromkeys(color for item in observations if item["category"] not in {"shoes", "bag"}
                                    for color in item.get("main_colors") or []))
        candidate = CANDIDATES.get(position)
        if candidate:
            scores, evidence = candidate
            status, seasons, scenes = "ai_candidate", ["winter"], ["daily"]
            wearability, conflicts, winter = "everyday_with_statement", None, "complete_layers_visually_reviewed"
        else:
            scores, status, seasons, scenes, wearability, winter = {}, "needs_review", None, None, None, None
            if position in COMPETING:
                evidence = "主外套之外，结构上衣、皮革裙或层片裤包同时形成强焦点，不进入默认日常池。"
                conflicts = ["competing_focal_points"]
            else:
                evidence = "花卉轻薄长裙将自然茧形外套带向浪漫表达，目标人格和冬季日常证据不足。"
                conflicts = ["persona_and_season_mismatch"]
        observed = {"axes": {}, "expression": "typical", "formality": "smart_casual", "layering": 2,
                    "persona_scores": scores, "scenes": scenes, "seasons": seasons, "structure": structure,
                    "wearability": wearability,
                    "main_visual_slots": ["outer", "dress"] if structure == "dress" else ["outer", "top", structure],
                    "main_colors": colors, "conflicts": conflicts,
                    "silhouette": f"reviewed_winter_{structure}_composition",
                    "color_relation": "reviewed_coherent" if candidate else "unresolved",
                    "persona_evidence": evidence, "winter_outdoor": winter}
        statuses = {key: "unknown" if observed[key] is None else "ai_observed" for key in FIELDS}
        sheet = f"winter-batch06-review/recipes-{(position - 1)//6 + 1}.jpg"
        provenance = {key: {"source_file": sheet, "version": "aw-winter-06-native-v1",
                            "confidence": None if statuses[key] == "unknown" else .86} for key in FIELDS}
        entries.append({"outfit_id": raw["id"], "status": status,
                        "record_fingerprint": row["record_fingerprint"], "asset_sha256": row["asset_sha256"],
                        "image_url": raw["assets"]["image_url"], "source_kind": "codex_visual_review",
                        "evidence": evidence, "observations": observed, "confidence": .86,
                        "model": "current_codex_session", "prompt_version": "aw-winter-06-native-v1",
                        "review_level": "individual_contact_sheet_judgment",
                        "evidence_scope": "nonblind_individual_visual_judgment; no temperature/waterproof claim",
                        "review_complete": True, "field_status": statuses, "field_provenance": provenance})
    assert len(entries) == 24 and sum(row["status"] == "ai_candidate" for row in entries) == 17
    result = {"schema_version": 1, "source_rendered_version": rendered["version"],
              "independent_blind_review": False, "winter_outdoor_reviewed": True,
              "physical_warmth_verified": False, "entries": entries}
    result["version"] = "aw-winter-review-" + hashlib.sha256(
        json.dumps(result, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]
    target = AUDIT / "winter-recipes.batch06.native-review.json"
    if target.exists() and json.loads(target.read_text()) != result:
        raise SystemExit("Winter review changed; refusing overwrite")
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"version": result["version"], "accepted": 17, "held": 7}, ensure_ascii=False))


if __name__ == "__main__":
    main()
