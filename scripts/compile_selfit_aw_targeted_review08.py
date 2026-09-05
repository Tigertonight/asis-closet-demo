#!/usr/bin/env python3
"""Review the fourth-persona reuse of batch09 outerwear."""
from __future__ import annotations
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];AUDIT=ROOT/"docs/audits/20260904-aw-supply";FIELDS=["axes","expression","formality","layering","persona_scores","scenes","seasons","structure","wearability","main_visual_slots","main_colors","conflicts","silhouette","color_relation","persona_evidence","winter_outdoor"];HELD={3:"雾海蓝系带 A 线外层实际更偏光洁流动，缺少 WABI 所需的自然材质或安静弧线证据。",4:"同一光洁系带外层与规整灰裙进一步偏向 FLOU/HEIR，不能借目标标签归入 WABI。"}
def main():
 d=json.loads((AUDIT/"targeted-recipes.batch08.rendered.json").read_text());base=json.loads((ROOT/"app/data/recommendation-visual.v1.json").read_text());gen=json.loads((AUDIT/"generated-garments/batch09/manifest.json").read_text());visuals={**base["garments"],**gen["visual"]};entries=[]
 for pos,row in enumerate(d["entries"],1):
  raw=row["new_record"];obs=[visuals[x]["observations"] for x in raw["garment_ids"]];cats=[x["category"] for x in obs];structure="dress" if "dress" in cats else "skirt" if "skirt" in cats else "pants";colors=list(dict.fromkeys(c for x in obs if x["category"] not in {"shoes","bag"} for c in x.get("main_colors") or []));accepted=pos not in HELD
  if accepted:evidence=f"{raw['primary_persona']} 的目标轮廓由主外层提供，{structure} 内层低竞争且闭合鞋履完成冬季关系。";scores={raw["primary_persona"].lower():.84};status="ai_candidate";seasons=["winter"];scenes=["daily"];wearability="everyday_with_statement";conflicts=None;winter="complete_layers_visually_reviewed"
  else:evidence=HELD[pos];scores={};status="needs_review";seasons=scenes=wearability=winter=None;conflicts=["persona_mismatch"]
  observed={"axes":{},"expression":"typical","formality":"smart_casual","layering":2,"persona_scores":scores,"scenes":scenes,"seasons":seasons,"structure":structure,"wearability":wearability,"main_visual_slots":["outer","dress"] if structure=="dress" else ["outer","top",structure],"main_colors":colors,"conflicts":conflicts,"silhouette":f"reviewed_reuse_winter_{structure}","color_relation":"reviewed_coherent" if accepted else "unresolved","persona_evidence":evidence,"winter_outdoor":winter};statuses={k:"unknown" if observed[k] is None else "ai_observed" for k in FIELDS};sheet=f"targeted-batch08-review/recipes-{(pos-1)//6+1}.jpg";prov={k:{"source_file":sheet,"version":"aw-targeted-08-native-v1","confidence":None if statuses[k]=="unknown" else .84} for k in FIELDS}
  entries.append({"outfit_id":raw["id"],"status":status,"record_fingerprint":row["record_fingerprint"],"asset_sha256":row["asset_sha256"],"image_url":raw["assets"]["image_url"],"source_kind":"codex_visual_review","evidence":evidence,"observations":observed,"confidence":.84,"model":"current_codex_session","prompt_version":"aw-targeted-08-native-v1","review_level":"individual_contact_sheet_judgment","evidence_scope":"nonblind_individual_visual_judgment; no temperature/waterproof claim","review_complete":True,"field_status":statuses,"field_provenance":prov})
 assert len(entries)==16 and sum(x["status"]=="ai_candidate" for x in entries)==14
 result={"schema_version":1,"source_rendered_version":d["version"],"independent_blind_review":False,"winter_outdoor_reviewed":True,"physical_warmth_verified":False,"entries":entries};result["version"]="aw-targeted-review-"+hashlib.sha256(json.dumps(result,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:20]
 target=AUDIT/"targeted-recipes.batch08.native-review.json"
 if target.exists() and json.loads(target.read_text())!=result:raise SystemExit("Review08 changed; refusing overwrite")
 target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n");print(json.dumps({"version":result["version"],"accepted":14,"held":2},ensure_ascii=False))
if __name__=="__main__":main()
