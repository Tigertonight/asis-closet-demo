"""Replace one candidate slot with a reviewed draft; never approve or publish it."""
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
from app.recommendation_diversity import FAMILY_PATH, main_recipe_signature, outfit_features, style_family_map
from app.recommendation_visual import attach_visual, load_visual
from app.recommendation_anchors import PERSONAS, TARGET_EXPRESSIONS
from app.selfit_content_quality import record_fingerprint
from scripts.prepare_selfit_p0_anchors import selection_gap


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def replace_slot(anchors, catalog, raw, target_id, candidate, title):
    targets = [a for a in anchors if a["outfit_id"] == target_id]
    if len(targets) != 1:
        raise ValueError("Replacement must resolve exactly one selected anchor")
    old = targets[0]
    fields = candidate["visual"]
    if (str(candidate["primary_persona"]).lower() != old["persona"]
            or fields["expression"] != old["expression"]):
        raise ValueError("Replacement must preserve persona and expression slot")
    signature = main_recipe_signature(candidate)
    if not signature or any(main_recipe_signature(catalog[a["outfit_id"]]) == signature
                            for a in anchors if a["outfit_id"] != target_id):
        raise ValueError("Replacement duplicates an existing main recipe")
    if any(outfit_features(catalog[a["outfit_id"]])[0] == outfit_features(candidate)[0]
           for a in anchors if a["outfit_id"] != target_id):
        raise ValueError("Replacement repeats a selected parent recipe")
    replacement = {"outfit_id": candidate["outfit_id"], "persona": old["persona"],
                   "expression": fields["expression"], "structure": fields["structure"],
                   "user_title": title, "record_fingerprint": record_fingerprint(raw),
                   "four_gate_current": False}
    updated = [replacement if a["outfit_id"] == target_id else deepcopy(a) for a in anchors]
    selected = [candidate if a["outfit_id"] == candidate["outfit_id"] else catalog[a["outfit_id"]]
                for a in updated if a["persona"] == old["persona"]]
    if selection_gap(old["persona"], selected, {}) is not None:
        raise ValueError("Replacement does not resolve persona count/mix/structure constraints")
    features = [outfit_features(row) for row in selected]
    if len({f[0] for f in features}) != len(features):
        raise ValueError("Replacement repeats a parent recipe")
    for dimension in (1, 2):
        if max(Counter(v for f in features for v in f[dimension]).values(), default=0) > 2:
            raise ValueError("Replacement exceeds main item or family cap")
    return updated


