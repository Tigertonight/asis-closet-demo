#!/usr/bin/env python3
"""Register eight distinct winter families for near-first-ten conditions."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.build_selfit_aw_generated_garment_batch import build, stable_write
from scripts.prepare_selfit_garment_asset import prepare

AUDIT = ROOT / "docs/audits/20260904-aw-supply/generated-garments/batch13"
STATIC = ROOT / "app/static/selfit/assets/content_v2_drafts/aw-targeted-12/garments"
SRC = Path("/Users/yuanzexiang/.codex/generated_images/01a056c3-ad43-77d1-aed3-35866995a6d6")
RAW = [
    ("iced-ocean-03", "n0080", "iced_ocean_03", "深海蓝交叠高领窄长大衣", "ocean", ["ICED", "NOIR", "MUTE"], ["sculpted_high_collar", "concealed_asymmetric_front", "ankle_column"], "precision_column_coat", ["deep_petrol_blue"], "exec-be1f5db6-2f57-4439-8faf-eb3a09d23a29.png", "窄长柱形、交叠高领和隐形斜门襟提供冷静精确感。"),
    ("iced-pastel-03", "n0081", "iced_pastel_03", "珠光粉灰斜襟窄长大衣", "pastel", ["ICED", "MELT", "EDGE"], ["sculpted_raglan", "diagonal_hidden_closure", "slim_ankle"], "pastel_sculpted_wrap_coat", ["pearl_blush_gray"], "exec-2ec1c0ee-5bbf-4386-acbb-a4ed200b9eef.png", "浅彩通过雕塑肩线、窄长比例和斜襟保持 ICED 的收净感。"),
    ("jade-mono-03", "n0082", "jade_mono_03", "炭黑立领斜襟纵线大衣", "mono", ["JADE", "NOIR", "ICED"], ["standing_wrap_collar", "restrained_diagonal_overlap", "long_vertical"], "restrained_wrap_column_coat", ["charcoal_black"], "exec-19496d87-c3bb-4198-8ec4-6fc0d42f8e6e.png", "立领、克制斜襟和连续纵线构成现代日常 JADE 证据。"),
    ("melt-mono-03", "n0083", "melt_mono_03", "鸽灰圆领柔茧摆大衣", "mono", ["MELT", "WABI", "EASE"], ["rounded_collar", "soft_balloon_sleeve", "curved_swing_cocoon"], "rounded_swing_cocoon_coat", ["dove_gray"], "exec-e0a76015-5173-46b1-bf88-0a2321ab5044.png", "圆领、柔圆袖和弧形茧摆形成可日常穿的 MELT 柔软线条。"),
    ("mute-jewel-03", "n0084", "mute_jewel_03", "深祖母绿无领直身长大衣", "jewel", ["MUTE", "LOOP", "ICED"], ["collarless", "dropped_clean_shoulder", "boxy_long_column"], "minimal_collarless_column_coat", ["deep_emerald"], "exec-916b4a94-c4fc-4438-98c0-01956ad8e837.png", "宝石色被限制在无领、暗扣、低装饰的直身长线中。"),
    ("wabi-bright-03", "n0085", "wabi_bright_03", "钴蓝木扣弧线茧形大衣", "bright", ["WABI", "EASE", "MELT"], ["soft_shawl_collar", "single_wood_toggle", "curved_cocoon"], "bright_handcrafted_cocoon", ["vivid_cobalt_blue"], "exec-18491a75-111a-401e-9844-937f9a2d8e83.png", "单一木扣、弧线茧形和织物观感提供明亮但不碎片化的 WABI。"),
    ("wabi-ocean-03", "n0086", "wabi_ocean_03", "靛蓝织感曲襟系带大衣", "ocean", ["WABI", "VOID", "EASE"], ["soft_shawl_collar", "low_asymmetric_tie", "curved_wrap_cocoon"], "indigo_textured_wrap_duster", ["indigo", "muted_slate_blue"], "exec-8da4c207-9481-4252-87b0-cdb9cd9bb5d9.png", "不规则织感、低位系带和曲线包裹构成安静手作层次。"),
    ("film-mono-03", "n0087", "film_mono_03", "黑白六十年代图形A线大衣", "mono", ["FILM", "BOLT", "EDGE"], ["wide_pointed_collar", "covered_buttons", "sixties_a_line"], "sixties_graphic_a_line_coat", ["black", "ivory"], "exec-0f7117dc-8e49-4fab-890b-a5171c60c96b.png", "宽尖领、图形格纹与六十年代 A 线比例构成明确复古证据。"),
]


def specs():
    return [
        {
            "slug": f"aw-main-{slug}",
            "token": token,
            "id": f"garment_aw_targeted12_outer_{key}_01",
            "name": name,
            "prompt": name + "，原创无品牌透明背景冬季独立主衣家族。",
            "personas": personas,
            "palette": palette,
            "fit": "宽松" if persona in {"WABI", "MELT"} else "合体",
            "silhouette": silhouette,
            "observation": {
                "subcategory": subtype,
                "neckline": "as_observed",
                "sleeve": "long",
                "length": "midi_or_long",
                "volume": "shaped",
                "construction": "distinct_near_threshold_family",
                "pattern": "graphic" if persona == "FILM" else "solid",
                "decoration": "controlled",
                "material_appearance": "dense_winter_material_as_observed",
                "main_colors": colors,
            },
            "evidence": evidence,
            "targets": [f"{target}×{palette}×winter" for target in personas],
            "source_output": str(SRC / filename),
        }
        for slug, token, key, name, palette, personas, silhouette, subtype, colors, filename, evidence in RAW
        for persona in [personas[0]]
    ]


def main():
    rows = specs()
    for row in rows:
        source = Path(row["source_output"])
        raw = AUDIT / "raw" / f"{row['slug']}-raw-v1.png"
        prepared = AUDIT / "prepared" / f"{row['slug']}-v1.png"
        qa = AUDIT / "qa" / f"{row['slug']}-v1.json"
        stable_write(raw, source.read_bytes())
        if not prepared.exists():
            report = prepare(raw, prepared)
            qa.parent.mkdir(parents=True, exist_ok=True)
            qa.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    result = build(specs=rows, audit=AUDIT, static=STATIC, batch_id="aw-generated-garments-13", prompt_version="selfit-aw-near-threshold-family-v1")
    result["binding_method"] = "individual_output_binding_verified_visually_and_by_filename"
    target = AUDIT / "manifest.json"
    if target.exists() and json.loads(target.read_text()) != result:
        raise SystemExit("Batch13 changed; refusing overwrite")
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"version": result["version"], "garments": 8, "published": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
