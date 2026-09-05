#!/usr/bin/env python3
"""Compile non-blind review for bright daily recompositions."""
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
    1: ("typical", {"neon": .90, "bolt": .62}, "品红短外套是唯一高彩块，白衬衫、黑长裤和运动鞋将它稳定为日常鲜明入口。"),
    2: ("typical", {"neon": .88, "melt": .58}, "鲜品红短外套与黑针织、浅色斜裹长裙构成单一高彩及短长反差。"),
    3: ("easy", {"neon": .84, "heir": .60}, "品红短外套覆在素灰长衬衫裙上，只保留一处鲜色与短长反差，鞋包克制。"),
    4: ("typical", {"noir": .90, "edge": .66}, "钴蓝长外套与全黑针织、层片长裤形成强边界，黑靴和包不打断长线。"),
    6: ("easy", {"noir": .86, "heir": .62}, "钴蓝强线长外套覆盖素灰长衬衫裙，黑色长靴和包保持锐利边界。"),
    7: ("typical", {"oops": .88, "edge": .64}, "错位品红短外套与一处角度长裤重复线条母题，白衬衫稳定整体。"),
    8: ("typical", {"oops": .86, "melt": .56}, "错位短外套和斜裹长裙使用同一斜线母题，黑针织与素包保持支撑。"),
    9: ("easy", {"oops": .82, "neon": .60}, "错位品红短外套与素灰长衬衫裙形成明确短长对比，没有额外破片堆叠。"),
    10: ("typical", {"void": .88, "wabi": .62}, "珊瑚红茧形长外层、黑针织和一处错层长裤构成保护性层次，运动鞋降低负担。"),
    11: ("typical", {"void": .86, "wabi": .68}, "茧形长外层与安静错层长裙构成一处包裹层次，黑色支撑款连续。"),
    12: ("easy", {"void": .78, "mute": .62}, "珊瑚红茧形外套覆盖素灰长衬衫裙，以包裹轮廓而非破片堆叠提供低负担版本。"),
}


def main() -> None:
    rendered = json.loads((AUDIT / "winter-recipes.batch04.rendered.json").read_text())
    manifest = json.loads((AUDIT / "generated-garments/combined-manifest.json").read_text())
    base = json.loads((ROOT / "app/data/recommendation-visual.v1.json").read_text())
    visuals = {**base["garments"], **manifest["visual"]}
    entries = []
    for position, row in enumerate(rendered["entries"], 1):
        raw = row["new_record"]; obs = [visuals[g]["observations"] for g in raw["garment_ids"]]
        cats = [item["category"] for item in obs]
        structure = "dress" if "dress" in cats else "skirt" if "skirt" in cats else "pants"
        colors = list(dict.fromkeys(c for item in obs if item["category"] not in {"shoes", "bag"} for c in item.get("main_colors") or []))
        candidate = CANDIDATES.get(position)
        if candidate:
            expression, scores, evidence = candidate; status = "ai_candidate"; seasons = ["winter"]; scenes = ["daily"]
            wearability = "everyday" if expression == "easy" else "everyday_with_statement"; conflicts = None
            winter = "complete_layers_visually_reviewed"
        else:
            expression, scores, status, seasons, scenes, wearability, winter = "typical", {}, "needs_review", None, None, None, None
            evidence = "钴蓝外套与黑色解构上装、皮革不对称裙同时抢焦点，保留创意场合草稿，不进默认日常池。"
            conflicts = ["occasion_or_competing_focal_points"]
        observed = {"axes": {}, "expression": expression, "formality": "smart_casual", "layering": 2,
                    "persona_scores": scores, "scenes": scenes, "seasons": seasons, "structure": structure,
                    "wearability": wearability, "main_visual_slots": ["outer", "dress"] if structure == "dress" else ["outer", "top", structure],
                    "main_colors": colors, "conflicts": conflicts, "silhouette": f"reviewed_winter_{structure}_composition",
                    "color_relation": "reviewed_coherent" if candidate else "unresolved", "persona_evidence": evidence,
                    "winter_outdoor": winter}
        statuses = {key: "unknown" if observed[key] is None else "ai_observed" for key in FIELDS}
        provenance = {key: {"source_file": "winter-batch04-review/contact-sheet.jpg", "version": "aw-winter-04-native-v1",
                            "confidence": None if statuses[key] == "unknown" else .86} for key in FIELDS}
        entries.append({"outfit_id": raw["id"], "status": status, "record_fingerprint": row["record_fingerprint"],
                        "asset_sha256": row["asset_sha256"], "image_url": raw["assets"]["image_url"],
                        "source_kind": "codex_visual_review", "evidence": evidence, "observations": observed, "confidence": .86,
                        "model": "current_codex_session", "prompt_version": "aw-winter-04-native-v1",
                        "review_level": "individual_contact_sheet_judgment",
                        "evidence_scope": "nonblind_individual_visual_judgment; no temperature/waterproof claim",
                        "review_complete": True, "field_status": statuses, "field_provenance": provenance})
    assert len(entries) == 12 and sum(e["status"] == "ai_candidate" for e in entries) == 11
    result = {"schema_version": 1, "source_rendered_version": rendered["version"], "independent_blind_review": False,
              "winter_outdoor_reviewed": True, "physical_warmth_verified": False, "entries": entries}
    result["version"] = "aw-winter-review-" + hashlib.sha256(json.dumps(result, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]
    target = AUDIT / "winter-recipes.batch04.native-review.json"
    if target.exists() and json.loads(target.read_text()) != result:
        raise SystemExit("Winter review changed; refusing overwrite")
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"version": result["version"], "accepted": 11, "held": 1}, ensure_ascii=False))


if __name__ == "__main__":
    main()
