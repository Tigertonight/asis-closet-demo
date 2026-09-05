#!/usr/bin/env python3
"""Build concrete winter outfit recipes around the first generated gap-fill coats."""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs/audits/20260904-aw-supply"

# Each generated main garment supports three visibly different main structures.
# Existing support garments are referenced by their bound visual-audit tokens.
RECIPES = [
    ("HEIR", "jewel", "pants", "n0001", ["n0001", "g0108", "g0003", "g0004", "g0270"], "勃艮第收腰长外套与白衬衫、直筒长裤构成经典清楚的冬日日常比例。"),
    ("MUTE", "jewel", "skirt", "n0001", ["n0001", "g0337", "g0433", "g0004", "g0513"], "低装饰内层与直筒中长裙承接长外套纵线，主色鲜明但结构克制。"),
    ("NOIR", "jewel", "dress", "n0001", ["n0001", "g0462", "g0069", "g0070"], "收腰长外套叠加锐利领型长裙和长靴，保留强边界而不增加多余装饰。"),
    ("ICED", "jewel", "pants", "n0002", ["n0002", "g0365", "g0172", "g0265", "g0513"], "立领暗门襟外套配浅色纵向内搭和长裤，以收净长线表达冷静感。"),
    ("JADE", "jewel", "skirt", "n0002", ["n0002", "g0089", "g0445", "g0258", "g0289"], "立领长外套和克制植物内搭组成清楚叠层，不再依赖同一米白宽裤。"),
    ("NOIR", "jewel", "dress", "n0002", ["n0002", "g0478", "g0069", "g0070"], "宝石青长外套压住黑色锐肩长裙的戏剧度，保留一个明确力量焦点。"),
    ("LOOP", "bright", "pants", "n0003", ["n0003", "g0337", "g0397", "g0249", "g0005"], "鲜蓝长外套作可复用模块的唯一色块，其余用素色针织、长裤和运动底鞋稳定。"),
    ("EDGE", "bright", "skirt", "n0003", ["n0003", "g0350", "g0429", "g0043", "g0526"], "利落长外套与短上身、不对称中长裙构成短长对比，高彩不再叠加复杂拼色。"),
    ("ICED", "bright", "dress", "n0003", ["n0003", "g0234", "g0265", "g0513"], "鲜蓝外套和收净衬衫连衣裙形成同向长线，配低跟靴保持日常可穿。"),
    ("EASE", "bright", "pants", "n0004", ["n0004", "g0561", "g0170", "g0261", "g0271"], "珊瑚红茧形外层配简洁内搭和收束感长裤，避免宽上宽下失去重心。"),
    ("MELT", "bright", "skirt", "n0004", ["n0004", "g0337", "g0209", "g0254", "g0529"], "圆线长外套与柔软分层裙统一，内层和鞋包保持简单，控制甜美元素数量。"),
    ("FLOU", "bright", "dress", "n0004", ["n0004", "g0220", "g0254", "g0271"], "可出门的长外层覆盖流动感衬衫裙，用平底鞋和软包将浪漫表达拉回日常。"),
]


def main() -> None:
    manifest = json.loads((AUDIT / "generated-garments/batch01/manifest.json").read_text())
    visual = json.loads((ROOT / "app/data/recommendation-visual.v1.json").read_text())
    recipes = []
    for persona, palette, structure, hero, items, intent in RECIPES:
        recipes.append({"persona": persona, "palette": palette, "season": "winter", "structure": structure,
                        "hero": hero, "items": items, "expression": "entry", "intent": intent})
    result = {
        "schema_version": 1, "batch_id": "aw-winter-02", "source_visual_version": visual["version"],
        "status": "designer_targets_pending_whole_image_review", "new_garments": manifest["garments"],
        "new_garment_manifest": "generated-garments/batch01/manifest.json",
        "new_garment_version": manifest["version"], "recipes": recipes,
    }
    target = AUDIT / "winter-recipes.batch02.json"
    if target.exists() and json.loads(target.read_text()) != result:
        raise SystemExit("Winter recipe batch changed; refusing overwrite")
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"recipes": len(recipes), "new_garments": len(manifest["garments"]), "production_approved": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
