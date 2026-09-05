"""Turn a visual-evidence anchor shortage into bounded production tasks."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


STRUCTURES = ("pants", "skirt", "dress")
EXPRESSION_ORDER = ("easy", "typical", "explore")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def allocate_structures(existing: Counter, count: int) -> list[str]:
    """Fill absent/least-used structures first without exceeding five of ten."""
    result = []
    counts = Counter(existing)
    for _ in range(count):
        eligible = [name for name in STRUCTURES if counts[name] < 5]
        if not eligible:
            raise ValueError("No structure capacity remains")
        choice = min(
            eligible,
            key=lambda name: (counts[name] > 0, counts[name], STRUCTURES.index(name)),
        )
        counts[choice] += 1
        result.append(choice)
    if sum(counts.values()) == 10 and set(counts) != set(STRUCTURES):
        raise ValueError("Ten-look target does not cover pants, skirt and dress")
    return result


def build(manifest_path: Path, templates_path: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    templates = json.loads(templates_path.read_text(encoding="utf-8"))["types"]
    by_persona = {}
    for row in manifest.get("anchors") or []:
        by_persona.setdefault(row["persona"], []).append(row)
    tasks = []
    for gap in manifest.get("readiness", {}).get("gaps") or []:
        persona = gap["persona"]
        current = by_persona.get(persona, [])
        missing_roles = [
            expression
            for expression in EXPRESSION_ORDER
            for _ in range(int(gap["missing_by_expression"].get(expression, 0)))
        ]
        structures = allocate_structures(
            Counter(row["structure"] for row in current), len(missing_roles)
        )
        metadata = templates[persona]
        for index, (expression, structure) in enumerate(zip(missing_roles, structures), 1):
            tasks.append({
                "task_id": f"P0-CONTENT-{persona.upper()}-{index:02d}",
                "persona": persona,
                "persona_name": metadata["metadata"]["name"],
                "persona_keywords": metadata.get("keywords") or [],
                "expression": expression,
                "structure": structure,
                "scene": "daily",
                "wearability": ["everyday", "everyday_with_statement"],
                "production_state": "not_started",
                "acceptance": {
                    "whole_image_persona_score_min": .55,
                    "exact_expression": expression,
                    "exact_structure": structure,
                    "exactly_one_hero": True,
                    "daily_context_required": True,
                    "distinct_parent_recipe_required": True,
                    "layer_graph_required_when_layering_gt_1": True,
                    "four_gate_editorial_review": "pending",
                    "independent_blind_review": "pending",
                },
            })
    return {
        "schema_version": 1,
        "status": "production_required",
        "source_anchor_manifest": str(manifest_path),
        "source_anchor_manifest_sha256": sha(manifest_path),
        "persona_signal": manifest.get("persona_signal"),
        "summary": {
            "current_visual_evidence_anchors": len(manifest.get("anchors") or []),
            "target_anchors": 160,
            "production_tasks": len(tasks),
            "by_persona": dict(Counter(row["persona"] for row in tasks)),
            "by_expression": dict(Counter(row["expression"] for row in tasks)),
            "by_structure": dict(Counter(row["structure"] for row in tasks)),
        },
        "tasks": tasks,
        "release_note": (
            "A production task is only a target. It cannot enter the release allow-list "
            "until whole-image review, all four editorial gates, and independent blind review pass."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--anchor-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Refusing to overwrite P0 production evidence")
    templates = Path(__file__).resolve().parents[1] / "app/static/selfit/data/personality-report-templates.v1.json"
    result = build(args.anchor_manifest, templates)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
