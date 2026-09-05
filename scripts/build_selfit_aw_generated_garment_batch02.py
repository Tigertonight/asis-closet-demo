#!/usr/bin/env python3
"""Register the second generated winter gap-fill batch without publishing it."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.build_selfit_aw_generated_garment_batch import ROOT, build


AUDIT = ROOT / "docs/audits/20260904-aw-supply/generated-garments/batch02"
STATIC = ROOT / "app/static/selfit/assets/content_v2_drafts/aw-winter-03/garments"
SPECS = [
    {
        "slug": "winter-jacket-bright-fuchsia", "token": "n0005", "id": "garment_aw_winter03_outer_fuchsia_01",
        "name": "品红锐肩短结构外套", "prompt": "Create a vivid fuchsia-magenta cropped structured winter jacket with crisp shoulders, a clean high waist, subtle asymmetric closure and long sleeves.",
        "personas": ["BOLT", "EDGE", "NEON", "OOPS"], "palette": "bright", "fit": "合体",
        "silhouette": ["cropped", "sharp_shoulder", "defined_waist"],
        "observation": {"subcategory": "cropped_asymmetric_jacket", "neckline": "asymmetric_stand", "sleeve": "long", "length": "hip", "volume": "fitted", "construction": "offset_front_princess_seams", "pattern": "solid", "decoration": "medium", "material_appearance": "dense_matte_wool_like", "main_colors": ["vivid_fuchsia"]},
        "evidence": "鲜品红短外套以锐肩、高腰截止和一处错位门襟建立强边界，除单颗扣外没有额外繁复装饰。",
        "targets": ["BOLT×bright×winter", "EDGE×bright×winter", "NEON×bright×winter", "OOPS×bright×winter"],
        "source_output": "/Users/yuanzexiang/.codex/generated_images/01a056c3-ad43-77d1-aed3-35866995a6d6/exec-b707060f-30e8-4531-8873-d19ccb93a98e.png",
    },
    {
        "slug": "winter-coat-jewel-amethyst", "token": "n0006", "id": "garment_aw_winter03_outer_amethyst_01",
        "name": "紫晶错位包裹长外套", "prompt": "Create a deep jewel amethyst-purple long wrap winter coat with soft protective volume, one offset overlap, restrained asymmetric collar and long sleeves.",
        "personas": ["VOID", "OOPS", "EDGE", "WABI"], "palette": "jewel", "fit": "宽松",
        "silhouette": ["wrap", "soft_cocoon", "asymmetric_overlap"],
        "observation": {"subcategory": "asymmetric_wrap_long_coat", "neckline": "asymmetric_wide_lapel", "sleeve": "long", "length": "maxi", "volume": "soft_wrap", "construction": "offset_overlap_attached_belt", "pattern": "solid", "decoration": "medium", "material_appearance": "dense_matte_wool_like", "main_colors": ["deep_amethyst"]},
        "evidence": "深紫长外套的宽驳领、单一错位包裹和连接腰带形成包裹层次，边缘完整，没有破片式堆叠。",
        "targets": ["VOID×jewel×winter", "OOPS×jewel×winter", "EDGE×jewel×winter", "WABI×jewel×winter"],
        "source_output": "/Users/yuanzexiang/.codex/generated_images/01a056c3-ad43-77d1-aed3-35866995a6d6/exec-8b3652cf-7ca8-40f3-ad44-32e1a9e60e49.png",
    },
    {
        "slug": "winter-coat-jewel-emerald", "token": "n0007", "id": "garment_aw_winter03_outer_emerald_01",
        "name": "祖母绿复古收腰长外套", "prompt": "Create an emerald jewel-green midi winter coat with defined classic shoulder, modest sculpted waist, rounded vintage collar and clean single-breasted closure.",
        "personas": ["FILM", "JADE", "BOLT", "HEIR"], "palette": "jewel", "fit": "合体",
        "silhouette": ["vintage_a_line", "defined_waist", "mid_calf"],
        "observation": {"subcategory": "vintage_rounded_collar_coat", "neckline": "rounded_collar", "sleeve": "long", "length": "maxi", "volume": "fitted_a_line", "construction": "single_breasted_princess_seams", "pattern": "solid", "decoration": "medium", "material_appearance": "dense_matte_wool_like", "main_colors": ["deep_emerald"]},
        "evidence": "祖母绿长外套的圆领、包扣、公主线和 A 形下摆形成可辨识复古比例，装饰集中在结构本身。",
        "targets": ["FILM×jewel×winter", "JADE×jewel×winter", "BOLT×jewel×winter", "HEIR×jewel×winter"],
        "source_output": "/Users/yuanzexiang/.codex/generated_images/01a056c3-ad43-77d1-aed3-35866995a6d6/exec-f30c025f-40ec-48de-a82c-f6ca69a964b3.png",
    },
    {
        "slug": "winter-coat-bright-marigold", "token": "n0008", "id": "garment_aw_winter03_outer_marigold_01",
        "name": "万寿菊黄克制长直外套", "prompt": "Create a vivid marigold-yellow clean long winter coat with collarless narrow round neckline, concealed closure, lightly defined shoulder and clear straight vertical line.",
        "personas": ["MUTE", "JADE", "FILM", "WABI"], "palette": "bright", "fit": "合体",
        "silhouette": ["long_column", "collarless", "clean_vertical_line"],
        "observation": {"subcategory": "collarless_long_coat", "neckline": "collarless_round", "sleeve": "long", "length": "maxi", "volume": "straight_shaped", "construction": "concealed_front_princess_seams", "pattern": "solid", "decoration": "low", "material_appearance": "dense_matte_wool_like", "main_colors": ["vivid_marigold"]},
        "evidence": "万寿菊黄是唯一表达点，无领、暗门襟和长直分割保持低装饰与清晰纵线。",
        "targets": ["MUTE×bright×winter", "JADE×bright×winter", "FILM×bright×winter", "WABI×bright×winter"],
        "source_output": "/Users/yuanzexiang/.codex/generated_images/01a056c3-ad43-77d1-aed3-35866995a6d6/exec-a9e51225-c5fb-499d-b24c-9975a4ea33f3.png",
    },
]


def main() -> None:
    result = build(specs=SPECS, audit=AUDIT, static=STATIC, batch_id="aw-generated-garments-02",
                   prompt_version="selfit-aw-winter-gap-v1")
    target = AUDIT / "manifest.json"
    if target.exists() and json.loads(target.read_text()) != result:
        raise SystemExit("Generated garment manifest changed; refusing overwrite")
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"version": result["version"], "garments": len(result["garments"]), "published": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
