"""Compile native whole-image reviews for focal repair batches 05 and 06."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs/audits/20260904-aw-supply"
VISUAL = ROOT / "app/data/recommendation-visual.v1.json"
FIELDS = [
    "axes", "expression", "formality", "layering", "persona_scores", "scenes",
    "seasons", "structure", "wearability", "main_visual_slots", "main_colors",
    "conflicts", "silhouette", "color_relation", "persona_evidence",
]

# token: expression, reviewed persona scores, whole-image visual evidence
CANDIDATES = {
    "o0017": ("typical", {"iced": .84, "flou": .68}, "斜褶上衣与冰蓝长裙用同方向褶线呼应，黑色低装饰鞋包压住浅色；焦点集中在纵向柔褶。"),
    "o0159": ("typical", {"wabi": .88, "void": .68}, "灰褐错层上衣和自然垂坠长裙形成同一松软轮廓，简洁黑鞋包不再竞争。"),
    "o0273": ("typical", {"flou": .78, "heir": .56}, "浅蓝简洁衬衫稳定浅色花纱阔裤，日常焦点只在下装流动层次。"),
    "o0298": ("typical", {"void": .84, "wabi": .72}, "深灰垂褶上衣与分层阔裤保持同色包裹感，黑鞋包成为安静支撑。"),
    "o0343": ("typical", {"jade": .90, "flou": .58}, "黑白花枝上衣与长裙共享同一水墨母题，红结仅作小面积重复，鞋包已简化。"),
    "o0398": ("typical", {"edge": .88, "noir": .74}, "黑粉结构短上衣与黑色不对称裙建立清楚短长边界，鞋包保持黑色低装饰。"),
    "o0413": ("typical", {"void": .86, "wabi": .80}, "灰绿错层上衣与灰褐层片裤沿同一自然解构语言展开，简洁黑鞋包收束。"),
    "o0416": ("typical", {"wabi": .88, "void": .76}, "灰褐错层上衣与弧线拼片裤保持自然材质和包裹比例，配件不抢焦点。"),
    "o0427": ("typical", {"wabi": .86, "flou": .66}, "灰绿垂褶背心与自然层片裙形成连续圆线，低装饰灰褐鞋包支撑日常。"),
    "o0634": ("typical", {"ease": .82, "wabi": .72}, "棕色收束短外层、灰绿背心与弧线裤构成松弛但有腰线的同色层次。"),
    "o0795": ("typical", {"oops": .82, "edge": .68}, "蓝灰错位衬衫作为唯一解构焦点，直筒牛仔与黑鞋包提供稳定基底。"),
    "o1007": ("typical", {"loop": .76, "wabi": .72}, "灰褐垂褶上衣和米灰拼片阔裤形成可复用同色模块，鞋包低装饰。"),
    "o1095": ("typical", {"void": .84, "wabi": .74}, "灰绿错层衬衫搭做旧直裤，结构集中在上衣和裤侧层片，黑鞋包降低噪音。"),
    "o1102": ("typical", {"void": .86, "wabi": .78}, "灰褐宽短上衣与深灰拼片裤形成一松一垂的包裹轮廓，配件保持克制。"),
    "o1119": ("easy", {"void": .78, "wabi": .70, "ease": .58}, "深灰软外套、简洁内层和弧线裤构成完整三层关系，配件不参与竞争。"),
    "o1129": ("typical", {"oops": .84, "edge": .60}, "白衬衫稳定黑灰粉错层裤，错位只发生在下装，黑鞋包延续清楚边界。"),
    "o1147": ("typical", {"oops": .82, "flou": .58}, "白衬衫稳定灰蓝黄不对称层裙，单一解构下装成为焦点，黑鞋包保持安静。"),
}


def digest(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def main() -> None:
    visual = json.loads(VISUAL.read_text())
    garment_visual = visual["garments"]
    candidate_seen = set()
    for batch in (5, 6):
        rendered = json.loads((AUDIT / f"repairs.batch0{batch}.rendered.json").read_text())
        entries = []
        for position, row in enumerate(rendered["entries"], 1):
            token = row["source_token"]
            raw = row["new_record"]
            candidate = CANDIDATES.get(token)
            categories = [garment_visual[gid]["observations"]["category"] for gid in raw["garment_ids"]]
            structure = "dress" if "dress" in categories else "skirt" if "skirt" in categories else "pants"
            colors = []
            for gid in raw["garment_ids"]:
                if garment_visual[gid]["observations"]["category"] not in {"shoes", "bag"}:
                    colors.extend(garment_visual[gid]["observations"].get("main_colors") or [])
            colors = list(dict.fromkeys(colors))
            if candidate:
                expression, scores, evidence = candidate
                status = "ai_candidate"
                candidate_seen.add(token)
                conflicts = None
                seasons, scenes = ["autumn"], ["daily"]
                wearability = "everyday" if expression == "easy" else "everyday_with_statement"
            else:
                expression, scores = "typical", {}
                status = "needs_review"
                evidence = "低装饰鞋包已降低配件噪音，但主服装仍存在多个竞争焦点；不进入秋冬日常候选。"
                conflicts = ["main_garment_competition_remaining"]
                seasons = scenes = wearability = None
            observations = {
                "axes": {}, "expression": expression, "formality": "smart_casual",
                "layering": max(1, categories.count("outer") + 1), "persona_scores": scores,
                "scenes": scenes, "seasons": seasons, "structure": structure,
                "wearability": wearability,
                "main_visual_slots": ["dress"] if structure == "dress" else ["top", structure],
                "main_colors": colors, "conflicts": conflicts,
                "silhouette": f"reviewed_focal_{structure}_composition",
                "color_relation": "controlled_after_accessory_simplification" if candidate else "unresolved",
                "persona_evidence": evidence,
            }
            field_status = {key: ("unknown" if observations[key] is None else "ai_observed") for key in FIELDS}
            sheet = f"repairs-batch0{batch}-review/recipes-{(position - 1) // 6 + 1}.jpg"
            provenance = {
                key: {"source_file": sheet, "version": f"aw-focal-repair-0{batch}-native-v1",
                      "confidence": None if field_status[key] == "unknown" else .8}
                for key in FIELDS
            }
            entries.append({
                "outfit_id": raw["id"], "source_token": token, "status": status,
                "record_fingerprint": row["record_fingerprint"], "asset_sha256": row["asset_sha256"],
                "image_url": raw["assets"]["image_url"], "source_kind": "codex_visual_review",
                "evidence": evidence, "observations": observations, "confidence": .8,
                "model": "current_codex_session", "prompt_version": f"aw-focal-repair-0{batch}-native-v1",
                "review_level": "individual_contact_sheet_judgment",
                "evidence_scope": "nonblind_individual_visual_judgment", "review_complete": True,
                "field_status": field_status, "field_provenance": provenance,
            })
        result = {
            "schema_version": 1, "source_rendered_version": rendered["batch_id"],
            "independent_blind_review": False, "winter_outdoor_reviewed": False,
            "entries": entries,
        }
        result["version"] = f"aw-focal-review-0{batch}-" + digest(result)[:20]
        target = AUDIT / f"repairs.batch0{batch}.native-review.json"
        if target.exists() and json.loads(target.read_text()) != result:
            raise SystemExit(f"Review changed; refusing overwrite: {target}")
        target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        print(target.name, result["version"], sum(e["status"] == "ai_candidate" for e in entries))
    assert candidate_seen == set(CANDIDATES)


if __name__ == "__main__":
    main()
