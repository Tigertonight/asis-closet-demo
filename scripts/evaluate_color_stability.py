from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.analyzer import analyze_image_bytes


DATASET_DIR = ROOT / "tests" / "fixtures" / "color_blindset_img2"
MANIFEST_PATH = DATASET_DIR / "manifest.json"
OUTPUT_PATH = ROOT / "tests" / "results" / "color_blindset_img2_results.json"


def _analyze_case(case: dict[str, Any]) -> dict[str, Any]:
    image_path = DATASET_DIR / case["image"]
    result = analyze_image_bytes(
        image_path.read_bytes(),
        f"blind_{case['case_id']}{image_path.suffix}",
        save_upload=False,
        fixture_case=None,
    )
    summary = result.get("result_summary", {})
    season = summary.get("season", {})
    dimensions = summary.get("dimensions", {})
    return {
        "case_id": case["case_id"],
        "capture_condition": case["capture_condition"],
        "status": result.get("status"),
        "result_tier": summary.get("capture", {}).get("result_tier"),
        "confidence": summary.get("confidence"),
        "season_4": season.get("season_4"),
        "season_12": season.get("season_12"),
        "top2": [item.get("season_12") for item in season.get("top_candidates", [])[:2]],
        "dimensions": {
            "temperature": dimensions.get("temperature"),
            "brightness": dimensions.get("brightness"),
            "chroma": dimensions.get("chroma"),
            "contrast": dimensions.get("contrast"),
        },
    }


def _identity_metrics(cases: list[dict[str, Any]]) -> dict[str, Any]:
    canonical = cases[0]
    variants = cases[1:]
    comparable = max(len(variants), 1)
    season4_matches = sum(item["season_4"] == canonical["season_4"] for item in variants)
    top2_overlaps = [len(set(canonical["top2"]) & set(item["top2"])) / 2 for item in variants]
    dimension_checks = 0
    dimension_flips = 0
    for item in variants:
        for key, value in canonical["dimensions"].items():
            if value is None or item["dimensions"].get(key) is None:
                continue
            dimension_checks += 1
            dimension_flips += int(value != item["dimensions"][key])
    confidences = [float(item["confidence"]) for item in cases if item.get("confidence") is not None]
    return {
        "analyzable_rate": round(sum(item["status"] == "analyzed" for item in cases) / len(cases), 4),
        "season_4_agreement": round(season4_matches / comparable, 4),
        "season_12_top2_overlap": round(sum(top2_overlaps) / comparable, 4) if variants else 1.0,
        "dimension_flip_rate": round(dimension_flips / dimension_checks, 4) if dimension_checks else 0.0,
        "confidence_spread": round(max(confidences) - min(confidences), 4) if confidences else None,
    }


def main() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    identities = []
    for identity in manifest["identities"]:
        cases = [_analyze_case(case) for case in identity["cases"]]
        identities.append(
            {
                "identity_id": identity["identity_id"],
                "split": identity["split"],
                "cases": cases,
                "metrics": _identity_metrics(cases),
            }
        )
    payload = {
        "dataset_id": manifest["dataset_id"],
        "targets": manifest["stability_metrics"],
        "identities": identities,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
