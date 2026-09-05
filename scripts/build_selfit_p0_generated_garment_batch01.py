#!/usr/bin/env python3
"""Register eleven low-expression P0 persona garments as internal candidates."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_selfit_aw_generated_garment_batch import build, stable_write
from scripts.prepare_selfit_garment_asset import prepare

AUDIT = ROOT / "docs/audits/20260904-p0-acceptance/generated-garments/batch01"
STATIC = ROOT / "app/static/selfit/assets/content_v2_drafts/p0-low-expression-01/garments"
SRC = Path("/Users/yuanzexiang/.codex/generated_images/01a06b62-ef79-7533-88b0-79111246bf6f")

RAW = [
    ("bolt-bow-blouse", "n0088", "top", "BOLT", "象牙白酒红丝绒结珍珠扣衬衫", "exec-f663f956-802f-4c50-ae3f-0b4d5ac44299.png",
     "bow_pearl_fitted_blouse", ["ivory", "wine_red"], "低强度丝绒领结、珍珠扣与收腰线提供日常化的精致贵气证据。"),
    ("bolt-bow-dress", "n0089", "dress", "BOLT", "象牙白酒红丝绒结衬衫裙", "exec-ff24811f-1006-4761-906c-5ba58936c4ae.png",
     "bow_pearl_a_line_shirtdress", ["ivory", "wine_red"], "单一酒红领结、珍珠扣与克制 A 线形成低强度在逃千金表达。"),
    ("edge-piped-knit", "n0090", "top", "EDGE", "灰粉黑皮革斜线针织上衣", "exec-c04f6ef9-696a-4d77-835f-2def28e1b0c8.png",
     "soft_knit_leather_piped_top", ["dusty_rose", "black"], "灰粉软针织与一条黑色皮革斜线、银环形成克制甜酷对撞。"),
    ("edge-piped-dress", "n0091", "dress", "EDGE", "灰紫黑皮革细带方领连衣裙", "exec-5fc4654f-6b2f-48e4-8048-95c7c88c723b.png",
     "soft_square_neck_piped_midi_dress", ["dusty_mauve", "black"], "柔和灰紫 A 线与细黑皮革腰线、小银扣形成日常甜酷证据。"),
    ("jade-wrap-dress", "n0092", "dress", "JADE", "暖白斜襟玉扣立领连衣裙", "exec-8fe47ed9-80ee-493e-823c-165b9cada9e6.png",
     "modern_stand_collar_wrap_midi_dress", ["warm_white", "jade_green"], "短立领、斜襟线与单颗玉色扣构成克制现代的东方线条。"),
    ("neon-polo", "n0093", "top", "NEON", "钴蓝荧光绿珊瑚口袋针织Polo", "exec-84fe5b0e-3c3d-4801-9a2f-e75f8bc38276.png",
     "simple_high_color_polo", ["cobalt_blue", "lime", "coral"], "高能钴蓝、荧光绿和珊瑚色被限制在简洁 Polo 轮廓和单一口袋内。"),
    ("neon-panel-dress", "n0094", "dress", "NEON", "钴蓝荧光绿侧片A线连衣裙", "exec-e35c04c5-e857-478a-9fef-1c6d499d1b8e.png",
     "simple_high_color_panel_midi_dress", ["cobalt_blue", "lime", "coral"], "钴蓝主色与单一荧光绿侧片构成吸睛焦点，A 线结构保持低复杂度。"),
    ("oops-split-skirt", "n0095", "skirt", "OOPS", "灰条纹鼠尾草异材质拼接裙", "exec-de1d8afb-031c-46ab-ad24-7aa08e10f98b.png",
     "controlled_mismatch_split_midi_skirt", ["charcoal", "sage", "cobalt"], "条纹西装料与鼠尾草棉料主动冲突，蓝色口袋是唯一意外点。"),
    ("oops-split-dress", "n0096", "dress", "OOPS", "蓝条纹米色错位拼接衬衫裙", "exec-2621cadb-e2c7-418c-90a6-fa7c0074e8ad.png",
     "controlled_mismatch_split_shirtdress", ["muted_blue", "beige", "coral"], "普通蓝条纹与米色衬衫面被刻意对半拼接，以小珊瑚扣保留失序趣味。"),
    ("void-washed-skirt", "n0097", "skirt", "VOID", "水洗炭灰偏置缝线补丁裙", "exec-02441b32-ae99-4884-86ae-bf96b554d280.png",
     "washed_offset_seam_midi_skirt", ["washed_charcoal", "faded_gray"], "默认制服般的水洗炭灰直裙，以偏置门襟和低对比补丁保留轻微游离感。"),
    ("void-pocket-dress", "n0098", "dress", "VOID", "水洗石墨灰偏置口袋T恤裙", "exec-eb80db25-170c-4003-ae3e-90ef0180ba3c.png",
     "washed_offset_pocket_tshirt_dress", ["washed_graphite", "faded_gray"], "松身石墨灰 T 恤裙接近默认制服，斜缝与偏置口袋提供低表达不确定感。"),
]


def specs() -> list[dict]:
    rows = []
    for slug, token, category, persona, name, filename, subtype, colors, evidence in RAW:
        rows.append({
            "slug": slug,
            "token": token,
            "id": f"garment_p0_low_{persona.lower()}_{category}_{token}",
            "name": name,
            "category": category,
            "prompt": name + "，原创无品牌透明背景日常低表达强度独立主衣。",
            "personas": [persona],
            "palette": "p0_persona_not_color_test",
            "fit": "合体" if persona in {"BOLT", "EDGE", "JADE"} else "宽松",
            "silhouette": ["daily", "single_focal", "low_expression"],
            "observation": {
                "subcategory": subtype,
                "neckline": "as_observed",
                "sleeve": "as_observed",
                "length": "midi" if category in {"dress", "skirt"} else "regular",
                "volume": "controlled",
                "construction": "single_persona_detail_on_daily_base",
                "pattern": "controlled_mismatch" if persona == "OOPS" else "solid_or_restrained",
                "decoration": "low",
                "material_appearance": "as_observed",
                "main_colors": colors,
            },
            "evidence": evidence,
            "targets": [f"{persona}×easy×daily"],
            "source_output": str(SRC / filename),
        })
    return rows


def main() -> None:
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
        batch_id="p0-generated-low-expression-01",
        prompt_version="selfit-p0-low-expression-persona-v1",
    )
    result["binding_method"] = "individual_output_binding_verified_visually_and_by_filename"
    result["limitations"] = [
        "Generated cutout approval is not outfit approval, four-gate editorial approval, or blind review.",
        "Persona and expression must be re-evaluated on the complete outfit image.",
        "Color testing is outside this P0 scope.",
    ]
    target = AUDIT / "manifest.json"
    if target.exists() and json.loads(target.read_text()) != result:
        raise SystemExit("P0 garment batch changed; refusing overwrite")
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"version": result["version"], "garments": len(rows), "published": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
