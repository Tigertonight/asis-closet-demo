"""Compile native review for the second paired-shoe repair batch."""
import hashlib,json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]; AUDIT=ROOT/"docs/audits/20260904-aw-supply"
FIELDS=["axes","expression","formality","layering","persona_scores","scenes","seasons","structure","wearability","main_visual_slots","main_colors","conflicts","silhouette","color_relation","persona_evidence"]
REVIEWS={
"o0797":("needs_review","灰色短靴已解除异跟问题，素蓝长上衣、灰粉蓝多面料阔裤与素托特主次清楚；但整体是 OOPS/EDGE 鲜明表达而非 NEON 秋季默认日常。","typical","pants",{"oops":.8,"edge":.72,"loop":.42},["ice_blue","gray","denim_blue","pale_pink"],"long_clean_top_complex_wide_pants","use_and_primary_persona_recheck",None),
"o1136":("ai_candidate","高彩短泡袖衬衫作为唯一焦点，浅灰直裤、灰米运动鞋和黑素包稳定支撑；短长反差支持 NEON 的可日常鲜明入口。","typical","pants",{"neon":.86,"oops":.62,"edge":.48},["cobalt","hot_pink","lime","ice_blue"],"bright_cropped_volume_top_straight_pants",None,"everyday_with_statement"),
"o1137":("ai_candidate","白色宽松衬衫、浅蓝灰直裤、灰米运动鞋和黑素包均低装饰，比例易穿；视觉更支持 LOOP/MUTE，不以旧 OOPS 名称决定人格。","easy","pants",{"loop":.82,"mute":.76,"ease":.62},["white","ice_blue","black","taupe"],"relaxed_long_shirt_straight_pants",None,"everyday"),
"o1166":("needs_review","蓝色玛丽珍鞋解决异跟问题，素灰包和小耳饰不争焦点；但丹宁、粉黑花纱、束胸和多层不对称长摆仍是高场合表达，不进秋冬日常。","experimental","dress",{"oops":.88,"edge":.72,"neon":.45},["charcoal","denim_blue","pale_pink"],"asymmetric_corset_patchwork_long_dress","occasion_not_daily",None)}

def digest(v): return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()
def main():
    rendered=json.loads((AUDIT/"repairs.batch02.rendered.json").read_text()); entries=[]
    for row in rendered["entries"]:
        status,evidence,expression,structure,scores,colors,silhouette,conflict,wearability=REVIEWS[row["source_token"]]
        hero_gid=next((gid for gid,role in row["new_record"]["slot_roles"].items() if role=="hero"),row["new_record"]["garment_ids"][0])
        hero_slot=next(p["slot"] for p in row["layout_qa"]["placements"] if p["garment_id"]==hero_gid)
        obs={"axes":{},"expression":expression,"formality":"smart_casual","layering":2 if "outer" in [p["slot"] for p in row["layout_qa"]["placements"]] else 1,
             "persona_scores":scores,"scenes":["daily"] if status=="ai_candidate" else ["social","creative"],
             "seasons":["autumn"] if status=="ai_candidate" else None,"structure":structure,"wearability":wearability,
             "main_visual_slots":[hero_slot],"main_colors":colors,"conflicts":[conflict] if conflict else None,
             "silhouette":silhouette,"color_relation":"controlled_support_colors","persona_evidence":evidence}
        fstatus={k:("unknown" if k=="axes" or obs[k] is None else "ai_observed") for k in FIELDS}
        provenance={k:{"source_file":"repairs-batch02-review/recipes-1.jpg","version":"aw-repair-native-v1","confidence":None if fstatus[k]=="unknown" else .8} for k in FIELDS}
        entries.append({"outfit_id":row["new_record"]["id"],"source_token":row["source_token"],"status":status,
          "record_fingerprint":row["record_fingerprint"],"asset_sha256":row["asset_sha256"],"image_url":row["new_record"]["assets"]["image_url"],
          "source_kind":"codex_visual_review","evidence":evidence,"observations":obs,"confidence":.8,"model":"current_codex_session",
          "prompt_version":"aw-repair-native-v1","review_level":"individual_contact_sheet_judgment","evidence_scope":"nonblind_individual_visual_judgment",
          "review_complete":True,"field_status":fstatus,"field_provenance":provenance})
    assert set(REVIEWS)=={e["source_token"] for e in entries} and sum(e["status"]=="ai_candidate" for e in entries)==2
    result={"schema_version":1,"source_rendered_version":rendered["batch_id"],"independent_blind_review":False,"winter_outdoor_reviewed":False,"entries":entries}
    result["version"]="aw-repair-review-"+digest(result)[:20]
    target=AUDIT/"repairs.batch02.native-review.json"; target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(result["version"])
if __name__=="__main__":main()