def add_slot(anchors, catalog, raw, candidate, title):
    """Fill a missing expression slot without weakening any upper bound."""
    persona = str(candidate.get("primary_persona") or "").lower()
    fields = candidate["visual"]
    expression, structure = fields["expression"], fields["structure"]
    if persona not in PERSONAS or expression not in TARGET_EXPRESSIONS or structure not in {"pants", "skirt", "dress"}:
        raise ValueError("Unknown candidate persona, expression or structure")
    selected = [a for a in anchors if a["persona"] == persona]
    if len(selected) >= 10 or sum(a["expression"] == expression for a in selected) >= TARGET_EXPRESSIONS[expression]:
        raise ValueError("Candidate exceeds persona or expression quota")
    signature = main_recipe_signature(candidate)
    if not signature or any(main_recipe_signature(catalog[a["outfit_id"]]) == signature for a in anchors):
        raise ValueError("Candidate duplicates an existing main recipe")
    if any(outfit_features(catalog[a["outfit_id"]])[0] == outfit_features(candidate)[0] for a in anchors):
        raise ValueError("Candidate repeats a selected parent recipe")
    counts = Counter(a["structure"] for a in selected)
    counts[structure] += 1
    if max(counts.values()) > 5 or len({"pants", "skirt", "dress"} - counts.keys()) > 9 - len(selected):
        raise ValueError("Candidate makes structure coverage impossible")
    features = [outfit_features(catalog[a["outfit_id"]]) for a in selected] + [outfit_features(candidate)]
    for dimension in (1, 2):
        if max(Counter(v for f in features for v in f[dimension]).values(), default=0) > 2:
            raise ValueError("Candidate exceeds main item or family cap")
    return deepcopy(anchors) + [{"outfit_id": candidate["outfit_id"], "persona": persona,
        "expression": expression, "structure": structure, "user_title": title,
        "record_fingerprint": record_fingerprint(raw), "four_gate_current": False}]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("anchor-manifest", "staging", "rendered", "visual-review", "output-manifest", "output-staging"):
        parser.add_argument("--" + name, type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--replace")
    mode.add_argument("--add", action="store_true")
    parser.add_argument("--garment-manifest", type=Path)
    parser.add_argument("--candidate-id", help="Select one reviewed candidate from a multi-row batch")
    parser.add_argument("--title", required=True)
    args = parser.parse_args()
    if args.output_manifest.exists() or args.output_staging.exists():
        raise ValueError("Use new output paths; review history is immutable")
    read = lambda path: json.loads(path.read_text())
    manifest, staging, rendered, review = map(read, (args.anchor_manifest, args.staging, args.rendered, args.visual_review))
    pool, visual = closet.selfit_content_pool(), load_visual()
    family_sha = hashlib.sha256(FAMILY_PATH.read_bytes()).hexdigest()
    if (manifest.get("staging_version") != staging.get("version")
            or manifest.get("content_version") != pool.metadata.get("contentVersion")
            or staging.get("base_content_version") != pool.metadata.get("contentVersion")
            or any(obj.get("visual_version") != visual["version"] for obj in (manifest, staging))
            or any(obj.get("family_registry_sha256") != family_sha for obj in (manifest, staging))
            or rendered.get("source_visual_version") != visual["version"]):
        raise ValueError("Source revisions are stale")
    garments = list(pool.garments)
    generated = None
    if args.garment_manifest:
        generated = read(args.garment_manifest)
        if (generated.get("schema_version") != 1 or generated.get("production_approved") is not False
                or not generated.get("version") or len(generated.get("garments", [])) > 24):
            raise ValueError("Invalid generated garment manifest")
        if {g["id"] for g in garments} & {g["id"] for g in generated["garments"]}:
            raise ValueError("Generated garment collides with published ID")
        garments.extend(generated["garments"])
        visual = deepcopy(visual)
        visual.setdefault("garments", {}).update(generated.get("visual", {}))
    candidates, review_version = load_recomposition_candidates(garments, visual, rendered, review, generated)
    if args.candidate_id:
        candidates = [row for row in candidates if row["outfit_id"] == args.candidate_id]
    if len(candidates) != 1:
        raise ValueError("Replacement requires exactly one reviewed candidate")
    candidate = candidates[0]
    raw = next(entry["new_record"] for entry in rendered["entries"] if entry["new_record"]["id"] == candidate["outfit_id"])
    if raw.get("annotation", {}).get("status") != "draft" or raw.get("quality_review"):
        raise ValueError("Only unapproved drafts may be staged")
    families = style_family_map(garments)
    for item in candidate["items"]:
        item["style_family_id"] = families.get(item["item_id"], "item:" + item["item_id"])
    catalog, _ = attach_visual(closet._published_catalog_outfits(), pool.garments, pool.outfits, visual)
    by_id = {row["outfit_id"]: row for row in catalog}
    raw_by_id = {row["id"]: row for row in pool.outfits}
    for entry in staging["entries"]:
        if entry["record_fingerprint"] != record_fingerprint(entry["raw_record"]):
            raise ValueError("Stale staging record")
        by_id[entry["outfit_id"]] = entry["catalog_record"]
        raw_by_id[entry["outfit_id"]] = entry["raw_record"]
    for anchor in manifest["anchors"]:
        if anchor["record_fingerprint"] != record_fingerprint(raw_by_id[anchor["outfit_id"]]):
            raise ValueError("Stale selected anchor")
    if candidate["outfit_id"] in by_id:
        raise ValueError("Candidate ID already exists")
    manifest["anchors"] = (add_slot(manifest["anchors"], by_id, raw, candidate, args.title) if args.add
        else replace_slot(manifest["anchors"], by_id, raw, args.replace, candidate, args.title))
    known_staged = {g["record"]["id"]: g for g in staging.get("staged_garments", [])}
    if generated:
        for garment in generated["garments"]:
            gid = garment["id"]
            if gid not in raw["garment_ids"]:
                continue
            if gid in known_staged:
                if known_staged[gid]["record_fingerprint"] != record_fingerprint(garment):
                    raise ValueError("Generated garment conflicts with previous staging")
                continue
            staging.setdefault("staged_garments", []).append({"record": garment,
                "record_fingerprint": record_fingerprint(garment), "visual_observation": generated["visual"][gid],
                "source_manifest": str(args.garment_manifest.resolve().relative_to(ROOT))})
    staging["entries"].append({"outfit_id": raw["id"], "raw_record": raw, "catalog_record": candidate,
        "record_fingerprint": record_fingerprint(raw), "four_gate_status": "pending",
        "source_rendered": str(args.rendered.resolve().relative_to(ROOT)), "source_review_bundle": review_version,
        "replaces_selected_outfit_id": args.replace})
    staging.pop("version", None)
    staging["version"] = "p0-replacement-staging-" + digest(staging)[:20]
    manifest.update(status="candidate", staging_version=staging["version"], blind_review_package_id=None)
    by_id[candidate["outfit_id"]] = candidate
    prior_supply = {g["persona"]: g.get("eligible_supply", {}) for g in manifest["readiness"]["gaps"]}
    gaps = []
    for persona in sorted({a["persona"] for a in manifest["anchors"]} | set(prior_supply)):
        selected = [by_id[a["outfit_id"]] for a in manifest["anchors"] if a["persona"] == persona]
        gap = selection_gap(persona, selected, prior_supply.get(persona, {}))
        if gap:
            gaps.append(gap)
    manifest["readiness"].update(gaps=gaps, release_ready=False, staging_candidates=len(staging["entries"]),
                                  selected=len(manifest["anchors"]),
                                  current_four_gate_reviews=sum(bool(a.get("four_gate_current")) for a in manifest["anchors"]))
    manifest.pop("version", None)
    manifest["version"] = "p0-replacement-candidates-" + digest(manifest)[:20]
    for path, value in ((args.output_staging, staging), (args.output_manifest, manifest)):
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"anchors": len(manifest["anchors"]), "remaining_quantity_gap": sum(g["missing"] for g in gaps),
                      "replacement": candidate["outfit_id"], "four_gate_status": "pending"}))


if __name__ == "__main__":
    main()
