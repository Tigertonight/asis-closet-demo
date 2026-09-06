"""Diagnose candidate sequences; never substitute for formal REC acceptance.

This calls the ranking/selection components, not the authenticated HTTP feed,
release admission, continuation cursors or browser. Even a complete diagnostic
matrix leaves all REC cases Not Run.
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
from app.recommendation_anchors import PERSONAS, P0_SEQUENCE_ROLES, adapt_released_anchor
from app.recommendation_diversity import FAMILY_PATH, outfit_features
from app.recommendation_feed import rank_candidates, select_sequence
from app.recommendation_visual import attach_visual, load_visual
from app.selfit_content_quality import record_fingerprint


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def diagnose_matrix(manifest: dict, catalog: list[dict]) -> dict:
    persona_results, errors = {}, []
    anchors = manifest.get("anchors")
    if not isinstance(anchors, list):
        anchors = []
        errors.append("anchors must be a list")
    if len(anchors) != 160:
        errors.append("anchor count must be exactly 160")
    entries = {}
    for row in anchors:
        if (not isinstance(row, dict) or not isinstance(row.get("outfit_id"), str)
                or not row["outfit_id"].strip()):
            errors.append("anchor must have a nonempty outfit_id")
            continue
        oid = row["outfit_id"]
        if oid in entries:
            errors.append(f"{oid}: duplicate anchor ID")
            continue
        if not isinstance(row.get("persona"), str) or row["persona"] not in PERSONAS:
            errors.append(f"{oid}: invalid persona")
            continue
        entries[oid] = row
    counts = Counter(row["persona"] for row in entries.values())
    current, seen = [], set()
    for row in catalog:
        oid = row.get("outfit_id")
        if oid not in entries:
            continue
        if oid in seen:
            errors.append(f"{oid}: duplicate catalog ID")
            continue
        seen.add(oid)
        if str(row.get("primary_persona") or "").lower() != entries[oid]["persona"]:
            errors.append(f"{oid}: catalog persona does not match manifest")
            continue
        current.append(adapt_released_anchor(row, entries[oid]))
    for oid in sorted(entries.keys() - seen):
        errors.append(f"{oid}: absent from candidate catalog")
    # Iterate the canonical set, not only personas present in an incomplete file.
    for persona in sorted(PERSONAS):
        if counts[persona] != 10:
            errors.append(f"{persona}: anchor count must be 10 (got {counts[persona]})")
        rows = [row for row in current if row["primary_persona"].lower() == persona]
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
    return {
        "schema_version": 1,
        "status": "diagnostic_pass" if not errors else "diagnostic_fail",
        "evidence_scope": "offline_candidate_sequence_only",
        "formal_acceptance": False,
        "unverified": ["current four-gate and blind-review admission", "authenticated HTTP feed",
                       "compatible-persona policy", "pagination and cursor snapshots",
                       "all sliding windows and cross-page overlap", "feedback and account isolation"],
        "personas": persona_results, "errors": errors,
        "cases": {f"REC-{number:03d}": "Not Run" for number in range(1, 15)},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--anchor-manifest", type=Path, required=True)
    parser.add_argument("--staging", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Refusing to overwrite recommendation evidence")
    # Bind the bytes actually parsed, then check for changes during diagnosis.
    anchor_bytes, staging_bytes = args.anchor_manifest.read_bytes(), args.staging.read_bytes()
    manifest, staging = json.loads(anchor_bytes), json.loads(staging_bytes)
    if not staging.get("version") or manifest.get("staging_version") != staging["version"]:
        raise ValueError("Staging version does not match anchor manifest")
    pool, visual = closet.selfit_content_pool(), load_visual()
    catalog, _ = attach_visual(closet._published_catalog_outfits(), pool.garments, pool.outfits, visual)
    catalog_by_id = {row["outfit_id"]: row for row in catalog}
    raw_by_id = {row["id"]: row for row in pool.outfits}
    staged_ids = set()
    for entry in staging["entries"]:
        raw, adapted = entry["raw_record"], entry["catalog_record"]
        oid = raw.get("id")
        if (not oid or oid != adapted.get("outfit_id") or oid in staged_ids
                or entry.get("record_fingerprint") != record_fingerprint(raw)):
            raise ValueError("Staging contains a stale, duplicate or malformed record")
        staged_ids.add(oid)
        raw_by_id[oid], catalog_by_id[oid] = raw, adapted
    result = diagnose_matrix(manifest, list(catalog_by_id.values()))
    for field, expected in (("content_version", pool.metadata.get("contentVersion")),
                            ("visual_version", visual.get("version")),
                            ("family_registry_sha256", sha(FAMILY_PATH))):
        if manifest.get(field) != expected:
            result["errors"].append(f"{field}: stale candidate manifest")
    for row in manifest.get("anchors") or []:
        if not isinstance(row, dict):
            continue
        raw = raw_by_id.get(row.get("outfit_id"))
        if raw is None or row.get("record_fingerprint") != record_fingerprint(raw):
            result["errors"].append(f"{row.get('outfit_id')}: stale candidate fingerprint")
    if args.anchor_manifest.read_bytes() != anchor_bytes or args.staging.read_bytes() != staging_bytes:
        result["errors"].append("input changed during diagnosis")
    result.update(anchor_manifest_sha256=hashlib.sha256(anchor_bytes).hexdigest(),
                  staging_sha256=hashlib.sha256(staging_bytes).hexdigest())
    if result["errors"]:
        result["status"] = "diagnostic_fail"
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "personas": len(result["personas"]),
                      "errors": len(result["errors"]), "formal_acceptance": False}, ensure_ascii=False))
    return 0 if not result["errors"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
