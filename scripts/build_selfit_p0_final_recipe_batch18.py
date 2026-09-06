#!/usr/bin/env python3
"""Bind the final twenty recipe targets to a verified generated-garment manifest."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.recommendation_visual import load_visual


DEFAULT_PLAN = ROOT / "docs/audits/20260904-p0-acceptance/p0-final-recipe-plan.v1.json"


def build_spec(plan: dict, manifest: dict, current_visual: dict, *, manifest_ref: str,
               batch_id: str = "p0-final-gap-18") -> dict:
    if plan.get("schema_version") != 1 or len(plan.get("recipes", [])) != 20:
        raise ValueError("final recipe plan must contain exactly 20 recipes")
    if (manifest.get("schema_version") != 1 or manifest.get("production_approved") is not False
            or manifest.get("status") != "internal_candidate"):
        raise ValueError("generated garment manifest is not an internal candidate")
    new_tokens = {row["token"] for row in manifest.get("visual", {}).values()}
    if len(new_tokens) != 15 or new_tokens != {f"n{i:04d}" for i in range(102, 117)}:
        raise ValueError("generated garment manifest does not bind n0102..n0116")
    existing_tokens = {row["token"] for row in current_visual.get("garments", {}).values()}
    recipes, task_ids, item_sets = [], set(), set()
    for row in plan["recipes"]:
        task_id = row["task_id"]
        if task_id in task_ids:
            raise ValueError(f"duplicate task id: {task_id}")
        task_ids.add(task_id)
        items = row["items"]
        if len(items) != len(set(items)) or any(token not in existing_tokens | new_tokens for token in items):
            raise ValueError(f"duplicate or unknown recipe token: {task_id}")
        signature = tuple(items)
        if signature in item_sets:
            raise ValueError(f"duplicate item recipe: {task_id}")
        item_sets.add(signature)
        if row["hero"] not in items:
            raise ValueError(f"hero absent from recipe: {task_id}")
        graph = row.get("layer_graph", [])
        for edge in graph:
            if set(edge) != {"inner", "outer"} or edge["inner"] not in items or edge["outer"] not in items:
                raise ValueError(f"invalid layer graph: {task_id}")
        recipe = {
            "persona": row["persona"], "palette": "evidence_first", "season": "autumn",
            "structure": row["structure"], "hero": row["hero"], "items": items,
            "expression": row["expression"], "intent": row["intent"],
        }
        if graph:
            recipe["layer_graph"] = graph
        recipes.append(recipe)
    return {
        "schema_version": 1,
        "batch_id": batch_id,
        "source_visual_version": current_visual["version"],
        "status": "designer_targets_pending_whole_image_review",
        "new_garments": [],
        "new_garment_manifest": manifest_ref,
        "new_garment_version": manifest["version"],
        "source_plan_status": plan["status"],
        "recipes": recipes,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--garment-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--batch-id", default="p0-final-gap-18")
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("output exists; refusing overwrite")
    plan = json.loads(args.plan.read_text())
    manifest = json.loads(args.garment_manifest.read_text())
    manifest_ref = os.path.relpath(args.garment_manifest.resolve(), args.output.resolve().parent)
    spec = build_spec(plan, manifest, load_visual(), manifest_ref=manifest_ref, batch_id=args.batch_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"recipes":len(spec["recipes"]),"garment_version":spec["new_garment_version"]},ensure_ascii=False))


if __name__ == "__main__":
    main()
