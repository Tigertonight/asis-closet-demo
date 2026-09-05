#!/usr/bin/env python3
"""Report resumable V2 content-production progress without publishing drafts."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from app.selfit_content_quality import review_is_current, publication_status
DEFAULT_PLAN = ROOT / "app/static/selfit/data/content-production-plan.v2.json"
DEFAULT_OUTPUT = ROOT / "docs/SELFIT_CONTENT_PRODUCTION_STATUS.json"


def _disk_path(public_path: str) -> Path:
    if public_path.startswith("/static/"):
        return ROOT / "app" / public_path.lstrip("/")
    return ROOT / public_path.lstrip("/")


def build_report(plan_path: Path) -> dict[str, Any]:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    jobs = plan.get("garmentJobs", [])
    masters = plan.get("masterOutfits", [])
    variants = plan.get("variantOutfits", [])

    approved_jobs = [job for job in jobs if job.get("status") == "approved"]
    approved_by_persona: dict[str, Counter[str]] = defaultdict(Counter)
    approved_by_category: Counter[str] = Counter()
    missing_approved_assets: list[str] = []
    for job in approved_jobs:
        persona = str(job.get("persona"))
        category = str(job.get("category"))
        approved_by_persona[persona][category] += 1
        approved_by_category[category] += 1
        record = job.get("record_template") or {}
        asset = ((record.get("assets") or {}).get("image_url"))
        if not asset or not _disk_path(str(asset)).exists():
            missing_approved_assets.append(str(job.get("job_id")))

    all_outfits = [*masters, *variants]
    rendered = [outfit for outfit in all_outfits if _disk_path(str((outfit.get("assets") or {}).get("image_url", ""))).exists()]
    reviewed = [
        outfit for outfit in all_outfits
        if review_is_current(outfit)
    ]

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "plan": str(plan_path.relative_to(ROOT)),
        "publish_ready": len(approved_jobs) == 600 and len(rendered) == 1200 and len(reviewed) == 1200 and not missing_approved_assets,
        "garments": {
            "target": 600,
            "approved": len(approved_jobs),
            "remaining": 600 - len(approved_jobs),
            "status_counts": dict(sorted(Counter(str(job.get("status", "unknown")) for job in jobs).items())),
            "approved_by_category": dict(sorted(approved_by_category.items())),
            "approved_by_persona": {persona: dict(sorted(counts.items())) for persona, counts in sorted(approved_by_persona.items())},
            "missing_approved_assets": missing_approved_assets,
        },
        "outfits": {
            "target": 1200,
            "master_recipes": len(masters),
            "variant_recipes": len(variants),
            "rendered": len(rendered),
            "designer_reviewed": len(reviewed),
            "review_definition": "revision-bound technical + aesthetic + persona + context evidence",
            "editorial_status_counts": dict(Counter(publication_status(row) for row in all_outfits)),
            "remaining_to_render": 1200 - len(rendered),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = build_report(args.plan)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
