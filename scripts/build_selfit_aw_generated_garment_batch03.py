#!/usr/bin/env python3
"""Ingest and register the third, exact-gap winter garment batch."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.build_selfit_aw_generated_garment_batch import ROOT, build, stable_write
from scripts.prepare_selfit_garment_asset import prepare


AUDIT = ROOT / "docs/audits/20260904-aw-supply/generated-garments/batch03"
STATIC = ROOT / "app/static/selfit/assets/content_v2_drafts/aw-winter-04/garments"
SOURCE_ROOT = Path("/Users/yuanzexiang/.codex/generated_images/01a056c3-ad43-77d1-aed3-35866995a6d6")


def spec(slug, token, garment_id, name, prompt, personas, palette, fit, silhouette,
         observation, evidence, targets, source):
    return {"slug": slug, "token": token, "id": garment_id, "name": name, "prompt": prompt,
            "personas": personas, "palette": palette, "fit": fit, "silhouette": silhouette,
            "observation": observation, "evidence": evidence, "targets": targets,
            "source_output": str(SOURCE_ROOT / source)}


SPECS = [
    spec("winter-jacket-earth-bolt", "n0009", "garment_aw_winter04_outer_bolt_camel_01",
         "驼棕收腰圆肩短外套", "Create a warm camel-brown cropped wool jacket with a softly defined waist and one restrained rounded shoulder detail.",
         ["BOLT", "HEIR", "FILM", "LOOP"], "earth", "合体", ["cropped", "defined_waist", "soft_sculpted_shoulder"],
         {"subcategory":"cropped_waisted_jacket","neckline":"point_collar","sleeve":"long","length":"hip","volume":"fitted","construction":"concealed_front_princess_seams","pattern":"solid","decoration":"low","material_appearance":"dense_matte_wool_like","main_colors":["camel_brown"]},
         "驼棕短外套以公主线收腰、克制圆肩和短长比例表达日常精致感，没有晚宴式装饰。", ["BOLT×earth×winter"], "exec-351766b6-e8e3-4aaa-962e-ddd4e7192622.png"),
    spec("winter-coat-pastel-bolt", "n0010", "garment_aw_winter04_outer_bolt_blush_01",
         "浅粉收腰A线长外套", "Create a pale blush-pink knee-length wool coat with a gently nipped waist, refined shoulder line and restrained sculptural collar.",
         ["BOLT", "MELT", "HEIR", "FLOU"], "pastel", "合体", ["long_a_line", "defined_waist", "refined_shoulder"],
         {"subcategory":"waisted_a_line_coat","neckline":"sculpted_lapel","sleeve":"long","length":"maxi","volume":"fitted_a_line","construction":"concealed_front_princess_seams","pattern":"solid","decoration":"low","material_appearance":"dense_matte_wool_like","main_colors":["pale_blush"]},
         "浅粉长外套用收腰、公主线与单一折领建立精致肩袖，整体仍是可出门的日常长外层。", ["BOLT×pastel×winter"], "exec-40de37de-9c0c-4526-9bac-b6170f5b1e21.png"),
    spec("winter-coat-pastel-edge", "n0011", "garment_aw_winter04_outer_edge_lilac_01",
         "冰丁香锐线中长外套", "Create an icy lilac structured mid-thigh wool jacket-coat with crisp angular lapels, a defined waist seam and clean sharp line.",
         ["EDGE", "ICED", "BOLT", "HEIR"], "pastel", "合体", ["mid_length", "sharp_lapel", "defined_waist"],
         {"subcategory":"angular_waisted_coat","neckline":"sharp_notched_lapel","sleeve":"long","length":"mid","volume":"fitted","construction":"offset_front_waist_seam","pattern":"solid","decoration":"low","material_appearance":"dense_matte_wool_like","main_colors":["icy_lilac"]},
         "冰丁香色没有削弱清楚锐线；尖驳领、腰部截止和中长比例构成 EDGE 的日常边界。", ["EDGE×pastel×winter"], "exec-7cbe125b-36ce-40ce-9004-71a4f535279b.png"),
    spec("winter-puffer-earth-neon", "n0012", "garment_aw_winter04_outer_neon_orange_01",
         "橙赭斜切拼色短羽绒外套", "Create a burnt-orange and warm ochre color-blocked cropped puffer jacket with one clear graphic diagonal color block.",
         ["NEON", "OOPS", "LOOP", "EASE"], "earth", "宽松", ["cropped_puffer", "diagonal_color_block", "rounded_volume"],
         {"subcategory":"diagonal_colorblock_puffer","neckline":"stand_collar","sleeve":"long","length":"hip","volume":"padded_relaxed","construction":"zip_front_diagonal_block","pattern":"color_block","decoration":"medium","material_appearance":"matte_padded_shell","main_colors":["burnt_orange","warm_ochre"]},
         "橙赭短羽绒只使用一道斜切色块作为图形重点，完整袖身和立领提供冬季外层证据。", ["NEON×earth×winter"], "exec-ba233d0b-1b3c-405b-85a6-b5ed5703e57a.png"),
    spec("winter-coat-earth-noir", "n0013", "garment_aw_winter04_outer_noir_chocolate_01",
         "深巧克力强肩长直外套", "Create a deep chocolate-brown calf-length structured wool coat with a strong clean shoulder and uninterrupted narrow vertical line.",
         ["NOIR", "HEIR", "MUTE", "EDGE"], "earth", "合体", ["maxi_column", "strong_shoulder", "sharp_vertical_line"],
         {"subcategory":"strong_shoulder_maxi_coat","neckline":"sharp_notched_lapel","sleeve":"long","length":"maxi","volume":"shaped_straight","construction":"concealed_front_long_princess_seams","pattern":"solid","decoration":"low","material_appearance":"dense_matte_wool_like","main_colors":["deep_chocolate"]},
         "深巧克力长外套以强肩、窄驳领和连续及踝纵线表达力量，色彩不是依赖黑色。", ["NOIR×earth×winter"], "exec-abcbcd0c-f3ee-4a82-9b26-cd746f458688.png"),
    spec("winter-coat-pastel-noir", "n0014", "garment_aw_winter04_outer_noir_ice_01",
         "浅冰蓝强肩长直外套", "Create a very pale icy blue-gray calf-length structured wool coat with squared shoulders, sharp narrow lapels and uninterrupted vertical seams.",
         ["NOIR", "ICED", "HEIR", "MUTE"], "pastel", "合体", ["maxi_column", "squared_shoulder", "sharp_vertical_line"],
         {"subcategory":"pale_strong_shoulder_maxi_coat","neckline":"sharp_notched_lapel","sleeve":"long","length":"maxi","volume":"shaped_straight","construction":"concealed_front_long_princess_seams","pattern":"solid","decoration":"low","material_appearance":"dense_matte_wool_like","main_colors":["pale_ice_blue"]},
         "柔浅冰蓝只改变色彩，方肩、尖窄驳领和长直结构仍保持 NOIR 所需的强边界。", ["NOIR×pastel×winter"], "exec-a1d7d43e-3bd8-41cc-889a-0c2437765461.png"),
    spec("winter-coat-ocean-void", "n0015", "garment_aw_winter04_outer_void_ocean_01",
         "深海蓝错位包裹茧形长外套", "Create a deep ocean-blue oversized cocoon wrap coat with enveloping dropped shoulders and one controlled offset overlapping front panel.",
         ["VOID", "WABI", "OOPS", "EASE"], "ocean", "宽松", ["long_cocoon", "offset_wrap", "enveloping_volume"],
         {"subcategory":"offset_wrap_cocoon_coat","neckline":"oversized_asymmetric_lapel","sleeve":"long","length":"maxi","volume":"oversized_cocoon","construction":"single_offset_overlap_button","pattern":"solid","decoration":"low","material_appearance":"dense_soft_wool_like","main_colors":["deep_ocean_blue"]},
         "深海蓝长外套以落肩包裹体积和一处错位叠门表达 VOID，避免破片与补丁同时堆叠。", ["VOID×ocean×winter"], "exec-9d230e26-64b6-47bf-98b2-e51c835ff6bd.png"),
    spec("winter-coat-ocean-wabi", "n0016", "garment_aw_winter04_outer_wabi_indigo_01",
         "水洗靛蓝自然茧形长外套", "Create a washed indigo-blue mid-calf wool-linen cocoon coat with softly rounded volume and restrained natural seam texture.",
         ["WABI", "VOID", "EASE", "FILM"], "ocean", "宽松", ["long_cocoon", "rounded_volume", "natural_seam_texture"],
         {"subcategory":"washed_indigo_cocoon_coat","neckline":"soft_stand_collar","sleeve":"long","length":"maxi","volume":"relaxed_cocoon","construction":"button_front_curved_seams","pattern":"solid","decoration":"low","material_appearance":"wool_linen_like","main_colors":["washed_indigo"]},
         "水洗靛蓝长外套通过圆茧轮廓、自然缝线与克制立领表达手作观感，没有毛边和碎片堆叠。", ["WABI×ocean×winter"], "exec-3340657a-f8e8-4612-8442-58b77b84205b.png"),
]


def ingest_sources() -> None:
    for row in SPECS:
        raw = AUDIT / "raw" / f"{row['slug']}-raw-v1.png"
        prepared = AUDIT / "prepared" / f"{row['slug']}-v1.png"
        qa_path = AUDIT / "qa" / f"{row['slug']}-v1.json"
        stable_write(raw, Path(row["source_output"]).read_bytes())
        if not prepared.exists():
            qa = prepare(raw, prepared)
            qa_path.parent.mkdir(parents=True, exist_ok=True)
            qa_path.write_text(json.dumps(qa, ensure_ascii=False, indent=2) + "\n")
        elif not qa_path.exists():
            raise FileNotFoundError(f"missing immutable QA record: {qa_path}")


def main() -> None:
    ingest_sources()
    result = build(specs=SPECS, audit=AUDIT, static=STATIC, batch_id="aw-generated-garments-03",
                   prompt_version="selfit-aw-winter-exact-gap-v1")
    target = AUDIT / "manifest.json"
    if target.exists() and json.loads(target.read_text()) != result:
        raise SystemExit("Generated garment manifest changed; refusing overwrite")
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"version": result["version"], "garments": len(result["garments"]), "published": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
