"""Audit the 16-persona P0 recommendation matrix without publishing it."""
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
from app.recommendation_anchors import P0_SEQUENCE_ROLES, adapt_released_anchor
from app.recommendation_diversity import outfit_features
from app.recommendation_feed import rank_candidates, select_sequence
from app.recommendation_visual import attach_visual, load_visual


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--anchor-manifest", type=Path, required=True)
    parser.add_argument("--staging", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Refusing to overwrite recommendation evidence")
    manifest, staging = json.loads(args.anchor_manifest.read_text()), json.loads(args.staging.read_text())
    if manifest.get("staging_version") != staging.get("version"):
        raise ValueError("Staging version does not match anchor manifest")
    pool, visual = closet.selfit_content_pool(), load_visual()
    catalog, _ = attach_visual(closet._published_catalog_outfits(), pool.garments, pool.outfits, visual)
    catalog.extend(entry["catalog_record"] for entry in staging["entries"])
    entries = {row["outfit_id"]: row for row in manifest["anchors"]}
    catalog = [adapt_released_anchor(row, entries[row["outfit_id"]])
               for row in catalog if row["outfit_id"] in entries]
    persona_results, errors = {}, []
    for persona in sorted({row["persona"] for row in manifest["anchors"]}):
        rows = [row for row in catalog if row["primary_persona"].lower() == persona]
        ranked, held = rank_candidates(rows, {
            "persona_id": persona, "palette": None, "axes": {}, "version": "p0-matrix",
        }, {"scene_tags": ["daily"], "season_tags": []})
        selected, gaps = select_sequence(ranked, 10, expression_roles=P0_SEQUENCE_ROLES)
        structures = Counter(row["visual"]["structure"] for row in selected)
        expressions = Counter(row["visual"]["expression"] for row in selected)
        features = [outfit_features(row) for row in selected]
        main_counts = Counter(value for feature in features for value in feature[1])
        family_counts = Counter(value for feature in features for value in feature[2])
        row_errors = []
        if len(selected) != 10 or gaps:
            row_errors.append("sequence did not produce 10 anchors")
        if any(row["primary_persona"].lower() != persona for row in selected):
            row_errors.append("non-primary persona entered the first 10")
        if set(structures) != {"pants", "skirt", "dress"} or max(structures.values(), default=0) > 5:
            row_errors.append("structure coverage/cap failed")
        if expressions != Counter({"easy": 4, "typical": 4, "explore": 2}):
            row_errors.append("expression mix failed")
        if len({feature[0] for feature in features[:6]}) != len(features[:6]):
            row_errors.append("first-screen parent recipes repeat")
        if max(main_counts.values(), default=0) > 2 or max(family_counts.values(), default=0) > 2:
            row_errors.append("main item or family cap failed")
        if row_errors:
            errors.extend(f"{persona}: {error}" for error in row_errors)
        persona_results[persona] = {
            "selected": [row["outfit_id"] for row in selected],
            "structures": dict(structures), "expressions": dict(expressions),
            "held": held, "errors": row_errors,
        }
    base_status = "Pass" if not errors else "Fail"
    cases = {f"REC-{number:03d}": "Not Run" for number in range(1, 15)}
    for number in range(1, 7):
        cases[f"REC-{number:03d}"] = base_status
    result = {
        "schema_version": 1, "status": "matrix_passed_pending_full_release" if not errors else "failed",
        "anchor_manifest_sha256": sha(args.anchor_manifest),
        "staging_sha256": sha(args.staging), "personas": persona_results,
        "errors": errors, "cases": cases,
    }
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "personas": len(persona_results), "errors": len(errors)}, ensure_ascii=False))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
