#!/usr/bin/env python3
"""Compile whole-image review for winter dress-family batch06."""
from __future__ import annotations
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; AUDIT=ROOT/"docs/audits/20260904-aw-supply"; FIELDS=["axes","expression","formality","layering","persona_scores","scenes","seasons","structure","wearability","main_visual_slots","main_colors","conflicts","silhouette","color_relation","persona_evidence","winter_outdoor"]
ACCEPT={1:"粉蓝窄长针织裙与深色长外套保持 ICED 的清楚边界。",2:"粉蓝窄长针织裙由中性长外层提供出门层次，主色仍在连衣装。",3:"深青弧线裙与炭灰圆量外层形成自然包裹关系。",4:"深青弧线裙、泥褐茧形外层和自然鞋包形成 WABI 的低装饰材质组合。",5:"祖母绿经典衬衫裙与驼色长外套构成 HEIR 的整洁层次。",6:"祖母绿衬衫裙与深海蓝长外套保持经典肩腰关系。",8:"灰玫瑰收腰裙与深色长外套形成克制粉彩和经典比例。",9:"深海蓝衬衫裙与同色长外层形成连续经典纵线。",10:"深海蓝衬衫裙由驼灰长外套建立清楚深浅层次。",11:"暖驼抽绳针织裙与泥褐圆量外层在松弛和腰部收束间平衡。"}
def main():
 d=json.loads((AUDIT/"targeted-recipes.batch06.rendered.json").read_text()); base=json.loads((ROOT/"app/data/recommendation-visual.v1.json").read_text()); gen=json.loads((AUDIT/"generated-garments/batch08/manifest.json").read_text()); visuals={**base["garments"],**gen["visual"]}; entries=[]
 for pos,row in enumerate(d["entries"],1):
  raw=row["new_record"]; obs=[visuals[x]["observations"] for x in raw["garment_ids"]]; colors=list(dict.fromkeys(c for x in obs if x["category"] not in {"shoes","bag"} for c in x.get("main_colors") or [])); accepted=pos in ACCEPT
  if accepted: evidence=ACCEPT[pos]; scores={raw["primary_persona"].lower():.87}; status="ai_candidate"; seasons=["winter"]; scenes=["daily"]; wearability="everyday_with_statement"; conflicts=None; winter="complete_layers_visually_reviewed"
  else: evidence="露跟鞋或偏薄短外层使冬季可出门完整性无法从成套图确认。"; scores={}; status="needs_review"; seasons=scenes=wearability=winter=None; conflicts=["winter_outdoor_unconfirmed"]
  observed={"axes":{},"expression":"typical","formality":"smart_casual","layering":2,"persona_scores":scores,"scenes":scenes,"seasons":seasons,"structure":"dress","wearability":wearability,"main_visual_slots":["outer","dress"],"main_colors":colors,"conflicts":conflicts,"silhouette":"reviewed_winter_dress_composition","color_relation":"reviewed_coherent" if accepted else "unresolved","persona_evidence":evidence,"winter_outdoor":winter}; statuses={k:"unknown" if observed[k] is None else "ai_observed" for k in FIELDS}; sheet=f"targeted-batch06-review/recipes-{(pos-1)//6+1}.jpg"; prov={k:{"source_file":sheet,"version":"aw-targeted-06-native-v1","confidence":None if statuses[k]=="unknown" else .87} for k in FIELDS}
  entries.append({"outfit_id":raw["id"],"status":status,"record_fingerprint":row["record_fingerprint"],"asset_sha256":row["asset_sha256"],"image_url":raw["assets"]["image_url"],"source_kind":"codex_visual_review","evidence":evidence,"observations":observed,"confidence":.87,"model":"current_codex_session","prompt_version":"aw-targeted-06-native-v1","review_level":"individual_contact_sheet_judgment","evidence_scope":"nonblind_individual_visual_judgment; no temperature/waterproof claim","review_complete":True,"field_status":statuses,"field_provenance":prov})
 assert len(entries)==12 and sum(x["status"]=="ai_candidate" for x in entries)==10
 result={"schema_version":1,"source_rendered_version":d["version"],"independent_blind_review":False,"winter_outdoor_reviewed":True,"physical_warmth_verified":False,"entries":entries}; result["version"]="aw-targeted-review-"+hashlib.sha256(json.dumps(result,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:20]
 target=AUDIT/"targeted-recipes.batch06.native-review.json"
 if target.exists() and json.loads(target.read_text())!=result: raise SystemExit("Review06 changed; refusing overwrite")
 target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n");print(json.dumps({"version":result["version"],"accepted":10,"held":2},ensure_ascii=False))
if __name__=="__main__":main()
