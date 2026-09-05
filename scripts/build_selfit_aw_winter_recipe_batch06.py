#!/usr/bin/env python3
"""Compose exact-gap generated winter outerwear into three main structures."""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs/audits/20260904-aw-supply"

# Each target receives pants, skirt and dress variants.  These are design
# candidates only; the resulting whole images must be reviewed separately.
TARGETS = [
    ("BOLT", "earth", "n0009", "收腰短外套是唯一精致焦点，内搭保持简洁。"),
    ("BOLT", "pastel", "n0010", "浅粉长外套用肩腰结构而非晚宴装饰表达精致。"),
    ("EDGE", "pastel", "n0011", "冰丁香锐线外套建立短长与腰线边界。"),
    ("NEON", "earth", "n0012", "橙赭斜切羽绒是唯一图形色块，其余单品稳定。"),
    ("NOIR", "earth", "n0013", "深巧克力强肩长外套建立力量感纵线。"),
    ("NOIR", "pastel", "n0014", "浅冰蓝主色配强肩长线，浅色不削弱结构。"),
    ("VOID", "ocean", "n0015", "深海蓝包裹外套只保留一处错位叠门。"),
    ("WABI", "ocean", "n0016", "水洗靛蓝茧形外套以自然缝线和圆量表达。"),
]

SUPPORTS = {
    "BOLT": {
        "pants": ["g0337", "g0003", "g0254", "g0513"],
        "skirt": ["g0337", "g0446", "g0254", "g0513"],
        "dress": ["g0222", "g0265", "g0513"],
    },
    "EDGE": {
        "pants": ["g0337", "g0068", "g0069", "g0070"],
        "skirt": ["g0350", "g0446", "g0069", "g0070"],
        "dress": ["g0222", "g0069", "g0070"],
    },
    "NEON": {
        "pants": ["g0108", "g0003", "g0043", "g0070"],
        "skirt": ["g0337", "g0188", "g0254", "g0513"],
        "dress": ["g0222", "g0265", "g0513"],
    },
    "NOIR": {
        "pants": ["g0337", "g0068", "g0069", "g0070"],
        "skirt": ["g0350", "g0446", "g0069", "g0070"],
        "dress": ["g0222", "g0069", "g0070"],
    },
    "VOID": {
        "pants": ["g0337", "g0415", "g0591", "g0526"],
        "skirt": ["g0337", "g0449", "g0591", "g0526"],
        "dress": ["g0222", "g0591", "g0526"],
    },
    "WABI": {
        "pants": ["g0108", "g0404", "g0497", "g0284"],
        "skirt": ["g0337", "g0439", "g0497", "g0284"],
        "dress": ["g0219", "g0497", "g0284"],
    },
}


def main() -> None:
    manifest = json.loads((AUDIT / "generated-garments/batch03/manifest.json").read_text())
    visual = json.loads((ROOT / "app/data/recommendation-visual.v1.json").read_text())
    recipes = []
    for persona, palette, hero, intent in TARGETS:
        for structure in ("pants", "skirt", "dress"):
            recipes.append({"persona": persona, "palette": palette, "season": "winter",
                            "structure": structure, "hero": hero,
                            "items": [hero, *SUPPORTS[persona][structure]],
                            "expression": "entry", "intent": intent})
    result = {"schema_version": 1, "batch_id": "aw-winter-06",
              "source_visual_version": visual["version"],
              "status": "designer_targets_pending_whole_image_review",
              "new_garments": manifest["garments"],
              "new_garment_manifest": "generated-garments/batch03/manifest.json",
              "new_garment_version": manifest["version"], "recipes": recipes}
    target = AUDIT / "winter-recipes.batch06.json"
    if target.exists() and json.loads(target.read_text()) != result:
        raise SystemExit("Winter recipe batch changed; refusing overwrite")
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"recipes": len(recipes), "new_garments": len(manifest["garments"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
