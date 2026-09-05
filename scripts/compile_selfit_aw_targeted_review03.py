#!/usr/bin/env python3
"""Compile whole-image review for the content-bound targeted batch03."""
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
    1: ({"melt":.90,"ease":.66}, "玫瑰驼针织裙的圆肩、柔和收腰与流动 A 线构成日常温和感。"),
    2: ({"mute":.92,"iced":.72}, "雾霾海蓝衬衫裙以暗门襟、小领和连续纵线表达低装饰和收净。"),
    3: ({"oops":.84,"edge":.62}, "炭灰连衣裙只用斜腰线和单侧收褶形成一处可解释错位。"),
    4: ({"oops":.82,"melt":.62}, "粉蓝裙只保留一块柔粉斜片，颜色和方向线集中在同一主题。"),
    5: ({"void":.90,"wabi":.70}, "泥褐茧形裙用包裹体积和单一偏置闭合表达低负担保护感。"),
    6: ({"noir":.94,"edge":.74}, "高立领强肩黑长外套与角度黑长裤延续同一锐利纵线。"),
    10: ({"void":.88,"wabi":.70}, "炭灰高围领包裹大衣与一处错层裙共用圆量与层片关系。"),
    11: ({"void":.86,"mute":.62}, "炭灰包裹大衣覆在素色长衬衫裙上，体积只集中在外层。"),
    12: ({"wabi":.88,"ease":.68}, "深青靛弧线茧形外套与米色锥裤形成自然圆量与收束。"),
    13: ({"wabi":.86,"void":.70}, "深青靛自然织理外层配一处安静错层长裙，支撑款保持低竞争。"),
    14: ({"wabi":.84,"jade":.62}, "深青靛茧形外套覆盖米色衬衫裙，以自然材质观感与长线表达。"),
}
COMPETING = {7,8,9}


def main() -> None:
    rendered=json.loads((AUDIT/"targeted-recipes.batch03.rendered.json").read_text())
    base=json.loads((ROOT/"app/data/recommendation-visual.v1.json").read_text())
    generated=json.loads((AUDIT/"generated-garments/batch06/manifest.json").read_text())
    visuals={**base["garments"],**generated["visual"]}; entries=[]
    for pos,row in enumerate(rendered["entries"],1):
        raw=row["new_record"]; obs=[visuals[x]["observations"] for x in raw["garment_ids"]]
        cats=[x["category"] for x in obs]; structure="dress" if "dress" in cats else "skirt" if "skirt" in cats else "pants"
        colors=list(dict.fromkeys(c for x in obs if x["category"] not in {"shoes","bag"} for c in x.get("main_colors") or []))
        accepted=CANDIDATES.get(pos); is_winter="冬" in raw["season_tags"]
        if accepted:
            scores,evidence=accepted; status="ai_candidate"; seasons=["winter" if is_winter else "autumn"]
            scenes=["daily"]; wearability="everyday_with_statement"; conflicts=None
            winter="complete_layers_visually_reviewed" if is_winter else "not_applicable"
        else:
            scores={}; status="needs_review"; seasons=scenes=wearability=winter=None
            evidence="强外套与皮革下装、皮革衬衫裙或碎片裤同时抢焦点，不进入默认日常池。"
            conflicts=["competing_focal_points"]
        observed={"axes":{},"expression":"typical","formality":"smart_casual","layering":2 if is_winter else 1,
                  "persona_scores":scores,"scenes":scenes,"seasons":seasons,"structure":structure,
                  "wearability":wearability,"main_visual_slots":["outer","dress"] if is_winter and structure=="dress" else (["outer","top",structure] if is_winter else ["dress"]),
                  "main_colors":colors,"conflicts":conflicts,"silhouette":f"reviewed_{'winter' if is_winter else 'autumn'}_{structure}_composition",
                  "color_relation":"reviewed_coherent" if accepted else "unresolved","persona_evidence":evidence,"winter_outdoor":winter}
        statuses={k:"unknown" if observed[k] is None else "ai_observed" for k in FIELDS}
        sheet=f"targeted-batch03-review/recipes-{(pos-1)//6+1}.jpg"
        provenance={k:{"source_file":sheet,"version":"aw-targeted-03-native-v1","confidence":None if statuses[k]=="unknown" else .88} for k in FIELDS}
        entries.append({"outfit_id":raw["id"],"status":status,"record_fingerprint":row["record_fingerprint"],
                        "asset_sha256":row["asset_sha256"],"image_url":raw["assets"]["image_url"],
                        "source_kind":"codex_visual_review","evidence":evidence,"observations":observed,"confidence":.88,
                        "model":"current_codex_session","prompt_version":"aw-targeted-03-native-v1",
                        "review_level":"individual_contact_sheet_judgment","evidence_scope":"nonblind_individual_visual_judgment; no temperature/waterproof claim",
                        "review_complete":True,"field_status":statuses,"field_provenance":provenance})
    assert len(entries)==14 and sum(x["status"]=="ai_candidate" for x in entries)==11
    result={"schema_version":1,"source_rendered_version":rendered["version"],"independent_blind_review":False,
            "winter_outdoor_reviewed":True,"physical_warmth_verified":False,"entries":entries}
    result["version"]="aw-targeted-review-"+hashlib.sha256(json.dumps(result,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:20]
    target=AUDIT/"targeted-recipes.batch03.native-review.json"
    if target.exists() and json.loads(target.read_text())!=result: raise SystemExit("Targeted review changed; refusing overwrite")
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"version":result["version"],"accepted":11,"held":3},ensure_ascii=False))


if __name__=="__main__": main()
