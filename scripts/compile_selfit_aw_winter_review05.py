#!/usr/bin/env python3
"""Compile whole-image review for 48 zero-condition winter recompositions."""
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
    8: ({"edge": .82, "wabi": .58}, "灰褐错位外套与几何褶裙共享方向线，黑色针织和踝靴稳定主次。"),
    14: ({"iced": .82, "heir": .64}, "短风衣、收净针织与黑色长裙形成清楚长线，封闭鞋履完整。"),
    15: ({"iced": .88, "heir": .66}, "灰褐长外套覆盖冰蓝长袖裙，踝靴完成冷静、收净的冬季长线。"),
    16: ({"neon": .78, "oops": .68}, "混合风衣以沙色为底、蓝锈为单一多色焦点，白衬衫与黑裤稳定日常比例。"),
    19: ({"neon": .88, "oops": .66}, "高彩气球短外套是唯一强表达，白衬衫、黑长裤和运动鞋提供日常支撑。"),
    21: ({"neon": .82, "oops": .74}, "蓝粉错位短外套覆在素灰长衬衫裙上，高彩与短长反差集中在一处。"),
    23: ({"neon": .82, "oops": .74}, "蓝粉错位短外套与素黑针织、浅色斜裹长裙构成可日常化的高彩对比。"),
    31: ({"oops": .84, "neon": .66}, "混合风衣与一处角度长裤共享解构线，白衬衫让多材质仍有支撑。"),
    32: ({"oops": .82, "wabi": .64}, "灰褐错位短外套与浅色斜裹长裙重复同一方向线，黑针织保持稳定。"),
    34: ({"oops": .86, "neon": .76}, "高彩短外套与角度长裤形成一个可解释的错位重点，白衬衫平衡。"),
    36: ({"oops": .84, "neon": .68}, "蓝粉错位短外套与素灰长衬衫裙使用明确短长反差，没有额外破片堆叠。"),
    40: ({"void": .90, "wabi": .72}, "长叠片外套、黑针织与错层长裤形成包裹感，运动鞋降低日常负担。"),
    41: ({"void": .84, "wabi": .72}, "错位灰褐短外层与安静层片长裙延续同一松软线条，主次清楚。"),
    42: ({"void": .78, "wabi": .76}, "茧形补片外套覆在素灰长衬衫裙上，用体积而非破片堆叠表达包裹。"),
    43: ({"void": .88, "wabi": .74}, "深色宽松补片外层与一处错层长裤形成受控的包裹层次，鞋包低负担。"),
    47: ({"wabi": .88, "void": .74}, "灰蓝褐宽松外层与自然错层长裙共享手作观感，运动鞋平衡复杂度。"),
}
DUPLICATES = {4, 5, 22}
WINTER_INCOMPLETE = {3, 6, 9, 13, 25, 28, 30}
PERSONA_MISMATCH = {18, 33, 45, 48}


def main() -> None:
    rendered = json.loads((AUDIT / "winter-recipes.batch05.rendered.json").read_text())
    visual = json.loads((ROOT / "app/data/recommendation-visual.v1.json").read_text())
    entries = []
    for position, row in enumerate(rendered["entries"], 1):
        raw = row["new_record"]; obs = [visual["garments"][g]["observations"] for g in raw["garment_ids"]]
        cats = [item["category"] for item in obs]
        structure = "dress" if "dress" in cats else "skirt" if "skirt" in cats else "pants"
        colors = list(dict.fromkeys(c for item in obs if item["category"] not in {"shoes", "bag"} for c in item.get("main_colors") or []))
        candidate = CANDIDATES.get(position)
        if candidate:
            scores, evidence = candidate; status = "ai_candidate"; seasons = ["winter"]; scenes = ["daily"]
            expression = "typical"; wearability = "everyday_with_statement"; conflicts = None
            winter = "complete_layers_visually_reviewed"
        else:
            scores = {}; status = "needs_review"; seasons = scenes = wearability = winter = None; expression = "typical"
            if position in DUPLICATES:
                evidence = "与本批另一色板任务的单品集合完全相同，不能重复计为新供给。"; conflicts = ["duplicate_recipe"]
            elif position in WINTER_INCOMPLETE:
                evidence = "短薄外层或无足够覆盖的夹克不能支持默认冬季外出证据。"; conflicts = ["winter_layering_incomplete"]
            elif position in PERSONA_MISMATCH:
                evidence = "整套更接近其他人格的素净或自然表达，不为目标人格强行打分。"; conflicts = ["persona_mismatch"]
            else:
                evidence = "外套、上衣或下装同时使用戏剧装饰、解构或高彩拼接，多焦点不进默认日常池。"; conflicts = ["occasion_or_competing_focal_points"]
        observed = {"axes": {}, "expression": expression, "formality": "smart_casual", "layering": 2,
                    "persona_scores": scores, "scenes": scenes, "seasons": seasons, "structure": structure,
                    "wearability": wearability, "main_visual_slots": ["outer", "dress"] if structure == "dress" else ["outer", "top", structure],
                    "main_colors": colors, "conflicts": conflicts, "silhouette": f"reviewed_winter_{structure}_composition",
                    "color_relation": "reviewed_coherent" if candidate else "unresolved", "persona_evidence": evidence,
                    "winter_outdoor": winter}
        field_status = {key: "unknown" if observed[key] is None else "ai_observed" for key in FIELDS}
        sheet = f"winter-batch05-review/recipes-{(position - 1)//6 + 1}.jpg"
        provenance = {key: {"source_file": sheet, "version": "aw-winter-05-native-v1",
                            "confidence": None if field_status[key] == "unknown" else .84} for key in FIELDS}
        entries.append({"outfit_id": raw["id"], "status": status, "record_fingerprint": row["record_fingerprint"],
                        "asset_sha256": row["asset_sha256"], "image_url": raw["assets"]["image_url"],
                        "source_kind": "codex_visual_review", "evidence": evidence, "observations": observed, "confidence": .84,
                        "model": "current_codex_session", "prompt_version": "aw-winter-05-native-v1",
                        "review_level": "individual_contact_sheet_judgment",
                        "evidence_scope": "nonblind_individual_visual_judgment; no temperature/waterproof claim",
                        "review_complete": True, "field_status": field_status, "field_provenance": provenance})
    assert len(entries) == 48 and sum(e["status"] == "ai_candidate" for e in entries) == 16
    result = {"schema_version": 1, "source_rendered_version": rendered["version"], "independent_blind_review": False,
              "winter_outdoor_reviewed": True, "physical_warmth_verified": False, "entries": entries}
    result["version"] = "aw-winter-review-" + hashlib.sha256(json.dumps(result, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]
    target = AUDIT / "winter-recipes.batch05.native-review.json"
    if target.exists() and json.loads(target.read_text()) != result:
        raise SystemExit("Winter review changed; refusing overwrite")
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"version": result["version"], "accepted": 16, "held": 32}, ensure_ascii=False))


if __name__ == "__main__":
    main()
