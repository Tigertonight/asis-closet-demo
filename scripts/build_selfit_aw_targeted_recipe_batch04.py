#!/usr/bin/env python3
"""Test bounded cross-persona reuse of newly reviewed winter outerwear."""
from __future__ import annotations

import json
from pathlib import Path


ROOT=Path(__file__).resolve().parents[1]
AUDIT=ROOT/"docs/audits/20260904-aw-supply"
RECIPES=[
    ("ICED","mono","pants","n0031",["n0031","g0114","g0172","g0258","g0289"]),
    ("ICED","mono","dress","n0031",["n0031","g0234","g0258","g0289"]),
    ("EDGE","mono","skirt","n0031",["n0031","g0337","g0429","g0069","g0070"]),
    ("MUTE","mono","dress","n0031",["n0031","g0222","g0265","g0513"]),
    ("EASE","mono","pants","n0032",["n0032","g0108","g0404","g0497","g0284"]),
    ("EASE","mono","dress","n0032",["n0032","g0468","g0497","g0284"]),
    ("LOOP","mono","pants","n0032",["n0032","g0365","g0172","g0258","g0289"]),
    ("LOOP","mono","dress","n0032",["n0032","g0222","g0265","g0513"]),
]


def main():
    visual=json.loads((ROOT/"app/data/recommendation-visual.v1.json").read_text())
    manifest=json.loads((AUDIT/"generated-garments/batch06/manifest.json").read_text())
    recipes=[{"persona":p,"palette":palette,"season":"winter","structure":structure,"hero":hero,"items":items,
              "expression":"entry","intent":f"验证 {hero} 在 {p} 的清晰视觉证据；同一人格最多两个结构。"}
             for p,palette,structure,hero,items in RECIPES]
    result={"schema_version":1,"batch_id":"aw-targeted-04","source_visual_version":visual["version"],
            "status":"designer_targets_pending_whole_image_review","new_garments":manifest["garments"],
            "new_garment_manifest":"generated-garments/batch06/manifest.json","new_garment_version":manifest["version"],
            "recipes":recipes}
    target=AUDIT/"targeted-recipes.batch04.json"
    if target.exists() and json.loads(target.read_text())!=result: raise SystemExit("Targeted batch changed; refusing overwrite")
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"recipes":len(recipes),"new_garments":0},ensure_ascii=False))


if __name__=="__main__":main()
