#!/usr/bin/env python3
"""Compile non-blind review for the second generated-garment recipe batch."""
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
    1: ("typical", {"bolt": .90, "edge": .62}, "品红短外套的锐肩与收腰是唯一戏剧点，白衬衫、黑长裤与踝靴将它稳定在日常比例。"),
    4: ("typical", {"void": .88, "wabi": .62}, "紫晶包裹长外套与深色针织、一处错层长裤形成保护性层次，运动鞋降低负担。"),
    5: ("typical", {"oops": .86, "edge": .60}, "错位包裹外套与斜裹长裙重复同一斜线母题，素色针织让解构可解释。"),
    6: ("typical", {"wabi": .82, "void": .68}, "紫色包裹长外套覆盖自然腰长衬衫裙，长靴与软包保持完整且低负担的冬日长线。"),
    7: ("easy", {"film": .88, "heir": .66}, "祖母绿圆领 A 形外套、浅花衬衫和浅色褶裤建立清楚复古比例，平底鞋保持日常。"),
    8: ("typical", {"jade": .86, "film": .60}, "祖母绿收腰外套与水墨内搭、黑色斜裁长裙构成克制纵线，线条母题连续。"),
    9: ("typical", {"bolt": .84, "heir": .72}, "祖母绿外套的锐肩、收腰和 A 形下摆构成精致主视觉，灰长裙和长靴不抢焦点。"),
    10: ("easy", {"mute": .88, "loop": .64}, "万寿菊黄是唯一高彩主色，无领长外套、白衬衫、灰直裤与黑鞋包保持清晰低装饰。"),
    11: ("typical", {"jade": .82, "film": .62}, "鲜黄长直外套与水墨内搭、黑长裙形成一明一暗的克制交叠，焦点明确。"),
    12: ("easy", {"film": .88, "wabi": .60}, "万寿菊黄长外套、棕色长衬衫裙和长靴形成暖色复古长线，软包不增加新焦点。"),
}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def main() -> None:
    rendered = json.loads((AUDIT / "winter-recipes.batch03.rendered.json").read_text())
    manifest = json.loads((AUDIT / "generated-garments/batch02/manifest.json").read_text())
    base = json.loads((ROOT / "app/data/recommendation-visual.v1.json").read_text())
    visuals = {**base["garments"], **manifest["visual"]}
    entries = []
    for position, row in enumerate(rendered["entries"], 1):
        raw = row["new_record"]
        item_obs = [visuals[gid]["observations"] for gid in raw["garment_ids"]]
        categories = [item["category"] for item in item_obs]
        structure = "dress" if "dress" in categories else "skirt" if "skirt" in categories else "pants"
        colors = list(dict.fromkeys(c for item in item_obs if item["category"] not in {"shoes", "bag"} for c in item.get("main_colors") or []))
        candidate = CANDIDATES.get(position)
        if candidate:
            expression, scores, evidence = candidate
            status, seasons, scenes = "ai_candidate", ["winter"], ["daily"]
            wearability = "everyday" if expression == "easy" else "everyday_with_statement"
            conflicts, winter = None, "complete_layers_visually_reviewed"
        else:
            expression, scores = "typical", {}
            status, seasons, scenes, wearability, winter = "needs_review", None, None, None, None
            evidence = "品红短外套与黑色解构上装、复杂裙装或戏剧长裙同时抢焦点，只保留场合/创意草稿。"
            conflicts = ["occasion_or_competing_focal_points"]
        observed = {"axes": {}, "expression": expression, "formality": "smart_casual", "layering": 2,
                    "persona_scores": scores, "scenes": scenes, "seasons": seasons, "structure": structure,
                    "wearability": wearability, "main_visual_slots": ["outer", "dress"] if structure == "dress" else ["outer", "top", structure],
                    "main_colors": colors, "conflicts": conflicts, "silhouette": f"reviewed_winter_{structure}_composition",
                    "color_relation": "reviewed_coherent" if candidate else "unresolved", "persona_evidence": evidence,
                    "winter_outdoor": winter}
        statuses = {key: "unknown" if observed[key] is None else "ai_observed" for key in FIELDS}
        provenance = {key: {"source_file": "winter-batch03-review/contact-sheet.jpg", "version": "aw-winter-03-native-v1",
                            "confidence": None if statuses[key] == "unknown" else .86} for key in FIELDS}
        entries.append({"outfit_id": raw["id"], "status": status, "record_fingerprint": row["record_fingerprint"],
                        "asset_sha256": row["asset_sha256"], "image_url": raw["assets"]["image_url"],
                        "source_kind": "codex_visual_review", "evidence": evidence, "observations": observed, "confidence": .86,
                        "model": "current_codex_session", "prompt_version": "aw-winter-03-native-v1",
                        "review_level": "individual_contact_sheet_judgment",
                        "evidence_scope": "nonblind_individual_visual_judgment; no temperature/waterproof claim",
                        "review_complete": True, "field_status": statuses, "field_provenance": provenance})
    assert len(entries) == 12 and sum(e["status"] == "ai_candidate" for e in entries) == 10
    result = {"schema_version": 1, "source_rendered_version": rendered["version"], "independent_blind_review": False,
              "winter_outdoor_reviewed": True, "physical_warmth_verified": False, "entries": entries}
    result["version"] = "aw-winter-review-" + digest(result)[:20]
    target = AUDIT / "winter-recipes.batch03.native-review.json"
    if target.exists() and json.loads(target.read_text()) != result:
        raise SystemExit("Winter review changed; refusing overwrite")
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"version": result["version"], "accepted": 10, "held": 2}, ensure_ascii=False))


if __name__ == "__main__":
    main()
