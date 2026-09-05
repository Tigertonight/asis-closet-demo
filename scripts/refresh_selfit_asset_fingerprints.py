#!/usr/bin/env python3
"""Refresh color-aware fingerprints for approved Selfit V2 garment assets."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.approve_selfit_generated_asset import _dhash  # noqa: E402


DEFAULT_PLAN = ROOT / "app/static/selfit/data/content-production-plan.v2.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    args = parser.parse_args()
    data = json.loads(args.plan.read_text(encoding="utf-8"))
    updated = 0
    for job in data.get("garmentJobs", []):
        if job.get("status") != "approved":
            continue
        path = ROOT / job["expected_output"]
        job["record_template"]["production"]["phash"] = _dhash(path)
        updated += 1
    args.plan.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"updated": updated, "plan": str(args.plan)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
