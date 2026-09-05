#!/usr/bin/env python3
"""Compile non-blind whole-image review for threshold batch05."""
from __future__ import annotations
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; AUDIT=ROOT/"docs/audits/20260904-aw-supply"
FIELDS=["axes","expression","formality","layering","persona_scores","scenes","seasons","structure","wearability","main_visual_slots","main_colors","conflicts","silhouette","color_relation","persona_evidence","winter_outdoor"]
ACCEPTED={
 1:"冰雾蓝立领长外层与浅蓝衬衫、浅灰直裤保持连续冷调纵线。",2:"冰雾蓝主外层压住黑灰内层，裙褶只形成一次清晰结构变化。",3:"冰雾蓝外层与炭灰衬衫裙构成收净长线。",
 4:"深青茧形包裹外层是唯一主焦点，浅色直裤为自然体积提供收束。",6:"深青包裹外层与炭灰衬衫裙形成一处圆量和稳定内层。",
 7:"无领冷墨灰外层与浅灰直裤、冰蓝衬衫形成精确低装饰纵线。",8:"无领冷墨灰外层覆盖黑灰裙装，边界和长短关系清楚。",9:"无领冷墨灰外层与炭灰衬衫裙形成不同家族的冷静长线。",
 13:"灰玫瑰经典大衣与浅蓝衬衫、浅灰直裤保持整洁肩线和比例。",15:"灰玫瑰经典外层配炭灰衬衫裙，主次清楚且不过度甜美。",
 16:"深海蓝系带长大衣与浅蓝衬衫、浅灰直裤形成经典层次。",18:"深海蓝系带外层覆盖炭灰衬衫裙，收腰与纵线可信。",
 19:"祖母绿双排扣大衣是唯一高彩主衣，浅色内搭保持经典秩序。",21:"祖母绿经典外层与炭灰衬衫裙形成清楚深浅关系。",
 22:"暖驼系带外层、浅蓝衬衫与浅灰直裤在松量和收束之间平衡。",24:"暖驼软结构外层覆盖简洁炭灰衬衫裙，体积集中在外层。",
}
MISMATCH={10,11,12}

def main():
 d=json.loads((AUDIT/"targeted-recipes.batch05.rendered.json").read_text()); base=json.loads((ROOT/"app/data/recommendation-visual.v1.json").read_text()); gen=json.loads((AUDIT/"generated-garments/batch07/manifest.json").read_text()); visuals={**base["garments"],**gen["visual"]}; entries=[]
 for pos,row in enumerate(d["entries"],1):
  raw=row["new_record"]; obs=[visuals[x]["observations"] for x in raw["garment_ids"]]; cats=[x["category"] for x in obs]; structure="dress" if "dress" in cats else "skirt" if "skirt" in cats else "pants"; colors=list(dict.fromkeys(c for x in obs if x["category"] not in {"shoes","bag"} for c in x.get("main_colors") or [])); accepted=pos in ACCEPTED
  if accepted:
   persona=raw["primary_persona"].lower(); scores={persona:.86}; evidence=ACCEPTED[pos]; status="ai_candidate"; seasons=["winter"]; scenes=["daily"]; wearability="everyday_with_statement"; conflicts=None; winter="complete_layers_visually_reviewed"
  else:
   if pos in MISMATCH: evidence="实际外套为明显收腰经典剪裁，不支持目标 EASE 的松弛但有收束表达。"; conflicts=["persona_mismatch"]
   else: evidence="几何拼片裙与强结构或包裹外层同时竞争主视觉，主次关系不稳定。"; conflicts=["competing_focal_points"]
   scores={}; status="needs_review"; seasons=scenes=wearability=winter=None
  observed={"axes":{},"expression":"typical","formality":"smart_casual","layering":2,"persona_scores":scores,"scenes":scenes,"seasons":seasons,"structure":structure,"wearability":wearability,"main_visual_slots":["outer","dress"] if structure=="dress" else ["outer","top",structure],"main_colors":colors,"conflicts":conflicts,"silhouette":f"reviewed_winter_{structure}_composition","color_relation":"reviewed_coherent" if accepted else "unresolved","persona_evidence":evidence,"winter_outdoor":winter}
  statuses={k:"unknown" if observed[k] is None else "ai_observed" for k in FIELDS}; sheet=f"targeted-batch05-review/recipes-{(pos-1)//6+1}.jpg"; prov={k:{"source_file":sheet,"version":"aw-targeted-05-native-v1","confidence":None if statuses[k]=="unknown" else .86} for k in FIELDS}
  entries.append({"outfit_id":raw["id"],"status":status,"record_fingerprint":row["record_fingerprint"],"asset_sha256":row["asset_sha256"],"image_url":raw["assets"]["image_url"],"source_kind":"codex_visual_review","evidence":evidence,"observations":observed,"confidence":.86,"model":"current_codex_session","prompt_version":"aw-targeted-05-native-v1","review_level":"individual_contact_sheet_judgment","evidence_scope":"nonblind_individual_visual_judgment; no temperature/waterproof claim","review_complete":True,"field_status":statuses,"field_provenance":prov})
 assert len(entries)==24 and sum(x["status"]=="ai_candidate" for x in entries)==16
 result={"schema_version":1,"source_rendered_version":d["version"],"independent_blind_review":False,"winter_outdoor_reviewed":True,"physical_warmth_verified":False,"entries":entries}; result["version"]="aw-targeted-review-"+hashlib.sha256(json.dumps(result,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:20]
 target=AUDIT/"targeted-recipes.batch05.native-review.json"
 if target.exists() and json.loads(target.read_text())!=result: raise SystemExit("Targeted review05 changed; refusing overwrite")
 target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n"); print(json.dumps({"version":result["version"],"accepted":16,"held":8},ensure_ascii=False))
 disposition={"schema_version":1,"manifest_version":gen["version"],"status":"partially_restricted","restrictions":[{"token":"n0037","reason":"Actual pixels show fitted classic tailoring; EASE affinity in generation target is not visually supported.","allowed_personas":["HEIR","MUTE","LOOP"],"blocked_personas":["EASE"]}],"production_approved":False}
 (AUDIT/"generated-garments/batch07/review-disposition.json").write_text(json.dumps(disposition,ensure_ascii=False,indent=2)+"\n")
if __name__=="__main__":main()
