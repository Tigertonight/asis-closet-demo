"""Compile native visual judgments for AW recomposition batch 02."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
AUDIT=ROOT/"docs/audits/20260904-aw-supply"
FIELDS=["axes","expression","formality","layering","persona_scores","scenes","seasons","structure","wearability","main_visual_slots","main_colors","conflicts","silhouette","color_relation","persona_evidence"]
REVIEWS={
"g0465":("炭灰短开衫、直筒中长裙、尖头短靴和黑包组成低装饰纵线；同色但衣长与开衩有清楚变化，MUTE 日常成立。","dress",{"mute":.86,"loop":.68,"noir":.5},["charcoal","black"],"short_plain_cardigan_straight_midi_dress"),
"g0581":("粉色贴身长袖上衣和粉白绒感层裙形成柔和同类色，炭灰开衫压住甜度，软运动鞋与米白托特使其明显区别于黑玛丽珍版本。","skirt",{"melt":.84,"ease":.58,"loop":.5},["pale_pink","ivory","charcoal"],"short_plain_cardigan_fitted_top_soft_tiered_midi_skirt")}

def digest(v): return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()

def main():
    rendered=json.loads((AUDIT/"recompose.batch02.rendered.json").read_text())
    sheets=json.loads((AUDIT/"recompose-batch02-review/manifest.json").read_text())
    assert sheets["source_version"]==rendered["version"]
    entries=[]
    for row in rendered["entries"]:
        evidence,structure,scores,colors,silhouette=REVIEWS[row["hero"]]
        hero_gid=next(gid for gid,role in row["new_record"]["slot_roles"].items() if role=="hero")
        hero_slot=next(p["slot"] for p in row["layout_qa"]["placements"] if p["garment_id"]==hero_gid)
        obs={"axes":{},"expression":"easy","formality":"smart_casual","layering":2,"persona_scores":scores,
             "scenes":["daily"],"seasons":["autumn"],"structure":structure,"wearability":"everyday",
             "main_visual_slots":[hero_slot],"main_colors":colors,"conflicts":None,"silhouette":silhouette,
             "color_relation":"controlled_tonal","persona_evidence":evidence}
        status={k:("unknown" if k=="axes" else "ai_observed") for k in FIELDS}
        provenance={k:{"source_file":"recompose-batch02-review/recipes-1.jpg","version":"aw-recompose-native-v1","confidence":None if k=="axes" else .8} for k in FIELDS}
        entries.append({"outfit_id":row["new_record"]["id"],"hero":row["hero"],"status":"ai_candidate",
                        "record_fingerprint":row["record_fingerprint"],"asset_sha256":row["asset_sha256"],
                        "image_url":row["new_record"]["assets"]["image_url"],"source_kind":"codex_visual_review",
                        "evidence":evidence,"observations":obs,"confidence":.8,"model":"current_codex_session",
                        "prompt_version":"aw-recompose-native-v1","review_level":"individual_contact_sheet_judgment",
                        "evidence_scope":"nonblind_individual_visual_judgment","review_complete":True,
                        "field_status":status,"field_provenance":provenance})
    assert set(REVIEWS)=={e["hero"] for e in entries}
    result={"schema_version":1,"source_rendered_version":rendered["version"],"independent_blind_review":False,
            "winter_outdoor_reviewed":False,"entries":entries}
    result["version"]="aw-recompose-review-"+digest(result)[:20]
    target=AUDIT/"recompose.batch02.native-review.json"
    if target.exists() and json.loads(target.read_text())!=result: raise SystemExit("Review changed; refusing overwrite")
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(result["version"])

if __name__=="__main__": main()
