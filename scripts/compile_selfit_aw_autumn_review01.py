#!/usr/bin/env python3
"""Compile the viewed autumn batch, excluding persona mismatch and visual duplicates."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs/audits/20260904-aw-supply"
FIELDS = ["axes","expression","formality","layering","persona_scores","scenes","seasons","structure",
          "wearability","main_visual_slots","main_colors","conflicts","silhouette","color_relation","persona_evidence"]
ACCEPTED = {
    1:({"bolt":.82,"iced":.76},"钴蓝收腰长外套与黑色长裤形成清楚长线，精致肩腰是唯一结构重点。"),
    2:({"bolt":.82,"iced":.72},"钴蓝长外套配素黑针织与象牙斜裙，色彩鲜明而焦点集中。"),
    3:({"bolt":.80,"iced":.76},"钴蓝长外层覆盖素灰衬衫裙，经典肩线和纵向比例清楚。"),
    4:({"bolt":.90,"film":.72},"祖母绿圆领收腰 A 线外套与黑色裤装构成可辨识精致复古比例。"),
    5:({"bolt":.88,"film":.72},"祖母绿收腰外套与浅色斜裙保留一个精致复古焦点。"),
    6:({"bolt":.86,"film":.70},"祖母绿 A 线长外套覆盖素灰长裙，肩腰和圆领建立完整主次。"),
    7:({"bolt":.88,"edge":.74},"品红错位短外套与黑色长裤形成鲜明短长反差，支撑款克制。"),
    8:({"bolt":.86,"melt":.62},"品红短外套与象牙斜裙形成单一鲜色和腰线重点。"),
    9:({"bolt":.84,"edge":.70},"品红短外套覆盖素灰长裙，精致结构集中在短外层。"),
    10:({"ease":.88,"loop":.66},"珊瑚茧形长外套、白衬衫和收束锥裤形成松弛但有收束的比例。"),
    11:({"ease":.86,"flou":.74,"loop":.64},"珊瑚圆线长外套与象牙斜裙形成柔和流动层次，黑针织稳定整体。"),
    12:({"ease":.84,"flou":.68},"珊瑚茧形长外层覆盖棕色衬衫裙，以圆量而非装饰表达松弛。"),
    16:({"edge":.90,"neon":.68},"品红锐肩短外套与黑色层片长裤共享清楚角度，长靴延续边界。"),
    18:({"edge":.84,"neon":.64},"品红锐线短外套覆盖素灰长裙，只保留短长和色块两个相关重点。"),
    23:({"flou":.86,"melt":.62},"紫晶包裹长外套与象牙斜裙形成连续柔软斜线，浪漫但不过度礼服化。"),
    24:({"flou":.88,"melt":.66},"紫晶包裹外层覆盖不透白色层次裙，流动感集中在衣长与下摆。"),
    25:({"flou":.78,"ease":.72},"珊瑚圆线外套与柔和锥裤形成轻流动日常裤装，黑针织稳定主次。"),
    28:({"heir":.88,"iced":.70},"钴蓝经典长外套、白衬衫和灰色压线裤形成整洁肩线与比例。"),
    30:({"heir":.86,"iced":.70},"钴蓝长外套覆盖灰色衬衫裙，经典剪裁和低装饰适合日常通勤。"),
    31:({"iced":.92,"jade":.72},"宝石青立领长外套与黑色长裤形成收净长线，侧开叉不破坏主线。"),
    33:({"iced":.90,"jade":.70},"宝石青立领外套覆盖灰色衬衫裙，纵线和覆盖完整。"),
    40:({"jade":.90,"iced":.76},"宝石青立领长外套、白衬衫和灰色直裤建立清楚领型与克制纵线。"),
    42:({"jade":.86,"iced":.70},"宝石青长外套覆盖棕色衬衫裙，纵向开合和领型是主视觉。"),
    43:({"jade":.84,"mute":.72},"万寿菊黄无领长外套与白衬衫、灰直裤保持低装饰和清楚纵线。"),
    45:({"jade":.82,"mute":.72},"万寿菊黄长外层覆盖棕色衬衫裙，鲜色仍由克制直线承载。"),
    46:({"loop":.86,"ease":.72},"珊瑚长外套与白衬衫、锥裤组成可复用模块，比例完整。"),
    48:({"loop":.84,"ease":.68},"珊瑚长外层覆盖灰色衬衫裙，基础模块有明确圆线比例。"),
}
DUPLICATES={26,27,34,35,36,47}
COMPETING={17,29}


def main():
    rendered=json.loads((AUDIT/"autumn-recipes.batch01.rendered.json").read_text())
    base=json.loads((ROOT/"app/data/recommendation-visual.v1.json").read_text())
    gen=json.loads((AUDIT/"generated-garments/combined-manifest-v2.json").read_text())
    visuals={**base["garments"],**gen["visual"]}; entries=[]
    for pos,row in enumerate(rendered["entries"],1):
        raw=row["new_record"]; observations=[visuals[item]["observations"] for item in raw["garment_ids"]]
        cats=[item["category"] for item in observations]
        structure="dress" if "dress" in cats else "skirt" if "skirt" in cats else "pants"
        colors=list(dict.fromkeys(c for item in observations if item["category"] not in {"shoes","bag"} for c in item.get("main_colors") or []))
        candidate=ACCEPTED.get(pos)
        if candidate:
            scores,evidence=candidate; status="ai_candidate"; seasons=["autumn"]; scenes=["daily"]
            wearability="everyday_with_statement"; conflicts=None
        elif pos in DUPLICATES:
            scores={}; status="needs_review"; seasons=scenes=wearability=None
            evidence="与本批已保留方案的主外层、上装及下装完全相同，只改变鞋包，不能作为独立新增配方。"; conflicts=["duplicate_main_recipe"]
        elif pos in COMPETING:
            scores={}; status="needs_review"; seasons=scenes=wearability=None
            evidence="皮革不对称裙与主外套同时形成强焦点，不进入默认日常池。"; conflicts=["competing_focal_points"]
        else:
            scores={}; status="needs_review"; seasons=scenes=wearability=None
            evidence="主外套的包裹、自然茧形或极简直线更支持其他人格，不能为目标人格强行放行。"; conflicts=["persona_mismatch"]
        observed={"axes":{},"expression":"typical","formality":"smart_casual","layering":2,
                  "persona_scores":scores,"scenes":scenes,"seasons":seasons,"structure":structure,
                  "wearability":wearability,"main_visual_slots":["outer","dress"] if structure=="dress" else ["outer","top",structure],
                  "main_colors":colors,"conflicts":conflicts,"silhouette":f"reviewed_autumn_{structure}_composition",
                  "color_relation":"reviewed_coherent" if candidate else "unresolved","persona_evidence":evidence}
        statuses={key:"unknown" if observed[key] is None else "ai_observed" for key in FIELDS}
        sheet=f"autumn-batch01-review/recipes-{(pos-1)//6+1}.jpg"
        provenance={key:{"source_file":sheet,"version":"aw-autumn-01-native-v1","confidence":None if statuses[key]=="unknown" else .85} for key in FIELDS}
        entries.append({"outfit_id":raw["id"],"status":status,"record_fingerprint":row["record_fingerprint"],
                        "asset_sha256":row["asset_sha256"],"image_url":raw["assets"]["image_url"],
                        "source_kind":"codex_visual_review","evidence":evidence,"observations":observed,"confidence":.85,
                        "model":"current_codex_session","prompt_version":"aw-autumn-01-native-v1",
                        "review_level":"individual_contact_sheet_judgment","evidence_scope":"nonblind_individual_visual_judgment",
                        "review_complete":True,"field_status":statuses,"field_provenance":provenance})
    assert len(entries)==48 and sum(x["status"]=="ai_candidate" for x in entries)==27
    result={"schema_version":1,"source_rendered_version":rendered["version"],"independent_blind_review":False,"entries":entries}
    result["version"]="aw-autumn-review-"+hashlib.sha256(json.dumps(result,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:20]
    target=AUDIT/"autumn-recipes.batch01.native-review.json"
    if target.exists() and json.loads(target.read_text())!=result: raise SystemExit("Autumn review changed; refusing overwrite")
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"version":result["version"],"accepted":27,"held":21},ensure_ascii=False))


if __name__=="__main__": main()
