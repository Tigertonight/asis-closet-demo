"""Apply explicit owner acceptance to exact displayed results, keeping machine evidence."""
from copy import deepcopy
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.batch_female_nano_presets import BATCH, now, read, sha, write_json_atomic

APPROVALS = ROOT / "app/data/female-nano-user-acceptances.v1.json"
RULE = "user_confirmed_exact_result_v1"


def approval_for(row):
    receipt = read(APPROVALS)
    if receipt.get("rule") != RULE or receipt.get("reviewer") != "user" or not receipt.get("userMessage"):
        raise ValueError("Missing explicit user confirmation")
    matches = [entry for entry in receipt["entries"] if entry["id"] == row["id"]]
    if len(matches) != 1:
        raise ValueError("Result is outside the confirmed set")
    entry = matches[0]
    expected = {key: row[key] for key in ("id", "modelId", "key", "outfitId", "sourceAssetId",
                                         "itemIds", "inputAssetIds", "selectedAttempt")}
    expected.update(modelSha256=row["model"]["sha256"], resultSha256=row["result"]["sha256"])
    if any(entry.get(key) != value for key, value in expected.items()):
        raise ValueError("Confirmation does not match this exact model, outfit or result")
    return entry, {"rule": RULE, "receiptPath": str(APPROVALS.relative_to(ROOT)),
                   "receiptSha256": sha(APPROVALS), "id": entry["id"],
                   "resultSha256": entry["resultSha256"], "reviewer": "user",
                   "confirmedAt": receipt["confirmedAt"]}


def accepted_quality(original, confirmation):
    quality = deepcopy(original)
    if quality["status"] != "pass":
        codes = {issue["code"] for issue in quality["issues"]}
        if codes != {"quality.face_changed"} or quality["evidence"]["protected_region_diff"] > 18:
            raise ValueError("Unconfirmed failure type; automated checks remain enforced")
    quality.update(status="pass", decisionSource="user_confirmation",
                   automatedStatus=original["status"], acceptedIssues=deepcopy(original.get("issues", [])),
                   issues=[], suggestions=[])
    quality["evidence"]["userConfirmation"] = confirmation
    return quality


def validate_user_acceptance(row, report, visual):
    if not report.get("userAcceptance"):
        if row.get("userAcceptance") or visual.get("userAcceptance"):
            raise ValueError("User confirmation report is missing")
        return False
    entry, confirmation = approval_for(row)
    folder = (ROOT / row["selectedAttempt"]).resolve()
    original_path = folder / "quality-report.json"
    if (report["originalReportPath"] != str(original_path.relative_to(ROOT))
            or sha(original_path) != entry["originalReportSha256"]
            or report["originalReportSha256"] != entry["originalReportSha256"]):
        raise ValueError("Original automated report changed")
    original = read(original_path)
    expected = deepcopy(original)
    expected.update(qualityReview=accepted_quality(original["qualityReview"], confirmation),
                    originalAutomatedQualityReview=original["qualityReview"], userAcceptance=confirmation,
                    originalReportPath=str(original_path.relative_to(ROOT)),
                    originalReportSha256=entry["originalReportSha256"])
    if (report != expected or visual.get("userAcceptance") != confirmation
            or visual.get("reviewer") != "user" or row.get("userAcceptance") != confirmation):
        raise ValueError("User acceptance evidence is inconsistent")
    return True


def accept_confirmed_results():
    changed = []
    for entry in read(APPROVALS)["entries"]:
        path = BATCH / entry["modelId"] / entry["key"] / "job.json"
        row = read(path)
        if row["status"] in {"reviewed", "uploaded"}:
            assert validate_user_acceptance(row, read(ROOT / row["qualityReportPath"]), row["visualReview"])
            continue
        assert row["status"] in {"failed_quality", "failed_visual"}
        attempt = row["attempts"][-1]
        assert attempt["path"] == entry["selectedAttempt"]
        backup = path.parent / "job.before-user-acceptance.json"
        if not backup.exists():
            write_json_atomic(backup, row)
        row.update(selectedAttempt=attempt["path"], result=deepcopy(attempt["result"]))
        approval, confirmation = approval_for(row)
        assert sha(ROOT / row["result"]["localPath"]) == approval["resultSha256"]
        folder = ROOT / row["selectedAttempt"]
        original_path = folder / "quality-report.json"
        assert sha(original_path) == approval["originalReportSha256"]
        original = read(original_path)
        report = deepcopy(original)
        report.update(qualityReview=accepted_quality(original["qualityReview"], confirmation),
                      originalAutomatedQualityReview=original["qualityReview"], userAcceptance=confirmation,
                      originalReportPath=str(original_path.relative_to(ROOT)),
                      originalReportSha256=approval["originalReportSha256"])
        visual_path = path.parent / "visual-review.json"
        if visual_path.exists() and not (path.parent / "visual-review.before-user-acceptance.json").exists():
            write_json_atomic(path.parent / "visual-review.before-user-acceptance.json", read(visual_path))
        visual = {"modelId": row["modelId"], "key": row["key"], "resultSha256": approval["resultSha256"],
                  "status": "pass", "verified": True, "reviewer": "user", "reviewedAt": now(),
                  "reviewedItemIds": row["itemIds"], "userAcceptance": confirmation,
                  "observations": "用户查看该结果后明确标记通过。原检查记录保留：" + approval["acceptedObservation"]}
        report_path = folder / "quality-user-acceptance.json"
        row.update(status="reviewed", qualityReview=report["qualityReview"],
                   qualityReportPath=str(report_path.relative_to(ROOT)), userAcceptance=confirmation,
                   visualReview=visual, semanticReview=visual, updatedAt=now())
        assert validate_user_acceptance(row, report, visual)
        write_json_atomic(report_path, report)
        write_json_atomic(visual_path, visual)
        write_json_atomic(path, row)
        changed.append(row["id"])
    return changed


if __name__ == "__main__":
    import json
    print(json.dumps({"accepted": accept_confirmed_results()}, ensure_ascii=False))
