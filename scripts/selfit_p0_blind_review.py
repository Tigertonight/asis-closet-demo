"""Build and grade the exact P0 anchor blind-review package.

Build refuses pending four-gate decisions. Grade never mutates catalog or
release files; it only emits revision-bound evidence for the release auditor.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import zipfile
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.recommendation_anchors import PERSONAS
from app.selfit_content_quality import GATES

PRODUCER = "codex-selfit-p0-content-production"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def editorial_errors(manifest: dict, editorial: dict, manifest_sha: str) -> list[str]:
    errors = []
    if editorial.get("anchor_manifest_sha256") != manifest_sha:
        errors.append("editorial review is not bound to the anchor manifest")
    anchors = manifest.get("anchors") if isinstance(manifest.get("anchors"), list) else []
    reviews = editorial.get("reviews") if isinstance(editorial.get("reviews"), list) else []
    by_id = {str(row.get("outfit_id") or ""): row for row in reviews if isinstance(row, dict)}
    ids = [str(row.get("outfit_id") or "") for row in anchors if isinstance(row, dict)]
    if len(ids) != 160 or len(set(ids)) != 160 or len(reviews) != 160 or len(by_id) != 160 or set(ids) != set(by_id):
        errors.append("editorial review must cover the exact 160 anchors")
        return errors
    for anchor in anchors:
        oid, row = str(anchor["outfit_id"]), by_id[str(anchor["outfit_id"])]
        if row.get("record_fingerprint") != anchor.get("record_fingerprint"):
            errors.append(f"{oid}: editorial record fingerprint is stale")
        if row.get("final_decision") != "approved":
            errors.append(f"{oid}: final editorial decision is not approved")
        gates = row.get("gates") if isinstance(row.get("gates"), dict) else {}
        for gate in GATES:
            decision = gates.get(gate) if isinstance(gates.get(gate), dict) else {}
            if (decision.get("status") != "passed" or not str(decision.get("reviewer") or "").strip()
                    or not str(decision.get("evidence") or "").strip()):
                errors.append(f"{oid}: {gate} gate is incomplete")
    return errors


def build(manifest_path: Path, editorial_path: Path, output: Path) -> None:
    if output.exists():
        raise ValueError("Use a new output directory; never overwrite blind-review evidence")
    manifest, editorial = json.loads(manifest_path.read_text()), json.loads(editorial_path.read_text())
    errors = editorial_errors(manifest, editorial, digest(manifest_path))
    if errors:
        raise ValueError("Four-gate review is not ready: " + "; ".join(errors[:8]))
    reviews = {row["outfit_id"]: row for row in editorial["reviews"]}
    selected = list(manifest["anchors"])
    random.Random(int(digest(manifest_path)[:16], 16)).shuffle(selected)
    reviewer_dir = output / "reviewer"
    reviewer_dir.mkdir(parents=True)
    templates = json.loads((ROOT / "app/static/selfit/data/personality-report-templates.v1.json").read_text())["types"]
    save(reviewer_dir / "persona-rubric.json", {
        key: {field: value[field] for field in ("metadata", "keywords", "summary")}
        for key, value in templates.items()
    })
    keys, answer_rows = {}, []
    sheets = []
    for index, anchor in enumerate(selected):
        token = f"look-{index + 1:03d}"
        review = reviews[anchor["outfit_id"]]
        source = ROOT / review["image_path"]
        if not source.is_file() or digest(source) != review.get("image_sha256"):
            raise ValueError(f"Missing or stale editorial image: {anchor['outfit_id']}")
        with Image.open(source) as opened:
            image = ImageOps.contain(opened.convert("RGB"), (600, 750))
            image.save(reviewer_dir / f"{token}.jpg", quality=95)
        if index % 20 == 0:
            sheet = Image.new("RGB", (1200, 1360), "white")
        thumb = ImageOps.contain(image, (230, 300))
        x, y = (index % 5) * 240, ((index % 20) // 5) * 340
        sheet.paste(thumb, (x + (240 - thumb.width) // 2, y + 25))
        ImageDraw.Draw(sheet).text((x + 10, y + 8), token, fill="black")
        if index % 20 == 19:
            sheet_path = reviewer_dir / f"sheet-{index // 20 + 1:02d}.jpg"
            sheet.save(sheet_path, quality=92)
            sheets.append(sheet_path.name)
        keys[token] = {
            "outfit_id": anchor["outfit_id"], "primary_persona": anchor["persona"],
            "record_fingerprint": anchor["record_fingerprint"],
            "source_image": review["image_path"], "source_image_sha256": review["image_sha256"],
            "review_image_sha256": digest(reviewer_dir / f"{token}.jpg"),
        }
        answer_rows.append({
            "token": token, "top1": "", "top2": "", "reason": "",
            "issues": [], "verdict": "pending",
        })
    package_id = hashlib.sha256(json.dumps(keys, sort_keys=True).encode()).hexdigest()
    save(output / "examiner-key.json", {
        "package_id": package_id, "producer": PRODUCER,
        "anchor_manifest_sha256": digest(manifest_path), "keys": keys,
    })
    save(reviewer_dir / "answers.json", {
        "package_id": package_id, "reviewer": "", "independent": False,
        "labels_hidden": False, "answers": answer_rows,
    })
    (reviewer_dir / "README.md").write_text(
        "# Selfit P0 独立盲审\n\n"
        "只使用本目录或 reviewer.zip，不得查看 examiner-key.json。\n"
        "审核者必须未参与这 160 套的生产、标注与四门审核。\n"
        "每套填写不同的 Top-1 / Top-2、视觉理由、问题和 accept/reject/uncertain。\n",
        encoding="utf-8",
    )
    with zipfile.ZipFile(output / "reviewer.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(reviewer_dir.iterdir()):
            archive.write(path, path.name)
    save(output / "status.json", {
        "status": "pending_independent_review", "package_id": package_id,
        "samples": 160, "reviewed": 0, "sheets": sheets,
    })


def grade(key_path: Path, answers_path: Path, manifest_path: Path, output: Path) -> None:
    if output.exists():
        raise ValueError("Use a new blind-review result path")
    key, answers, manifest = (json.loads(path.read_text()) for path in (key_path, answers_path, manifest_path))
    if key.get("anchor_manifest_sha256") != digest(manifest_path):
        raise ValueError("Blind package is stale for this anchor manifest")
    if (answers.get("package_id") != key.get("package_id") or not str(answers.get("reviewer") or "").strip()
            or answers.get("reviewer") == key.get("producer") or answers.get("independent") is not True
            or answers.get("labels_hidden") is not True):
        raise ValueError("Matching package and declared independent, blinded reviewer required")
    records, rows = key["keys"], answers.get("answers") or []
    if len(rows) != 160 or {row.get("token") for row in rows} != set(records):
        raise ValueError("Every blind token must appear exactly once")
    manifest_rows = {row["outfit_id"]: row for row in manifest["anchors"]}
    scores, decisions = {}, []
    for row in rows:
        expected = records[row["token"]]
        current = manifest_rows.get(expected["outfit_id"])
        source = ROOT / expected["source_image"]
        if (not current or current.get("record_fingerprint") != expected["record_fingerprint"]
                or current.get("persona") != expected.get("primary_persona")
                or not source.is_file() or digest(source) != expected["source_image_sha256"]):
            raise ValueError(f"Stale blind sample: {row['token']}")
        if (row.get("top1") not in PERSONAS or row.get("top2") not in PERSONAS
                or row["top1"] == row["top2"] or not str(row.get("reason") or "").strip()
                or row.get("verdict") not in {"accept", "reject", "uncertain"}
                or not isinstance(row.get("issues"), list)):
            raise ValueError(f"Incomplete blind review: {row['token']}")
        persona = expected["primary_persona"]
        counter = scores.setdefault(persona, Counter())
        counter["samples"] += 1
        counter["top1_hits"] += row["top1"] == persona
        counter["top2_hits"] += persona in {row["top1"], row["top2"]}
        decisions.append({**row, "outfit_id": expected["outfit_id"],
                          "expected_persona": persona, "record_fingerprint": expected["record_fingerprint"]})
    totals = sum(scores.values(), Counter())
    result = {
        "status": "independent_review_recorded_pending_release",
        "package_id": key["package_id"], "reviewer": answers["reviewer"],
        "identity_verification": "declaration_only", "catalog_mutated": False,
        "independent": answers["independent"], "labels_hidden": answers["labels_hidden"],
        "samples": totals["samples"],
        "top1_accuracy": totals["top1_hits"] / totals["samples"],
        "top2_accuracy": totals["top2_hits"] / totals["samples"],
        "by_persona": scores,
        "thresholds": {"overall_top1": .70, "overall_top2": .90,
                       "persona_top1": .60, "persona_top2": .80},
        "decisions": decisions,
    }
    save(output, result)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    build_parser = sub.add_parser("build")
    build_parser.add_argument("--anchor-manifest", type=Path, required=True)
    build_parser.add_argument("--editorial-review", type=Path, required=True)
    build_parser.add_argument("--output", type=Path, required=True)
    grade_parser = sub.add_parser("grade")
    grade_parser.add_argument("--key", type=Path, required=True)
    grade_parser.add_argument("--answers", type=Path, required=True)
    grade_parser.add_argument("--anchor-manifest", type=Path, required=True)
    grade_parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "build":
        build(args.anchor_manifest, args.editorial_review, args.output)
    else:
        grade(args.key, args.answers, args.anchor_manifest, args.output)


if __name__ == "__main__":
    main()
