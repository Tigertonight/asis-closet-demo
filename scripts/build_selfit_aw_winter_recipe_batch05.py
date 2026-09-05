#!/usr/bin/env python3
"""Design 48 existing-asset winter recipes for the remaining zero conditions.

Three different outerwear heroes are used per condition so the batch does not
pretend that changing only the lower garment creates independent supply.
"""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs/audits/20260904-aw-supply"

OUTERS = {
    ("BOLT", "earth"): ["g0394", "g0570", "g0378"],
    ("BOLT", "pastel"): ["g0394", "g0570", "g0373"],
    ("EDGE", "earth"): ["g0368", "g0390", "g0051"],
    ("EDGE", "pastel"): ["g0384", "g0569", "g0377"],
    ("ICED", "earth"): ["g0157", "g0134", "g0131"],
    ("NEON", "earth"): ["g0368", "g0392", "g0051"],
    ("NEON", "ocean"): ["g0376", "g0392", "g0384"],
    ("NEON", "pastel"): ["g0376", "g0384", "g0569"],
    ("NOIR", "earth"): ["g0157", "g0131", "g0395"],
    ("NOIR", "pastel"): ["g0133", "g0140", "g0156"],
    ("OOPS", "earth"): ["g0368", "g0390", "g0395"],
    ("OOPS", "ocean"): ["g0376", "g0392", "g0384"],
    ("OOPS", "pastel"): ["g0384", "g0569", "g0377"],
    ("VOID", "earth"): ["g0374", "g0390", "g0395"],
    ("VOID", "ocean"): ["g0383", "g0384", "g0152"],
    ("WABI", "ocean"): ["g0051", "g0383", "g0152"],
}

SUPPORT = {
    "BOLT": {"pants": ["g0108", "g0003", "g0265", "g0270"], "skirt": ["g0337", "g0207", "g0254", "g0270"], "dress": ["g0222", "g0069", "g0070"]},
    "EDGE": {"pants": ["g0350", "g0398", "g0043", "g0526"], "skirt": ["g0337", "g0429", "g0265", "g0513"], "dress": ["g0462", "g0265", "g0513"]},
    "ICED": {"pants": ["g0365", "g0172", "g0265", "g0513"], "skirt": ["g0337", "g0206", "g0258", "g0289"], "dress": ["g0234", "g0265", "g0513"]},
    "NEON": {"pants": ["g0108", "g0003", "g0043", "g0070"], "skirt": ["g0337", "g0188", "g0254", "g0513"], "dress": ["g0222", "g0265", "g0513"]},
    "NOIR": {"pants": ["g0337", "g0068", "g0069", "g0070"], "skirt": ["g0350", "g0446", "g0069", "g0070"], "dress": ["g0462", "g0069", "g0070"]},
    "OOPS": {"pants": ["g0096", "g0398", "g0505", "g0526"], "skirt": ["g0337", "g0188", "g0505", "g0513"], "dress": ["g0222", "g0505", "g0513"]},
    "VOID": {"pants": ["g0337", "g0415", "g0591", "g0526"], "skirt": ["g0337", "g0449", "g0591", "g0526"], "dress": ["g0222", "g0591", "g0526"]},
    "WABI": {"pants": ["g0337", "g0415", "g0591", "g0284"], "skirt": ["g0337", "g0447", "g0591", "g0284"], "dress": ["g0468", "g0497", "g0284"]},
}


def main() -> None:
    visual = json.loads((ROOT / "app/data/recommendation-visual.v1.json").read_text())
    recipes = []
    structures = ("pants", "skirt", "dress")
    for (persona, palette), outers in OUTERS.items():
        for structure, outer in zip(structures, outers, strict=True):
            support = SUPPORT[persona][structure]
            recipes.append({"persona": persona, "palette": palette, "season": "winter", "structure": structure,
                            "hero": outer, "items": [outer, *support], "expression": "entry",
                            "intent": f"{persona} × {palette} 冬季日常 {structure}；使用独立外层主衣、封闭鞋履和低竞争支撑款，待整图复核。"})
    assert len(recipes) == 48
    result = {"schema_version": 1, "batch_id": "aw-winter-05", "source_visual_version": visual["version"],
              "status": "designer_targets_pending_whole_image_review", "new_garments": [], "recipes": recipes}
    target = AUDIT / "winter-recipes.batch05.json"
    if target.exists() and json.loads(target.read_text()) != result:
        raise SystemExit("Winter recipe batch changed; refusing overwrite")
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"recipes": len(recipes), "conditions": len(OUTERS), "new_garments": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
