"""Compile native visual judgments for AW recomposition batch 01."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs/audits/20260904-aw-supply"

# hero: status, evidence, expression, structure, persona scores, colors, silhouette, conflict
REVIEWS = {
"g0021":("ai_candidate","粉色短绒开衫、贴身米白内层与灰褐直筒裤主次明确；黑玛丽珍鞋稍硬但不竞争，适合柔软日常。","easy","pants",{"melt":.82,"loop":.58,"heir":.45},["pale_pink","ivory","taupe"],"cropped_soft_outer_fitted_inner_straight_pants",None),
"g0051":("ai_candidate","棕蓝复古短夹克搭白衬衫与灰褐直筒裤，运动鞋降低工作服厚重感，色彩和年代语汇连续。","easy","pants",{"film":.82,"ease":.66,"loop":.52},["brown","washed_blue","white","taupe"],"boxy_short_outer_straight_pants",None),
"g0057":("ai_candidate","黑色交领外套是唯一结构焦点，米白内层、黑阔裤、黑鞋包稳定支撑；东方纵线清楚但不成套戏服化。","typical","pants",{"jade":.86,"mute":.62,"heir":.55},["black","ivory","burgundy"],"waisted_wrap_outer_wide_long_pants",None),
"g0066":("ai_candidate","长黑皮感风衣的强肩和长线主导，米白内层、炭灰阔裤和尖头短靴维持锐利边界。","typical","pants",{"noir":.9,"mute":.58,"edge":.5},["black","charcoal","ivory"],"strong_shoulder_long_outer_wide_long_pants",None),
"g0369":("ai_candidate","炭灰素开衫、米白贴身针织和浅蓝灰锥裤装饰低，蓝色鞋包形成受控同类色变化。","easy","pants",{"mute":.82,"iced":.67,"loop":.64},["charcoal","ivory","ice_blue"],"relaxed_cardigan_fitted_inner_tapered_pants",None),
"g0372":("ai_candidate","奶白棕领短夹克配灰褐贴身内层和直筒牛仔裤，上松下直；棕包和复古运动鞋保持日常一致。","easy","pants",{"ease":.84,"film":.68,"loop":.58},["ivory","brown","taupe","denim_blue"],"soft_short_outer_fitted_inner_straight_jeans",None),
"g0381":("ai_candidate","奶白灰边宽开衫配炭灰贴身背心与阔裤，松紧关系成立；鞋包低装饰，模块复用感明确。","easy","pants",{"loop":.84,"mute":.68,"ease":.58},["ivory","gray","charcoal","taupe"],"oversized_cardigan_fitted_inner_wide_pants",None),
"g0387":("ai_candidate","藏蓝奶油边短开衫、米白高领和灰褐直筒中裙比例规整，金扣是唯一精致点，乐福鞋和结构包协调。","easy","skirt",{"heir":.88,"loop":.64,"mute":.58},["navy","ivory","taupe"],"cropped_classic_cardigan_straight_midi_skirt",None),
"g0390":("ai_candidate","灰褐错位外层的茧型和不齐摆为主视觉，贴身灰褐内层、米色素阔裤与低装饰靴包提供稳定基底。","typical","pants",{"wabi":.86,"void":.64,"ease":.6},["taupe","olive","brown","beige"],"cocoon_asymmetric_outer_wide_long_pants",None),
"g0437":("ai_candidate","粉白长层裙是唯一甜味焦点，炭灰素开衫和米白贴身上衣压低装饰；粉包有呼应但未增加新结构。","easy","skirt",{"melt":.8,"flou":.58,"loop":.48},["pale_pink","ivory","charcoal"],"short_cardigan_fitted_top_soft_tiered_long_skirt",None),
"g0449":("ai_candidate","炭灰开衫与黑灰错层长裙形成包裹纵线，米白内层留出层级，尖头靴和黑包不争焦点。","typical","skirt",{"void":.82,"mute":.74,"loop":.58},["charcoal","black","taupe","ivory"],"relaxed_cardigan_layered_wrap_long_skirt",None),
"g0452":("ai_candidate","棕蓝短工作夹克与米色流动长裙构成长短反差，灰褐内层、棕包和运动鞋维持日常；复古感略强但不冲突。","easy","skirt",{"ease":.76,"film":.73,"wabi":.58},["beige","taupe","brown","washed_blue"],"boxy_short_outer_soft_a_line_long_skirt",None),
"g0459":("ai_candidate","棕蓝橄榄纵拼吊带长裙配炭灰素开衫，长靴与棕包延续复古材料观感，外层没有新增装饰竞争。","typical","dress",{"film":.86,"wabi":.66,"ease":.55},["brown","washed_blue","olive","charcoal"],"short_plain_cardigan_waisted_patchwork_long_dress",None),
"g0462":("ai_candidate","黑色长袖收腰衬衫裙以强肩、贯穿门襟和尖片长摆形成完整长线；酒红短靴只延续内层点色。","typical","dress",{"noir":.92,"edge":.68,"heir":.45},["black","burgundy"],"strong_shoulder_waisted_long_shirt_dress",None),
"g0465":("needs_review","炭灰直筒中长裙本身克制，但藏蓝奶油边金扣开衫把整体推向经典学院；成套更接近 HEIR/LOOP，不能按 MUTE 原目标直接通过。","easy","dress",{"heir":.78,"loop":.7,"mute":.5},["charcoal","navy","ivory","taupe"],"cropped_classic_cardigan_straight_midi_dress","primary_persona_mismatch"),
"g0468":("ai_candidate","米色长袖衬衫长裙由腰带收束，炭灰素开衫、棕长靴和软包保持自然日常；没有额外装饰竞争。","easy","dress",{"ease":.84,"loop":.64,"wabi":.58},["beige","charcoal","brown"],"relaxed_cardigan_belted_long_shirt_dress",None),
"g0477":("ai_candidate","奶油灰蓝模块无袖长裙与藏蓝短开衫形成明确短长比例，浅蓝鞋包同类色呼应；结构变化来自侧抽结和内褶。","easy","dress",{"loop":.86,"iced":.68,"heir":.62},["ivory","navy","blue_gray","ice_blue"],"cropped_classic_cardigan_modular_long_dress",None),
"g0581":("needs_review","奶油粉绒感层裙与 g0437 方案共用炭灰开衫、米白上衣和黑玛丽珍鞋，首屏体感过近；该裙需换成更轻松的上层和鞋包后再审。","easy","skirt",{"melt":.72,"flou":.52,"loop":.45},["ivory","pale_pink","charcoal"],"short_cardigan_fitted_top_soft_tiered_midi_skirt","near_duplicate_recomposition")
}

FIELDS = ["axes","expression","formality","layering","persona_scores","scenes","seasons","structure","wearability","main_visual_slots","main_colors","conflicts","silhouette","color_relation","persona_evidence"]

def digest(v):
    return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()

def main():
    rendered=json.loads((AUDIT/"recompose.batch01.rendered.json").read_text())
    sheets=json.loads((AUDIT/"recompose-batch01-review/manifest.json").read_text())
    assert sheets["source_version"]==rendered["version"]
    entries=[]
    for pos,row in enumerate(rendered["entries"],1):
        status,evidence,expression,structure,scores,colors,silhouette,conflict=REVIEWS[row["hero"]]
        item_categories=[p["slot"] for p in row["layout_qa"]["placements"]]
        obs={"axes":{},"expression":expression,"formality":"smart_casual","layering":2 if "outer" in item_categories else 1,
             "persona_scores":scores,"scenes":["daily"],"seasons":["autumn"],"structure":structure,
             "wearability":"everyday" if status=="ai_candidate" else None,
             "main_visual_slots":[row["new_record"]["slot_roles"][gid] == "hero" and next(p["slot"] for p in row["layout_qa"]["placements"] if p["garment_id"]==gid) for gid in row["new_record"]["garment_ids"] if row["new_record"]["slot_roles"][gid]=="hero"],
             "main_colors":colors,"conflicts":[conflict] if conflict else None,"silhouette":silhouette,
             "color_relation":"controlled_neutral_or_tonal","persona_evidence":evidence}
        conf=.8
        field_status={k:("unknown" if k=="axes" or obs[k] is None else "ai_observed") for k in FIELDS}
        provenance={k:{"source_file":"recompose-batch01-review/recipes-%d.jpg"%((pos-1)//6+1),"version":"aw-recompose-native-v1","confidence":None if field_status[k]=="unknown" else conf} for k in FIELDS}
        entries.append({"outfit_id":row["new_record"]["id"],"hero":row["hero"],"status":status,
                        "record_fingerprint":row["record_fingerprint"],"asset_sha256":row["asset_sha256"],
                        "image_url":row["new_record"]["assets"]["image_url"],"source_kind":"codex_visual_review",
                        "evidence":evidence,"observations":obs,"confidence":conf,"model":"current_codex_session",
                        "prompt_version":"aw-recompose-native-v1","review_level":"individual_contact_sheet_judgment",
                        "evidence_scope":"nonblind_individual_visual_judgment","review_complete":True,
                        "field_status":field_status,"field_provenance":provenance})
    assert set(REVIEWS)=={e["hero"] for e in entries} and sum(e["status"]=="ai_candidate" for e in entries)==16
    result={"schema_version":1,"source_rendered_version":rendered["version"],"independent_blind_review":False,
            "winter_outdoor_reviewed":False,"entries":entries}
    result["version"]="aw-recompose-review-"+digest(result)[:20]
    target=AUDIT/"recompose.batch01.native-review.json"
    if target.exists() and json.loads(target.read_text())!=result: raise SystemExit("Review changed; refusing overwrite")
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"version":result["version"],"candidate":16,"needs_review":2}))

if __name__=="__main__": main()
