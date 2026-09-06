#!/usr/bin/env python3
"""Dry-run a reviewed draft batch against the complete P0 anchor constraints."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import closet
from app.recommendation_aw import load_recomposition_candidates
from app.recommendation_diversity import FAMILY_PATH, outfit_features, style_family_map
from app.recommendation_visual import attach_visual, load_visual
from scripts.prepare_selfit_p0_anchors import selection_gap
from scripts.stage_selfit_p0_replacement import add_slot


def build_audit(anchor_path: Path, staging_path: Path, rendered_path: Path,
                review_path: Path, garment_path: Path) -> dict:
    read = lambda path: json.loads(path.read_text())
    manifest, staging, rendered, review, generated = map(
        read, (anchor_path, staging_path, rendered_path, review_path, garment_path))
    pool, visual = closet.selfit_content_pool(), load_visual()
    family_sha = hashlib.sha256(FAMILY_PATH.read_bytes()).hexdigest()
    if (manifest.get("staging_version") != staging.get("version")
            or manifest.get("content_version") != pool.metadata.get("contentVersion")
            or manifest.get("visual_version") != visual.get("version")
            or manifest.get("family_registry_sha256") != family_sha
            or rendered.get("source_visual_version") != visual.get("version")):
        raise ValueError("Source revisions are stale")

    garments = list(pool.garments) + generated["garments"]
    combined_visual = deepcopy(visual)
    combined_visual.setdefault("garments", {}).update(generated["visual"])
    candidates, review_version = load_recomposition_candidates(
        garments, combined_visual, rendered, review, generated)
    candidate_by_id = {row["outfit_id"]: row for row in candidates}
    raw_by_candidate = {row["new_record"]["id"]: row["new_record"] for row in rendered["entries"]}
    ordered_ids = [row["new_record"]["id"] for row in rendered["entries"]]
    if len(ordered_ids) != 20 or set(ordered_ids) != set(candidate_by_id):
        raise ValueError("Expected exactly the 20 reviewed rendered candidates")

    published, _ = attach_visual(
        closet._published_catalog_outfits(), pool.garments, pool.outfits, visual)
    catalog = {row["outfit_id"]: row for row in published}
    for entry in staging["entries"]:
        catalog[entry["outfit_id"]] = entry["catalog_record"]
    families = style_family_map(garments)

    anchors = deepcopy(manifest["anchors"])
    violations = []
    for candidate_id in ordered_ids:
        candidate = candidate_by_id[candidate_id]
        for item in candidate["items"]:
            item["style_family_id"] = families.get(item["item_id"], "item:" + item["item_id"])
        try:
            anchors = add_slot(
                anchors, catalog, raw_by_candidate[candidate_id], candidate,
                "P0 batch preflight")
            catalog[candidate_id] = candidate
        except ValueError as exc:
            violations.append({"outfit_id": candidate_id, "error": str(exc)})

    personas = {}
    all_recipe_parents = []
    for persona in sorted({row["persona"] for row in anchors}):
        selected = [catalog[row["outfit_id"]] for row in anchors if row["persona"] == persona]
        features = [outfit_features(row) for row in selected]
        parent_counts = Counter(feature[0] for feature in features)
        item_counts = Counter(value for feature in features for value in feature[1])
        family_counts = Counter(value for feature in features for value in feature[2])
        expression_counts = Counter(row["visual"]["expression"] for row in selected)
        structure_counts = Counter(row["visual"]["structure"] for row in selected)
        gap = selection_gap(persona, selected, {})
        personas[persona] = {
            "count": len(selected),
            "expressions": dict(sorted(expression_counts.items())),
            "structures": dict(sorted(structure_counts.items())),
            "parent_over_cap": {str(key): value for key, value in parent_counts.items() if value > 1},
            "main_item_over_cap": {key: value for key, value in item_counts.items() if value > 2},
            "family_over_cap": {key: value for key, value in family_counts.items() if value > 2},
            "selection_gap": gap,
        }
        all_recipe_parents.extend(feature[0] for feature in features)

    complete = (not violations and len(anchors) == 160
                and all(row["selection_gap"] is None for row in personas.values())
                and all(not row["parent_over_cap"] and not row["main_item_over_cap"]
                        and not row["family_over_cap"] for row in personas.values())
                and len(set(all_recipe_parents)) == len(all_recipe_parents))
    result = {
        "schema_version": 1,
        "source_anchor_version": manifest["version"],
        "source_staging_version": staging["version"],
        "source_rendered_version": rendered["version"],
        "source_review_version": review_version,
        "candidate_count": len(candidates),
        "resulting_anchor_count": len(anchors),
        "constraints_pass": complete,
        "formal_acceptance": False,
        "violations": violations,
        "personas": personas,
    }
    digest = hashlib.sha256(json.dumps(result, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    result["version"] = "p0-final-batch-preflight-" + digest[:20]
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("anchor-manifest", "staging", "rendered", "visual-review", "garment-manifest", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    result = build_audit(args.anchor_manifest, args.staging, args.rendered,
                         args.visual_review, args.garment_manifest)
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output.exists() and args.output.read_text() != payload:
        raise SystemExit("preflight changed; refusing overwrite")
    args.output.write_text(payload)
    print(json.dumps({key: result[key] for key in
                      ("version", "candidate_count", "resulting_anchor_count", "constraints_pass")},
                     ensure_ascii=False))
    if not result["constraints_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
