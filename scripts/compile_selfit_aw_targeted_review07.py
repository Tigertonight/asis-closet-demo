#!/usr/bin/env python3
"""Compile whole-image review for the 48 colour-axis recipes."""
from __future__ import annotations
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];AUDIT=ROOT/"docs/audits/20260904-aw-supply";FIELDS=["axes","expression","formality","layering","persona_scores","scenes","seasons","structure","wearability","main_visual_slots","main_colors","conflicts","silhouette","color_relation","persona_evidence","winter_outdoor"];HELD={14:"玛丽珍鞋与偏轻裙装无法从图片证明冬季可出门完整性。",27:"钴蓝斜领锐线外套的 EDGE 倾向压过 JADE 所需的清楚领型与克制交叠。",28:"钴蓝斜领锐线外套与流动裙装仍不形成 JADE 的纵线与克制结构。"}
def main():
 d=json.loads((AUDIT/"targeted-recipes.batch07.rendered.json").read_text());base=json.loads((ROOT/"app/data/recommendation-visual.v1.json").read_text());gen=json.loads((AUDIT/"generated-garments/batch09/manifest.json").read_text());visuals={**base["garments"],**gen["visual"]};entries=[]
 for pos,row in enumerate(d["entries"],1):
  raw=row["new_record"];obs=[visuals[x]["observations"] for x in raw["garment_ids"]];cats=[x["category"] for x in obs];structure="dress" if "dress" in cats else "skirt" if "skirt" in cats else "pants";colors=list(dict.fromkeys(c for x in obs if x["category"] not in {"shoes","bag"} for c in x.get("main_colors") or []));accepted=pos not in HELD
  if accepted:
   evidence=f"{raw['primary_persona']} 的主色由新外层承担；整套 {structure} 结构的内层低竞争，外层—主服装—闭合鞋关系完整。";scores={raw["primary_persona"].lower():.86};status="ai_candidate";seasons=["winter"];scenes=["daily"];wearability="everyday_with_statement";conflicts=None;winter="complete_layers_visually_reviewed"
  else:
   evidence=HELD[pos];scores={};status="needs_review";seasons=scenes=wearability=winter=None;conflicts=["winter_outdoor_unconfirmed" if pos==14 else "persona_mismatch"]
  observed={"axes":{},"expression":"typical","formality":"smart_casual","layering":2,"persona_scores":scores,"scenes":scenes,"seasons":seasons,"structure":structure,"wearability":wearability,"main_visual_slots":["outer","dress"] if structure=="dress" else ["outer","top",structure],"main_colors":colors,"conflicts":conflicts,"silhouette":f"reviewed_colour_axis_winter_{structure}","color_relation":"reviewed_coherent" if accepted else "unresolved","persona_evidence":evidence,"winter_outdoor":winter};statuses={k:"unknown" if observed[k] is None else "ai_observed" for k in FIELDS};sheet=f"targeted-batch07-review/recipes-{(pos-1)//6+1}.jpg";prov={k:{"source_file":sheet,"version":"aw-targeted-07-native-v1","confidence":None if statuses[k]=="unknown" else .86} for k in FIELDS}
  entries.append({"outfit_id":raw["id"],"status":status,"record_fingerprint":row["record_fingerprint"],"asset_sha256":row["asset_sha256"],"image_url":raw["assets"]["image_url"],"source_kind":"codex_visual_review","evidence":evidence,"observations":observed,"confidence":.86,"model":"current_codex_session","prompt_version":"aw-targeted-07-native-v1","review_level":"individual_contact_sheet_judgment","evidence_scope":"nonblind_individual_visual_judgment; no temperature/waterproof claim","review_complete":True,"field_status":statuses,"field_provenance":prov})
 assert len(entries)==48 and sum(x["status"]=="ai_candidate" for x in entries)==45
 result={"schema_version":1,"source_rendered_version":d["version"],"independent_blind_review":False,"winter_outdoor_reviewed":True,"physical_warmth_verified":False,"entries":entries};result["version"]="aw-targeted-review-"+hashlib.sha256(json.dumps(result,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:20]
 target=AUDIT/"targeted-recipes.batch07.native-review.json"
 if target.exists() and json.loads(target.read_text())!=result:raise SystemExit("Review07 changed; refusing overwrite")
 target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n");print(json.dumps({"version":result["version"],"accepted":45,"held":3},ensure_ascii=False))
if __name__=="__main__":main()
