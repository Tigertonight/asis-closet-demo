"""Turn a reproducible AW coverage matrix into condition-level supply tasks."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


def digest(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("matrix", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = json.loads(args.matrix.read_text())
    tasks = []
    actions = Counter()
    for row in data["matrix"]:
        count = row["flexible_selected_count"]
        if count >= 30:
            continue
        missing_structures = sorted({structure for gap in row.get("gaps") or []
                                     for structure in gap.get("missing_structures") or []})
        if row["season"] == "winter" and row["palette"] in {"bright", "jewel"} and count == 0:
            action = "design_palette_specific_winter_main_garments"
        elif count < 10:
            action = "recompose_existing_then_assess_new_garments"
        else:
            action = "add_non_similar_parent_recipes_for_browse_depth"
        actions[action] += 1
        tasks.append({
            "season": row["season"], "persona": row["persona"], "palette": row["palette"],
            "current_valid_sequence": count, "shortfall_to_first_ten": max(0, 10 - count),
            "shortfall_to_thirty": 30 - count, "missing_main_structures": missing_structures,
            "next_action": action,
            "evidence": {
                "eligible_by_expression_structure": row.get("eligible_by_expression_structure") or {},
                "reported_gap_reasons": [gap.get("reason") for gap in row.get("gaps") or []],
                "search_complete": (row.get("selection") or {}).get("search_complete"),
            },
        })
    tasks.sort(key=lambda task: (
        task["season"] != "winter", task["shortfall_to_first_ten"] == 0,
        task["shortfall_to_first_ten"] if task["shortfall_to_first_ten"] else task["shortfall_to_thirty"],
        task["persona"], task["palette"],
    ))
    result = {
        "schema_version": 1, "source_matrix": args.matrix.name,
        "source_strategy_version": data["strategy_version"], "source_bundle": data["bundle"],
        "conditions_with_remaining_gap": len(tasks), "action_counts": dict(sorted(actions.items())),
        "tasks": tasks, "production_approved": False,
        "interpretation": "Shortfalls count sequence positions, not unique garments or promised production quantities.",
    }
    result["version"] = "aw-gap-tasks-" + digest(result)[:20]
    if args.output.exists() and json.loads(args.output.read_text()) != result:
        raise SystemExit("Gap task file changed; refusing overwrite")
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(result["version"], len(tasks), result["action_counts"])


if __name__ == "__main__":
    main()
