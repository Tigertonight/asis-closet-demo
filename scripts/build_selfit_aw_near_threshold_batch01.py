#!/usr/bin/env python3
"""Design a bounded AW batch for conditions closest to first-ten coverage.

The batch uses a different main outerwear item for every incremental recipe
within a condition.  It deliberately stops at the measured shortfall instead
of manufacturing 3 variants for every target.
"""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs/audits/20260904-aw-supply"


RECIPES = [
    # Winter: 19 recipes for ten conditions currently at 7–9 selected looks.
    ("HEIR", "earth", "winter", "pants", "g0155", ["g0155", "g0108", "g0403", "g0069", "g0070"]),
    ("NOIR", "mono", "winter", "skirt", "g0067", ["g0067", "g0337", "g0446", "g0069", "g0070"]),
    ("VOID", "mono", "winter", "skirt", "g0143", ["g0143", "g0337", "g0449", "g0591", "g0526"]),
    ("EASE", "mono", "winter", "pants", "g0129", ["g0129", "g0337", "g0404", "g0497", "g0289"]),
    ("EASE", "mono", "winter", "skirt", "g0369", ["g0369", "g0337", "g0449", "g0591", "g0526"]),
    ("EDGE", "mono", "winter", "pants", "g0066", ["g0066", "g0337", "g0068", "g0069", "g0070"]),
    ("EDGE", "mono", "winter", "dress", "g0067", ["g0067", "g0462", "g0069", "g0070"]),
    ("HEIR", "jewel", "winter", "pants", "g0138", ["g0138", "g0115", "g0172", "g0258", "g0289"]),
    ("HEIR", "jewel", "winter", "dress", "g0371", ["g0371", "g0234", "g0069", "g0070"]),
    ("ICED", "mono", "winter", "pants", "g0130", ["g0130", "g0337", "g0172", "g0258", "g0289"]),
    ("ICED", "mono", "winter", "dress", "g0146", ["g0146", "g0222", "g0265", "g0513"]),
    ("WABI", "jewel", "winter", "pants", "g0152", ["g0152", "g0108", "g0415", "g0591", "g0284"]),
    ("WABI", "jewel", "winter", "skirt", "g0051", ["g0051", "g0337", "g0449", "g0591", "g0526"]),
    ("HEIR", "pastel", "winter", "pants", "g0133", ["g0133", "g0114", "g0172", "g0258", "g0289"]),
    ("HEIR", "pastel", "winter", "dress", "g0154", ["g0154", "g0234", "g0069", "g0070"]),
    ("HEIR", "pastel", "winter", "skirt", "n0010", ["n0010", "g0108", "g0206", "g0258", "g0289"]),
    ("ICED", "pastel", "winter", "dress", "g0130", ["g0130", "g0234", "g0258", "g0289"]),
    ("ICED", "pastel", "winter", "pants", "g0386", ["g0386", "g0337", "g0172", "g0258", "g0289"]),
    ("ICED", "pastel", "winter", "skirt", "n0014", ["n0014", "g0114", "g0206", "g0258", "g0289"]),
    # Autumn: 9 recipes for conditions currently at 8–9 selected looks.
    ("MELT", "earth", "autumn", "pants", "g0388", ["g0388", "g0108", "g0404", "g0258", "g0284"]),
    ("MUTE", "ocean", "autumn", "skirt", "g0146", ["g0146", "g0114", "g0200", "g0258", "g0289"]),
    ("OOPS", "mono", "autumn", "pants", "g0144", ["g0144", "g0337", "g0068", "g0069", "g0070"]),
    ("OOPS", "pastel", "autumn", "skirt", "g0384", ["g0384", "g0108", "g0439", "g0254", "g0513"]),
    ("VOID", "pastel", "autumn", "skirt", "g0569", ["g0569", "g0337", "g0449", "g0591", "g0526"]),
    ("JADE", "earth", "autumn", "skirt", "g0134", ["g0134", "g0108", "g0204", "g0258", "g0284"]),
    ("JADE", "earth", "autumn", "pants", "g0064", ["g0064", "g0108", "g0404", "g0258", "g0284"]),
    ("LOOP", "jewel", "autumn", "pants", "g0147", ["g0147", "g0012", "g0403", "g0069", "g0070"]),
    ("LOOP", "jewel", "autumn", "skirt", "g0371", ["g0371", "g0115", "g0200", "g0258", "g0289"]),
    ("VOID", "earth", "autumn", "pants", "g0026", ["g0026", "g0337", "g0415", "g0591", "g0526"]),
    ("VOID", "earth", "autumn", "skirt", "g0395", ["g0395", "g0337", "g0449", "g0591", "g0526"]),
]


def main() -> None:
    visual = json.loads((ROOT / "app/data/recommendation-visual.v1.json").read_text())
    generated = json.loads((AUDIT / "generated-garments/combined-manifest-v3.json").read_text())
    recipes = []
    for persona, palette, season, structure, hero, items in RECIPES:
        recipes.append({
            "persona": persona,
            "palette": palette,
            "season": season,
            "structure": structure,
            "hero": hero,
            "items": items,
            "expression": "entry",
            "intent": (
                f"补齐 {persona} × {palette} 的 {season} 日常临界供给；"
                f"以 {hero} 为主视觉，不使用仅换鞋包的重复变体。"
            ),
        })
    assert len(recipes) == 30
    result = {
        "schema_version": 1,
        "batch_id": "aw-near-threshold-01",
        "source_visual_version": visual["version"],
        "status": "designer_targets_pending_whole_image_review",
        "new_garments": generated["garments"],
        "new_garment_manifest": "generated-garments/combined-manifest-v3.json",
        "new_garment_version": generated["version"],
        "recipes": recipes,
    }
    target = AUDIT / "near-threshold-recipes.batch01.json"
    if target.exists() and json.loads(target.read_text()) != result:
        raise SystemExit("Near-threshold batch changed; refusing overwrite")
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"recipes": len(recipes), "new_garments": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
