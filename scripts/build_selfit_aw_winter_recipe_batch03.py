#!/usr/bin/env python3
"""Build winter recipes around the second generated gap-fill garment batch."""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs/audits/20260904-aw-supply"
RECIPES = [
    ("BOLT", "bright", "pants", "n0005", ["n0005", "g0108", "g0003", "g0265", "g0513"], "品红锐肩短外套作唯一戏剧点，白衬衫与黑直裤稳定日常比例。"),
    ("EDGE", "bright", "skirt", "n0005", ["n0005", "g0350", "g0429", "g0265", "g0526"], "短外套与不对称中长裙建立锐利短长对比，黑色支撑款控制高彩。"),
    ("NEON", "bright", "dress", "n0005", ["n0005", "g0462", "g0043", "g0070"], "品红短外套覆在黑色长衬衫裙上，以一处高彩和明确短长反差表达。"),
    ("VOID", "jewel", "pants", "n0006", ["n0006", "g0337", "g0415", "g0591", "g0526"], "紫晶包裹外套配简洁针织与一处错层长裤，不叠加多余破片。"),
    ("OOPS", "jewel", "skirt", "n0006", ["n0006", "g0337", "g0188", "g0505", "g0521"], "错位包裹外套与斜裹长裙共享同一线条母题，内层保持简单。"),
    ("WABI", "jewel", "dress", "n0006", ["n0006", "g0468", "g0497", "g0284"], "包裹长外套与自然色长衬衫裙统一松紧层次，鞋包保持低负担。"),
    ("FILM", "jewel", "pants", "n0007", ["n0007", "g0101", "g0176", "g0258", "g0270"], "祖母绿圆领 A 形外套与微花卉衬衫、褶裤建立可辨识的复古日常比例。"),
    ("JADE", "jewel", "skirt", "n0007", ["n0007", "g0365", "g0206", "g0258", "g0289"], "祖母绿收腰外套与水墨内搭、斜裁长裙共享克制纵向线条。"),
    ("BOLT", "jewel", "dress", "n0007", ["n0007", "g0222", "g0069", "g0070"], "收腰祖母绿外套作精致主视觉，长衬衫裙和长靴延续整洁长线。"),
    ("MUTE", "bright", "pants", "n0008", ["n0008", "g0096", "g0160", "g0004", "g0513"], "万寿菊黄长外套是唯一色彩焦点，其余用低装饰衬衫、直裤和乐福鞋维持克制。"),
    ("JADE", "bright", "skirt", "n0008", ["n0008", "g0365", "g0206", "g0258", "g0289"], "鲜黄长直外套与水墨内搭、斜裁长裙形成主次明确的克制交叠。"),
    ("FILM", "bright", "dress", "n0008", ["n0008", "g0219", "g0497", "g0271"], "万寿菊黄长外套与棕色长衬衫裙建立暖色复古比例，长靴完成外出层次。"),
]


def main() -> None:
    manifest = json.loads((AUDIT / "generated-garments/batch02/manifest.json").read_text())
    visual = json.loads((ROOT / "app/data/recommendation-visual.v1.json").read_text())
    recipes = [{"persona": p, "palette": pal, "season": "winter", "structure": structure, "hero": hero,
                "items": items, "expression": "entry", "intent": intent}
               for p, pal, structure, hero, items, intent in RECIPES]
    result = {"schema_version": 1, "batch_id": "aw-winter-03", "source_visual_version": visual["version"],
              "status": "designer_targets_pending_whole_image_review", "new_garments": manifest["garments"],
              "new_garment_manifest": "generated-garments/batch02/manifest.json",
              "new_garment_version": manifest["version"], "recipes": recipes}
    target = AUDIT / "winter-recipes.batch03.json"
    if target.exists() and json.loads(target.read_text()) != result:
        raise SystemExit("Winter recipe batch changed; refusing overwrite")
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"recipes": len(recipes), "new_garments": len(manifest["garments"]), "production_approved": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
