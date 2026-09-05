"""Compile native visual review of 29 coverage-only parent revisions."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; AUDIT=ROOT/"docs/audits/20260904-aw-supply"
FIELDS=["axes","expression","formality","layering","persona_scores","scenes","seasons","structure","wearability","main_visual_slots","main_colors","conflicts","silhouette","color_relation","persona_evidence"]

# token: status, structure, expression, persona scores, main colors, evidence, conflict
R={
"o0023":("needs_review","pants","easy",{"mute":.65,"iced":.6},["ice_blue","denim_blue","black"],"不透蓝衬衫已替换，但蓬袖内层与短收口外套的袖量仍需结构复核。","outer_inner_volume_unverified"),
"o0031":("ai_candidate","pants","easy",{"iced":.86,"loop":.58},["ice_blue","silver"],"不透冰蓝长袖衬衫配同色宽裤、蓝包和银色尖头鞋，长线收净且主次清楚。",None),
"o0041":("ai_candidate","skirt","typical",{"iced":.84,"flou":.62},["ice_blue","silver","black"],"不透冰蓝衬衫配斜向光泽长裙和银色尖头鞋，黑包压住亮度；冷感来自长线与材质观感。",None),
"o0044":("ai_candidate","skirt","easy",{"iced":.78,"mute":.72,"heir":.55},["ice_blue","taupe"],"不透抽褶蓝衬衫配灰褐直中裙、长靴和蓝托特，色块安静，长度适合秋季日常。",None),
"o0054":("needs_review","pants","easy",{"iced":.65,"heir":.58},["ice_blue","taupe","denim_blue"],"覆盖已修复，但抽褶蓬袖衬衫与合体西装外套的袖量没有穿着证据。","outer_inner_volume_unverified"),
"o0123":("ai_candidate","pants","easy",{"melt":.76,"ease":.68,"flou":.62},["ice_blue","ivory","pale_pink"],"不透抽褶蓝衬衫配奶油软裤，花纱包为小面积浪漫点，酒红玛丽珍鞋稳定下盘。",None),
"o0134":("needs_review","skirt","typical",{"melt":.7,"flou":.68},["pale_pink","ivory","sage"],"不透粉针织已替换，但花纱裙、珍珠软包和花饰鞋同时为焦点，不进默认日常。","multiple_focal_competition"),
"o0181":("ai_candidate","pants","easy",{"melt":.8,"flou":.72,"ease":.58},["ice_blue","pale_pink","ivory"],"不透抽褶蓝衬衫配粉白软裤，花纱包和酒红玛丽珍鞋体量受控，柔软圆线清楚。",None),
"o0186":("ai_candidate","pants","easy",{"iced":.88,"loop":.62,"mute":.58},["ice_blue","ivory"],"不透冰蓝衬衫、锥裤、蓝低跟鞋和奶油包构成清楚同类色，覆盖与主次均成立。",None),
"o0279":("needs_review","skirt","easy",{"flou":.7,"heir":.62},["ice_blue","ivory","burgundy"],"蓝抽褶衬衫与奶油 A 裙协调，但与 o0756 主衣鞋结构近似，只换包不能算独立供给。","near_duplicate_recomposition"),
"o0396":("needs_review","skirt","easy",{"noir":.68,"mute":.65},["charcoal","black","pale_pink"],"不透炭灰中裙已修复覆盖，但黑粉多带包仍与清简上下装竞争，须换素包。","accessory_language_competition"),
"o0480":("ai_candidate","pants","easy",{"iced":.86,"mute":.68,"loop":.6},["ice_blue","sage","ivory"],"不透冰蓝衬衫与同色直裤组成收净长线，灰绿托特和米白后绊鞋低装饰。",None),
"o0516":("needs_review","pants","easy",{"iced":.85,"loop":.6},["ice_blue"],"成套本身清楚，但与 o0186 的冰蓝衬衫裤装、蓝鞋包几乎同构，不能作为独立新增。","near_duplicate_recomposition"),
"o0526":("ai_candidate","pants","easy",{"iced":.82,"mute":.74,"noir":.55},["ice_blue","black","silver"],"不透冰蓝衬衫配黑阔裤和黑托特，银尖头鞋形成小面积冷亮点，主次明确。",None),
"o0536":("ai_candidate","skirt","easy",{"iced":.88,"heir":.6,"loop":.58},["ice_blue"],"不透冰蓝衬衫、蓝 A 裙、蓝包鞋同类色完整，衬衫直线和裙摆提供结构区别。",None),
"o0648":("ai_candidate","pants","typical",{"flou":.74,"melt":.64,"ease":.58},["ice_blue","pale_pink","taupe"],"不透蓝抽褶衬衫配浅蓝阔裤，花纱包集中浪漫点，灰褐长靴提供秋季重量。",None),
"o0668":("ai_candidate","skirt","easy",{"melt":.8,"flou":.7,"ease":.55},["ice_blue","ivory","pale_pink"],"不透蓝抽褶衬衫配奶油褶裙和粉白运动鞋，花纱包与裙的柔软线条呼应但不遮盖主结构。",None),
"o0670":("ai_candidate","skirt","easy",{"iced":.78,"mute":.72,"heir":.62},["ivory","blue_gray","taupe"],"不透米白船领上衣配蓝灰直中裙、灰褐短靴和奶油包，纵线和色块克制。",None),
"o0677":("needs_review","skirt","typical",{"flou":.72,"melt":.68},["pale_pink","ivory","sage"],"不透粉针织、花纱长裙、花饰鞋和粉软包仍然同时抢焦点。","multiple_focal_competition"),
"o0736":("needs_review","pants","easy",{"flou":.65,"heir":.58},["ice_blue","ivory","burgundy"],"覆盖已修复，蓝衬衫与奶油裤易穿，但酒红繁饰结构包成为不必要第二焦点。","accessory_language_competition"),
"o0746":("ai_candidate","pants","easy",{"ease":.76,"flou":.68,"loop":.62},["ice_blue","ivory","taupe"],"不透蓝抽褶衬衫配奶油软裤，蓝托特和灰褐长靴保持低装饰，松量有下装收束。",None),
"o0756":("ai_candidate","skirt","easy",{"flou":.74,"heir":.64,"melt":.6},["ice_blue","ivory","burgundy"],"不透蓝抽褶衬衫配奶油 A 裙，素包和圆头玛丽珍鞋让流动领袖成为唯一柔软焦点。",None),
"o0766":("needs_review","skirt","typical",{"flou":.72,"melt":.62},["pale_pink","ivory","sage","ice_blue"],"覆盖已修复，但粉针织、花纱裙、透明蓝包和花饰鞋仍过度集中浪漫细节。","multiple_focal_competition"),
"o0875":("ai_candidate","pants","easy",{"iced":.74,"melt":.64,"loop":.58},["ice_blue","pale_pink","taupe"],"不透蓝抽褶衬衫与浅蓝阔裤形成长线，粉包只作小面积柔和点，长靴增加秋季重量。",None),
"o0883":("needs_review","pants","typical",{"flou":.68,"oops":.55},["ivory","pale_pink","sage"],"米白不透上衣已解决覆盖，但花纱拼裤与花纱包重复复杂母题，须换素包。","accessory_language_competition"),
"o0885":("ai_candidate","pants","easy",{"ease":.7,"film":.64,"flou":.58},["ice_blue","denim_blue","pale_pink","burgundy"],"不透蓝抽褶衬衫配直筒牛仔，粉包和酒红玛丽珍鞋提供受控暖色点，适合轻松日常。",None),
"o0895":("ai_candidate","skirt","easy",{"iced":.74,"mute":.7,"flou":.58},["ice_blue","pale_pink","taupe"],"不透蓝抽褶衬衫配蓝灰直中裙，粉包为小面积点色，灰褐短靴稳定纵线。",None),
"o0903":("needs_review","pants","typical",{"bolt":.72,"heir":.6},["ivory","burgundy"],"米白不透内层已补，但刺绣披肩外套、装饰裤和酒红鞋仍偏礼仪且多焦点。","multiple_focal_occasion"),
"o0904":("needs_review","pants","typical",{"flou":.65,"oops":.58},["ivory","ice_blue","pale_pink","sage"],"覆盖已修复，但蓝蓬袖衬衫与收口短外套的袖量未知，花纱拼裤又是强焦点。","outer_inner_volume_unverified")}

def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()
def main():
 d=json.loads((AUDIT/"repairs.batch03.rendered.json").read_text());entries=[]
 for pos,row in enumerate(d["entries"],1):
  status,structure,expression,scores,colors,evidence,conflict=R[row["source_token"]]
  obs={"axes":{},"expression":expression,"formality":"smart_casual","layering":2 if "outer" in [p["slot"] for p in row["layout_qa"]["placements"]] else 1,
   "persona_scores":scores,"scenes":["daily"] if status=="ai_candidate" else None,"seasons":["autumn"] if status=="ai_candidate" else None,
   "structure":structure,"wearability":"everyday" if status=="ai_candidate" else None,"main_visual_slots":[structure],"main_colors":colors,
   "conflicts":[conflict] if conflict else None,"silhouette":f"reviewed_{structure}_composition","color_relation":"controlled_or_review_pending","persona_evidence":evidence}
  fs={k:("unknown" if k=="axes" or obs[k] is None else "ai_observed") for k in FIELDS}
  prov={k:{"source_file":f"repairs-batch03-review/recipes-{(pos-1)//6+1}.jpg","version":"aw-coverage-repair-native-v1","confidence":None if fs[k]=="unknown" else .8} for k in FIELDS}
  entries.append({"outfit_id":row["new_record"]["id"],"source_token":row["source_token"],"status":status,"record_fingerprint":row["record_fingerprint"],
   "asset_sha256":row["asset_sha256"],"image_url":row["new_record"]["assets"]["image_url"],"source_kind":"codex_visual_review","evidence":evidence,
   "observations":obs,"confidence":.8,"model":"current_codex_session","prompt_version":"aw-coverage-repair-native-v1",
   "review_level":"individual_contact_sheet_judgment","evidence_scope":"nonblind_individual_visual_judgment","review_complete":True,
   "field_status":fs,"field_provenance":prov})
 assert set(R)=={e["source_token"] for e in entries} and sum(e["status"]=="ai_candidate" for e in entries)==17
 result={"schema_version":1,"source_rendered_version":d["batch_id"],"independent_blind_review":False,"winter_outdoor_reviewed":False,"entries":entries}
 result["version"]="aw-coverage-review-"+digest(result)[:20]
 target=AUDIT/"repairs.batch03.native-review.json"
 if target.exists() and json.loads(target.read_text())!=result:raise SystemExit("Review changed; refusing overwrite")
 target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n");print(result["version"],17,12)
if __name__=="__main__":main()
