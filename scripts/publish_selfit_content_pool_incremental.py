#!/usr/bin/env python3
"""Publish reviewed V2 assets without waiting for the full 600/1,200 release.

The incremental artifact keeps the migrated V1 outfits as a stable recommendation
baseline, then appends only V2 outfits whose image, review state, rights and garment
dependencies all pass the production gates. The full V2 publisher remains strict.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.publish_selfit_content_pool_v2 import SCHEMA, _disk_path, _validate_cutout
from app.selfit_content_quality import publication_status


DEFAULT_BASE = ROOT / "app/static/selfit/data/content-pool.v2.draft.json"
DEFAULT_PLAN = ROOT / "app/static/selfit/data/content-production-plan.v2.json"
DEFAULT_OUTPUT = ROOT / "app/static/selfit/data/content-pool.v2.incremental.json"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _published_annotation(record: dict[str, Any]) -> dict[str, Any]:
    return {**record["annotation"], "status": "published"}


def _validate_owned_asset(record: dict[str, Any], kind: str) -> list[str]:
    errors: list[str] = []
    assets = record.get("assets") or {}
    if assets.get("rights_status") != "owned":
        errors.append(f"{kind} rights are not owned: {record.get('id')}")
    image_url = str(assets.get("image_url") or "")
    if not image_url or not _disk_path(image_url).exists():
        errors.append(f"missing {kind} image: {record.get('id')}")
    return errors


def build(base_path: Path = DEFAULT_BASE, plan_path: Path = DEFAULT_PLAN) -> dict[str, Any]:
    base = _load(base_path)
    plan = _load(plan_path)
    errors: list[str] = []

    # Only migrated V1 records are baseline content. Capsules and other draft-only
    # records must pass the same production gates as every other V2 addition.
    baseline_outfits = [
        copy.deepcopy(item)
        for item in base.get("outfits", [])
        if isinstance(item, dict) and not item.get("garment_ids")
    ]
    baseline_ids = {str(item.get("id") or "") for item in baseline_outfits}
    if not baseline_outfits or "" in baseline_ids:
        errors.append("incremental baseline is empty or contains an invalid outfit id")

    garments: list[dict[str, Any]] = []
    for job in plan.get("garmentJobs", []):
        if job.get("status") != "approved":
            continue
        record = copy.deepcopy(job.get("record_template") or {})
        if not record:
            errors.append(f"approved garment has no record template: {job.get('job_id')}")
            continue
        production = record.get("production") or {}
        if production.get("qa_status") != "approved":
            errors.append(f"approved job has non-approved QA: {job.get('job_id')}")
        errors.extend(_validate_owned_asset(record, "garment"))
        errors.extend(_validate_cutout(record))
        record.setdefault("assets", {})["alpha_verified"] = True
        record.setdefault("production", {})["qa_status"] = "approved"
        record["annotation"] = _published_annotation(record)
        garments.append(record)

    garment_ids = {str(item.get("id") or "") for item in garments}
    if len(garment_ids) != len(garments):
        errors.append("approved garment ids are empty or duplicated")

    additions: list[dict[str, Any]] = []
    candidates = [*plan.get("masterOutfits", []), *plan.get("variantOutfits", [])]
    for source in candidates:
        # Quarantined and new/unreviewed recipes cannot sneak back via the
        # incremental release path when the full pool is unavailable.
        if publication_status(source) not in {"approved", "legacy_allowed"}:
            continue
        annotation_status = (source.get("annotation") or {}).get("status")
        if annotation_status not in {"designer_reviewed", "published"}:
            continue
        outfit = copy.deepcopy(source)
        outfit_id = str(outfit.get("id") or "")
        if not outfit_id or outfit_id in baseline_ids:
            errors.append(f"reviewed outfit id conflicts with baseline: {outfit_id!r}")
            continue
        referenced_ids = {str(value) for value in outfit.get("garment_ids") or []}
        missing = referenced_ids - garment_ids
        if not referenced_ids:
            errors.append(f"reviewed outfit has no garments: {outfit_id}")
            continue
        if missing:
            errors.append(f"reviewed outfit has unpublished garments: {outfit_id}: {sorted(missing)}")
            continue
        errors.extend(_validate_owned_asset(outfit, "outfit"))
        outfit["annotation"] = _published_annotation(outfit)
        outfit["imageUrl"] = str((outfit.get("assets") or {}).get("image_url") or "")
        additions.append(outfit)

    addition_ids = {str(item.get("id") or "") for item in additions}
    if len(addition_ids) != len(additions):
        errors.append("incremental outfit ids are empty or duplicated")
    compositions = [tuple(sorted(item["garment_ids"])) for item in additions]
    if len(compositions) != len(set(compositions)):
        errors.append("duplicate garment sets in incremental publication")
    if not additions:
        errors.append("no reviewed V2 outfit is ready for incremental publication")

    if errors:
        preview = "\n".join(errors[:30])
        suffix = f"\n... and {len(errors) - 30} more" if len(errors) > 30 else ""
        raise ValueError(f"incremental publish gates failed ({len(errors)}):\n{preview}{suffix}")

    pool = {
        "schemaVersion": "2.0",
        "contentVersion": "2026.09-v2-incremental1",
        "status": "published",
        "releaseMode": "incremental",
        "generatedAt": datetime.now(UTC).isoformat(),
        "sourceVersion": str(base.get("sourceVersion") or "content-pool.v1.json"),
        "publication": {
            "baselineOutfitCount": len(baseline_outfits),
            "incrementalGarmentCount": len(garments),
            "incrementalOutfitCount": len(additions),
            "incrementalGarmentIds": sorted(garment_ids),
            "incrementalOutfitIds": sorted(addition_ids),
        },
        "outfits": [*baseline_outfits, *additions],
        "garments": garments,
        "makeup": copy.deepcopy(base.get("makeup") or {}),
        "hair": copy.deepcopy(base.get("hair") or {}),
    }
    validator = Draft202012Validator(_load(SCHEMA))
    schema_errors = sorted(validator.iter_errors(pool), key=lambda error: list(error.path))
    if schema_errors:
        raise ValueError("schema validation failed:\n" + "\n".join(error.message for error in schema_errors[:30]))
    return pool


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    pool = build(args.base, args.plan)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(pool, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), **pool["publication"], "totalOutfits": len(pool["outfits"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
