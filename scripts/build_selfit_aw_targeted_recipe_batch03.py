#!/usr/bin/env python3
"""Render the content-bound correction of targeted recipe batch02."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.build_selfit_aw_targeted_recipe_batch02 import RECIPES as UNBOUND_RECIPES


AUDIT = ROOT / "docs/audits/20260904-aw-supply"
TOKEN_MAP = {f"n{i:04d}": f"n{i + 8:04d}" for i in range(18, 26)}


def main() -> None:
    visual = json.loads((ROOT / "app/data/recommendation-visual.v1.json").read_text())
    manifest = json.loads((AUDIT / "generated-garments/batch06/manifest.json").read_text())
    recipes = []
    for persona, palette, season, structure, hero, items in UNBOUND_RECIPES:
        hero = TOKEN_MAP.get(hero, hero)
        items = [TOKEN_MAP.get(item, item) for item in items]
        recipes.append({
            "persona": persona, "palette": palette, "season": season,
            "structure": structure, "hero": hero, "items": items, "expression": "entry",
            "intent": f"针对 {persona} × {palette} × {season} 缺失的 {structure} 主结构或新主衣家族。",
        })
    result = {
        "schema_version": 1, "batch_id": "aw-targeted-03",
        "source_visual_version": visual["version"],
        "status": "designer_targets_pending_whole_image_review",
        "new_garments": manifest["garments"],
        "new_garment_manifest": "generated-garments/batch06/manifest.json",
        "new_garment_version": manifest["version"], "recipes": recipes,
    }
    target = AUDIT / "targeted-recipes.batch03.json"
    if target.exists() and json.loads(target.read_text()) != result:
        raise SystemExit("Corrected targeted recipe batch changed; refusing overwrite")
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"recipes": len(recipes), "new_garments": len(manifest["garments"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
