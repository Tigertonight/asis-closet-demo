"""Create a fail-closed Selfit P0 release report.

Human visual judgment, independent blind review, browser runs and performance
measurements remain external evidence.  This script verifies their revision
binding and completeness; it never invents a passing result for missing work.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import closet
from app.recommendation_anchors import blind_review_errors, validate_manifest
from app.recommendation_diversity import FAMILY_PATH
from app.recommendation_visual import DEFAULT_PATH as VISUAL_PATH, attach_visual, load_visual
from app.selfit_content_quality import record_fingerprint, review_is_current

FEED_CASES = {f"FEED-{number:03d}" for number in range(1, 15)}
REC_CASES = {f"REC-{number:03d}" for number in range(1, 15)}
E2E_CASES = {f"E2E-{number:03d}" for number in range(1, 13)}
PERF_CASES = {f"PERF-{number:03d}" for number in range(1, 7)}
ALLOWED_CASE_STATUS = {"Pass", "Fail", "Blocked", "Not Run"}


def read_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def sha256(path: Path | None) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path and path.is_file() else None


def git_value(*args: str) -> str | None:
    try:
        return subprocess.run(
            ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
        ).stdout.strip() or None
    except (OSError, subprocess.CalledProcessError):
        return None


def evidence_cases(evidence: dict[str, Any]) -> dict[str, str]:
    rows = evidence.get("cases")
    if isinstance(rows, dict):
        return {
            str(case_id): str(value.get("status") if isinstance(value, dict) else value)
            for case_id, value in rows.items()
        }
    if isinstance(rows, list):
        return {
            str(row.get("id")): str(row.get("status"))
            for row in rows if isinstance(row, dict) and row.get("id")
        }
    return {}


def evidence_gate(evidence: dict[str, Any], required: set[str], anchor_sha: str | None) -> dict[str, Any]:
    if not evidence:
        return {"status": "Not Run", "errors": ["evidence file is missing"]}
    errors = []
    if evidence.get("schema_version") != 1:
        errors.append("evidence schema_version must be 1")
    if evidence.get("anchor_manifest_sha256") != anchor_sha:
        errors.append("evidence is not bound to this anchor manifest")
    cases = evidence_cases(evidence)
    missing = sorted(required - cases.keys())
    invalid = sorted(case_id for case_id in required if cases.get(case_id) not in ALLOWED_CASE_STATUS)
    failed = sorted(case_id for case_id in required if cases.get(case_id) in {"Fail", "Blocked", "Not Run"})
    if missing:
        errors.append("missing cases: " + ", ".join(missing))
    if invalid:
        errors.append("invalid case statuses: " + ", ".join(invalid))
    if failed:
        errors.append("non-passing cases: " + ", ".join(failed))
    return {"status": "Pass" if not errors else "Fail", "errors": errors, "cases": cases}


def make_report(anchor_path: Path, blind_path: Path | None, browser_path: Path | None,
                performance_path: Path | None, staging_path: Path | None = None,
                recommendation_path: Path | None = None) -> dict[str, Any]:
    manifest, blind = read_json(anchor_path), read_json(blind_path)
    browser, performance = read_json(browser_path), read_json(performance_path)
    recommendation = read_json(recommendation_path)
    pool = closet.selfit_content_pool()
    visual = load_visual()
    catalog, held = attach_visual(
        closet._published_catalog_outfits(), pool.garments, pool.outfits, visual
    )
    content_version = str(pool.metadata.get("contentVersion") or "unknown")
    visual_version = str(visual.get("version") or "pending-vision")
    family_sha = sha256(FAMILY_PATH) or "missing"
    anchor_sha = sha256(anchor_path)
    raw_rows = list(pool.outfits)
    raw_by_id = {str(row.get("id") or ""): row for row in raw_rows}
    staging = read_json(staging_path)
    staging_errors = []
    if staging:
        for entry in staging.get("entries") or []:
            raw, adapted = entry.get("raw_record"), entry.get("catalog_record")
            if (not isinstance(raw, dict) or not isinstance(adapted, dict)
                    or entry.get("record_fingerprint") != record_fingerprint(raw)
                    or raw.get("id") != adapted.get("outfit_id")):
                staging_errors.append("staging contains a stale or malformed outfit")
                continue
            raw_by_id[str(raw.get("id") or "")] = raw
            catalog.append(adapted)
        raw_rows = list(raw_by_id.values())
    anchor_ids = [str(row.get("outfit_id") or "") for row in manifest.get("anchors", []) if isinstance(row, dict)]

    structure = validate_manifest(
        manifest, catalog, raw_rows,
        content_version=content_version,
        visual_version=visual_version,
        family_registry_sha256=family_sha,
        require_release=False,
    )
    current_reviews = sum(
        review_is_current(raw_by_id[oid]) for oid in anchor_ids if oid in raw_by_id
    )
    content_errors = []
    if len(anchor_ids) != 160:
        content_errors.append(f"anchor count is {len(anchor_ids)}, expected 160")
    if current_reviews != 160:
        content_errors.append(f"current four-gate reviews are {current_reviews}/160")

    package_id = str(manifest.get("blind_review_package_id") or "")
    blind_errors = blind_review_errors(blind, package_id, manifest.get("anchors") or [])
    blind_status = "Not Run" if not blind else "Pass" if not blind_errors else "Fail"
    feed = evidence_gate(browser, FEED_CASES, anchor_sha)
    rec = evidence_gate(recommendation or browser, REC_CASES, anchor_sha)
    e2e = evidence_gate(browser, E2E_CASES, anchor_sha)
    perf = evidence_gate(performance, PERF_CASES, anchor_sha)

    trace_errors = []
    trace_errors.extend(staging_errors)
    if not git_value("rev-parse", "HEAD"):
        trace_errors.append("git commit is unavailable")
    if git_value("status", "--porcelain") not in {None, ""}:
        trace_errors.append("git worktree is not frozen/clean")
    for label, expected, actual in (
        ("content", manifest.get("content_version"), content_version),
        ("visual", manifest.get("visual_version"), visual_version),
        ("family registry", manifest.get("family_registry_sha256"), family_sha),
    ):
        if expected != actual:
            trace_errors.append(f"{label} version/fingerprint mismatch")
    if manifest.get("staging_version"):
        if not staging:
            trace_errors.append("anchor manifest requires a staging bundle")
        elif manifest.get("staging_version") != staging.get("version"):
            trace_errors.append("staging bundle version mismatch")

    gates = {
        "G0_traceability": {"status": "Pass" if not trace_errors else "Fail", "errors": trace_errors},
        "G1_home_feed_stability": feed,
        "G2_content_admission": {"status": "Pass" if not content_errors else "Fail", "errors": content_errors},
        "G3_anchor_completeness": {"status": "Pass" if structure["valid"] else "Fail", "errors": structure["errors"]},
        "G4_persona_blind_review": {"status": blind_status, "errors": blind_errors},
        "G5_recommendation_quality": rec,
        "G6_end_to_end": e2e,
        "G7_performance_and_regression": perf,
    }
    releasable = all(gate["status"] == "Pass" for gate in gates.values())
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "release_decision": "allow_internal_gray" if releasable else "do_not_release",
        "releasable": releasable,
        "versions": {
            "git_commit": git_value("rev-parse", "HEAD"),
            "git_worktree_clean": git_value("status", "--porcelain") in {None, ""},
            "content_version": content_version,
            "content_sha256": sha256(Path(pool._path)),
            "visual_version": visual_version,
            "visual_sha256": sha256(VISUAL_PATH),
            "family_registry_sha256": family_sha,
            "anchor_manifest_sha256": anchor_sha,
            "blind_result_sha256": sha256(blind_path),
            "browser_evidence_sha256": sha256(browser_path),
            "performance_evidence_sha256": sha256(performance_path),
            "recommendation_evidence_sha256": sha256(recommendation_path),
            "staging_version": staging.get("version"),
            "staging_sha256": sha256(staging_path),
        },
        "inventory": {
            "anchor_rows": len(anchor_ids),
            "current_four_gate_reviews": current_reviews,
            "visual_eligible_catalog": len(catalog),
            "visual_held_catalog": len(held),
        },
        "gates": gates,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--anchor-manifest", type=Path, required=True)
    parser.add_argument("--blind-result", type=Path)
    parser.add_argument("--browser-evidence", type=Path)
    parser.add_argument("--performance-evidence", type=Path)
    parser.add_argument("--recommendation-evidence", type=Path)
    parser.add_argument("--staging", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Refusing to overwrite existing release evidence")
    report = make_report(args.anchor_manifest, args.blind_result, args.browser_evidence,
                         args.performance_evidence, args.staging, args.recommendation_evidence)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"release_decision": report["release_decision"], "gates": {
        name: gate["status"] for name, gate in report["gates"].items()
    }}, ensure_ascii=False, indent=2))
    return 0 if report["releasable"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
