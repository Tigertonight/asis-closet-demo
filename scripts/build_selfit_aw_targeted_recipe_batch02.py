#!/usr/bin/env python3
"""Compose exact missing autumn dresses and new winter outerwear families."""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs/audits/20260904-aw-supply"


RECIPES = [
    ("MELT", "earth", "autumn", "dress", "n0018", ["n0018", "g0497", "g0284"]),
    ("MUTE", "ocean", "autumn", "dress", "n0019", ["n0019", "g0258", "g0289"]),
    # n0020 is intentionally rendered but must be held if actual color evidence remains warm-brown.
    ("OOPS", "mono", "autumn", "dress", "n0020", ["n0020", "g0069", "g0070"]),
    ("OOPS", "pastel", "autumn", "dress", "n0021", ["n0021", "g0254", "g0513"]),
    ("VOID", "earth", "autumn", "dress", "n0022", ["n0022", "g0591", "g0526"]),
]

WINTER_SUPPORTS = {
    "NOIR": {
        "pants": ["g0337", "g0068", "g0069", "g0070"],
        "skirt": ["g0337", "g0446", "g0069", "g0070"],
        "dress": ["g0462", "g0069", "g0070"],
    },
    "VOID": {
        "pants": ["g0337", "g0415", "g0591", "g0526"],
        "skirt": ["g0337", "g0449", "g0591", "g0526"],
        "dress": ["g0222", "g0591", "g0526"],
    },
    "WABI": {
        "pants": ["g0108", "g0404", "g0497", "g0284"],
        "skirt": ["g0337", "g0449", "g0591", "g0526"],
        "dress": ["g0468", "g0497", "g0284"],
    },
}

for persona, palette, hero in (
    ("NOIR", "mono", "n0023"),
    ("VOID", "mono", "n0024"),
    ("WABI", "jewel", "n0025"),
):
    for structure in ("pants", "skirt", "dress"):
        RECIPES.append((persona, palette, "winter", structure, hero,
                        [hero, *WINTER_SUPPORTS[persona][structure]]))


def main() -> None:
    visual = json.loads((ROOT / "app/data/recommendation-visual.v1.json").read_text())
    manifest = json.loads((AUDIT / "generated-garments/batch05/manifest.json").read_text())
    recipes = [{
        "persona": persona, "palette": palette, "season": season,
        "structure": structure, "hero": hero, "items": items, "expression": "entry",
        "intent": f"针对 {persona} × {palette} × {season} 缺失的 {structure} 主结构或新主衣家族。",
    } for persona, palette, season, structure, hero, items in RECIPES]
    assert len(recipes) == 14
    result = {
        "schema_version": 1, "batch_id": "aw-targeted-02",
        "source_visual_version": visual["version"],
        "status": "designer_targets_pending_whole_image_review",
        "new_garments": manifest["garments"],
        "new_garment_manifest": "generated-garments/batch05/manifest.json",
        "new_garment_version": manifest["version"], "recipes": recipes,
    }
    target = AUDIT / "targeted-recipes.batch02.json"
    if target.exists() and json.loads(target.read_text()) != result:
        raise SystemExit("Targeted recipe batch changed; refusing overwrite")
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"recipes": len(recipes), "new_garments": len(manifest["garments"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
