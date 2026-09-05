"""Design a first bounded winter recipe batch from existing reviewed garments.

The output is a proposal queue only. Whole-image review decides winter and persona
eligibility; target labels are never treated as observations.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.closet import selfit_content_pool
from app.recommendation_feed import palette_affinity
from app.recommendation_profile import PERSONAS
from app.recommendation_visual import load_visual, valid_observation


AUDIT = ROOT / "docs/audits/20260904-aw-supply"
PALETTES = ["mono", "earth", "ocean", "pastel"]
STRUCTURES = ["bottom", "skirt", "dress"]


def affinity(garment: dict, palette: str) -> float:
    swatches = (garment.get("color_evidence") or {}).get("swatches") or []
    values = []
    for swatch in swatches:
        score = palette_affinity(swatch.get("hex"), palette)
        if score is not None:
            values.append((score, max(0.0, float(swatch.get("weight") or 0))))
    total = sum(weight for _, weight in values)
    return sum(score * weight for score, weight in values) / total if total else 0.0


def suitable(observation: dict, category: str) -> bool:
    subcategory = str(observation.get("subcategory") or "").lower()
    length = str(observation.get("length") or "").lower()
    sleeve = str(observation.get("sleeve") or "").lower()
    covered_sleeve = sleeve == "long" or sleeve.startswith("long_") or sleeve.startswith("three_quarter")
    forbidden = ("sheer", "cutout", "corset", "slip", "sleeveless", "mini", "slingback", "stiletto")
    if any(word in subcategory for word in forbidden):
        return False
    if category == "outer":
        return covered_sleeve and any(word in subcategory for word in ("coat", "trench", "jacket", "blazer", "parka", "puffer", "bomber"))
    if category == "top":
        return covered_sleeve
    if category == "bottom":
        return length in {"long", "full", "ankle"}
    if category in {"skirt", "dress"}:
        return length in {"midi", "maxi", "knee", "long"} and (category != "dress" or covered_sleeve)
    if category == "shoes":
        return any(word in subcategory for word in ("boot", "loafer", "trainer", "sneaker", "mary_jane"))
    return category == "bag"


def main() -> None:
    visual = load_visual()
    pool = selfit_content_pool()
    garment_by_id = {row["id"]: row for row in pool.garments}
    candidates = {category: [] for category in ("outer", "top", "bottom", "skirt", "dress", "shoes", "bag")}
    for gid, review in visual["garments"].items():
        garment = garment_by_id[gid]
        observation = review["observations"]
        category = observation["category"]
        if category not in candidates or not valid_observation(garment, review, garment["assets"]["image_url"], "garments"):
            continue
        if suitable(observation, category):
            candidates[category].append((review["token"], garment, observation))
    assert all(candidates.values())

    usage = Counter()
    recipes = []
    for persona_index, persona in enumerate(sorted(PERSONAS)):
        for structure_index, structure in enumerate(STRUCTURES):
            target_palette = PALETTES[(persona_index + structure_index) % len(PALETTES)]
            categories = ["outer", structure, "shoes", "bag"] if structure == "dress" else ["outer", "top", structure, "shoes", "bag"]
            selected = []
            for category in categories:
                ranked = []
                for token, garment, observation in candidates[category]:
                    personas = set(observation.get("visual_personas") or [])
                    palette_score = affinity(garment, target_palette)
                    decoration = observation.get("decoration")
                    score = (2.2 if persona in personas else .45 if personas & {persona} else 0)
                    score += 1.5 * palette_score
                    score += .25 if decoration == "low" else 0
                    score -= .32 * usage[token]
                    ranked.append((score, palette_score, token, garment, observation))
                ranked.sort(key=lambda row: (-row[0], -row[1], row[2]))
                chosen = ranked[0]
                selected.append(chosen)
                usage[chosen[2]] += 1
            tokens = [row[2] for row in selected]
            main_rows = [row for row in selected if row[4]["category"] in {"outer", "top", "bottom", "skirt", "dress"}]
            hero = max(main_rows, key=lambda row: ((persona in set(row[4].get("visual_personas") or [])), row[0]))[2]
            recipes.append({
                "persona": persona.upper(), "palette": target_palette, "season": "winter",
                "structure": "pants" if structure == "bottom" else structure,
                "hero": hero, "items": tokens, "expression": "entry",
                "intent": (
                    f"冬季日常目标：{persona.upper()} × {target_palette} × "
                    f"{'pants' if structure == 'bottom' else structure}；外层、内层、主结构与封闭鞋履完整，待整图复核。"
                ),
            })
    assert len(recipes) == 48 and all(len(recipe["items"]) == len(set(recipe["items"])) for recipe in recipes)
    result = {
        "schema_version": 1, "batch_id": "aw-winter-01", "source_visual_version": visual["version"],
        "status": "designer_targets_pending_whole_image_review", "new_garments": [], "recipes": recipes,
    }
    target = AUDIT / "winter-recipes.batch01.json"
    if target.exists() and json.loads(target.read_text()) != result:
        raise SystemExit("Winter recipe batch changed; refusing overwrite")
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(target, len(recipes), dict(usage.most_common(10)))


if __name__ == "__main__":
    main()
