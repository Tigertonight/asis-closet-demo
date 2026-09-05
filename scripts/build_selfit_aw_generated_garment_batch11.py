#!/usr/bin/env python3
"""Register eight inspected long-outer families for the lowest AW conditions."""
from __future__ import annotations
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.build_selfit_aw_generated_garment_batch import build,stable_write
from scripts.prepare_selfit_garment_asset import prepare
AUDIT=ROOT/"docs/audits/20260904-aw-supply/generated-garments/batch11";STATIC=ROOT/"app/static/selfit/assets/content_v2_drafts/aw-targeted-09/garments";SRC=Path("/Users/yuanzexiang/.codex/generated_images/01a056c3-ad43-77d1-aed3-35866995a6d6")
RAW=[
 ("flou-earth","n0064","flou_earth","蕈褐流动系带长大衣","earth",["FLOU","MELT","EASE"],["soft_drop_shoulder","wrap_waist","sweeping_a_line"],"fluid_wrap_long_coat",["warm_mushroom_taupe"],"exec-294afd39-7863-418c-9ae3-dbe129f7b831.png","柔软落肩、完整系带和流动长摆构成可日常穿的浪漫外层。"),
 ("mute-bright","n0065","mute_bright","番茄红无领直线长大衣","bright",["MUTE","ICED","LOOP"],["quiet_shoulder","collarless","straight_column"],"collarless_minimal_column_coat",["vivid_tomato_red"],"exec-a8dc276d-dddd-4ea5-a0f6-28ab3d7a7c59.png","鲜明主色被无领、暗门襟和极少分割约束，保持 MUTE 的低装饰直线。"),
 ("noir-earth","n0066","noir_earth","深驼强肩长直大衣","earth",["NOIR","HEIR","EDGE"],["strong_square_shoulder","narrow_peak_lapel","long_power_column"],"double_breasted_power_coat",["deep_camel_brown"],"exec-aff0baad-cacf-489f-ada8-a17a132a1ccb.png","强肩、窄戗驳领和长直下摆在非黑色中保留 NOIR 的力量边界。"),
 ("void-pastel","n0067","void_pastel","雾紫包裹茧形长羽绒","pastel",["VOID","WABI","MELT"],["protective_wrap_collar","dropped_shoulder","padded_cocoon"],"asymmetric_wrap_padded_cocoon",["dusty_pale_lilac"],"exec-7246b9cc-b094-4c7c-8816-3629f194c6f2.png","高包裹领、单一错位闭合和茧形量感形成低负担 VOID 日常表达。"),
 ("neon-earth","n0068","neon_earth","焦橙几何拼线长羽绒","earth",["NEON","OOPS","EDGE"],["high_collar","straight_padded_column","single_graphic_diagonal"],"single_panel_graphic_puffer",["saturated_burnt_orange"],"exec-710e0f8d-360b-4c9e-8e67-4c1531230b1b.png","焦橙主色与一组连续斜向绗线形成 NEON 图形感，其余结构保持单纯。"),
 ("wabi-bright","n0069","wabi_bright","藏红花黄自然茧形长大衣","bright",["WABI","MELT","EASE"],["rounded_drop_shoulder","quiet_curved_seam","organic_cocoon"],"nubby_curved_cocoon_coat",["saturated_saffron_yellow"],"exec-40f9f666-75ac-4a59-b67e-7aa1d94a51a8.png","粗粝观感、圆肩与一处弧线使亮色仍具有自然克制的 WABI 结构。"),
 ("oops-earth","n0070","oops_earth","陶褐错位门襟长大衣","earth",["OOPS","EDGE","VOID"],["offset_collar","asymmetric_placket","stable_long_column"],"offset_placket_long_coat",["rich_terracotta_brown"],"exec-431d88dc-ed22-4844-85d0-b41e6a090178.png","领口、门襟与口袋由同一斜线母题连接，解构具有可解释秩序。"),
 ("edge-pastel","n0071","edge_pastel","冰粉锐线不对称长大衣","pastel",["EDGE","BOLT","HEIR"],["crisp_shoulder","defined_waist","asymmetric_long_hem"],"sharp_asymmetric_long_coat",["icy_blush_pink"],"exec-3654cc82-90d0-443d-a64c-eb5ef96b2afe.png","清楚肩腰、单一斜襟和不对称长摆提供 EDGE 的锐利短长张力。"),
]
def specs():
 return [{"slug":f"aw-main-{s}","token":t,"id":f"garment_aw_targeted09_outer_{k}_01","name":n,"prompt":n+"，原创无品牌透明背景秋冬主外层。","personas":ps,"palette":pal,"fit":"宽松" if any(x in k for x in ("flou","void","wabi")) else "合体","silhouette":sil,"observation":{"subcategory":sub,"neckline":"as_observed","sleeve":"long","length":"midi","volume":"shaped","construction":"single_clear_primary_line","pattern":"solid","decoration":"minimal","material_appearance":"dense_winter_material_as_observed","main_colors":colors},"evidence":ev,"targets":[f"{p}×{pal}×autumn/winter" for p in ps],"source_output":str(SRC/file)} for s,t,k,n,pal,ps,sil,sub,colors,file,ev in RAW]
def main():
 rows=specs()
 for row in rows:
  source=Path(row["source_output"]);raw=AUDIT/"raw"/f"{row['slug']}-raw-v1.png";prepared=AUDIT/"prepared"/f"{row['slug']}-v1.png";qa=AUDIT/"qa"/f"{row['slug']}-v1.json";stable_write(raw,source.read_bytes())
  if not prepared.exists(): report=prepare(raw,prepared);qa.parent.mkdir(parents=True,exist_ok=True);qa.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
 result=build(specs=rows,audit=AUDIT,static=STATIC,batch_id="aw-generated-garments-11",prompt_version="selfit-aw-lowest-condition-long-outer-v1");result["binding_method"]="individual_output_binding_verified_visually_and_by_filename";target=AUDIT/"manifest.json"
 if target.exists() and json.loads(target.read_text())!=result:raise SystemExit("Batch11 changed; refusing overwrite")
 target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n");print(json.dumps({"version":result["version"],"garments":len(result["garments"]),"published":False},ensure_ascii=False))
if __name__=="__main__":main()
