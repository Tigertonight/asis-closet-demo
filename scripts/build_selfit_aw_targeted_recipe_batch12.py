#!/usr/bin/env python3
"""Build 24 winter recipes for near-first-ten family assets."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
AUDIT = ROOT / "docs/audits/20260904-aw-supply"
from scripts.build_selfit_aw_targeted_recipe_batch09 import SETS, structure

TARGETS = [
    ("n0080", "ocean", "ICED"),
    ("n0081", "pastel", "ICED"),
    ("n0082", "mono", "JADE"),
    ("n0083", "mono", "MELT"),
    ("n0084", "jewel", "MUTE"),
    ("n0085", "bright", "WABI"),
    ("n0086", "ocean", "WABI"),
    ("n0087", "mono", "FILM"),
]


def main():
    visual = json.loads((ROOT / "app/data/recommendation-visual.v1.json").read_text())
    manifest = json.loads((AUDIT / "generated-garments/batch13/manifest.json").read_text())
    recipes = []
    for hero, palette, persona in TARGETS:
        for key in ("pants_clean", "skirt_dark", "dress_classic"):
            recipes.append(
                {
                    "persona": persona,
                    "palette": palette,
                    "season": "winter",
                    "structure": structure(key),
                    "hero": hero,
                    "items": [hero, *SETS[key]],
                    "expression": "entry",
                    "intent": f"{persona}×{palette}×winter 的独立临界家族 {structure(key)} 配方。",
                }
            )
    result = {
        "schema_version": 1,
        "batch_id": "aw-targeted-12",
        "source_visual_version": visual["version"],
        "status": "designer_targets_pending_whole_image_review",
        "new_garments": manifest["garments"],
        "new_garment_manifest": "generated-garments/batch13/manifest.json",
        "new_garment_version": manifest["version"],
        "recipes": recipes,
    }
    assert len(recipes) == 24
    target = AUDIT / "targeted-recipes.batch12.json"
    if target.exists() and json.loads(target.read_text()) != result:
        raise SystemExit("Targeted batch12 changed; refusing overwrite")
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"recipes": 24, "new_garments": 8}, ensure_ascii=False))


if __name__ == "__main__":
    main()
