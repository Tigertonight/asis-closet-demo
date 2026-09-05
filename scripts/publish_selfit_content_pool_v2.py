#!/usr/bin/env python3
"""Publish the V2 pool only when every production and coverage gate passes."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image
from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from app.selfit_content_quality import publication_status
DEFAULT_PLAN = ROOT / "app/static/selfit/data/content-production-plan.v2.json"
DEFAULT_OUTPUT = ROOT / "app/static/selfit/data/content-pool.v2.published.json"
SCHEMA = ROOT / "app/static/selfit/data/content-pool.schema.v2.json"
PERSONAS = ("MUTE", "ICED", "HEIR", "EASE", "MELT", "WABI", "FLOU", "NEON", "EDGE", "BOLT", "FILM", "JADE", "LOOP", "NOIR", "VOID", "OOPS")


def _disk_path(public_path: str) -> Path:
    if public_path.startswith("/static/"):
        return ROOT / "app" / public_path.lstrip("/")
    return ROOT / public_path.lstrip("/")


def _validate_cutout(record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    path = _disk_path(str(record["assets"]["image_url"]))
    if not path.exists():
        return [f"missing cutout: {path}"]
    image = Image.open(path).convert("RGBA")
    alpha = image.getchannel("A")
    if image.size != (1200, 1200):
        errors.append(f"invalid cutout size {image.size}: {record['id']}")
    if alpha.getextrema() != (0, 255):
        errors.append(f"invalid alpha extrema {alpha.getextrema()}: {record['id']}")
    bbox = alpha.getbbox()
    if not bbox:
        errors.append(f"empty alpha: {record['id']}")
    elif min(bbox[0], bbox[1], 1200 - bbox[2], 1200 - bbox[3]) / 1200 < 0.055:
        errors.append(f"unsafe cutout margin: {record['id']}")
    return errors


def build(plan_path: Path) -> dict[str, Any]:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    garments: list[dict[str, Any]] = []
    for job in plan.get("garmentJobs", []):
        record = job["record_template"]
        if job.get("status") != "approved":
            errors.append(f"garment not approved: {job.get('job_id')}")
            continue
        record["assets"]["alpha_verified"] = True
        record["production"]["qa_status"] = "approved"
        record["annotation"] = {**record["annotation"], "status": "published"}
        errors.extend(_validate_cutout(record))
        garments.append(record)

    outfits = []
    for outfit in [*plan.get("masterOutfits", []), *plan.get("variantOutfits", [])]:
        status = publication_status(outfit)
        if status in {"hold", "alias"}:
            continue
        if status == "pending":
            errors.append(f"missing or stale four-gate review: {outfit['id']}")
        outfits.append(outfit)
    garment_ids = {item["id"] for item in garments}
    for outfit in outfits:
        if (outfit.get("annotation") or {}).get("status") not in {"designer_reviewed", "published"}:
            errors.append(f"outfit not designer reviewed: {outfit['id']}")
        missing = set(outfit.get("garment_ids", [])) - garment_ids
        if missing:
            errors.append(f"dangling garment ids in {outfit['id']}: {sorted(missing)}")
        image_path = _disk_path(str(outfit["assets"]["image_url"]))
        if not image_path.exists():
            errors.append(f"missing flatlay: {image_path}")
        outfit["annotation"] = {**outfit["annotation"], "status": "published"}

    primary_counts = Counter(item.get("primary_persona") for item in outfits)
    for persona in PERSONAS:
        if primary_counts[persona] < 10:
            errors.append(f"{persona} recommendable coverage is {primary_counts[persona]}, minimum 10")
    if len(garments) != 600:
        errors.append(f"approved garment count is {len(garments)}, expected 600")
    fingerprints = [tuple(sorted(item.get("garment_ids") or [])) for item in outfits]
    if len(fingerprints) != len(set(fingerprints)):
        errors.append("duplicate garment sets in publication")
    if errors:
        preview = "\n".join(errors[:30])
        suffix = f"\n... and {len(errors) - 30} more" if len(errors) > 30 else ""
        raise ValueError(f"V2 publish gates failed ({len(errors)}):\n{preview}{suffix}")

    pool = {
        "schemaVersion": "2.0",
        "contentVersion": "2026.09-v2-curated1",
        "status": "published",
        "garments": garments,
        "outfits": outfits,
    }
    validator = Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8")))
    schema_errors = sorted(validator.iter_errors(pool), key=lambda error: list(error.path))
    if schema_errors:
        raise ValueError("schema validation failed:\n" + "\n".join(error.message for error in schema_errors[:30]))
    return pool


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    pool = build(args.plan)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(pool, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "garments": len(pool["garments"]), "outfits": len(pool["outfits"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
