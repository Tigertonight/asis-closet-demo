"""Prepare a revision-bound P0 anchor candidate manifest.

This command never marks content approved.  It selects only current visual-AI
candidates and reports the exact editorial/production gaps that remain before
four-gate review and independent blind review can begin.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import closet
from app.recommendation_anchors import PERSONAS, TARGET_EXPRESSIONS
from app.recommendation_diversity import FAMILY_PATH, outfit_features, main_recipe_signature
from app.recommendation_visual import attach_visual, load_visual
from app.selfit_content_quality import record_fingerprint, review_is_current

DAILY = {"everyday", "everyday_with_statement"}
STRUCTURES = {"pants", "skirt", "dress"}
PERSONA_NAMES = {
    "mute": "静音时髦", "iced": "冷感冰面", "heir": "老钱新穿", "ease": "松弛讲究",
    "melt": "奶油治愈", "wabi": "手作侘寂", "flou": "造梦浪漫", "neon": "灵动吸睛",
    "edge": "甜酷轻亚", "bolt": "在逃千金", "film": "虚焦胶片", "jade": "东方玉骨",
    "loop": "无限重启", "noir": "暗黑肃杀", "void": "人间失格", "oops": "搭配事故",
}
TITLE_TAILS = ("轻松出门", "日常有序", "柔和转场", "比例游戏", "一件成型", "层次呼吸", "利落收束", "细节聚焦", "周末漫游", "小幅冒险")


def select_persona(rows, excluded_parents=frozenset(), excluded_recipes=frozenset()):
    rows = [row for row in rows if (row.get("visual") or {}).get("expression") in TARGET_EXPRESSIONS
            and (row.get("visual") or {}).get("structure") in STRUCTURES
            and (row.get("visual") or {}).get("wearability") in DAILY
            and (not (row.get("visual") or {}).get("scenes")
                 or "daily" in row["visual"]["scenes"])
            and sum(role == "hero" for role in (row.get("_raw") or {}).get("slot_roles", {}).values()) == 1
            and (int((row.get("visual") or {}).get("layering") or 1) <= 1
                 or (row.get("_raw") or {}).get("layer_graph"))]
    distinct_rows, recipes = [], set(excluded_recipes)
    for row in sorted(rows, key=lambda value: (-float(value.get("_target_persona_score") or 0), value["outfit_id"])):
        signature = main_recipe_signature(row)
        if not signature or signature in recipes or outfit_features(row)[0] in excluded_parents:
            continue
        recipes.add(signature)
        distinct_rows.append(row)
    rows = distinct_rows
    by_expression = {
        name: [
            row for row in rows
            if row["visual"]["expression"] == name
            and outfit_features(row)[0] not in excluded_parents
        ]
        for name in TARGET_EXPRESSIONS
    }
    order = ["explore"] * 2 + ["typical"] * 4 + ["easy"] * 4
    best = []

    def walk(position, chosen, parents, main_counts, family_counts, structure_counts):
        nonlocal best
        if len(chosen) > len(best):
            best = list(chosen)
        if position == len(order):
            return list(chosen) if set(structure_counts) == STRUCTURES else None
        expression = order[position]
        candidates = []
        for row in by_expression[expression]:
            parent, main_ids, families = outfit_features(row)
            if parent in parents or any(main_counts[value] >= 2 for value in main_ids) or any(family_counts[value] >= 2 for value in families):
                continue
            structure = row["visual"]["structure"]
            if structure_counts[structure] >= 5:
                continue
            candidates.append((row, parent, main_ids, families, structure))
        candidates.sort(key=lambda value: (
            structure_counts[value[4]] > 0,
            sum(main_counts[item] for item in value[2]),
            sum(family_counts[item] for item in value[3]),
            -float(value[0].get("_target_persona_score") or 0),
            value[0]["outfit_id"],
        ))
        for row, parent, main_ids, families, structure in candidates:
            chosen.append(row); parents.add(parent); structure_counts[structure] += 1
            main_counts.update(main_ids); family_counts.update(families)
            result = walk(position + 1, chosen, parents, main_counts, family_counts, structure_counts)
            if result is not None:
                return result
            for value in main_ids:
                main_counts[value] -= 1
            for value in families:
                family_counts[value] -= 1
            structure_counts[structure] -= 1; parents.remove(parent); chosen.pop()
        return None

    enough_by_expression = all(
        len(by_expression[name]) >= required
        for name, required in TARGET_EXPRESSIONS.items()
    )
    all_structures = {
        row["visual"]["structure"]
        for values in by_expression.values()
        for row in values
    }
    complete = (
        walk(0, [], set(), Counter(), Counter(), Counter())
        if enough_by_expression and all_structures == STRUCTURES
        else None
    )
    if complete is not None:
        return complete, {name: len(values) for name, values in by_expression.items()}

    # When the exact mix is impossible, still prepare the largest useful
    # editorial queue.  Skipping an unavailable role lets later roles remain
    # visible instead of reporting only the DFS prefix before the first gap.
    def greedy(order):
        partial, parents = [], set()
        main_counts, family_counts, structure_counts = Counter(), Counter(), Counter()
        for expression in order:
            candidates = []
            for row in by_expression[expression]:
                parent, main_ids, families = outfit_features(row)
                structure = row["visual"]["structure"]
                if (parent in parents or structure_counts[structure] >= 5
                        or any(main_counts[value] >= 2 for value in main_ids)
                        or any(family_counts[value] >= 2 for value in families)):
                    continue
                candidates.append((row, parent, main_ids, families, structure))
            if not candidates:
                continue
            row, parent, main_ids, families, structure = min(candidates, key=lambda value: (
                structure_counts[value[4]] > 0,
                sum(main_counts[item] for item in value[2]),
                sum(family_counts[item] for item in value[3]),
                -float(value[0].get("_target_persona_score") or 0),
                value[0]["outfit_id"],
            ))
            partial.append(row); parents.add(parent); structure_counts[structure] += 1
            main_counts.update(main_ids); family_counts.update(families)
        return partial

    attempts = [
        greedy(["easy"] * 4 + ["typical"] * 4 + ["explore"] * 2),
        greedy(["explore"] * 2 + ["typical"] * 4 + ["easy"] * 4),
    ]
    partial = max(attempts, key=lambda values: (
        len(values),
        sum(row["visual"]["expression"] == "explore" for row in values),
    ))
    return partial, {name: len(values) for name, values in by_expression.items()}


def build_manifest(staging_path: Path | None = None, persona_signal: str = "visual"):
    pool = closet.selfit_content_pool()
    visual = load_visual()
    catalog, held = attach_visual(closet._published_catalog_outfits(), pool.garments, pool.outfits, visual)
    raw = {row["id"]: row for row in pool.outfits}
    staging_version = None
    staging_count = 0
    if staging_path:
        staging = json.loads(staging_path.read_text(encoding="utf-8"))
        family_sha = hashlib.sha256(FAMILY_PATH.read_bytes()).hexdigest() if FAMILY_PATH.is_file() else "missing"
        if (staging.get("schema_version") != 1
                or staging.get("base_content_version") != pool.metadata.get("contentVersion")
                or staging.get("visual_version") != visual.get("version")
                or staging.get("family_registry_sha256") != family_sha):
            raise ValueError("P0 staging bundle is missing, invalid, or stale")
        staging_version = staging.get("version")
        staging_count = len(staging.get("entries") or [])
        for entry in staging.get("entries") or []:
            source, adapted = entry.get("raw_record"), entry.get("catalog_record")
            if (not isinstance(source, dict) or not isinstance(adapted, dict)
                    or entry.get("record_fingerprint") != record_fingerprint(source)
                    or source.get("id") != adapted.get("outfit_id")):
                raise ValueError("P0 staging contains a stale candidate")
            if source["id"] in raw:
                raise ValueError(f"P0 staging duplicates published content: {source['id']}")
            raw[source["id"]] = source
            catalog.append(adapted)
    catalog = [{**row, "_raw": raw.get(row["outfit_id"], {})} for row in catalog]
    if persona_signal not in {"visual", "primary"}:
        raise ValueError("persona_signal must be visual or primary")
    candidates_by_persona = {}
    for persona in sorted(PERSONAS):
        candidates = []
        for row in catalog:
            score = ((row.get("visual") or {}).get("persona_scores") or {}).get(persona)
            primary_match = str(row.get("primary_persona") or "").lower() == persona
            if persona_signal == "visual":
                if not isinstance(score, (int, float)) or isinstance(score, bool) or score < .55:
                    continue
            elif not primary_match:
                continue
            candidates.append({**row, "_target_persona_score": score or 0})
        candidates_by_persona[persona] = candidates

    # Scarce personas claim their distinct source recipes first. Abundant
    # personas have enough alternatives to avoid cross-persona duplication.
    persona_order = sorted(PERSONAS, key=lambda name: (len(candidates_by_persona[name]), name))
    selected_by_persona, supply_by_persona, used_parents = {}, {}, set()
    used_recipes = set()
    for persona in persona_order:
        selected, supply = select_persona(candidates_by_persona[persona], used_parents, used_recipes)
        selected_by_persona[persona], supply_by_persona[persona] = selected, supply
        used_parents.update(outfit_features(row)[0] for row in selected)
        used_recipes.update(main_recipe_signature(row) for row in selected)

    anchors, gaps = [], []
    for persona in sorted(PERSONAS):
        selected, supply = selected_by_persona[persona], supply_by_persona[persona]
        if len(selected) != 10:
            selected_mix = Counter(row["visual"]["expression"] for row in selected)
            gaps.append({
                "persona": persona,
                "required": dict(TARGET_EXPRESSIONS),
                "eligible_supply": supply,
                "selected_mix": dict(selected_mix),
                "missing_by_expression": {
                    expression: max(0, count - selected_mix[expression])
                    for expression, count in TARGET_EXPRESSIONS.items()
                },
                "selected": len(selected),
                "missing": 10 - len(selected),
            })
        # User titles are an override in the release allow-list; legacy internal
        # titles remain untouched for historical resolution.
        for index, row in enumerate(selected):
            oid = row["outfit_id"]
            source = raw[oid]
            anchors.append({
                "outfit_id": oid,
                "persona": persona,
                "expression": row["visual"]["expression"],
                "structure": row["visual"]["structure"],
                "user_title": f"{PERSONA_NAMES[persona]} · {TITLE_TAILS[index]}",
                "record_fingerprint": record_fingerprint(source),
                "four_gate_current": review_is_current(source),
            })
    return {
        "schema_version": 1,
        "status": "candidate",
        "version": "selfit-p0-anchor-candidates-20260904-v1",
        "content_version": str(pool.metadata.get("contentVersion") or "unknown"),
        "visual_version": str(visual.get("version") or "pending-vision"),
        "family_registry_sha256": hashlib.sha256(FAMILY_PATH.read_bytes()).hexdigest() if FAMILY_PATH.is_file() else "missing",
        "blind_review_package_id": None,
        "staging_version": staging_version,
        "persona_signal": persona_signal,
        "anchors": anchors,
        "readiness": {
            "selected": len(anchors),
            "required": 160,
            "current_four_gate_reviews": sum(row["four_gate_current"] for row in anchors),
            "visual_catalog_candidates": len(catalog),
            "visual_catalog_held": len(held),
            "staging_candidates": staging_count,
            "gaps": gaps,
            "release_ready": False,
            "note": "AI visual candidates are not editorial approval or independent blind review.",
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--staging", type=Path)
    parser.add_argument(
        "--persona-signal", choices=("visual", "primary"), default="visual",
        help="visual requires a >=0.55 whole-image persona score; primary preserves the legacy metadata-only queue",
    )
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Refusing to overwrite existing anchor evidence")
    result = build_manifest(args.staging, args.persona_signal)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["readiness"], ensure_ascii=False, indent=2))
    return 0 if result["readiness"]["release_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
