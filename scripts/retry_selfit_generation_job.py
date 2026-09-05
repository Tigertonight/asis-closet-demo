#!/usr/bin/env python3
"""Create a non-destructive next attempt for a Selfit garment generation job."""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PLAN = ROOT / "app/static/selfit/data/content-production-plan.v2.json"


def _bump(path: str) -> str:
    match = re.search(r"-v(\d+)\.png$", path)
    if not match:
        raise ValueError(f"versioned PNG path required: {path}")
    version = int(match.group(1)) + 1
    return path[: match.start()] + f"-v{version}.png"


def retry(plan_path: Path, job_id: str, reason: str) -> dict[str, object]:
    data = json.loads(plan_path.read_text(encoding="utf-8"))
    job = next((item for item in data.get("garmentJobs", []) if item.get("job_id") == job_id), None)
    if job is None:
        raise KeyError(f"unknown generation job: {job_id}")
    record = job["record_template"]
    attempts = job.setdefault("attempts", [])
    attempts.append({
        "status": job.get("status"),
        "raw": job.get("expected_raw_output"),
        "output": job.get("expected_output"),
        "phash": (record.get("production") or {}).get("phash", ""),
        "reason": reason,
        "archived_at": datetime.now(UTC).isoformat(),
    })
    job["expected_raw_output"] = _bump(job["expected_raw_output"])
    job["expected_output"] = _bump(job["expected_output"])
    job["status"] = "planned"
    assets = record["assets"]
    assets["image_url"] = "/static/" + job["expected_output"].removeprefix("app/static/")
    assets["alpha_verified"] = False
    production = record["production"]
    production["qa_status"] = "planned"
    production["phash"] = ""
    record["annotation"] = {"status": "unlabeled", "source": "designer", "confidence": 0.0, "review_notes": [reason]}
    plan_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"job_id": job_id, "status": "planned", "raw": job["expected_raw_output"], "output": job["expected_output"], "attempts": len(attempts)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("job_id")
    parser.add_argument("--reason", required=True)
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    args = parser.parse_args()
    print(json.dumps(retry(args.plan, args.job_id, args.reason), ensure_ascii=False))


if __name__ == "__main__":
    main()
