"""Local contact sheets and explicit, hash-bound visual review receipts."""
import argparse
import json
from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.batch_female_nano_presets import BATCH, MODEL_IDS, job_paths, key_for, now, read, sha, write_json_atomic


def ready(include_incomplete=False):
    result = []
    for look in read(BATCH / "source-snapshot.json")["looks"]:
        key = key_for(look)
        rows = [read(BATCH / mid / key / "job.json") for mid in MODEL_IDS]
        if any(r["status"] == "generated_local" for r in rows) and (include_incomplete or all(
                r["status"] in {"generated_local", "reviewed", "uploaded"} for r in rows)):
            result.append({"key": key, "title": look["note_binding"]["name"],
                           "items": [i["garment_name"] for i in look["items"]],
                           "models": {r["modelId"]: r["status"] for r in rows}})
    return result


def sheets(keys):
    output = BATCH / "review-sheets"
    output.mkdir(exist_ok=True)
    font = ImageFont.truetype("/System/Library/Fonts/STHeiti Light.ttc", 23)
    reports = []
    # Each row contains one source photo and the three model results at 480px wide.
    for start in range(0, len(keys), 2):
        page_keys = keys[start:start + 2]
        canvas = Image.new("RGB", (1920, 730 * len(page_keys)), "#fffaf8")
        draw = ImageDraw.Draw(canvas)
        page = []
        for yindex, key in enumerate(page_keys):
            catalog = read(BATCH / "catalog" / key / "catalog.json")
            rows = [read(BATCH / mid / key / "job.json") for mid in MODEL_IDS]
            files = [Path(catalog["plan"]["style_reference"]["image_path"])]
            labels = [key + " 原搭配"]
            for row in rows:
                result = row.get("result") or next((a.get("result") for a in reversed(row["attempts"]) if a.get("result")), None)
                source = ROOT / result["localPath"] if result else None
                if source:
                    assert sha(source) == result["sha256"]
                files.append(source)
                labels.append(row["model"]["display_name"] + " " + row["status"])
            for col, (file, label) in enumerate(zip(files, labels)):
                if file is None:
                    draw.text((480 * col + 10, 730 * yindex + 10), label, fill="#49373b", font=font)
                    draw.text((480 * col + 140, 730 * yindex + 340), "尚无生成结果", fill="#80676d", font=font)
                    continue
                im = Image.open(file).convert("RGB")
                thumb = ImageOps.contain(im, (468, 655), Image.Resampling.LANCZOS)
                canvas.paste(thumb, (480 * col + (480 - thumb.width) // 2, 730 * yindex + 53 + (655 - thumb.height) // 2))
                draw.text((480 * col + 10, 730 * yindex + 10), label, fill="#49373b", font=font)
            page.append({"key": key, "title": catalog["plan"]["title"],
                         "items": [i["title"] for i in catalog["plan"]["items"]],
                         "files": [str(p) if p else None for p in files],
                         "results": [{"id": r["id"], "sha256": r.get("result", {}).get("sha256"),
                                      "faceDiff": r.get("qualityReview", {}).get("evidence", {}).get("face_diff")} for r in rows]})
        target = output / ("__".join(page_keys) + ".jpg")
        canvas.save(target, quality=96)
        write_json_atomic(target.with_suffix(".json"), page)
        reports.append({"image": str(target), "outfits": [{"key": p["key"], "items": p["items"]} for p in page]})
    return reports


def record_reviews(path):
    # This file must be written only after the actual images are visually viewed.
    reviews = read(path)
    changed = []
    for review in reviews:
        mid, key = review["modelId"], review["key"]
        if mid not in MODEL_IDS or key not in {key_for(x) for x in read(BATCH / "source-snapshot.json")["looks"]}:
            raise ValueError("Unknown model or outfit")
        job_path = BATCH / mid / key / "job.json"
        row = read(job_path)
        if row["status"] not in {"generated_local", "reviewed"}:
            raise ValueError("Cannot review a running, failed or published job")
        result = row["result"]
        if review["resultSha256"] != result["sha256"] or sha(ROOT / result["localPath"]) != result["sha256"]:
            raise ValueError("Review is stale")
        if not review.get("observations") or review["status"] not in {"pass", "fail"}:
            raise ValueError("Explicit visual observations are required")
        visual = {**review, "verified": review["status"] == "pass", "reviewer": "assistant_visual_inspection",
                  "reviewedAt": now(), "reviewedItemIds": row["itemIds"]}
        if review["status"] == "pass" and row["qualityReview"]["status"] != "pass":
            raise ValueError("Cannot bypass numeric quality failure")
        write_json_atomic(job_path.parent / "visual-review.json", visual)
        row.update(status="reviewed" if visual["verified"] else "failed_visual", visualReview=visual,
                   semanticReview=visual, updatedAt=now())
        if not visual["verified"]:
            row["retryCorrection"] = review["correction"]
            # Keep the failing result in its attempt, never as a selected preset.
            row["attempts"][-1]["visualReview"] = visual
            row.pop("result", None)
            row.pop("selectedAttempt", None)
        write_json_atomic(job_path, row)
        changed.append({"id": row["id"], "status": row["status"]})
    return changed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["ready", "pending", "sheets", "record"])
    parser.add_argument("--keys", nargs="+")
    parser.add_argument("--file", type=Path)
    args = parser.parse_args()
    result = ready(args.action == "pending") if args.action in {"ready", "pending"} else sheets(args.keys) if args.action == "sheets" else record_reviews(args.file)
    print(json.dumps(result, ensure_ascii=False, indent=2))
