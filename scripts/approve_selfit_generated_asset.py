#!/usr/bin/env python3
"""Ingest one built-in imagegen result and update its production job safely."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image, ImageStat

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.prepare_selfit_garment_asset import prepare  # noqa: E402


DEFAULT_PLAN = ROOT / "app/static/selfit/data/content-production-plan.v2.json"


def _dhash(path: Path) -> str:
    rgba = Image.open(path).convert("RGBA")
    image = rgba.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
    bits = []
    for y in range(8):
        for x in range(8):
            bits.append(image.getpixel((x, y)) > image.getpixel((x + 1, y)))
    shape_hash = f"{sum(int(value) << index for index, value in enumerate(bits)):016x}"
    mean = ImageStat.Stat(rgba.convert("RGB"), mask=rgba.getchannel("A")).mean
    color_signature = "".join(f"{max(0, min(255, round(value))):02x}" for value in mean)
    return f"{shape_hash}-{color_signature}"


def ingest(plan_path: Path, job_id: str, generated_path: Path, *, designer_approved: bool) -> dict[str, object]:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    job = next((item for item in plan.get("garmentJobs", []) if item.get("job_id") == job_id), None)
    if job is None:
        raise KeyError(f"unknown generation job: {job_id}")
    raw_path = ROOT / job["expected_raw_output"]
    output_path = ROOT / job["expected_output"]
    if raw_path.exists() or output_path.exists():
        raise FileExistsError(f"asset version already exists for {job_id}")
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(generated_path, raw_path)
    qa = prepare(raw_path, output_path)
    qa.update({
        "job_id": job_id,
        "designer_reviewed": designer_approved,
        "reviewed_at": datetime.now(UTC).isoformat() if designer_approved else None,
        "visual_checks": {
            "one_item_only": designer_approved,
            "no_person_mannequin_hanger": designer_approved,
            "no_text_logo_watermark": designer_approved,
            "complete_silhouette": designer_approved,
            "metadata_matches_asset": designer_approved,
        },
    })
    qa_path = output_path.with_suffix(".qa.json")
    qa_path.write_text(json.dumps(qa, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    approved = bool(qa["passed"] and designer_approved)
    job["status"] = "approved" if approved else "generated"
    record = job["record_template"]
    record["assets"]["alpha_verified"] = bool(qa["passed"])
    record["production"]["qa_status"] = job["status"]
    record["production"]["phash"] = _dhash(output_path)
    record["annotation"] = {
        "status": "designer_reviewed" if approved else "machine_draft",
        "source": "designer" if designer_approved else "source_record",
        "confidence": 0.96 if approved else 0.7,
        "review_notes": [] if approved else ["等待视觉审核"],
    }
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"job_id": job_id, "status": job["status"], "raw": str(raw_path), "output": str(output_path), "qa": str(qa_path), "phash": record["production"]["phash"], "checks": qa}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("job_id")
    parser.add_argument("generated_path", type=Path)
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--designer-approved", action="store_true")
    args = parser.parse_args()
    print(json.dumps(ingest(args.plan, args.job_id, args.generated_path, designer_approved=args.designer_approved), ensure_ascii=False))


if __name__ == "__main__":
    main()
