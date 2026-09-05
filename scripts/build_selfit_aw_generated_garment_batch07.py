#!/usr/bin/env python3
"""Register the content-inspected winter threshold coat batch."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.build_selfit_aw_generated_garment_batch import build,stable_write
from scripts.prepare_selfit_garment_asset import prepare

AUDIT=ROOT/"docs/audits/20260904-aw-supply/generated-garments/batch07"
STATIC=ROOT/"app/static/selfit/assets/content_v2_drafts/aw-targeted-05/garments"
SRC=Path("/Users/yuanzexiang/.codex/generated_images/01a056c3-ad43-77d1-aed3-35866995a6d6")

SPECS=[
 {"slug":"winter-coat-pastel-iced-blue","token":"n0034","id":"garment_aw_targeted05_outer_iced_pastel_01","name":"冰雾蓝收净立领长大衣","prompt":"Muted powder-blue precise long winter coat with restrained stand collar and concealed closure.","personas":["ICED","MUTE","JADE","LOOP"],"palette":"pastel","fit":"合体","silhouette":["narrow_long_column","stand_collar","clean_vertical"],"observation":{"subcategory":"clean_stand_collar_long_coat","neckline":"restrained_stand","sleeve":"long","length":"maxi","volume":"narrow_straight","construction":"concealed_front_princess_seams","pattern":"solid","decoration":"minimal","material_appearance":"dense_matte_wool_like","main_colors":["powder_blue"]},"evidence":"冰雾蓝长大衣以收净立领、暗门襟和窄长纵线形成冷静且完整的外层。","targets":["ICED×pastel×winter"],"source_output":str(SRC/"exec-bc0a4750-31dc-4c89-abb8-b35e12ffd19e.png")},
 {"slug":"winter-coat-jewel-wabi-wrap","token":"n0035","id":"garment_aw_targeted05_outer_wabi_jewel_02","name":"深青错位包裹茧形大衣","prompt":"Deep-teal WABI cocoon winter coat with one controlled asymmetric wrap seam.","personas":["WABI","VOID","EASE","LOOP"],"palette":"jewel","fit":"宽松","silhouette":["sculptural_cocoon","single_asymmetric_wrap","rounded_volume"],"observation":{"subcategory":"asymmetric_wrap_cocoon_coat","neckline":"soft_funnel","sleeve":"long_dropped","length":"maxi","volume":"rounded_cocoon","construction":"single_button_asymmetric_wrap","pattern":"solid","decoration":"minimal","material_appearance":"brushed_wool_like","main_colors":["deep_teal"]},"evidence":"深青外层用圆量茧形和一条连续错位包裹线表达手作感，没有碎片或毛边堆叠。","targets":["WABI×jewel×winter"],"source_output":str(SRC/"exec-d7e62205-84d3-4c9d-b65c-3dadf86fa767.png")},
 {"slug":"winter-coat-mono-iced-graphite","token":"n0036","id":"garment_aw_targeted05_outer_iced_mono_01","name":"冷墨灰无领纵线长大衣","prompt":"Cool graphite ICED collarless precise long winter coat with concealed closure.","personas":["ICED","MUTE","NOIR","JADE"],"palette":"mono","fit":"合体","silhouette":["precise_long_column","collarless","shaped_seams"],"observation":{"subcategory":"collarless_precise_long_coat","neckline":"collarless_round","sleeve":"long","length":"maxi","volume":"shaped_straight","construction":"concealed_front_vertical_seams","pattern":"solid","decoration":"minimal","material_appearance":"dense_matte_wool_like","main_colors":["cool_graphite"]},"evidence":"冷墨灰大衣以无领、暗门襟和精确纵向分割构成收净冷感，面料观感厚实不透。","targets":["ICED×mono×winter"],"source_output":str(SRC/"exec-e6e22491-853f-415c-8d8f-bd370a0ec316.png")},
 {"slug":"winter-coat-mono-ease-charcoal","token":"n0037","id":"garment_aw_targeted05_outer_ease_mono_01","name":"炭黑松弛翻领中长大衣","prompt":"Deep-charcoal EASE relaxed polished winter coat with soft tailoring.","personas":["EASE","LOOP","MUTE","HEIR"],"palette":"mono","fit":"宽松","silhouette":["soft_tailored","gentle_dropped_shoulder","controlled_straight"],"observation":{"subcategory":"soft_tailored_midcalf_coat","neckline":"notched_lapel","sleeve":"long_relaxed","length":"maxi","volume":"relaxed_straight","construction":"single_breasted_soft_seams","pattern":"solid","decoration":"minimal","material_appearance":"soft_dense_wool_like","main_colors":["deep_charcoal"]},"evidence":"炭黑翻领大衣保留柔和肩部与松量，长度和纵线又为宽松造型提供收束。","targets":["EASE×mono×winter"],"source_output":str(SRC/"exec-ca4130f4-a37f-4fb1-be73-546c88dca168.png")},
 {"slug":"winter-coat-pastel-heir-rose","token":"n0038","id":"garment_aw_targeted05_outer_heir_pastel_01","name":"灰玫瑰经典收腰长大衣","prompt":"Muted dusty-rose HEIR classic tailored winter coat, sophisticated not sweet.","personas":["HEIR","BOLT","MUTE","LOOP"],"palette":"pastel","fit":"合体","silhouette":["classic_tailored","defined_waist","clean_shoulder"],"observation":{"subcategory":"classic_single_breasted_long_coat","neckline":"notched_lapel","sleeve":"long","length":"maxi","volume":"shaped_straight","construction":"single_breasted_princess_seams","pattern":"solid","decoration":"low","material_appearance":"smooth_dense_wool_like","main_colors":["dusty_rose"]},"evidence":"灰玫瑰大衣的经典肩线、收腰分割与单排扣清楚，粉彩色不依赖甜美装饰。","targets":["HEIR×pastel×winter"],"source_output":str(SRC/"exec-c54df252-a5da-4210-91f5-00cdf8184314.png")},
 {"slug":"winter-coat-ocean-heir-navy","token":"n0039","id":"garment_aw_targeted05_outer_heir_ocean_01","name":"深海蓝系带经典长大衣","prompt":"Deep navy HEIR classic belted winter coat with refined peak collar.","personas":["HEIR","MUTE","NOIR","LOOP"],"palette":"ocean","fit":"合体","silhouette":["classic_belted","clean_shoulder","long_vertical"],"observation":{"subcategory":"classic_belted_long_coat","neckline":"peak_lapel","sleeve":"long","length":"maxi","volume":"shaped_straight","construction":"single_breasted_neat_self_belt","pattern":"solid","decoration":"low","material_appearance":"smooth_dense_wool_like","main_colors":["deep_navy"]},"evidence":"深海蓝长大衣以清楚肩线、峰领和收束系带形成经典比例，腰带完整无裁切。","targets":["HEIR×ocean×winter"],"source_output":str(SRC/"exec-4248560f-8e70-4800-9957-d04427f9ee25.png")},
 {"slug":"winter-coat-jewel-heir-emerald","token":"n0040","id":"garment_aw_targeted05_outer_heir_jewel_01","name":"祖母绿经典双排扣长大衣","prompt":"Deep emerald HEIR classic double-breasted winter coat with crisp shoulder.","personas":["HEIR","NOIR","JADE","BOLT"],"palette":"jewel","fit":"合体","silhouette":["classic_double_breasted","crisp_shoulder","long_straight"],"observation":{"subcategory":"classic_double_breasted_long_coat","neckline":"notched_lapel","sleeve":"long","length":"maxi","volume":"shaped_straight","construction":"double_breasted_princess_seams","pattern":"solid","decoration":"low","material_appearance":"smooth_dense_wool_like","main_colors":["deep_emerald"]},"evidence":"祖母绿大衣的清楚肩线、双排扣与长直轮廓表达经典秩序，高彩只集中在主衣。","targets":["HEIR×jewel×winter"],"source_output":str(SRC/"exec-dc456820-c891-4395-b86a-3a5583713e4d.png")},
 {"slug":"winter-coat-earth-ease-camel","token":"n0041","id":"garment_aw_targeted05_outer_ease_earth_01","name":"暖驼松弛系带长大衣","prompt":"Warm camel EASE relaxed soft-tailored belted winter coat.","personas":["EASE","HEIR","LOOP","MELT"],"palette":"earth","fit":"宽松","silhouette":["relaxed_belted","gentle_dropped_shoulder","long_soft_line"],"observation":{"subcategory":"relaxed_belted_long_coat","neckline":"broad_notched_lapel","sleeve":"long_relaxed","length":"maxi","volume":"relaxed_straight","construction":"single_breasted_neat_self_belt","pattern":"solid","decoration":"low","material_appearance":"plush_matte_wool_like","main_colors":["warm_camel"]},"evidence":"暖驼大衣以柔和落肩和可收束腰带平衡松量，不是无边界的宽上宽下。","targets":["EASE×earth×winter"],"source_output":str(SRC/"exec-34310eae-5e61-435b-a6ed-c468b9285904.png")},
]

def main():
 for row in SPECS:
  source=Path(row["source_output"]); raw=AUDIT/"raw"/f"{row['slug']}-raw-v1.png"; prepared=AUDIT/"prepared"/f"{row['slug']}-v1.png"; qa=AUDIT/"qa"/f"{row['slug']}-v1.json"
  stable_write(raw,source.read_bytes())
  if not prepared.exists():
   report=prepare(raw,prepared); qa.parent.mkdir(parents=True,exist_ok=True); qa.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
 result=build(specs=SPECS,audit=AUDIT,static=STATIC,batch_id="aw-generated-garments-07",prompt_version="selfit-aw-threshold-winter-v1")
 result["binding_method"]="individual_contact_sheet_and_full_resolution_content_inspection"
 target=AUDIT/"manifest.json"
 if target.exists() and json.loads(target.read_text())!=result: raise SystemExit("Batch07 manifest changed; refusing overwrite")
 target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
 print(json.dumps({"version":result["version"],"garments":len(result["garments"]),"published":False},ensure_ascii=False))

if __name__=="__main__": main()
