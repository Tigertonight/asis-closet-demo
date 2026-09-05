"""Assemble exactly seven P0 gap candidates into an immutable staging bundle."""
from __future__ import annotations

import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import closet
from app.recommendation_aw import load_recomposition_candidates
from app.recommendation_diversity import FAMILY_PATH
from app.recommendation_visual import load_visual
from app.selfit_content_quality import record_fingerprint

AUDIT = ROOT / "docs/audits/20260904-p0-acceptance"
AW = ROOT / "docs/audits/20260904-aw-supply"
EXISTING_IDS = {
    "outfit_neon_aw-winter-04_02",
    "outfit_oops_aw-winter-04_09",
    "outfit_neon_master_09_v2__aw-repair-05",
}


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def find_raw_records(ids: set[str]) -> dict[str, dict]:
    found = {}
    for path in sorted(AW.glob("*.rendered.json")):
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        for entry in data.get("entries") or []:
            raw = entry.get("new_record") if isinstance(entry, dict) else None
            if isinstance(raw, dict) and raw.get("id") in ids:
                oid = raw["id"]
                if oid in found and found[oid]["raw_record"] != raw:
                    raise ValueError(f"Conflicting staged record: {oid}")
                found[oid] = {"raw_record": raw, "source_rendered": str(path.relative_to(ROOT))}
    if set(found) != ids:
        raise ValueError("Missing existing staged records: " + ", ".join(sorted(ids - found.keys())))
    return found


def main() -> None:
    output = AUDIT / "p0-gap-staging.v4.json"
    if output.exists():
        raise ValueError("Refusing to overwrite P0 staging evidence")
    pool, visual = closet.selfit_content_pool(), load_visual()
    supplemental, supplemental_version = load_recomposition_candidates(pool.garments, visual)
    adapted_existing = {row["outfit_id"]: row for row in supplemental if row["outfit_id"] in EXISTING_IDS}
    if set(adapted_existing) != EXISTING_IDS:
        raise ValueError("Selected internal drafts are not current visual candidates")
    raw_existing = find_raw_records(EXISTING_IDS)
    entries = []
    for oid in sorted(EXISTING_IDS):
        raw = deepcopy(raw_existing[oid]["raw_record"])
        adapted = adapted_existing[oid]
        normalizations = []
        if str(raw.get("primary_persona") or "").lower() != str(adapted.get("primary_persona") or "").lower():
            raw["primary_persona"] = adapted["primary_persona"]
            normalizations.append("primary_persona_aligned_to_current_whole-image_observation")
        if int((adapted.get("visual") or {}).get("layering") or 1) > 1 and not raw.get("layer_graph"):
            categories = {item["item_id"]: (item.get("slot") or item.get("category")) for item in adapted["items"]}
            outer = next((gid for gid in raw["garment_ids"] if categories.get(gid) == "outer"), None)
            inner = next((gid for gid in raw["garment_ids"] if categories.get(gid) in {"top", "dress"}), None)
            if not outer or not inner:
                raise ValueError(f"Cannot infer explicit layer graph: {oid}")
            raw["layer_graph"] = [{"inner": inner, "outer": outer}]
            normalizations.append("explicit_outer_over_main_layer_graph_added")
        entries.append({
            "outfit_id": oid,
            "raw_record": raw,
            "catalog_record": adapted,
            "record_fingerprint": record_fingerprint(raw),
            "source_rendered": raw_existing[oid]["source_rendered"],
            "source_review_bundle": supplemental_version,
            "staging_normalization": normalizations,
            "four_gate_status": "pending",
        })
    for number in (1, 2):
        rendered_path = AUDIT / f"gap-recipes.batch0{number}.rendered.json"
        review_path = AUDIT / f"gap-recipes.batch0{number}.visual-review.json"
        rendered, review = json.loads(rendered_path.read_text()), json.loads(review_path.read_text())
        adapted, review_version = load_recomposition_candidates(pool.garments, visual, rendered, review)
        raw_by_id = {entry["new_record"]["id"]: entry["new_record"] for entry in rendered["entries"]}
        for row in adapted:
            oid, raw = row["outfit_id"], raw_by_id[row["outfit_id"]]
            entries.append({
                "outfit_id": oid,
                "raw_record": raw,
                "catalog_record": row,
                "record_fingerprint": record_fingerprint(raw),
                "source_rendered": str(rendered_path.relative_to(ROOT)),
                "source_review_bundle": review_version,
                "four_gate_status": "pending",
            })
    if len(entries) != 7 or len({entry["outfit_id"] for entry in entries}) != 7:
        raise ValueError("P0 staging must contain exactly seven unique gap candidates")
    known_garments = {row["id"] for row in pool.garments}
    missing_garments = {
        gid for entry in entries for gid in entry["raw_record"].get("garment_ids", [])
        if gid not in known_garments
    }
    generated_manifest = json.loads((AW / "generated-garments/batch02/manifest.json").read_text())
    generated_by_id = {row["id"]: row for row in generated_manifest.get("garments") or []}
    if not missing_garments <= generated_by_id.keys():
        raise ValueError("Staging is missing generated garment records")
    staged_garments = [{
        "record": generated_by_id[gid],
        "record_fingerprint": record_fingerprint(generated_by_id[gid]),
        "visual_observation": (generated_manifest.get("visual") or {}).get(gid),
        "source_manifest": "docs/audits/20260904-aw-supply/generated-garments/batch02/manifest.json",
    } for gid in sorted(missing_garments)]
    result = {
        "schema_version": 1,
        "status": "staging_pending_four_gate_review",
        "base_content_version": pool.metadata.get("contentVersion"),
        "visual_version": visual.get("version"),
        "family_registry_sha256": hashlib.sha256(FAMILY_PATH.read_bytes()).hexdigest(),
        "staged_garments": staged_garments,
        "entries": entries,
    }
    result["version"] = "p0-gap-staging-" + digest(result)[:20]
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"version": result["version"], "candidates": len(entries)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
