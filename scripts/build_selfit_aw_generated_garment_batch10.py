#!/usr/bin/env python3
"""Register eight inspected autumn/winter main-garment families for precise gaps."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_selfit_aw_generated_garment_batch import build, stable_write
from scripts.prepare_selfit_garment_asset import prepare

AUDIT = ROOT / "docs/audits/20260904-aw-supply/generated-garments/batch10"
STATIC = ROOT / "app/static/selfit/assets/content_v2_drafts/aw-targeted-08/garments"
SRC = Path("/Users/yuanzexiang/.codex/generated_images/01a056c3-ad43-77d1-aed3-35866995a6d6")

RAW = [
    ("film-pastel", "n0056", "film_pastel", "粉雾蓝六十年代圆领摆型大衣", "pastel", ["FILM", "HEIR", "MELT", "BOLT"], ["rounded_collar", "fitted_upper", "swing_a_line"], "sixties_round_collar_swing_coat", ["dusty_powder_blue"], "exec-576c4726-dbd2-4c88-8ed8-fbeddd6a884d.png", "圆领、包扣、合体上身与摆型下部形成清楚的六十年代比例，长袖与膝下长度支持秋冬外层。"),
    ("film-bright", "n0057", "film_bright", "万寿菊黄七十年代灯芯绒长大衣", "bright", ["FILM", "HEIR", "NEON", "BOLT"], ["wide_point_collar", "defined_waist", "long_a_line"], "seventies_corduroy_long_coat", ["saturated_marigold"], "exec-f670835c-b572-4e8f-ba38-caee8495d241.png", "宽尖领、贴袋、收腰与细灯芯绒共同构成七十年代剪裁证据，而不是仅靠黄色冒充复古。"),
    ("bolt-earth", "n0058", "bolt_earth", "肉桂褐雕塑肩收腰短大衣", "earth", ["BOLT", "HEIR", "EDGE", "FILM"], ["sculpted_shoulder", "defined_waist", "peplum_hip"], "sculpted_peplum_short_coat", ["warm_cinnamon_brown"], "exec-65e2a704-e9c9-41bd-aa04-9c14251012ec.png", "雕塑肩、单扣收腰和受控伞摆形成日常可穿的精致力量感。"),
    ("bolt-pastel", "n0059", "bolt_pastel", "冰紫公主线长大衣", "pastel", ["BOLT", "ICED", "HEIR", "MUTE"], ["precise_shoulder", "princess_seam", "shaped_long_a_line"], "princess_seam_midi_coat", ["icy_lavender"], "exec-a85916c4-ea14-40af-a4ae-af0dce4f6966.png", "精确肩线、公主线和克制收腰把浅彩用于结构表达，避免礼服化。"),
    ("bolt-bright", "n0060", "bolt_bright", "朱红雕塑斜襟短外套", "bright", ["BOLT", "EDGE", "NEON", "OOPS"], ["raised_shoulder", "defined_waist", "cropped_architectural"], "sculpted_asymmetric_cropped_jacket", ["vivid_vermilion"], "exec-a50ea55d-ea44-44dd-a80c-32608515eac1.png", "短比例、明确肩腰与单一斜襟折线构成鲜明主视觉，配方必须使用稳定下装。"),
    ("iced-bright", "n0061", "iced_bright", "钴蓝高领窄长大衣", "bright", ["ICED", "MUTE", "NOIR", "JADE"], ["exact_shoulder", "high_neck", "narrow_long_column"], "minimal_high_neck_column_coat", ["vivid_cobalt"], "exec-9036b8b8-366b-4c31-ba0f-c7a4b60420ae.png", "高领、暗门襟和窄长直线使高彩仍保持冷静收净。"),
    ("edge-earth", "n0062", "edge_earth", "深浓咖斜襟短夹克", "earth", ["EDGE", "OOPS", "NOIR", "JADE"], ["crisp_shoulder", "diagonal_closure", "cropped_fitted"], "asymmetric_cropped_twill_jacket", ["deep_espresso_brown"], "exec-5923f31c-5e23-44e4-89fb-9fc3e1beb9c4.png", "短身、斜向闭合和一处错位门襟形成锐利边界，不依赖随机配件。"),
    ("jade-bright", "n0063", "jade_bright", "朱砂红立领交叠长大衣", "bright", ["JADE", "ICED", "NOIR", "EDGE"], ["precise_shoulder", "stand_collar", "restrained_crossover_column"], "stand_collar_crossover_long_coat", ["clear_cinnabar_red"], "exec-f9791e39-5f63-4b19-9bb1-c96b2859bec7.png", "立领、克制交叠和纵向省线提供 JADE 所需的清楚领型与纵线，避免服装化符号堆叠。"),
]


def specs():
    result = []
    for slug, token, key, name, palette, personas, silhouette, subcategory, colors, filename, evidence in RAW:
        result.append({
            "slug": f"aw-main-{slug}",
            "token": token,
            "id": f"garment_aw_targeted08_outer_{key}_01",
            "name": name,
            "prompt": name + "，原创无品牌透明背景秋冬主外层。",
            "personas": personas,
            "palette": palette,
            "fit": "合体",
            "silhouette": silhouette,
            "observation": {
                "subcategory": subcategory,
                "neckline": "as_observed",
                "sleeve": "long",
                "length": "cropped" if "cropped" in subcategory or "short" in subcategory else "midi",
                "volume": "shaped",
                "construction": "single_clear_primary_line",
                "pattern": "solid",
                "decoration": "minimal",
                "material_appearance": "dense_matte_wool_like" if "corduroy" not in subcategory and "twill" not in subcategory else subcategory,
                "main_colors": colors,
            },
            "evidence": evidence,
            "targets": [f"{persona}×{palette}×autumn/winter" for persona in personas],
            "source_output": str(SRC / filename),
        })
    return result


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
    result = build(
        specs=rows,
        audit=AUDIT,
        static=STATIC,
        batch_id="aw-generated-garments-10",
        prompt_version="selfit-aw-persona-gap-main-v1",
    )
    result["binding_method"] = "individual_output_binding_verified_visually_and_by_filename"
    target = AUDIT / "manifest.json"
    if target.exists() and json.loads(target.read_text()) != result:
        raise SystemExit("Batch10 changed; refusing overwrite")
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"version": result["version"], "garments": len(result["garments"]), "published": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
