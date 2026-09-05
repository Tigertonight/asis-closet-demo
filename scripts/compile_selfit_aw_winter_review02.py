#!/usr/bin/env python3
"""Compile non-blind whole-image review for generated-coat winter recipes."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs/audits/20260904-aw-supply"
FIELDS = ["axes", "expression", "formality", "layering", "persona_scores", "scenes", "seasons",
          "structure", "wearability", "main_visual_slots", "main_colors", "conflicts", "silhouette",
          "color_relation", "persona_evidence", "winter_outdoor"]

# Three more theatrical dress/skirt combinations remain accessible as drafts but
# do not enter the default winter-daily candidate pool.
CANDIDATES = {
    1: ("easy", {"heir": .90, "mute": .66}, "勃艮第收腰长外套与白衬衫、黑长裤比例经典，封闭乐福鞋与低装饰包保持日常完成度。"),
    2: ("easy", {"mute": .90, "heir": .64}, "勃艮第主色鲜明，但内层、直裙和鞋包均为低装饰深色，焦点单一且纵线清楚。"),
    4: ("typical", {"iced": .90, "jade": .64}, "立领宝石青长外套与浅色内搭长裤形成收净纵线，踝靴和软包不增加新焦点。"),
    5: ("typical", {"jade": .86, "flou": .58}, "立领长外套和植物线条内搭、纵向抽褶长裙共享克制的东方线条，焦点可辨。"),
    7: ("typical", {"loop": .86, "ease": .58}, "鲜蓝长外套是唯一高彩块，素色针织、机能长裤与运动鞋构成可复用的模块组合。"),
    9: ("typical", {"iced": .88, "heir": .62}, "鲜蓝长外套覆盖浅蓝收腰长袖裙，低跟踝靴完成长线冬日外出关系。"),
    10: ("easy", {"ease": .88, "loop": .62}, "珊瑚红茧形外层配浅色长裤与运动鞋，内搭与下装仍有收束，没有宽上宽下失焦。"),
    11: ("typical", {"melt": .88, "flou": .60}, "珊瑚红圆线外层与柔软浅色分层裙呼应，黑色简洁内搭和鞋包控制甜美元素数量。"),
    12: ("easy", {"flou": .88, "ease": .64}, "珊瑚红长外层、奶油色长袖衬衫裙和平底鞋形成可日常出门的流动长线。"),
}


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def main() -> None:
    rendered = json.loads((AUDIT / "winter-recipes.batch02.rendered.json").read_text())
    manifest = json.loads((AUDIT / "generated-garments/batch01/manifest.json").read_text())
    base_visual = json.loads((ROOT / "app/data/recommendation-visual.v1.json").read_text())
    observations_by_id = {**base_visual["garments"], **manifest["visual"]}
    entries = []
    for position, row in enumerate(rendered["entries"], 1):
        raw = row["new_record"]
        item_observations = [observations_by_id[gid]["observations"] for gid in raw["garment_ids"]]
        categories = [item["category"] for item in item_observations]
        structure = "dress" if "dress" in categories else "skirt" if "skirt" in categories else "pants"
        colors = list(dict.fromkeys(color for item in item_observations if item["category"] not in {"shoes", "bag"}
                                    for color in (item.get("main_colors") or [])))
        candidate = CANDIDATES.get(position)
        if candidate:
            expression, scores, evidence = candidate
            status, seasons, scenes = "ai_candidate", ["winter"], ["daily"]
            wearability = "everyday" if expression == "easy" else "everyday_with_statement"
            conflicts, winter = None, "complete_layers_visually_reviewed"
        else:
            expression, scores = "typical", {}
            status, seasons, scenes, wearability, winter = "needs_review", None, None, None, None
            evidence = "外层完整，但黑色戏剧连衣裙或解构裙装与鲜色外套同时抢焦点，更适合场合/创意用途，不进默认冬季日常池。"
            conflicts = ["occasion_or_competing_focal_points"]
        observed = {
            "axes": {}, "expression": expression, "formality": "smart_casual", "layering": 2,
            "persona_scores": scores, "scenes": scenes, "seasons": seasons, "structure": structure,
            "wearability": wearability, "main_visual_slots": ["outer", "dress"] if structure == "dress" else ["outer", "top", structure],
            "main_colors": colors, "conflicts": conflicts, "silhouette": f"reviewed_winter_{structure}_composition",
            "color_relation": "reviewed_coherent" if candidate else "unresolved", "persona_evidence": evidence,
            "winter_outdoor": winter,
        }
        field_status = {key: "unknown" if observed[key] is None else "ai_observed" for key in FIELDS}
        provenance = {key: {"source_file": "winter-batch02-review/contact-sheet.jpg", "version": "aw-winter-02-native-v1",
                            "confidence": None if field_status[key] == "unknown" else .86} for key in FIELDS}
        entries.append({
            "outfit_id": raw["id"], "status": status, "record_fingerprint": row["record_fingerprint"],
            "asset_sha256": row["asset_sha256"], "image_url": raw["assets"]["image_url"],
            "source_kind": "codex_visual_review", "evidence": evidence, "observations": observed, "confidence": .86,
            "model": "current_codex_session", "prompt_version": "aw-winter-02-native-v1",
            "review_level": "individual_contact_sheet_judgment",
            "evidence_scope": "nonblind_individual_visual_judgment; no temperature/waterproof claim",
            "review_complete": True, "field_status": field_status, "field_provenance": provenance,
        })
    assert len(entries) == 12 and sum(row["status"] == "ai_candidate" for row in entries) == 9
    result = {"schema_version": 1, "source_rendered_version": rendered["version"], "independent_blind_review": False,
              "winter_outdoor_reviewed": True, "physical_warmth_verified": False, "entries": entries}
    result["version"] = "aw-winter-review-" + digest(result)[:20]
    target = AUDIT / "winter-recipes.batch02.native-review.json"
    if target.exists() and json.loads(target.read_text()) != result:
        raise SystemExit("Winter review changed; refusing overwrite")
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"version": result["version"], "accepted": 9, "held": 3}, ensure_ascii=False))


if __name__ == "__main__":
    main()
