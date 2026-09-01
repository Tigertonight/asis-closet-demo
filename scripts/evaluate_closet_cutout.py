#!/usr/bin/env python3
"""Run repeatable closet garment-splitting evaluations on imagegen fixtures.

The default inventory mode exercises the configured vision model without writing
closet data. Full mode runs the real import pipeline in an isolated output folder
and verifies PNG transparency, unique IDs, and manifest persistence.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app.closet as closet  # noqa: E402


FIXTURE_DIR = ROOT / "tests" / "fixtures" / "closet_cutout_imagegen"
MANIFEST_PATH = FIXTURE_DIR / "manifest.json"
GENERATED_DIR = FIXTURE_DIR / "generated"
DEFAULT_CASES = ["A01", "B01", "B02", "C01", "C02", "C03", "C04", "G01", "K01", "T01"]


def _case_catalog() -> dict[str, dict[str, Any]]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {
        case["id"]: case
        for group in manifest["groups"]
        for case in group["cases"]
    }


def _fixture_path(case_id: str) -> Path:
    matches = sorted(GENERATED_DIR.glob(f"{case_id}_*.png"))
    if len(matches) != 1:
        raise RuntimeError(f"{case_id}: expected exactly one generated fixture, found {len(matches)}")
    return matches[0]


def _expected_categories(case: dict[str, Any]) -> Counter[str]:
    return Counter({item["slot"]: int(item["count"]) for item in case.get("expected_items", [])})


def _categories(items: list[dict[str, Any]]) -> Counter[str]:
    return Counter(str(item.get("category") or "") for item in items if item.get("category"))


def _category_metrics(expected: Counter[str], actual: Counter[str]) -> dict[str, Any]:
    true_positive = sum(min(expected[key], actual[key]) for key in expected.keys() | actual.keys())
    predicted = sum(actual.values())
    wanted = sum(expected.values())
    precision = true_positive / predicted if predicted else (1.0 if wanted == 0 else 0.0)
    recall = true_positive / wanted if wanted else (1.0 if predicted == 0 else 0.0)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "exact": expected == actual,
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
    }


def _configure_isolated_output(run_dir: Path) -> None:
    closet.CLOSET_OUTPUT_DIR = run_dir / "closet"
    closet.CLOSET_SOURCE_DIR = closet.CLOSET_OUTPUT_DIR / "sources"
    closet.CLOSET_ITEM_DIR = closet.CLOSET_OUTPUT_DIR / "items"
    closet.CLOSET_MANIFEST_PATH = closet.CLOSET_OUTPUT_DIR / "closet_manifest.json"
    closet.OUTFIT_DIR = closet.CLOSET_OUTPUT_DIR / "outfits"
    closet.OUTFIT_MANIFEST_PATH = closet.CLOSET_OUTPUT_DIR / "outfits_manifest.json"
    closet.TRYON_RECORD_DIR = closet.CLOSET_OUTPUT_DIR / "tryon_records"
    closet.TRYON_RECORDS_MANIFEST_PATH = closet.CLOSET_OUTPUT_DIR / "tryon_records_manifest.json"


def _evaluate_inventory(case: dict[str, Any], fixture: Path, provider: closet.AIGarmentCutoutProvider) -> dict[str, Any]:
    with Image.open(fixture) as image:
        candidates = provider._analyze_inventory(image.convert("RGB"))
    expected = _expected_categories(case)
    actual = _categories(candidates)
    return {
        "case_id": case["id"],
        "title": case["title"],
        "fixture": str(fixture.relative_to(ROOT)),
        "expected": dict(expected),
        "actual": dict(actual),
        "metrics": _category_metrics(expected, actual),
        "candidates": candidates,
    }


def _evaluate_full(case: dict[str, Any], fixture: Path, run_dir: Path) -> dict[str, Any]:
    raw = fixture.read_bytes()
    source = closet._save_source_image(raw, fixture.name, "evaluation")
    result = closet._import_sources([source], import_type="evaluation")
    items = result.get("items") or []
    expected = _expected_categories(case)
    actual = _categories(items)
    cutout_checks: list[dict[str, Any]] = []
    for item in items:
        disk_path = closet._closet_disk_path((item.get("assets") or {}).get("cutout_path"))
        exists = bool(disk_path and disk_path.exists())
        mode = None
        transparent = False
        if exists and disk_path:
            with Image.open(disk_path) as cutout:
                mode = cutout.mode
                transparent = closet._has_meaningful_transparency(cutout)
        cutout_checks.append({
            "item_id": item.get("item_id"),
            "category": item.get("category"),
            "exists": exists,
            "mode": mode,
            "meaningful_transparency": transparent,
            "path": str(disk_path.relative_to(run_dir)) if disk_path and disk_path.is_relative_to(run_dir) else str(disk_path),
        })
    manifest = json.loads(closet.CLOSET_MANIFEST_PATH.read_text(encoding="utf-8")) if closet.CLOSET_MANIFEST_PATH.exists() else {"items": []}
    ids = [str(item.get("item_id")) for item in items]
    contract = {
        "unique_item_ids": len(ids) == len(set(ids)),
        "all_cutouts_exist": all(check["exists"] for check in cutout_checks),
        "all_cutouts_rgba": all(check["mode"] == "RGBA" for check in cutout_checks),
        "all_cutouts_transparent": all(check["meaningful_transparency"] for check in cutout_checks),
        "manifest_persisted": all(item_id in {entry.get("item_id") for entry in manifest.get("items", [])} for item_id in ids),
    }
    return {
        "case_id": case["id"],
        "title": case["title"],
        "fixture": str(fixture.relative_to(ROOT)),
        "expected": dict(expected),
        "actual": dict(actual),
        "metrics": _category_metrics(expected, actual),
        "contract": contract,
        "contract_pass": all(contract.values()),
        "cutouts": cutout_checks,
        "pipeline_summary": result.get("summary"),
        "status": result.get("status"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("inventory", "full"), default="inventory")
    parser.add_argument("--cases", nargs="+", default=DEFAULT_CASES)
    parser.add_argument("--output", type=Path, help="Directory for report and isolated full-pipeline artifacts")
    args = parser.parse_args()

    catalog = _case_catalog()
    unknown = [case_id for case_id in args.cases if case_id not in catalog]
    if unknown:
        parser.error(f"unknown cases: {', '.join(unknown)}")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = (args.output or ROOT / "outputs" / "evaluations" / "closet_cutout" / f"{timestamp}_{args.mode}").resolve()
    run_dir.mkdir(parents=True, exist_ok=True)

    provider = closet.AIGarmentCutoutProvider()
    if not provider.available():
        raise RuntimeError(f"AI garment provider unavailable: {provider.status()}")
    if args.mode == "full":
        _configure_isolated_output(run_dir)

    results: list[dict[str, Any]] = []
    for case_id in args.cases:
        case = catalog[case_id]
        fixture = _fixture_path(case_id)
        print(f"[{args.mode}] {case_id} {fixture.name}", flush=True)
        if args.mode == "inventory":
            result = _evaluate_inventory(case, fixture, provider)
        else:
            result = _evaluate_full(case, fixture, run_dir)
        results.append(result)
        print(json.dumps({"case_id": case_id, "actual": result["actual"], "metrics": result["metrics"], "contract_pass": result.get("contract_pass")}, ensure_ascii=False), flush=True)

    exact_count = sum(1 for result in results if result["metrics"]["exact"])
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": args.mode,
        "provider": provider.status(),
        "model": provider.model,
        "cases": results,
        "summary": {
            "total": len(results),
            "category_exact": exact_count,
            "category_exact_rate": round(exact_count / len(results), 3) if results else 0.0,
            "contract_pass": sum(1 for result in results if result.get("contract_pass")) if args.mode == "full" else None,
        },
    }
    report_path = run_dir / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"report={report_path}")
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0 if exact_count == len(results) and (args.mode != "full" or all(result["contract_pass"] for result in results)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
