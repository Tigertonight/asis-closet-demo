#!/usr/bin/env python3
"""Design the first 48 autumn recipes for sixteen zero-supply conditions."""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs/audits/20260904-aw-supply"
TARGETS = [
    ("BOLT","ocean","n0003"),("BOLT","jewel","n0007"),("BOLT","bright","n0005"),
    ("EASE","bright","n0004"),("EDGE","jewel","n0006"),("EDGE","bright","n0005"),
    ("FILM","bright","n0008"),("FLOU","jewel","n0006"),("FLOU","bright","n0004"),
    ("HEIR","bright","n0003"),("ICED","jewel","n0002"),("ICED","bright","n0003"),
    ("JADE","ocean","n0016"),("JADE","jewel","n0002"),("JADE","bright","n0008"),
    ("LOOP","bright","n0004"),
]
SUPPORTS = {
    "BOLT":{"pants":["g0337","g0003","g0254","g0513"],"skirt":["g0337","g0188","g0254","g0513"],"dress":["g0222","g0265","g0513"]},
    "EASE":{"pants":["g0108","g0404","g0497","g0284"],"skirt":["g0337","g0188","g0497","g0284"],"dress":["g0219","g0497","g0284"]},
    "EDGE":{"pants":["g0337","g0068","g0069","g0070"],"skirt":["g0337","g0446","g0069","g0070"],"dress":["g0222","g0069","g0070"]},
    "FILM":{"pants":["g0108","g0171","g0491","g0523"],"skirt":["g0337","g0439","g0491","g0523"],"dress":["g0219","g0491","g0523"]},
    "FLOU":{"pants":["g0337","g0404","g0497","g0516"],"skirt":["g0337","g0188","g0497","g0516"],"dress":["g0220","g0497","g0516"]},
    "HEIR":{"pants":["g0108","g0166","g0265","g0275"],"skirt":["g0337","g0446","g0265","g0275"],"dress":["g0222","g0265","g0275"]},
    "ICED":{"pants":["g0337","g0003","g0265","g0513"],"skirt":["g0337","g0188","g0265","g0513"],"dress":["g0222","g0265","g0513"]},
    "JADE":{"pants":["g0108","g0166","g0497","g0284"],"skirt":["g0337","g0188","g0497","g0284"],"dress":["g0219","g0497","g0284"]},
    "LOOP":{"pants":["g0108","g0164","g0254","g0513"],"skirt":["g0337","g0188","g0254","g0513"],"dress":["g0222","g0254","g0513"]},
}


def main() -> None:
    manifest = json.loads((AUDIT / "generated-garments/combined-manifest-v2.json").read_text())
    visual = json.loads((ROOT / "app/data/recommendation-visual.v1.json").read_text())
    recipes = []
    for persona, palette, hero in TARGETS:
        for structure in ("pants", "skirt", "dress"):
            recipes.append({"persona": persona, "palette": palette, "season": "autumn",
                            "structure": structure, "hero": hero,
                            "items": [hero, *SUPPORTS[persona][structure]], "expression": "entry",
                            "intent": f"以 {hero} 主外层解决 {persona}×{palette} 秋季零供给，并保留单一主视觉。"})
    result = {"schema_version":1,"batch_id":"aw-autumn-01","source_visual_version":visual["version"],
              "status":"designer_targets_pending_whole_image_review","new_garments":manifest["garments"],
              "new_garment_manifest":"generated-garments/combined-manifest-v2.json",
              "new_garment_version":manifest["version"],"recipes":recipes}
    target = AUDIT / "autumn-recipes.batch01.json"
    if target.exists() and json.loads(target.read_text()) != result:
        raise SystemExit("Autumn recipe batch changed; refusing overwrite")
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"recipes":len(recipes),"new_garments":0,"reused_generated":len(manifest["garments"])},ensure_ascii=False))


if __name__ == "__main__": main()
