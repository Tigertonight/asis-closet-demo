#!/usr/bin/env python3
"""Register five exact-structure dresses and three winter outerwear families."""
from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.build_selfit_aw_generated_garment_batch import build, stable_write
from scripts.prepare_selfit_garment_asset import prepare


AUDIT = ROOT / "docs/audits/20260904-aw-supply/generated-garments/batch05"
STATIC = ROOT / "app/static/selfit/assets/content_v2_drafts/aw-targeted-03/garments"
SOURCE_ROOT = Path("/Users/yuanzexiang/.codex/generated_images/01a056c3-ad43-77d1-aed3-35866995a6d6")


SPECS = [
    {"slug":"autumn-dress-earth-melt","token":"n0018","id":"garment_aw_targeted03_dress_melt_earth_01",
     "name":"玫瑰驼柔软针织中长裙","category":"dress","layer_role":"single","tryon_slot":"dress","season_tags":["秋"],
     "prompt":"Create a warm camel and rose-taupe soft knit midi dress with rounded shoulder, softly defined waist and fluid A-line skirt.",
     "personas":["MELT","EASE","FLOU","LOOP"],"palette":"earth","fit":"合体",
     "silhouette":["soft_a_line","rounded_shoulder","defined_waist"],
     "observation":{"subcategory":"soft_knit_midi_dress","neckline":"crew","sleeve":"long","length":"midi","volume":"soft_a_line","construction":"knit_waist_panel","pattern":"solid","decoration":"low","material_appearance":"soft_fine_knit","main_colors":["rose_taupe","warm_camel"]},
     "evidence":"玫瑰驼针织裙以圆肩、柔和收腰和流动 A 线形成温和日常轮廓，面料视觉不透。",
     "targets":["MELT×earth×autumn"],"source_output":str(SOURCE_ROOT/"exec-bb098185-0e49-4d2d-8a4a-a4228740c3c0.png")},
    {"slug":"autumn-dress-ocean-mute","token":"n0019","id":"garment_aw_targeted03_dress_mute_ocean_01",
     "name":"雾霾海蓝直线衬衫裙","category":"dress","layer_role":"single","tryon_slot":"dress","season_tags":["秋"],
     "prompt":"Create a muted slate-ocean-blue straight midi shirt dress with crisp collar, concealed placket and clean vertical line.",
     "personas":["MUTE","ICED","JADE","LOOP"],"palette":"ocean","fit":"合体",
     "silhouette":["long_column","clean_vertical","subtle_waist"],
     "observation":{"subcategory":"concealed_placket_shirt_dress","neckline":"small_shirt_collar","sleeve":"long","length":"midi","volume":"straight","construction":"concealed_placket_subtle_princess_seams","pattern":"solid","decoration":"minimal","material_appearance":"matte_woven","main_colors":["slate_ocean_blue"]},
     "evidence":"雾霾海蓝衬衫裙以暗门襟、清楚小领和连续纵线表达低装饰与收净感。",
     "targets":["MUTE×ocean×autumn"],"source_output":str(SOURCE_ROOT/"exec-b7e67a5c-c0e6-4ebf-8093-72f3c03df4b5.png")},
    {"slug":"autumn-dress-mono-oops","token":"n0020","id":"garment_aw_targeted03_dress_oops_mono_01",
     "name":"炭灰单侧收褶错位中长裙","category":"dress","layer_role":"single","tryon_slot":"dress","season_tags":["秋"],
     "prompt":"Create a charcoal long-sleeve midi dress with one diagonal waist seam and one controlled offset wrap panel.",
     "personas":["OOPS","EDGE","VOID","MUTE"],"palette":"mono","fit":"合体",
     "silhouette":["stable_column","single_offset_wrap","diagonal_waist"],
     "observation":{"subcategory":"single_offset_wrap_midi_dress","neckline":"crew","sleeve":"long","length":"midi","volume":"straight","construction":"diagonal_waist_single_side_gather","pattern":"solid","decoration":"low","material_appearance":"matte_jersey","main_colors":["charcoal"]},
     "evidence":"炭灰裙只用一条斜腰线和单侧收褶形成可解释错位，其余轮廓稳定。",
     "targets":["OOPS×mono×autumn"],"source_output":str(SOURCE_ROOT/"exec-b2a088f2-2ae1-4b41-91c6-0c8684e171ec.png")},
    {"slug":"autumn-dress-pastel-oops","token":"n0021","id":"garment_aw_targeted03_dress_oops_pastel_01",
     "name":"粉蓝斜片错位中长裙","category":"dress","layer_role":"single","tryon_slot":"dress","season_tags":["秋"],
     "prompt":"Create a powder-blue midi dress with one soft-blush offset side panel following a coherent diagonal seam.",
     "personas":["OOPS","EDGE","MELT","LOOP"],"palette":"pastel","fit":"合体",
     "silhouette":["stable_a_line","single_offset_panel","defined_waist"],
     "observation":{"subcategory":"pastel_offset_panel_midi_dress","neckline":"crew","sleeve":"long","length":"midi","volume":"a_line","construction":"single_diagonal_blush_panel","pattern":"colorblock","decoration":"low","material_appearance":"smooth_matte_woven","main_colors":["powder_blue","soft_blush"]},
     "evidence":"粉蓝主身与一块柔粉斜片共用同一方向线，错位集中且不形成随机拼接。",
     "targets":["OOPS×pastel×autumn"],"source_output":str(SOURCE_ROOT/"exec-eee6e83c-d414-4266-ab42-4d4080991147.png")},
    {"slug":"autumn-dress-earth-void","token":"n0022","id":"garment_aw_targeted03_dress_void_earth_01",
     "name":"泥褐包裹茧形中长裙","category":"dress","layer_role":"single","tryon_slot":"dress","season_tags":["秋"],
     "prompt":"Create an earthy taupe-brown cocoon wrap midi dress with protective volume and one subtle offset closure.",
     "personas":["VOID","WABI","EASE","LOOP"],"palette":"earth","fit":"宽松",
     "silhouette":["cocoon_wrap","protective_volume","single_offset_closure"],
     "observation":{"subcategory":"cocoon_wrap_midi_dress","neckline":"wrap_v","sleeve":"long_dropped","length":"midi","volume":"cocoon","construction":"single_offset_button_wrap","pattern":"solid","decoration":"minimal","material_appearance":"soft_matte_woven","main_colors":["earth_taupe_brown"]},
     "evidence":"泥褐连衣裙以包裹体积和一处偏置闭合表达保护感，没有破片或多余装饰。",
     "targets":["VOID×earth×autumn"],"source_output":str(SOURCE_ROOT/"exec-c3bfa959-129d-4059-a4fc-0d94c26a9ddf.png")},
    {"slug":"winter-coat-mono-noir-stand","token":"n0023","id":"garment_aw_targeted03_outer_noir_mono_01",
     "name":"墨黑高立领强肩长外套","category":"outer","season_tags":["秋","冬"],
     "prompt":"Create a deep charcoal-black strong-shoulder long coat with sculpted square shoulder, high stand collar and concealed closure.",
     "personas":["NOIR","EDGE","ICED","MUTE"],"palette":"mono","fit":"合体",
     "silhouette":["strong_shoulder","long_column","stand_collar"],
     "observation":{"subcategory":"strong_shoulder_stand_collar_coat","neckline":"high_stand_collar","sleeve":"long","length":"maxi","volume":"shaped_column","construction":"concealed_front_sculpted_seams","pattern":"solid","decoration":"minimal","material_appearance":"dense_matte_wool_like","main_colors":["deep_charcoal_black"]},
     "evidence":"墨黑长外套以高立领、强肩和连续雕塑分割形成锐利纵线，与普通翻领风衣家族不同。",
     "targets":["NOIR×mono×winter"],"source_output":str(SOURCE_ROOT/"exec-1e8b336a-2fd6-403e-8ee9-15f29ce5cbb8.png")},
    {"slug":"winter-coat-mono-void-wrap","token":"n0024","id":"garment_aw_targeted03_outer_void_mono_01",
     "name":"炭灰高围领错位包裹大衣","category":"outer","season_tags":["秋","冬"],
     "prompt":"Create a charcoal cocoon wrap coat with dropped shoulder, one off-center wrap closure and soft funnel collar.",
     "personas":["VOID","WABI","EASE","LOOP"],"palette":"mono","fit":"宽松",
     "silhouette":["cocoon_wrap","dropped_shoulder","offset_closure"],
     "observation":{"subcategory":"funnel_collar_cocoon_wrap_coat","neckline":"soft_funnel_wrap","sleeve":"long_dropped","length":"maxi","volume":"rounded_cocoon","construction":"single_offset_button_wrap","pattern":"solid","decoration":"minimal","material_appearance":"dense_matte_wool_like","main_colors":["charcoal"]},
     "evidence":"炭灰大衣以高围领、圆量和单一错位门襟形成包裹感，未使用随机破片。",
     "targets":["VOID×mono×winter"],"source_output":str(SOURCE_ROOT/"exec-b6f2aba1-f897-425c-b8f6-df0c27afd367.png")},
    {"slug":"winter-coat-jewel-wabi-teal","token":"n0025","id":"garment_aw_targeted03_outer_wabi_jewel_01",
     "name":"深青靛自然弧线茧形大衣","category":"outer","season_tags":["秋","冬"],
     "prompt":"Create a deep teal-indigo naturally textured cocoon coat with quiet curved seams and a clean closing line.",
     "personas":["WABI","VOID","EASE","JADE"],"palette":"jewel","fit":"宽松",
     "silhouette":["natural_cocoon","curved_seam","clean_closure"],
     "observation":{"subcategory":"textured_curved_seam_cocoon_coat","neckline":"soft_stand","sleeve":"long","length":"maxi","volume":"natural_cocoon","construction":"single_button_curved_seams","pattern":"solid","decoration":"minimal","material_appearance":"subtle_textured_woven","main_colors":["deep_teal_indigo"]},
     "evidence":"深青靛大衣用自然织物观感和弧线分割表达安静手作感，没有拼布或毛边堆叠。",
     "targets":["WABI×jewel×winter"],"source_output":str(SOURCE_ROOT/"exec-d035b346-2abf-4285-8bc4-912635760359.png")},
]


def main() -> None:
    for row in SPECS:
        source = Path(row["source_output"])
        raw = AUDIT / "raw" / f"{row['slug']}-raw-v1.png"
        prepared = AUDIT / "prepared" / f"{row['slug']}-v1.png"
        qa_path = AUDIT / "qa" / f"{row['slug']}-v1.json"
        stable_write(raw, source.read_bytes())
        if not prepared.exists():
            qa = prepare(raw, prepared)
            qa_path.parent.mkdir(parents=True, exist_ok=True)
            qa_path.write_text(json.dumps(qa, ensure_ascii=False, indent=2) + "\n")
    result = build(specs=SPECS, audit=AUDIT, static=STATIC,
                   batch_id="aw-generated-garments-05",
                   prompt_version="selfit-aw-targeted-structure-v1")
    target = AUDIT / "manifest.json"
    if target.exists() and json.loads(target.read_text()) != result:
        raise SystemExit("Generated garment manifest changed; refusing overwrite")
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"version": result["version"], "garments": len(result["garments"]), "published": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
