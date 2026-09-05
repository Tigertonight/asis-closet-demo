#!/usr/bin/env python3
"""Compile whole-image review for bounded outerwear reuse batch04."""
from __future__ import annotations
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; AUDIT=ROOT/"docs/audits/20260904-aw-supply"
FIELDS=["axes","expression","formality","layering","persona_scores","scenes","seasons","structure","wearability","main_visual_slots","main_colors","conflicts","silhouette","color_relation","persona_evidence","winter_outdoor"]
CANDIDATES={
 1:({"iced":.82,"noir":.72},"高立领黑长外套与冰蓝衬衫、浅灰直裤构成收净冷调长线。"),
 2:({"iced":.84,"noir":.70},"黑色纵线外层覆盖冰蓝衬衫裙，颜色对比和边界清楚。"),
 3:({"edge":.90,"noir":.72},"强肩黑外套与几何百褶裙共用锐利边界，内层低竞争。"),
 5:({"ease":.84,"void":.70},"高围领茧形外层和米色锥裤形成松弛与收束，白衬衫保持清楚。"),
 6:({"ease":.82,"void":.68},"包裹茧形外套覆在米色衬衫裙上，只保留一处宽松体积。"),
 7:({"loop":.80,"void":.70},"包裹外层、浅色图形衬衫与灰直裤构成可拆分复用的完整模块。"),
 8:({"loop":.82,"void":.72},"包裹外层与素灰衬衫裙形成简洁且可复用的冬季单元。")}
def main():
 d=json.loads((AUDIT/"targeted-recipes.batch04.rendered.json").read_text()); base=json.loads((ROOT/"app/data/recommendation-visual.v1.json").read_text()); gen=json.loads((AUDIT/"generated-garments/batch06/manifest.json").read_text()); visuals={**base["garments"],**gen["visual"]}; entries=[]
 for pos,row in enumerate(d["entries"],1):
  raw=row["new_record"]; obs=[visuals[x]["observations"] for x in raw["garment_ids"]]; cats=[x["category"] for x in obs]; structure="dress" if "dress" in cats else "skirt" if "skirt" in cats else "pants"; colors=list(dict.fromkeys(c for x in obs if x["category"] not in {"shoes","bag"} for c in x.get("main_colors") or [])); accepted=CANDIDATES.get(pos)
  if accepted: scores,evidence=accepted; status="ai_candidate"; seasons=["winter"];scenes=["daily"];wearability="everyday_with_statement";conflicts=None;winter="complete_layers_visually_reviewed"
  else: scores={}; evidence="强肩雕塑外套的戏剧边界压过 MUTE 所需的低装饰和克制结构。";status="needs_review";seasons=scenes=wearability=winter=None;conflicts=["persona_mismatch"]
  observed={"axes":{},"expression":"typical","formality":"smart_casual","layering":2,"persona_scores":scores,"scenes":scenes,"seasons":seasons,"structure":structure,"wearability":wearability,"main_visual_slots":["outer","dress"] if structure=="dress" else ["outer","top",structure],"main_colors":colors,"conflicts":conflicts,"silhouette":f"reviewed_winter_{structure}_composition","color_relation":"reviewed_coherent" if accepted else "unresolved","persona_evidence":evidence,"winter_outdoor":winter}
  statuses={k:"unknown" if observed[k] is None else "ai_observed" for k in FIELDS};sheet=f"targeted-batch04-review/recipes-{(pos-1)//6+1}.jpg";prov={k:{"source_file":sheet,"version":"aw-targeted-04-native-v1","confidence":None if statuses[k]=="unknown" else .86} for k in FIELDS}
  entries.append({"outfit_id":raw["id"],"status":status,"record_fingerprint":row["record_fingerprint"],"asset_sha256":row["asset_sha256"],"image_url":raw["assets"]["image_url"],"source_kind":"codex_visual_review","evidence":evidence,"observations":observed,"confidence":.86,"model":"current_codex_session","prompt_version":"aw-targeted-04-native-v1","review_level":"individual_contact_sheet_judgment","evidence_scope":"nonblind_individual_visual_judgment; no temperature/waterproof claim","review_complete":True,"field_status":statuses,"field_provenance":prov})
 assert len(entries)==8 and sum(x["status"]=="ai_candidate" for x in entries)==7
 result={"schema_version":1,"source_rendered_version":d["version"],"independent_blind_review":False,"winter_outdoor_reviewed":True,"physical_warmth_verified":False,"entries":entries};result["version"]="aw-targeted-review-"+hashlib.sha256(json.dumps(result,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:20]
 target=AUDIT/"targeted-recipes.batch04.native-review.json"
 if target.exists() and json.loads(target.read_text())!=result:raise SystemExit("Targeted review changed; refusing overwrite")
 target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n");print(json.dumps({"version":result["version"],"accepted":7,"held":1},ensure_ascii=False))
if __name__=="__main__":main()
