"""Reproducible effective supply, using only revision-bound visual candidates."""
import argparse
import json
import sys
from copy import deepcopy
from collections import Counter
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.closet import selfit_content_pool, _published_catalog_outfits
from app.recommendation_diversity import outfit_features, style_family_map
from app.recommendation_feed import VERSION as STRATEGY_VERSION, rank_candidates, select_sequence
from app.recommendation_profile import PALETTES, PERSONAS
from app.recommendation_visual import attach_visual, load_visual


def sequence_diagnostics(rows):
    """Describe actual selected content; empty/short feeds never prove richness."""
    count = len(rows)
    features = [outfit_features(o) for o in rows]
    ids = Counter(g for f in features for g in f[1])
    families = Counter(g for f in features for g in f[2])
    accessories = Counter(i["item_id"] for o in rows for i in o["items"] if i.get("category") in {"shoes", "bag"})
    colors = Counter(c for o in rows for c in set(o["visual"].get("main_colors") or []))
    violations = []
    for index, (parent, main, group) in enumerate(features):
        prior = features[max(0, index-9):index]
        for kind, members, slot in (("main", main, 1), ("family", group, 2)):
            previous = Counter(g for f in prior for g in f[slot])
            if any(previous[g] >= 2 for g in members):
                violations.append({"position": index, "type": kind})
        if parent in {f[0] for f in features[max(0, index-7):index]}:
            violations.append({"position": index, "type": "parent"})
    pairs = list(combinations(features, 2))
    return {"count": count, "main_items": len(ids), "main_families": len(families),
            "structures": dict(Counter(o["visual"]["structure"] for o in rows)),
            "silhouettes": dict(Counter(o["visual"].get("silhouette") or "unknown" for o in rows)),
            "layer_counts": dict(Counter(str(o["visual"].get("layering", "unknown")) for o in rows)),
            "color_appearance_counts": dict(colors),
            "highest_color_appearance_share": max(colors.values())/count if count and colors else None,
            "most_used_shoes_and_bags": accessories.most_common(5),
            "mean_pairwise_main_family_jaccard": sum(len(a[2] & b[2])/len(a[2] | b[2]) if a[2] | b[2] else 0 for a,b in pairs)/len(pairs) if pairs else None,
            "constraint_violations": violations,
            "interpretation": "Color counts are reviewed semantic labels, not pixel area; family similarity is not calibrated perception. Short feeds are not a richness pass."}


def audit(season="autumn", registry=None):
    pool = selfit_content_pool()
    catalog = _published_catalog_outfits()
    visual = load_visual()
    if registry is not None:
        assert registry["visual_version"] == visual["version"], "Stale draft families"
        # Override copies only: never poison the shared catalog cache or activate a file.
        catalog = deepcopy(catalog)
        family_map = style_family_map(pool.garments, registry)
        expected = {g for f in registry["families"] for g in f["members"]}
        assert expected == family_map.keys(), "Invalid draft family fingerprints"
        for outfit in catalog:
            for item in outfit["items"]:
                item["style_family_id"] = family_map.get(item["item_id"], "item:" + item["item_id"])
    candidates, held = attach_visual(catalog, pool.garments, pool.outfits, visual)
    matrix, first_tens = [], {}
    for persona in sorted(PERSONAS):
        for palette in PALETTES:
            profile = {"persona_id": persona, "palette": palette, "palette_source": "audit_condition", "axes": {}}
            ranked, rejected = rank_candidates(candidates, profile, {"season_tags": [season], "scene_tags": ["daily"]})
            chosen, gaps = select_sequence(ranked, 30)
            features = [outfit_features(o) for o in ranked]
            top = chosen[:10]
            first_tens[persona, palette] = {o["outfit_id"] for o in top}
            matrix.append({"persona": persona, "palette": palette, "eligible": len(ranked),
                           "parent_recipes": len({f[0] for f in features}),
                           "main_garments": len(set().union(*(f[1] for f in features))),
                           "style_families": len(set().union(*(f[2] for f in features))),
                           "first_ten": len(top), "browse_thirty": len(chosen),
                           "first_ten_structures": dict(Counter(o["visual"]["structure"] for o in top)),
                           "eligible_by_expression_structure": dict(Counter(o["visual"]["expression"]+":"+o["visual"]["structure"] for o in ranked)),
                           "selected_ids": [o["outfit_id"] for o in chosen],
                           "first_ten_diagnostics": sequence_diagnostics(top),
                           "browse_thirty_diagnostics": sequence_diagnostics(chosen),
                           "qualified_first_ten": len(top) == 10, "qualified_browse_thirty": len(chosen) == 30,
                           "gaps": gaps, "rejected": rejected,
                           "required_next_action": "review_existing_images_then_recombine_unused_assets" if len(chosen) < 30 else None})
    comparable, changed = 0, 0
    for persona in PERSONAS:
        for a, b in combinations(PALETTES, 2):
            left, right = first_tens[persona, a], first_tens[persona, b]
            if len(left) == len(right) == 10:
                comparable += 1
                changed += len(left - right) >= 3
    return {"schema_version": 1, "visual_version": visual.get("version"), "strategy_version": STRATEGY_VERSION,
            "scenario": {"season": season, "scene": "daily", "palettes": PALETTES},
            "family_registry": registry.get("version") if registry else "production_registry_unchanged",
            "offline_family_override": registry is not None,
            "interpretation": "Revision-valid visual candidates include experimental expressions, not automatic daily eligibility. Conditions use the current greedy ranking, not maximum feasible supply. Pending review is not proof that an asset is unsuitable. No human or independent blind review.",
            "counts": {"garments": len(pool.garments), "active_outfits": len(catalog),
                       "visual_candidate_outfits": len(candidates), "held_outfits": len(held),
                       "conditions": len(matrix), "qualified_first_ten": sum(r["qualified_first_ten"] for r in matrix),
                       "qualified_browse_thirty": sum(r["qualified_browse_thirty"] for r in matrix)},
            "palette_differentiation": {"comparable_pairs": comparable, "changed_at_least_three": changed,
                                        "pass_fraction": changed/comparable if comparable else None},
            "independent_top1": None, "independent_top2": None, "matrix": matrix}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", choices=["spring", "summer", "autumn", "winter"], default="autumn")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--family-registry", type=Path, help="Offline override only; does not change production registry")
    args = parser.parse_args()
    report = audit(args.season, json.loads(args.family_registry.read_text()) if args.family_registry else None)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report["counts"]))
