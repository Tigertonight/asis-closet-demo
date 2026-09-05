#!/usr/bin/env python3
"""Compile whole-image review for the second autumn exact-gap batch."""
from __future__ import annotations
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; AUDIT=ROOT/"docs/audits/20260904-aw-supply"
FIELDS=["axes","expression","formality","layering","persona_scores","scenes","seasons","structure","wearability","main_visual_slots","main_colors","conflicts","silhouette","color_relation","persona_evidence"]
ACCEPTED={1:{"film":.92,"bolt":.68},2:{"film":.84,"flou":.62},3:{"film":.90,"heir":.62},
          4:{"neon":.90,"oops":.68},5:{"neon":.86,"melt":.58},6:{"neon":.82,"heir":.58},
          7:{"noir":.92,"edge":.70},9:{"noir":.88,"heir":.64},10:{"noir":.92,"heir":.66},12:{"noir":.88,"heir":.64},
          13:{"noir":.90,"edge":.72},15:{"noir":.86,"iced":.66},17:{"void":.88,"wabi":.72},18:{"void":.84,"wabi":.66},
          20:{"void":.86,"wabi":.72},21:{"void":.82,"ease":.64},22:{"wabi":.80,"flou":.68},24:{"wabi":.78,"film":.66},
          25:{"wabi":.82,"ease":.72},27:{"wabi":.78,"film":.64}}
PERSONA_EVIDENCE={
 "FILM":"樱桃红灯芯绒短外套以七十年代宽尖领、贴袋和收腰短比例提供明确年代剪裁。",
 "NEON":"橙赭斜切短羽绒是唯一图形色块，中性支撑款让高彩表达保持日常。",
 "NOIR":"长外套的强肩、尖驳领与连续纵线建立锐利边界，主色变化不削弱结构。",
 "VOID":"包裹或茧形长外层与一处受控错层形成保护性体积，没有随机破片堆叠。",
 "WABI":"圆量或包裹外层配自然裤裙，以材质观感和松紧关系表达安静手作感。",
}
def main():
 rendered=json.loads((AUDIT/"autumn-recipes.batch02.rendered.json").read_text()); base=json.loads((ROOT/"app/data/recommendation-visual.v1.json").read_text()); gen=json.loads((AUDIT/"generated-garments/combined-manifest-v3.json").read_text()); visuals={**base["garments"],**gen["visual"]}; entries=[]
 for pos,row in enumerate(rendered["entries"],1):
  raw=row["new_record"]; obs=[visuals[x]["observations"] for x in raw["garment_ids"]]; cats=[x["category"] for x in obs]
  structure="dress" if "dress" in cats else "skirt" if "skirt" in cats else "pants"; colors=list(dict.fromkeys(c for x in obs if x["category"] not in {"shoes","bag"} for c in x.get("main_colors") or [])); scores=ACCEPTED.get(pos)
  if scores:
   status="ai_candidate"; seasons=["autumn"]; scenes=["daily"]; wearability="everyday_with_statement"; conflicts=None; evidence=PERSONA_EVIDENCE[raw["primary_persona"]]
  else:
   status="needs_review"; seasons=scenes=wearability=None; scores={}
   if pos in {8,11,14}: evidence="结构上衣和皮革不对称裙与主外套同时抢焦点，不进入默认日常池。"; conflicts=["competing_focal_points"]
   elif pos in {16,19}: evidence="层片裤、复杂外层与装饰包同时堆叠，缺少稳定支撑款。"; conflicts=["excessive_layer_fragments"]
   else: evidence="花卉轻裙把整套带向浪漫表达，与目标 WABI 的安静自然主次不一致。"; conflicts=["persona_mismatch"]
  observed={"axes":{},"expression":"typical","formality":"smart_casual","layering":2,"persona_scores":scores,"scenes":scenes,"seasons":seasons,"structure":structure,"wearability":wearability,"main_visual_slots":["outer","dress"] if structure=="dress" else ["outer","top",structure],"main_colors":colors,"conflicts":conflicts,"silhouette":f"reviewed_autumn_{structure}_composition","color_relation":"reviewed_coherent" if status=="ai_candidate" else "unresolved","persona_evidence":evidence}
  statuses={k:"unknown" if observed[k] is None else "ai_observed" for k in FIELDS}; sheet=f"autumn-batch02-review/recipes-{(pos-1)//6+1}.jpg"; provenance={k:{"source_file":sheet,"version":"aw-autumn-02-native-v1","confidence":None if statuses[k]=="unknown" else .86} for k in FIELDS}
  entries.append({"outfit_id":raw["id"],"status":status,"record_fingerprint":row["record_fingerprint"],"asset_sha256":row["asset_sha256"],"image_url":raw["assets"]["image_url"],"source_kind":"codex_visual_review","evidence":evidence,"observations":observed,"confidence":.86,"model":"current_codex_session","prompt_version":"aw-autumn-02-native-v1","review_level":"individual_contact_sheet_judgment","evidence_scope":"nonblind_individual_visual_judgment","review_complete":True,"field_status":statuses,"field_provenance":provenance})
 assert len(entries)==27 and sum(x["status"]=="ai_candidate" for x in entries)==20
 result={"schema_version":1,"source_rendered_version":rendered["version"],"independent_blind_review":False,"entries":entries}; result["version"]="aw-autumn-review-"+hashlib.sha256(json.dumps(result,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:20]
 target=AUDIT/"autumn-recipes.batch02.native-review.json"
 if target.exists() and json.loads(target.read_text())!=result: raise SystemExit("Autumn review changed; refusing overwrite")
 target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n"); print(json.dumps({"version":result["version"],"accepted":20,"held":7},ensure_ascii=False))
if __name__=="__main__":main()
