"""Recheck stored worn-hat face-only failures without generating or editing images."""
from copy import deepcopy
from pathlib import Path
import sys

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.batch_female_nano_presets import BATCH, MODEL_SHA, fixed_face, now, read, sha, write_json_atomic
from scripts.female_nano_quality import HEADWEAR_RULE, HEADWEAR_RULES, review_worn_hat


def recheck(path):
    row = read(path)
    if row["status"] != "failed_quality":
        return None
    attempt = row["attempts"][-1]
    assert attempt["status"] == "failed_quality"
    folder = ROOT / attempt["path"]
    initial_path = folder / "quality-report.json"
    initial = read(initial_path)
    model_path = ROOT / row["model"]["localPath"]
    result_path = ROOT / attempt["result"]["localPath"]
    assert sha(model_path) == initial["modelSha256"] == row["model"]["sha256"] == MODEL_SHA[row["modelId"]]
    assert sha(result_path) == initial["resultSha256"] == attempt["result"]["sha256"]
    catalog = read(BATCH / "catalog" / row["key"] / "catalog.json")
    original = Image.open(model_path).convert("RGB")
    result = Image.open(result_path).convert("RGB")
    raw = initial.get("originalExpandedQualityReview", initial["qualityReview"])
    checked = review_worn_hat(original, result, raw, catalog["itemContext"],
                              fixed_face(row["modelId"])["evidence"]["primary_face"]["box"],
                              allow_forehead_occlusion=True)
    rule = checked["evidence"].get("face_metric")
    if checked["status"] != "pass" or rule not in HEADWEAR_RULES:
        return {"id": row["id"], "status": "unchanged"}
    target = folder / ("quality-recheck-headwear.v1.json" if rule == HEADWEAR_RULE else "quality-recheck-headwear.v2.json")
    report = {**initial, "qualityReview": checked, "originalExpandedQualityReview": raw,
              "recheck": {"rule": rule, "initialReportPath": str(initial_path.relative_to(ROOT)),
                          "initialReportSha256": sha(initial_path), "recheckedAt": now()}}
    if target.exists():
        saved = read(target)
        assert saved["qualityReview"] == checked and saved["recheck"]["initialReportSha256"] == sha(initial_path)
    else:
        write_json_atomic(target, report)
    row.update(status="generated_local", result=deepcopy(attempt["result"]), qualityReview=checked,
               selectedAttempt=attempt["path"], qualityReportPath=str(target.relative_to(ROOT)),
               semanticReview={"status": "pending", "verified": False}, updatedAt=now(),
               imageEdit={"status": "pass", "provider": row["provider"],
                          "evidence": {"requestId": attempt["requestId"], "nativeSha256": attempt["nativeSha256"]}})
    # The original attempt status, original report and original image bytes stay intact.
    write_json_atomic(path, row)
    return {"id": row["id"], "status": row["status"], "expandedFaceDiff": raw["evidence"]["face_diff"],
            "faceDiff": checked["evidence"]["face_diff"], "visualReview": "pending"}


if __name__ == "__main__":
    import json
    results = [v for p in sorted(BATCH.glob("female_*/*/job.json")) if (v := recheck(p))]
    print(json.dumps(results, ensure_ascii=False, indent=2))
