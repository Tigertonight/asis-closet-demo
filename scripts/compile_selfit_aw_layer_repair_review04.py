"""Compile native visual review of 27 inner-volume repair drafts."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];AUDIT=ROOT/"docs/audits/20260904-aw-supply"
FIELDS=["axes","expression","formality","layering","persona_scores","scenes","seasons","structure","wearability","main_visual_slots","main_colors","conflicts","silhouette","color_relation","persona_evidence"]
# token: status, expression, scores, colors, evidence, conflict
R={
"o0052":("ai_candidate","easy",{"iced":.86,"mute":.7},["ice_blue","charcoal","black"],"冰蓝长风衣、贴身无袖内层和同色锥裤层次清楚，黑鞋包压住冷亮色；袖量冲突已解除。",None),
"o0111":("ai_candidate","easy",{"ease":.78,"film":.65,"loop":.55},["taupe","ice_blue","beige","brown"],"灰褐短夹克配贴身蓝 T 和米色锥裤，上短下松有收束；复古包靴延续自然色。",None),
"o0172":("ai_candidate","easy",{"loop":.74,"heir":.66,"ease":.6},["ivory","ice_blue","charcoal"],"奶油短外套、贴身蓝 T 和炭灰阔裤规整易穿；整套更接近 LOOP/HEIR，不沿用旧 WABI 名称。",None),
"o0197":("ai_candidate","typical",{"flou":.84,"melt":.72},["pale_pink","ivory","ice_blue"],"透感花纱外层内已有不透粉色贴身上衣，浅蓝直裤和灰靴稳定，柔软外层成为单一浪漫焦点。",None),
"o0199":("ai_candidate","easy",{"melt":.8,"heir":.66,"flou":.58},["navy","pale_pink","ivory"],"藏蓝短夹克配粉色贴身上衣与粉白软裤，深浅有边界，奶油包和长靴保持日常。",None),
"o0230":("ai_candidate","typical",{"edge":.82,"noir":.66,"iced":.58},["black","ice_blue","charcoal"],"黑皮短夹克、贴身蓝 T 和蓝灰宽裤形成硬软短长对比，灰包与蓝玛丽珍鞋不争焦点。",None),
"o0231":("ai_candidate","easy",{"iced":.78,"loop":.74,"mute":.6},["black","ice_blue"],"黑长外套与蓝 T、蓝灰直裤构成长线，蓝鞋包同类色但体量受控；更接近 ICED/LOOP。",None),
"o0256":("ai_candidate","typical",{"edge":.78,"oops":.7},["gray","black","burgundy","bright"],"灰短开衫、黑贴身内层和黑酒红直裤建立稳定基底，高彩小包为唯一跳色，运动鞋降低攻击性。",None),
"o0285":("needs_review","typical",{"bolt":.72,"heir":.58},["ivory","burgundy","ice_blue"],"贴身蓝 T 解决袖量，但刺绣短外套与蝴蝶结花饰高跟鞋仍同时为礼仪焦点。","multiple_focal_occasion"),
"o0402":("ai_candidate","typical",{"noir":.86,"edge":.7},["black","charcoal"],"黑灰短外套、贴身黑内层和黑阔裤主线完整，黑包克制，系带靴作为局部锐利点。",None),
"o0434":("ai_candidate","typical",{"wabi":.86,"void":.76,"ease":.6},["taupe","olive","brown"],"灰褐茧型错层外套配贴身上衣和直裤，鞋包低装饰；松软包裹感来自轮廓而非做旧堆叠。",None),
"o0461":("ai_candidate","easy",{"loop":.76,"iced":.68},["ice_blue","ivory","bright"],"蓝色长直外套、贴身蓝 T 和奶油锥裤简洁，荧彩运动鞋仅作小面积轻探索；不沿用旧 OOPS 主人格。",None),
"o0507":("needs_review","easy",{"mute":.7,"heir":.6},["ivory","black","ice_blue","brown"],"袖量已解除且风衣裤装清楚，但成套图只显示一只棕色长靴，鞋对展示不完整。","paired_shoe_display_incomplete"),
"o0547":("ai_candidate","easy",{"iced":.86,"mute":.66},["ice_blue","black","ivory"],"合体冰蓝外套配黑贴身内层与冰蓝直裤，浅鞋包低装饰，长线与轻贴合支持 ICED。",None),
"o0595":("needs_review","easy",{"heir":.72,"loop":.58},["navy","ivory","beige","brown"],"藏蓝长外套、米白内层和米色锥裤比例经典，但成套图只显示一只棕长靴。","paired_shoe_display_incomplete"),
"o0680":("ai_candidate","easy",{"melt":.78,"ease":.66,"heir":.55},["ivory","ice_blue","pale_pink"],"奶油短西装、蓝色贴身 T 与奶油宽裤松紧适中，粉白绒靴是柔软焦点；只计秋季，不作冬季保暖承诺。",None),
"o0728":("ai_candidate","typical",{"wabi":.88,"void":.74},["brown","taupe","olive"],"棕褐茧型外套、贴身灰褐上衣和弧线裤形成同色包裹轮廓，软包和长靴延续自然线。",None),
"o0769":("ai_candidate","typical",{"bolt":.8,"heir":.68},["ivory","burgundy","pale_pink"],"奶油酒红短礼仪外套配贴身米白内层和素锥裤，粉包与白运动鞋降低正式度；作为 BOLT 日常鲜明入口。",None),
"o0772":("needs_review","typical",{"flou":.68,"oops":.58},["ivory","pale_pink","sage","ice_blue"],"内层袖量已修复，但花纱拼裤、花饰高跟鞋和蓝包仍缺清楚主次。","multiple_focal_competition"),
"o0901":("needs_review","typical",{"bolt":.72,"flou":.58},["ivory","burgundy","ice_blue"],"袖量已修复，但刺绣短外套、花纱包与花饰靴同时为焦点，不进默认日常。","multiple_focal_competition"),
"o0902":("ai_candidate","easy",{"heir":.8,"loop":.66,"bolt":.55},["navy","ivory","ice_blue","burgundy"],"藏蓝短外套、米白贴身内层和浅蓝宽裤规整，酒红装饰包为单一点色；更接近 HEIR。",None),
"o0950":("needs_review","easy",{"film":.7,"loop":.62},["navy","ice_blue","brown"],"长外套、贴身 T 和棕阔裤已解除袖量冲突，但成套图只显示一只棕长靴。","paired_shoe_display_incomplete"),
"o0991":("ai_candidate","typical",{"jade":.82,"heir":.66},["ivory","black","red","sage"],"奶油短西装配贴身米白内层与墨枝阔裤，灰绿托特和奶油乐福鞋低装饰，东方纵线为主。",None),
"o0992":("ai_candidate","typical",{"jade":.9,"noir":.56},["ivory","black","red"],"墨枝交叠长外套、黑贴身内层与奶油阔裤主次清楚，墨纹托特形成受控重复母题。",None),
"o0993":("ai_candidate","typical",{"jade":.88,"flou":.56},["ivory","black","red","sage"],"墨枝交叠长外套配米白贴身内层和灰绿宽裤，长短、黑白与小红穗关系清楚。",None),
"o1031":("ai_candidate","easy",{"loop":.82,"heir":.68,"film":.6},["taupe","ivory","denim_blue"],"灰褐西装外套、米白贴身内层和直筒牛仔构成可复用模块，鞋包克制。",None),
"o1076":("ai_candidate","typical",{"noir":.9,"edge":.72},["black","charcoal"],"黑皮短夹克、黑贴身内层和黑锥裤形成锐利短长边界，黑鞋包保持主线完整。",None)}

def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()
def main():
 d=json.loads((AUDIT/"repairs.batch04.rendered.json").read_text());entries=[]
 for pos,row in enumerate(d["entries"],1):
  status,expression,scores,colors,evidence,conflict=R[row["source_token"]]
  obs={"axes":{},"expression":expression,"formality":"smart_casual","layering":2,"persona_scores":scores,
   "scenes":["daily"] if status=="ai_candidate" else None,"seasons":["autumn"] if status=="ai_candidate" else None,
   "structure":"pants","wearability":"everyday_with_statement" if status=="ai_candidate" and expression=="typical" else "everyday" if status=="ai_candidate" else None,
   "main_visual_slots":["outer","bottom"],"main_colors":colors,"conflicts":[conflict] if conflict else None,
   "silhouette":"reviewed_layered_pants_composition","color_relation":"controlled_or_review_pending","persona_evidence":evidence}
  fs={k:("unknown" if k=="axes" or obs[k] is None else "ai_observed") for k in FIELDS}
  prov={k:{"source_file":f"repairs-batch04-review/recipes-{(pos-1)//6+1}.jpg","version":"aw-layer-repair-native-v1","confidence":None if fs[k]=="unknown" else .8} for k in FIELDS}
  entries.append({"outfit_id":row["new_record"]["id"],"source_token":row["source_token"],"status":status,"record_fingerprint":row["record_fingerprint"],
   "asset_sha256":row["asset_sha256"],"image_url":row["new_record"]["assets"]["image_url"],"source_kind":"codex_visual_review","evidence":evidence,
   "observations":obs,"confidence":.8,"model":"current_codex_session","prompt_version":"aw-layer-repair-native-v1","review_level":"individual_contact_sheet_judgment",
   "evidence_scope":"nonblind_individual_visual_judgment","review_complete":True,"field_status":fs,"field_provenance":prov})
 assert set(R)=={e["source_token"] for e in entries} and sum(e["status"]=="ai_candidate" for e in entries)==21
 result={"schema_version":1,"source_rendered_version":d["batch_id"],"independent_blind_review":False,"winter_outdoor_reviewed":False,"entries":entries}
 result["version"]="aw-layer-review-"+digest(result)[:20]
 target=AUDIT/"repairs.batch04.native-review.json"
 if target.exists() and json.loads(target.read_text())!=result:raise SystemExit("Review changed; refusing overwrite")
 target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n");print(result["version"],21,6)
if __name__=="__main__":main()
