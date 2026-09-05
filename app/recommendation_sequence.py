"""Deterministic bounded look-ahead; expression targets never relax quality.

Inputs must already have passed personal ranking and revision-bound visual QA.
This module does not infer garment suitability or promote audit observations.
"""
from collections import Counter
from heapq import nlargest

from app.recommendation_diversity import outfit_features

VERSION = "personal_home_aw_v2"
STRUCTURES = ("pants", "skirt", "dress")
DAILY_WEARABILITY = {"everyday", "everyday_with_statement"}
EXPRESSIONS = {"easy", "typical", "explore"}


def daily_candidates(ranked, winter=False):
    accepted, rejected = [], Counter()
    for row in ranked:
        visual = row.get("visual") or {}
        if visual.get("expression") not in EXPRESSIONS or visual.get("wearability") not in DAILY_WEARABILITY:
            rejected["daily_wearability_unconfirmed"] += 1
        elif winter and visual.get("winter_outdoor") != "complete_layers_visually_reviewed":
            rejected["winter_outdoor_unconfirmed"] += 1
        else:
            accepted.append(row)
    return accepted, dict(rejected)


def select_flexible_sequence(ranked, limit=30, recent_hero=(), category_filtered=False, beam_width=128):
    if not 1 <= beam_width <= 128:
        raise ValueError("Beam width must be between 1 and 128")
    limit = max(0, min(int(limit), 30))
    # Stable IDs de-duplicate before search; source ranking order is preserved.
    rows = list({r["outfit_id"]: r for r in reversed(ranked)}.values())[::-1]
    n = len(rows)
    if not n or not limit:
        return [], ([{"reason": "no_eligible_candidates", "position": 0}] if limit else []), {"strategy_version": VERSION, "beam_width": beam_width, "search_complete": False}
    features = [outfit_features(r) for r in rows]
    structures = [(r.get("visual") or {}).get("structure") for r in rows]
    expressions = [(r.get("visual") or {}).get("expression") for r in rows]
    scores = [float((r.get("recommendation") or {}).get("score", 1 - i / max(1,n))) for i,r in enumerate(rows)]
    parent_masks, item_masks, family_masks = {}, {}, {}
    for i,(parent,items,families) in enumerate(features):
        bit = 1 << i
        parent_masks[parent] = parent_masks.get(parent,0) | bit
        for k in items: item_masks[k] = item_masks.get(k,0) | bit
        for k in families: family_masks[k] = family_masks.get(k,0) | bit
    valid_mask = sum(1 << i for i in range(n) if expressions[i] in EXPRESSIONS and structures[i] in STRUCTURES)
    fresh_mask = sum(1 << i for i,r in enumerate(rows) if r["outfit_id"] not in recent_hero)
    by_structure = {s: sum(1 << i for i in range(n) if structures[i]==s) for s in STRUCTURES}
    # (path, used-mask, structure counts, utility). Longest feasible path wins.
    states = [((), 0, (0,0,0), 0.)]
    best = states[0]
    targets = ["easy","easy","easy","typical","easy","easy","easy","easy","typical","explore"]
    expansions = 0
    dead_reasons = Counter()

    for position in range(limit):
        next_states = []
        for path,used,counts,utility in states:
            allowed = valid_mask & ~used
            unselected = allowed
            for j in path[-7:]: allowed &= ~parent_masks[features[j][0]]
            for slot,masks in ((1,item_masks),(2,family_masks)):
                seen = set()
                twice = set()
                for j in path[-9:]:
                    twice.update(seen & features[j][slot])
                    seen.update(features[j][slot])
                for key in twice: allowed &= ~masks[key]
            after_repeat = allowed
            if position < 10 and not category_filtered:
                missing = [s for k,s in enumerate(STRUCTURES) if not counts[k]]
                for k,s in enumerate(STRUCTURES):
                    if counts[k]>=5: allowed &= ~by_structure[s]
                if 10-position <= len(missing):
                    allowed &= sum(by_structure[s] for s in missing)
            if not allowed:
                dead_reasons["pool_exhausted" if not unselected else "repeat_constraints" if not after_repeat else "main_structure_constraints"] += 1
            if position < 4 and allowed & fresh_mask:
                allowed &= fresh_mask
            # Bound fan-out without starving a lower-ranked main structure.
            # Sixteen per structure is deliberate: eight let a newly inserted,
            # high-scoring family displace older feasible paths and made supply
            # coverage non-monotonic even for pools smaller than twenty rows.
            choices = []
            for s in STRUCTURES:
                mask = allowed & by_structure[s]
                for _ in range(16):
                    if not mask: break
                    bit = mask & -mask
                    choices.append(bit.bit_length()-1)
                    mask ^= bit
            for i in sorted(choices):
                changed = list(counts)
                if position < 10: changed[STRUCTURES.index(structures[i])] += 1
                # Role matching is secondary and never constrains availability;
                # position zero is always evaluated on personal fit only.
                bonus = .10 if 0 < position < 10 and expressions[i]==targets[position] else 0.
                if position < 10 and not category_filtered and counts[STRUCTURES.index(structures[i])]==0:
                    bonus += .02
                next_states.append((path+(i,), used | (1<<i), tuple(changed), utility+scores[i]+bonus))
            expansions += len(choices)
        if not next_states:
            break
        # During the first ten, preserve paths that establish all three main
        # structures early. Ranking only by utility postponed a scarce skirt or
        # dress until slot ten, where rolling family/item constraints could make
        # it unreachable even though a valid ordering existed.
        states = nlargest(
            beam_width,
            next_states,
            key=lambda s: (
                sum(bool(count) for count in s[2]) if position < 10 and not category_filtered else 0,
                s[3],
                tuple(-i for i in s[0]),
            ),
        )
        best = states[0]
    selected = [rows[i] for i in best[0]]
    gap = []
    missing_structures = sorted(set(STRUCTURES)-set(structures))
    if len(selected)<limit:
        reason = "missing_main_structure" if missing_structures and not category_filtered else "search_unmet"
        gap = [{"reason": reason, "position":len(selected), "missing_structures":missing_structures,
                "observed_blockages":dict(dead_reasons),
                "candidate_count":n, "exhaustive_infeasibility_proven":False}]
    return selected,gap,{"strategy_version":VERSION,"beam_width":beam_width,"fanout_per_structure":16,
        "expanded_states":expansions,"search_complete":len(selected)==limit,
        "expression_distribution":{"carousel":dict(Counter(r["visual"]["expression"] for r in selected[:4])),
                                   "feed":dict(Counter(r["visual"]["expression"] for r in selected[4:10]))},
        "first_ten_structures":dict(Counter(r["visual"]["structure"] for r in selected[:10])),
        "exhaustive_infeasibility_proven":False}
