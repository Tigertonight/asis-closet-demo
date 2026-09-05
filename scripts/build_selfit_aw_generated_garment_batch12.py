#!/usr/bin/env python3
"""Register second non-similar families for eight lowest AW conditions."""
from __future__ import annotations
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.build_selfit_aw_generated_garment_batch import build,stable_write
from scripts.prepare_selfit_garment_asset import prepare
AUDIT=ROOT/"docs/audits/20260904-aw-supply/generated-garments/batch12";STATIC=ROOT/"app/static/selfit/assets/content_v2_drafts/aw-targeted-10/garments";SRC=Path("/Users/yuanzexiang/.codex/generated_images/01a056c3-ad43-77d1-aed3-35866995a6d6")
RAW=[
 ("flou-earth-02","n0072","flou_earth_02","可可米瀑布领斗篷长外套","earth",["FLOU","MELT","EASE"],["cape_overlay","waterfall_front","straight_midi"],"waterfall_cape_sleeve_coat",["warm_cocoa_beige"],"exec-862337f6-6afc-4197-b85f-c987b59fa50e.png","斗篷覆层、完整内袖和瀑布前襟形成不同于系带 A 线的流动家族。"),
 ("mute-bright-02","n0073","mute_bright_02","钴蓝立领盒型车衣","bright",["MUTE","ICED","LOOP"],["dropped_straight_shoulder","stand_collar","boxy_knee"],"minimal_boxy_car_coat",["vivid_cobalt_blue"],"exec-f35f4baf-b8e7-43a7-8393-bc2d75d2e56e.png","盒型直身、小立领和暗门襟把高彩限制在极简车衣结构中。"),
 ("noir-earth-02","n0074","noir_earth_02","浓咖皮革强肩长风衣","earth",["NOIR","EDGE","HEIR"],["extended_shoulder","storm_collar","ankle_column"],"leather_power_trench",["deep_espresso_brown"],"exec-04fc8851-0a9e-49e9-b98a-8a5f11875256.png","皮革观感、强肩、高风雨领和及踝直线形成不同于羊毛大衣的 NOIR 力量家族。"),
 ("void-pastel-02","n0075","void_pastel_02","雾蓝曲线绗缝长派克","pastel",["VOID","WABI","MELT"],["sculpted_hood","offset_zip","curved_padded_cocoon"],"quilted_modular_long_parka",["pale_mist_blue"],"exec-0fe93e95-891f-4d3c-acc2-4822d2d4e482.png","错位拉链、连续曲线绗缝和保护性兜帽形成技术感包裹层。"),
 ("neon-earth-02","n0076","neon_earth_02","砖红焦橙斜切拼色长大衣","earth",["NEON","OOPS","EDGE"],["crisp_collar","single_diagonal_block","straight_long"],"two_tone_diagonal_wool_coat",["brick_red","burnt_sienna"],"exec-7b331282-2734-477d-aa0c-ce045bf7f81c.png","仅一块贯穿全身的斜向拼色形成图形表达，与上一件绗缝羽绒家族不同。"),
 ("wabi-bright-02","n0077","wabi_bright_02","柿橙手织感直身和服大衣","bright",["WABI","MELT","EASE"],["wide_full_sleeve","off_center_toggle","straight_midi"],"handwoven_kimono_coat",["vivid_persimmon_orange"],"exec-f7c0185c-56a3-4d0f-b060-aee475bd030d.png","直身、宽袖、单一布扣与不规则织感形成区别于茧形的 WABI 家族。"),
 ("oops-earth-02","n0078","oops_earth_02","橄榄褐曲线错位长大衣","earth",["OOPS","VOID","WABI"],["offset_high_collar","repeated_curved_panels","oversized_column"],"curved_panel_offset_coat",["muted_olive_brown"],"exec-857bb2ce-88fd-42c3-a08a-2081cc9b8c59.png","领口和两条连续弧线构成可解释的错位母题，与陶褐斜线门襟家族不同。"),
 ("edge-pastel-02","n0079","edge_pastel_02","冰紫斜拉链高领锐线大衣","pastel",["EDGE","BOLT","ICED"],["raised_shoulder","funnel_neck","zip_asymmetric_flare"],"funnel_neck_zip_asymmetric_coat",["icy_lavender"],"exec-61f11f5e-9513-4da3-8452-ea3885b8952e.png","高领、斜拉链和折角摆形成不同于翻领粉大衣的锐利家族。"),
]
def specs():
 return [{"slug":f"aw-main-{s}","token":t,"id":f"garment_aw_targeted10_outer_{k}_01","name":n,"prompt":n+"，原创无品牌透明背景秋冬第二主衣家族。","personas":ps,"palette":pal,"fit":"宽松" if p in {"FLOU","VOID","WABI","OOPS"} else "合体","silhouette":sil,"observation":{"subcategory":sub,"neckline":"as_observed","sleeve":"long","length":"midi","volume":"shaped","construction":"distinct_second_family","pattern":"solid_or_single_block","decoration":"controlled","material_appearance":"dense_winter_material_as_observed","main_colors":colors},"evidence":ev,"targets":[f"{x}×{pal}×autumn/winter" for x in ps],"source_output":str(SRC/file)} for s,t,k,n,pal,ps,sil,sub,colors,file,ev in RAW for p in [ps[0]]]
def main():
 rows=specs()
 for row in rows:
  source=Path(row["source_output"]);raw=AUDIT/"raw"/f"{row['slug']}-raw-v1.png";prepared=AUDIT/"prepared"/f"{row['slug']}-v1.png";qa=AUDIT/"qa"/f"{row['slug']}-v1.json";stable_write(raw,source.read_bytes())
  if not prepared.exists():report=prepare(raw,prepared);qa.parent.mkdir(parents=True,exist_ok=True);qa.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
 result=build(specs=rows,audit=AUDIT,static=STATIC,batch_id="aw-generated-garments-12",prompt_version="selfit-aw-second-family-v1");result["binding_method"]="individual_output_binding_verified_visually_and_by_filename";target=AUDIT/"manifest.json"
 if target.exists() and json.loads(target.read_text())!=result:raise SystemExit("Batch12 changed; refusing overwrite")
 target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n");print(json.dumps({"version":result["version"],"garments":8,"published":False},ensure_ascii=False))
if __name__=="__main__":main()
