#!/usr/bin/env python3
"""Build 48 autumn/winter recipes for eight exact persona-colour gaps."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs/audits/20260904-aw-supply"
SETS = {
    "pants_clean": ["g0114", "g0172", "g0258", "g0289"],
    "skirt_dark": ["g0337", "g0190", "g0069", "g0070"],
    "dress_classic": ["g0217", "g0004", "g0270"],
}
TARGETS = [
    ("n0056", "pastel", "FILM"),
    ("n0057", "bright", "FILM"),
    ("n0058", "earth", "BOLT"),
    ("n0059", "pastel", "BOLT"),
    ("n0060", "bright", "BOLT"),
    ("n0061", "bright", "ICED"),
    ("n0062", "earth", "EDGE"),
    ("n0063", "bright", "JADE"),
]


def structure(key: str) -> str:
    return "dress" if key.startswith("dress") else "skirt" if key.startswith("skirt") else "pants"


def main():
    visual = json.loads((ROOT / "app/data/recommendation-visual.v1.json").read_text())
    manifest = json.loads((AUDIT / "generated-garments/batch10/manifest.json").read_text())
    recipes = []
    for hero, palette, persona in TARGETS:
        for season in ("autumn", "winter"):
            for key in ("pants_clean", "skirt_dark", "dress_classic"):
                recipes.append({
                    "persona": persona,
                    "palette": palette,
                    "season": season,
                    "structure": structure(key),
                    "hero": hero,
                    "items": [hero, *SETS[key]],
                    "expression": "entry",
                    "intent": f"{persona}×{palette}×{season} 的 {structure(key)} 缺口；新主衣提供颜色与人格轮廓，支撑款保持低竞争。",
                })
    assert len(recipes) == 48
    result = {
        "schema_version": 1,
        "batch_id": "aw-targeted-09",
        "source_visual_version": visual["version"],
        "status": "designer_targets_pending_whole_image_review",
        "new_garments": manifest["garments"],
        "new_garment_manifest": "generated-garments/batch10/manifest.json",
        "new_garment_version": manifest["version"],
        "recipes": recipes,
    }
    target = AUDIT / "targeted-recipes.batch09.json"
    if target.exists() and json.loads(target.read_text()) != result:
        raise SystemExit("Targeted batch09 changed; refusing overwrite")
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"recipes": len(recipes), "new_garments": 8}, ensure_ascii=False))


if __name__ == "__main__":
    main()
