#!/usr/bin/env python3
"""Find an exact first-10 sequence for selected AW conditions.

This is an audit-only depth-first feasibility check. It uses the same quality
gate and hard first-10 constraints as the production selector, but does not
change ranking or claim that failure beyond the configured node cap is proof.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.closet import _published_catalog_outfits, selfit_content_pool
from app.recommendation_aw import load_recomposition_candidates, prepare_candidates
from app.recommendation_diversity import outfit_features
from app.recommendation_feed import rank_candidates
from app.recommendation_profile import PALETTES, PERSONAS
from app.recommendation_sequence import DAILY_WEARABILITY, EXPRESSIONS, STRUCTURES, daily_candidates
from app.recommendation_visual import attach_visual, load_visual

DEFAULT_TARGETS = {
    ("winter", "iced", "ocean"),
    ("winter", "iced", "pastel"),
    ("winter", "mute", "jewel"),
    ("winter", "wabi", "bright"),
    ("winter", "wabi", "ocean"),
}


def _ordered_subset(combo, features):
    """Order a valid 10-row subset so repeated parents are eight slots apart."""
    by_parent = {}
    for index in combo:
        by_parent.setdefault(features[index][0], []).append(index)
    duplicated = [members for members in by_parent.values() if len(members) == 2]
    if len(duplicated) > 2 or any(len(members) > 2 for members in by_parent.values()):
        return None
    slots = [None] * 10
    if duplicated:
        slots[0], slots[8] = duplicated[0]
    if len(duplicated) == 2:
        slots[1], slots[9] = duplicated[1]
    placed = {index for index in slots if index is not None}
    remaining = iter(index for index in combo if index not in placed)
    for position in range(10):
        if slots[position] is None:
            slots[position] = next(remaining)
    return tuple(slots)


def exact_first_ten(rows, node_cap=2_000_000):
    rows = list({row["outfit_id"]: row for row in reversed(rows)}.values())[::-1]
    features = [outfit_features(row) for row in rows]
    structures = [(row.get("visual") or {}).get("structure") for row in rows]
    valid = [i for i, row in enumerate(rows) if structures[i] in STRUCTURES and (row.get("visual") or {}).get("expression") in EXPRESSIONS]
    nodes = 0
    capped = False
    path = None
    for combo in combinations(valid, 10):
        nodes += 1
        if nodes > node_cap:
            capped = True
            break
        structure_counts = Counter(structures[index] for index in combo)
        if set(structure_counts) != set(STRUCTURES) or max(structure_counts.values()) > 5:
            continue
        parent_counts = Counter(features[index][0] for index in combo)
        if max(parent_counts.values()) > 2 or sum(value == 2 for value in parent_counts.values()) > 2:
            continue
        item_counts = Counter(item for index in combo for item in features[index][1])
        if any(value > 2 for value in item_counts.values()):
            continue
        family_counts = Counter(family for index in combo for family in features[index][2])
        if any(value > 2 for value in family_counts.values()):
            continue
        path = _ordered_subset(combo, features)
        if path is not None:
            break
    return {
        "status": "feasible" if path is not None else "combination_cap_reached" if capped else "infeasible_proven",
        "nodes": nodes,
        "node_cap": node_cap,
        "candidate_count": len(rows),
        "method": "exact_10_row_combination_enumeration_then_parent_distance_ordering",
        "selected_ids": [rows[i]["outfit_id"] for i in path] if path is not None else [],
        "structures": dict(Counter(structures[i] for i in path)) if path is not None else {},
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--node-cap", type=int, default=2_000_000)
    args = parser.parse_args()

    pool = selfit_content_pool()
    visual = load_visual()
    published, _ = attach_visual(_published_catalog_outfits(), pool.garments, pool.outfits, visual)
    supplemental, supplemental_version = load_recomposition_candidates(pool.garments, visual)
    candidates, bundle = prepare_candidates(published + supplemental, pool.garments, visual, supplemental_version=supplemental_version)
    results = []
    for season, persona, palette in sorted(DEFAULT_TARGETS):
        assert persona in PERSONAS and palette in PALETTES
        ranked, rejected = rank_candidates(candidates, {"persona_id": persona, "palette": palette, "axes": {}}, {"season_tags": [season], "scene_tags": ["daily"]})
        daily, daily_rejected = daily_candidates(ranked, winter=season == "winter")
        result = exact_first_ten(daily, args.node_cap)
        result.update({"season": season, "persona": persona, "palette": palette, "rank_rejected": rejected, "daily_rejected": daily_rejected})
        results.append(result)
        print(season, persona, palette, result["status"], result["candidate_count"], result["nodes"], flush=True)
    payload = {
        "schema_version": 1,
        "scope": "audit_only_exact_first10_for_search_unmet_conditions",
        "hard_constraints": {"all_structures": list(STRUCTURES), "max_one_structure": 5, "same_main_item_or_family_in_rolling_10": 2, "same_parent_minimum_distance": 8},
        "quality_gate": {"expressions": sorted(EXPRESSIONS), "wearability": sorted(DAILY_WEARABILITY), "winter_outdoor": "complete_layers_visually_reviewed"},
        "bundle": bundle,
        "results": results,
        "production_approved": False,
        "interpretation": "Feasible proves the current bounded selector missed a valid ordering. Infeasible_proven applies only to this revision-bound eligible candidate set and these explicit first-10 constraints.",
    }
    if args.output.exists():
        raise SystemExit("Output exists; refusing overwrite")
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
