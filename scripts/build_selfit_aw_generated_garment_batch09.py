#!/usr/bin/env python3
"""Register eight inspected colour-axis winter outer families."""
from __future__ import annotations
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.build_selfit_aw_generated_garment_batch import build,stable_write
from scripts.prepare_selfit_garment_asset import prepare
AUDIT=ROOT/"docs/audits/20260904-aw-supply/generated-garments/batch09";STATIC=ROOT/"app/static/selfit/assets/content_v2_drafts/aw-targeted-07/garments";SRC=Path("/Users/yuanzexiang/.codex/generated_images/01a056c3-ad43-77d1-aed3-35866995a6d6")
RAW=[
 ("ocean-precise","n0048","ocean_precise","深海蓝立领纵线长大衣","ocean",["MUTE","ICED","JADE","BOLT"],["precise_shoulder","stand_collar","long_column"],"stand_collar_precise_long_coat",["deep_ocean_blue"],"exec-8446c661-0a78-4b35-9f97-a9007cbbfa35.png","深海蓝长外层以立领、精确肩线和暗门襟形成清楚纵向边界。"),
 ("ocean-soft","n0049","ocean_soft","雾海蓝柔和系带A线大衣","ocean",["FLOU","MELT","EASE","WABI"],["soft_rounded_shoulder","controlled_wrap","flowing_a_line"],"soft_wrap_a_line_long_coat",["muted_ocean_blue"],"exec-373b60a9-456f-4ec9-b9b8-db69e01c54d7.png","雾海蓝外层以圆肩、受控系带和流动 A 线形成柔和但完整的冬季外层。"),
 ("earth-precise","n0050","earth_precise","冷蕈褐立领收净长大衣","earth",["ICED","MUTE","JADE","HEIR"],["disciplined_shoulder","stand_collar","narrow_column"],"stand_collar_narrow_long_coat",["cool_mushroom_taupe"],"exec-e67238d2-d081-4e8a-a173-980f816819bb.png","冷蕈褐长外层以小立领、精确肩线和窄长轮廓表达克制结构。"),
 ("earth-soft","n0051","earth_soft","暖陶褐弧线茧形长大衣","earth",["WABI","VOID","MELT","EASE"],["rounded_cocoon","dropped_shoulder","quiet_curved_seam"],"curved_seam_cocoon_long_coat",["warm_clay_taupe"],"exec-597ba771-0d28-4db0-92c2-cf142a7be7d1.png","暖陶褐外层用一处弧线、落肩和完整茧形表达自然包裹感。"),
 ("bright-sharp","n0052","bright_sharp","钴蓝斜领锐线中长大衣","bright",["EDGE","NEON","JADE","NOIR"],["crisp_shoulder","single_asymmetric_lapel","sharp_mid_length"],"single_asymmetric_lapel_coat",["vivid_cobalt"],"exec-3957580d-9f8c-4952-aea6-c6654397b74f.png","钴蓝主衣仅以一条斜领线和清楚肩腰边界形成高彩锐感。"),
 ("bright-soft","n0053","bright_soft","万寿菊黄无领茧形长大衣","bright",["WABI","MELT","EASE","LOOP"],["soft_cocoon","collarless","gentle_dropped_shoulder"],"collarless_soft_cocoon_long_coat",["vivid_marigold"],"exec-24c58983-c74b-4c3e-8932-6e1afea7f4c0.png","万寿菊黄集中在低装饰圆量外层，颜色鲜明但结构保持单纯。"),
 ("jewel-sharp","n0054","jewel_sharp","深红宝石强肩收腰长大衣","jewel",["BOLT","EDGE","NOIR","HEIR"],["sculpted_shoulder","defined_waist","long_straight"],"sculpted_shoulder_jewel_long_coat",["deep_ruby_red"],"exec-3653ad7a-b171-4ee9-9613-7d9026e45496.png","深红宝石大衣以雕塑肩线、克制高领口和收腰纵线形成精致力量感。"),
 ("jewel-soft","n0055","jewel_soft","深紫晶包裹茧形长大衣","jewel",["MELT","FLOU","VOID","WABI"],["soft_wrap_cocoon","rounded_shoulder","single_diagonal_closure"],"amethyst_wrap_cocoon_long_coat",["deep_amethyst"],"exec-79db1481-009d-4d27-9f47-a07477a5fbfc.png","深紫晶外层以圆肩、单一斜向闭合和受控茧形形成柔和包裹感。"),
]
def specs():
 out=[]
 for slug,token,key,name,palette,personas,sil,sub,colors,file,evidence in RAW:
  out.append({"slug":f"winter-coat-{slug}","token":token,"id":f"garment_aw_targeted07_outer_{key}_01","name":name,"prompt":name+"，原创无品牌透明背景冬季主外层。","personas":personas,"palette":palette,"fit":"宽松" if "soft" in key else "合体","silhouette":sil,"observation":{"subcategory":sub,"neckline":"stand_or_wrap_as_observed","sleeve":"long","length":"maxi","volume":"soft_cocoon" if "soft" in key else "shaped_straight","construction":"single_clear_closing_line","pattern":"solid","decoration":"minimal","material_appearance":"dense_matte_wool_like","main_colors":colors},"evidence":evidence,"targets":[f"{p}×{palette}×winter" for p in personas],"source_output":str(SRC/file)})
 return out
def main():
 rows=specs()
 for row in rows:
  source=Path(row["source_output"]);raw=AUDIT/"raw"/f"{row['slug']}-raw-v1.png";prepared=AUDIT/"prepared"/f"{row['slug']}-v1.png";qa=AUDIT/"qa"/f"{row['slug']}-v1.json";stable_write(raw,source.read_bytes())
  if not prepared.exists(): report=prepare(raw,prepared);qa.parent.mkdir(parents=True,exist_ok=True);qa.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
 result=build(specs=rows,audit=AUDIT,static=STATIC,batch_id="aw-generated-garments-09",prompt_version="selfit-aw-colour-axis-outer-v1");result["binding_method"]="individual_order_binding_verified_by_contact_sheet"
 target=AUDIT/"manifest.json"
 if target.exists() and json.loads(target.read_text())!=result:raise SystemExit("Batch09 changed; refusing overwrite")
 target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n");print(json.dumps({"version":result["version"],"garments":len(result["garments"]),"published":False},ensure_ascii=False))
if __name__=="__main__":main()
