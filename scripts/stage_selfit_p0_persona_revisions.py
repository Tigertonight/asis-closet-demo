"""Freeze proposed persona corrections as new, pending-review content revisions."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import closet
from app.recommendation_diversity import FAMILY_PATH
from app.recommendation_visual import attach_visual, load_visual
from app.selfit_content_quality import record_fingerprint


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def revise(anchor, raw, catalog):
    if anchor.get("record_fingerprint") != record_fingerprint(raw):
        raise ValueError("Source anchor fingerprint is stale")
    persona = anchor["persona"]
    score = (catalog.get("visual", {}).get("persona_scores") or {}).get(persona)
    if type(score) not in (int, float) or not .55 <= score <= 1:
        raise ValueError("Persona revision requires current whole-image evidence")
    oid = raw["id"] + "__p0-persona-" + persona
    updated, adapted = deepcopy(raw), deepcopy(catalog)
    for field in ("quality_review", "curation", "annotation"):
        updated.pop(field, None)
    updated.update(id=oid, primary_persona=persona.upper(), secondary_personas=[],
                   persona_affinity={}, recipe_version="p0-persona-revision-v1",
                   parent_outfit_id=catalog.get("parent_outfit_id") or raw["id"],
                   annotation={"status": "draft", "source": "persona_revision_proposal"})
    adapted.update(outfit_id=oid, primary_persona=persona.upper(),
                   parent_outfit_id=updated["parent_outfit_id"])
    for field in ("quality_review", "curation", "anchor_release_persona"):
        adapted.pop(field, None)
    fingerprint = record_fingerprint(updated)
    entry = {
        "outfit_id": oid, "raw_record": updated, "catalog_record": adapted,
        "record_fingerprint": fingerprint, "four_gate_status": "pending",
        "source_outfit_id": raw["id"], "source_record_fingerprint": record_fingerprint(raw),
        "previous_persona": raw.get("primary_persona"), "proposed_persona": persona,
        "staging_normalization": ["proposed_persona_correction_requires_new_four_gate_review"],
    }
    return {**anchor, "outfit_id": oid, "record_fingerprint": fingerprint,
            "four_gate_current": False}, entry


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("anchor-manifest", "staging", "output-manifest", "output-staging"):
        parser.add_argument("--" + arg, type=Path, required=True)
    args = parser.parse_args()
    if args.output_manifest.exists() or args.output_staging.exists():
        raise ValueError("Use new output paths")
    manifest = json.loads(args.anchor_manifest.read_text())
    staging = json.loads(args.staging.read_text())
    pool, visual = closet.selfit_content_pool(), load_visual()
    if (manifest.get("staging_version") != staging.get("version")
            or staging.get("base_content_version") != pool.metadata.get("contentVersion")
            or staging.get("visual_version") != visual.get("version")
            or staging.get("family_registry_sha256") != hashlib.sha256(FAMILY_PATH.read_bytes()).hexdigest()):
        raise ValueError("Source revisions are stale")
    catalog, _ = attach_visual(closet._published_catalog_outfits(), pool.garments, pool.outfits, visual)
    raw = {row["id"]: row for row in pool.outfits}
    by_id = {row["outfit_id"]: row for row in catalog}
    for entry in staging["entries"]:
        raw[entry["outfit_id"]] = entry["raw_record"]
        by_id[entry["outfit_id"]] = entry["catalog_record"]
    revisions = []
    for index, anchor in enumerate(manifest["anchors"]):
        source = raw[anchor["outfit_id"]]
        if str(source.get("primary_persona") or "").lower() == anchor["persona"]:
            continue
        replacement, entry = revise(anchor, source, by_id[anchor["outfit_id"]])
        if entry["outfit_id"] in raw:
            raise ValueError("Revision ID already exists")
        manifest["anchors"][index] = replacement
        revisions.append(entry)
    staging["entries"].extend(revisions)
    staging.pop("version", None)
    staging["version"] = "p0-persona-staging-" + digest(staging)[:20]
    manifest.update(staging_version=staging["version"], status="candidate", blind_review_package_id=None)
    manifest["readiness"].update(release_ready=False, persona_revision_proposals=len(revisions),
                                current_four_gate_reviews=sum(bool(a.get("four_gate_current")) for a in manifest["anchors"]))
    manifest["version"] = "p0-persona-revised-" + digest(manifest)[:20]
    args.output_staging.write_text(json.dumps(staging, ensure_ascii=False, indent=2) + "\n")
    args.output_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"proposed_revisions": len(revisions), "anchors": len(manifest["anchors"]),
                      "release_ready": False}))


if __name__ == "__main__":
    main()
