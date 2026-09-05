"""Deterministic feed constraints, including the preceding page's exposure window.

Scores decide preference, never permission to violate repetition limits. Unknown
families are singletons; machine similarity candidates are not merged silently.
"""
from __future__ import annotations

import json
from collections import Counter
from functools import lru_cache
from pathlib import Path

from app.selfit_content_quality import record_fingerprint

VERSION = "diverse_feed_v1"
MAIN_SLOTS = {"top", "outer", "bottom", "skirt", "dress"}
FAMILY_PATH = Path(__file__).parent / "data/garment-style-families.v1.json"


def main_recipe_signature(outfit: dict) -> tuple[str, ...]:
    """Identify the clothing recipe independently of accessory changes or IDs."""
    return tuple(sorted({
        str(item["item_id"]) for item in outfit.get("items", [])
        if (item.get("slot") or item.get("category")) in MAIN_SLOTS
        and item.get("item_id")
    }))


@lru_cache(maxsize=4)
def _read_families(path: str, stamp: int) -> dict:
    try:
        data = json.loads(Path(path).read_text())
        return data if isinstance(data, dict) and data.get("schema_version") == 1 else {}
    except (OSError, ValueError):
        return {}


def style_family_map(garments: list[dict], registry: dict | None = None) -> dict[str, str]:
    if registry is None:
        try:
            registry = _read_families(str(FAMILY_PATH), FAMILY_PATH.stat().st_mtime_ns)
        except OSError:
            registry = {}
    if not isinstance(registry, dict) or not isinstance(registry.get("families", []), list):
        return {}
    records = {g["id"]: g for g in garments}
    result = {}
    for family in registry.get("families", []):
        if not isinstance(family, dict) or not family.get("id"):
            continue
        members = family.get("members", {})
        if (not isinstance(members, dict) or family.get("status") != "visual_reviewed" or not family.get("evidence")
                or not family.get("reviewer") or len(members) < 2):
            continue
        # A changed member invalidates the whole association, not just that ID.
        if any(gid not in records or fingerprint != record_fingerprint(records[gid])
               for gid, fingerprint in members.items()):
            continue
        if len({records[gid].get("category") for gid in members}) != 1:
            continue
        if set(members) & result.keys():
            return {}  # Invalid registry: keep safe singleton / exact-ID limits.
        result.update({gid: family["id"] for gid in members})
    return result


def outfit_features(outfit: dict) -> tuple[str, frozenset, frozenset]:
    oid = str(outfit.get("outfit_id") or "")
    parent = str(outfit.get("parent_outfit_id") or oid)
    main = [i for i in outfit.get("items", [])
            if (i.get("slot") or i.get("category")) in MAIN_SLOTS and i.get("item_id")]
    ids = frozenset(str(i["item_id"]) for i in main)
    families = frozenset(str(i.get("style_family_id") or "item:" + str(i["item_id"])) for i in main)
    return parent, ids, families


def select_diverse_outfits(ranked: list[dict], seen_ids: list[str], limit: int) -> dict:
    """Main IDs/families <=2 in every 10; recipe relatives >=8 positions apart.

    Reconsider deferred candidates after every pick. Probe one extra pick for
    has_more, without recording it as exposure. No filler when constraints block.
    seen_ids must be the client-delivered order, not a set or score order.
    """
    by_id = {str(o["outfit_id"]): o for o in ranked}
    features = {oid: outfit_features(o) for oid, o in by_id.items()}
    seen = list(dict.fromkeys(str(oid) for oid in seen_ids))
    history = [features[oid] if oid in features else None for oid in seen[-9:]]
    excluded = set(seen)
    candidates = [oid for oid in by_id if oid not in excluded]
    chosen = []
    for _ in range(limit + 1):
        main_counts = Counter(g for f in history[-9:] if f for g in f[1])
        family_counts = Counter(g for f in history[-9:] if f for g in f[2])
        recent_parents = {f[0] for f in history[-7:] if f}
        pick = next((oid for oid in candidates
                     if features[oid][0] not in recent_parents
                     and all(main_counts[g] < 2 for g in features[oid][1])
                     and all(family_counts[g] < 2 for g in features[oid][2])), None)
        if pick is None:
            break
        candidates.remove(pick)
        chosen.append(pick)
        history.append(features[pick])
    has_more = len(chosen) > limit
    returned = chosen[:limit]
    remaining = len(by_id.keys() - excluded - set(returned))
    return {
        "outfits": [by_id[oid] for oid in returned],
        "has_more": has_more,
        "diversity": {
            "version": VERSION, "window": 10, "main_item_cap": 2,
            "style_family_cap": 2, "recipe_min_distance": 8,
            "remaining_candidates": remaining,
            "stop_reason": None if has_more else "diversity_limit" if remaining else "pool_exhausted",
        },
    }
