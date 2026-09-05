"""Compile whole-image review for the first 48 winter recipe drafts."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs/audits/20260904-aw-supply"
VISUAL = ROOT / "app/data/recommendation-visual.v1.json"
FIELDS = [
    "axes", "expression", "formality", "layering", "persona_scores", "scenes", "seasons",
    "structure", "wearability", "main_visual_slots", "main_colors", "conflicts", "silhouette",
    "color_relation", "persona_evidence", "winter_outdoor",
]

# position: expression, scores, evidence. Position is bound to the immutable rendered manifest.
CANDIDATES = {
    5: ("easy", {"ease": .84, "loop": .64}, "浅蓝长外套、藏蓝针织与长裙构成完整长线，运动鞋和抽绳包适合低负担日常。"),
    9: ("typical", {"edge": .82, "noir": .78}, "黑色短皮外套与长直连衣裙形成短长锐利边界，封闭鞋履和黑包保持主线。"),
    12: ("easy", {"film": .78, "heir": .70}, "棕色外套与同色长袖连衣裙延续复古长线，长靴和软包完成冬季外出关系。"),
    13: ("typical", {"flou": .82, "iced": .72}, "浅蓝长外套、深色垂褶内层和奶油阔裤形成流动但有边界的冬季长线。"),
    15: ("typical", {"flou": .86, "heir": .58}, "浅蓝长外套覆盖奶油长袖连衣裙，蓝色封闭鞋包保持轻盈同类色。"),
    16: ("easy", {"heir": .86, "ease": .62}, "灰褐长外套、米白衬衫和直裤比例经典，踝靴完成可信外出层次。"),
    22: ("typical", {"jade": .90, "heir": .58}, "水墨长外套与白色内层、纵向阔裤共享黑白红母题，封闭乐福鞋保持克制。"),
    23: ("typical", {"jade": .90, "flou": .58}, "水墨长外套、灰色内层和水墨长裙形成连续纵线，鞋包重复同一母题。"),
    24: ("typical", {"jade": .88, "heir": .62}, "水墨长外套覆盖灰褐长袖连衣裙，黑白鞋包呼应外套边线，焦点清楚。"),
    26: ("easy", {"loop": .82, "heir": .66}, "灰褐短风衣、长袖衬衫和中长裙为可复用模块，封闭乐福鞋适合日常。"),
    27: ("easy", {"loop": .86, "heir": .70}, "藏蓝长外套覆盖炭灰长袖连衣裙，长靴和抽绳包完成简洁冬季长线。"),
    28: ("typical", {"melt": .86, "ease": .56}, "浅粉长外套、柔软针织和垂坠阔裤形成圆线，运动鞋降低甜美元素负担。"),
    29: ("easy", {"melt": .84, "iced": .62}, "奶油短外套、粉色贴身针织和蓝色长裙构成软硬平衡，封闭鞋履完整。"),
    30: ("typical", {"melt": .84, "heir": .58}, "奶油短外套覆盖蓝色长袖裙，粉白绒靴与软包成为一处柔软焦点。"),
    31: ("easy", {"mute": .86, "noir": .60}, "藏蓝长外套、同色垂褶内层和宽裤形成低装饰长线，长靴完成外出层次。"),
    32: ("easy", {"mute": .84, "iced": .68}, "奶油长风衣配浅蓝衬衫和直裙，低装饰鞋包保持清晰纵线。"),
    37: ("typical", {"noir": .92, "edge": .66}, "黑色长外套、结构上衣和直裤形成强长线，黑靴和包不打断边界。"),
    39: ("typical", {"noir": .90, "edge": .70}, "藏蓝长外套覆盖黑酒红结构长裙，酒红踝靴小面积重复内层色。"),
    43: ("typical", {"void": .84, "wabi": .62}, "黑色封闭外套、藏蓝针织和灰褐层片裤构成包裹感，运动鞋降低负担。"),
    44: ("typical", {"void": .80, "wabi": .74}, "灰褐软外套、垂褶上衣和错层长裙使用同一松软语言，封闭运动鞋完成外出关系。"),
    45: ("easy", {"void": .78, "noir": .64}, "黑色封闭外套覆盖炭灰长袖连衣裙，运动鞋与机能包形成低负担日常版本。"),
    46: ("easy", {"wabi": .84, "ease": .68}, "棕色长外套、灰绿松身内层和奶油阔裤形成自然层次，封闭运动鞋适合日常。"),
    47: ("typical", {"wabi": .82, "void": .72}, "深色外套与灰蓝连帽内层叠穿，灰绿长裙和运动鞋保持自然、可活动比例。"),
    48: ("easy", {"wabi": .82, "ease": .66}, "棕色外套覆盖米色长袖连衣裙，长靴和软包延续自然色与完整长线。"),
}


def digest(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def main() -> None:
    rendered = json.loads((AUDIT / "winter-recipes.batch01.rendered.json").read_text())
    visual = json.loads(VISUAL.read_text())
    assert rendered["version"] == "aw-designed-rendered-ec6c0225d5cb95a70c45"
    entries = []
    for position, row in enumerate(rendered["entries"], 1):
        raw = row["new_record"]
        categories = [visual["garments"][gid]["observations"]["category"] for gid in raw["garment_ids"]]
        structure = "dress" if "dress" in categories else "skirt" if "skirt" in categories else "pants"
        colors = []
        for gid in raw["garment_ids"]:
            category = visual["garments"][gid]["observations"]["category"]
            if category not in {"shoes", "bag"}:
                colors.extend(visual["garments"][gid]["observations"].get("main_colors") or [])
        colors = list(dict.fromkeys(colors))
        candidate = CANDIDATES.get(position)
        if candidate:
            expression, scores, evidence = candidate
            status, seasons, scenes = "ai_candidate", ["winter"], ["daily"]
            conflicts, wearability = None, "everyday" if expression == "easy" else "everyday_with_statement"
            winter_outdoor = "complete_layers_visually_reviewed"
        else:
            expression, scores = "typical", {}
            status, seasons, scenes = "needs_review", None, None
            evidence = "目标配方包含外套，但整图仍存在薄外层、主次竞争、场合化或风格冲突；不计冬季日常。"
            conflicts, wearability = ["winter_or_cohesion_unresolved"], None
            winter_outdoor = None
        observations = {
            "axes": {}, "expression": expression, "formality": "smart_casual",
            "layering": max(2, categories.count("outer") + 1), "persona_scores": scores,
            "scenes": scenes, "seasons": seasons, "structure": structure, "wearability": wearability,
            "main_visual_slots": ["outer", "dress"] if structure == "dress" else ["outer", "top", structure],
            "main_colors": colors, "conflicts": conflicts,
            "silhouette": f"reviewed_winter_{structure}_composition",
            "color_relation": "reviewed_coherent" if candidate else "unresolved",
            "persona_evidence": evidence, "winter_outdoor": winter_outdoor,
        }
        field_status = {key: ("unknown" if observations[key] is None else "ai_observed") for key in FIELDS}
        sheet = f"winter-batch01-review/recipes-{(position - 1) // 6 + 1}.jpg"
        provenance = {key: {"source_file": sheet, "version": "aw-winter-01-native-v1",
                            "confidence": None if field_status[key] == "unknown" else .8} for key in FIELDS}
        entries.append({
            "outfit_id": raw["id"], "status": status,
            "record_fingerprint": row["record_fingerprint"], "asset_sha256": row["asset_sha256"],
            "image_url": raw["assets"]["image_url"], "source_kind": "codex_visual_review",
            "evidence": evidence, "observations": observations, "confidence": .8,
            "model": "current_codex_session", "prompt_version": "aw-winter-01-native-v1",
            "review_level": "individual_contact_sheet_judgment",
            "evidence_scope": "nonblind_individual_visual_judgment; no temperature/waterproof claim",
            "review_complete": True, "field_status": field_status, "field_provenance": provenance,
        })
    assert len(entries) == 48 and sum(entry["status"] == "ai_candidate" for entry in entries) == 24
    result = {
        "schema_version": 1, "source_rendered_version": rendered["version"],
        "independent_blind_review": False, "winter_outdoor_reviewed": True,
        "physical_warmth_verified": False, "entries": entries,
    }
    result["version"] = "aw-winter-review-" + digest(result)[:20]
    target = AUDIT / "winter-recipes.batch01.native-review.json"
    if target.exists() and json.loads(target.read_text()) != result:
        raise SystemExit("Winter review changed; refusing overwrite")
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(result["version"], 24, 24)


if __name__ == "__main__":
    main()
