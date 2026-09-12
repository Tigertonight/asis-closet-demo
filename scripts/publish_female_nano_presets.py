"""Publish only reviewed current-source Nano presets to the existing private bucket."""
import argparse
from copy import deepcopy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.material_assets import MaterialRegistry, asset_content_url, asset_id_for_bytes, write_json_atomic
from app.selfit_tryon_presets import _model_matches
from app.styling_catalog import outfit_id
from scripts.batch_female_nano_presets import BATCH, MODEL_DIR, MODEL_IDS, fixed_face, key_for, looks, now, read, sha
from scripts.female_nano_quality import HEADWEAR_FEATURES_RULE, HEADWEAR_RULES, review_worn_hat

INDEX = ROOT / "app/data/tryon-examples.v1.json"


def validate_row(path, current):
    row = deepcopy(read(path))
    assert row["status"] in {"reviewed", "uploaded"}
    look = current[row["key"]]
    assert row["outfitId"] == outfit_id(look)
    assert row["sourceAssetId"] == look["source_asset"]["assetId"]
    assert row["itemIds"] == [i["item_id"] for i in look["items"]]
    assert row["inputAssetIds"] == [i["image_asset"]["assetId"] for i in look["items"]]
    model = ROOT / row["model"]["localPath"]
    assert _model_matches(MODEL_DIR.resolve(), row["modelId"], row["model"], model.read_bytes())
    assert row["strategy"] == "complete_outfit_single_call" and row["generationModel"] == "gemini-3.1-flash-image"
    result = row["result"]
    result_path = (ROOT / result["localPath"]).resolve()
    assert result_path.is_relative_to(path.parent.resolve()) and sha(result_path) == result["sha256"]
    folder = (ROOT / row["selectedAttempt"]).resolve()
    assert folder.is_relative_to(path.parent.resolve()) and result_path.parent == folder
    quality_path = (ROOT / row["qualityReportPath"]).resolve() if row.get("qualityReportPath") else folder / "quality-report.json"
    assert quality_path.parent == folder
    quality = read(quality_path)
    assert quality["resultSha256"] == result["sha256"] and quality["qualityReview"]["status"] == "pass"
    assert row["qualityReview"] == quality["qualityReview"]
    visual = read(path.parent / "visual-review.json")
    assert visual["status"] == "pass" and visual["verified"] is True and visual.get("observations")
    assert visual["resultSha256"] == result["sha256"] and visual["reviewedItemIds"] == row["itemIds"]
    row["visualReview"] = visual
    row["semanticReview"] = visual
    row["qualityReview"]["evidence"]["semantic_review"] = visual
    attempt = read(folder / "attempt.json")
    if attempt["status"] != "generated_local":
        assert attempt["status"] == "failed_quality" and quality.get("recheck", {}).get("rule") in HEADWEAR_RULES
        original_report_path = ROOT / quality["recheck"]["initialReportPath"]
        assert original_report_path.resolve() == folder / "quality-report.json"
        assert sha(original_report_path) == quality["recheck"]["initialReportSha256"]
        initial = read(original_report_path)
        assert initial["resultSha256"] == quality["resultSha256"] and initial["nativeSha256"] == quality["nativeSha256"]
        assert initial.get("originalExpandedQualityReview", initial["qualityReview"]) == quality["originalExpandedQualityReview"]
    face_metric = quality["qualityReview"]["evidence"].get("face_metric")
    if face_metric in HEADWEAR_RULES:
        from PIL import Image
        catalog = read(BATCH / "catalog" / row["key"] / "catalog.json")
        recomputed = review_worn_hat(Image.open(model).convert("RGB"), Image.open(result_path).convert("RGB"),
                                    quality["originalExpandedQualityReview"], catalog["itemContext"],
                                    fixed_face(row["modelId"])["evidence"]["primary_face"]["box"],
                                    allow_forehead_occlusion=face_metric == HEADWEAR_FEATURES_RULE)
        assert recomputed == quality["qualityReview"]
    assert sha(ROOT / attempt["nativePath"]) == attempt["nativeSha256"] == quality["nativeSha256"]
    if attempt.get("reused"):
        request = read(folder / "request-metadata.json")
        receipt = read(folder / "generation-result.json")
        assert request["request_id"] == receipt["request_id"] == attempt["requestId"]
        assert request["inputs"][0]["sha256"] == row["model"]["sha256"]
        references = request["inputs"]
    else:
        request = read(folder / "request.json")
        request_id = request.pop("requestId")
        assert hashlib.sha256(json.dumps(request, sort_keys=True, ensure_ascii=False).encode()).hexdigest() == request_id == attempt["requestId"]
        assert request["model"] == row["generationModel"]
        assert hashlib.sha256((folder / "prompt.txt").read_bytes()).hexdigest() == request["promptSha256"]
        references = request["images"]
    assert all(sha(ref["path"]) == ref["sha256"] for ref in references)
    from PIL import Image
    with Image.open(result_path) as im:
        assert im.format == "PNG" and list(im.size) == [row["model"]["width"], row["model"]["height"]]
        im.verify()
    return row


def ready_rows():
    current = {key_for(x): x for x in looks()}
    return [(p, validate_row(p, current)) for p in sorted(BATCH.glob("female_*/*/job.json"))
            if read(p)["status"] == "reviewed"]


def verify_publication(finalize=False):
    """Audit current published rows and preserve the original male presets."""
    current = {key_for(x): x for x in looks()}
    expected = {mid + "--" + key for mid in MODEL_IDS for key in current}
    assert len(expected) == 288
    baseline = read(BATCH / "baseline-tryon-examples.v1.json")
    with INDEX.with_suffix(INDEX.suffix + ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        index = read(INDEX)
        entries = {r["id"]: r for r in index["examples"]}
        assert len(entries) == len(index["examples"])
        before_male = {r["id"]: r for r in baseline["examples"] if r.get("model", {}).get("gender") == "male"}
        after_male = {r["id"]: r for r in index["examples"] if r.get("model", {}).get("gender") == "male"}
        assert len(before_male) == 16 and before_male == after_male
        assert set(entries) <= expected | set(before_male)
        registry = MaterialRegistry()
        checked = []
        for path in sorted(BATCH.glob("female_*/*/job.json")):
            stored = read(path)
            if stored["status"] != "uploaded":
                continue
            row = validate_row(path, current)
            assert row["id"] in expected
            indexed = entries[row["id"]]
            for field in ("model", "outfitId", "itemIds", "inputAssetIds", "sourceAssetId", "result",
                          "qualityReview", "visualReview", "strategy", "generationModel", "selectedAttempt", "status"):
                assert indexed[field] == row[field], (row["id"], field)
            result = row["result"]
            receipt = read(ROOT / row["selectedAttempt"] / "upload.json")
            assert receipt["verified"] is True and receipt["sha256"] == result["sha256"]
            assert result["contentUrl"] == asset_content_url(result["assetId"])
            record = registry.get(result["assetId"])
            assert record["sha256"] == result["sha256"]
            assert record["storage"]["bucket"] == "selfit"
            assert sha(ROOT / "outputs/material-cache" / (result["assetId"] + ".image")) == result["sha256"]
            checked.append(row["id"])
        published = {r["id"] for r in index["examples"] if r.get("strategy") == "complete_outfit_single_call"
                     and r.get("modelId") in MODEL_IDS}
        assert published == set(checked)
        report = {"verifiedAt": now(), "expected": 288, "uploaded": len(checked),
                  "missing": sorted(expected - set(checked)), "malePreserved": 16,
                  "sourceAndModelAndResultBindingsVerified": True,
                  "status": "complete" if set(checked) == expected else "in_progress"}
        if finalize:
            assert not report["missing"], "Cannot finalize an incomplete batch"
            assert len(entries) == 304 and all(r["status"] == "uploaded" for r in entries.values())
            index.update(status="complete", updatedAt=now(), counts={
                "expected": 304, "records": 304, "outfits": 112, "models": 4,
                "generated": 304, "uploaded": 304, "failed": 0, "failedImages": 0,
                "failedUploaded": 0, "blocked": 0, "pending": 0,
                "totalImages": 304, "totalUploaded": 304, "processed": 304})
            index["femaleOneShotBatch"].update(status="complete", uploaded=288,
                sourceSnapshot=str((BATCH / "source-snapshot.json").relative_to(ROOT)),
                sourceSnapshotSha256=sha(BATCH / "source-snapshot.json"), verifiedAt=now())
            write_json_atomic(INDEX, index)
        write_json_atomic(BATCH / "publication-validation.json", report)
        return {k: v for k, v in report.items() if k != "missing"}


def publish():
    import httpx
    from dotenv import load_dotenv
    from app.material_asset_signing import sign_qiniu_url
    from scripts.qiniu_material_upload import qiniu_client_from_env
    rows = ready_rows()
    if not rows:
        return {"published": 0}
    load_dotenv(ROOT / ".env.qiniu", override=False)
    assert os.environ["QINIU_BUCKET"] == "selfit"
    client = qiniu_client_from_env("selfit")
    assert client.private is True
    base = os.environ["QINIU_PUBLIC_BASE"].rstrip("/")
    registry = MaterialRegistry()
    backup = BATCH / "before-publication"
    backup.mkdir(exist_ok=True)
    for source in [INDEX, registry.path]:
        if not (backup / source.name).exists():
            shutil.copyfile(source, backup / source.name)
    for path, row in rows:
        result = row["result"]
        raw = (ROOT / result["localPath"]).read_bytes()
        aid = asset_id_for_bytes(raw)
        key = f"selfit/tryon-examples/{BATCH.name}/{aid}.png"
        url = base + "/" + key
        receipt_path = (ROOT / row["selectedAttempt"]) / "upload.json"
        receipt = read(receipt_path) if receipt_path.exists() else {}
        if receipt.get("assetId") != aid or receipt.get("verified") is not True:
            client.put_object(Bucket="selfit", Key=key, Body=raw, ContentType="image/png")
            signed, _ = sign_qiniu_url(url, ttl_seconds=3600)
            with httpx.Client(trust_env=False) as http:
                response = http.get(signed, timeout=90, follow_redirects=False)
            if response.status_code != 200 or hashlib.sha256(response.content).hexdigest() != result["sha256"]:
                raise RuntimeError("Private asset readback failed for " + row["id"])
            registry.register(raw, url, "image/png", storage=client.storage_metadata(key), replace_url=False)
            receipt = {"assetId": aid, "contentUrl": asset_content_url(aid), "sha256": result["sha256"],
                       "verified": True, "verifiedAt": now(), "storage": client.storage_metadata(key)}
            write_json_atomic(receipt_path, receipt)
        assert registry.get(aid)["sha256"] == result["sha256"]
        cache = ROOT / "outputs/material-cache" / (aid + ".image")
        if not cache.exists():
            cache.write_bytes(raw)
        row["result"].update(receipt)
        row.update(status="uploaded", updatedAt=now())
        # Keep each index merge and its durable job update under one publisher lock.
        with INDEX.with_suffix(INDEX.suffix + ".lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            index = read(INDEX)
            merged = {r["id"]: r for r in index["examples"]}
            assert len(merged) == len(index["examples"])
            old = merged.get(row["id"])
            if old and old.get("strategy") == "complete_outfit_single_call" and old.get("result", {}).get("sha256") != row["result"]["sha256"]:
                raise ValueError("A different new preset was already published")
            merged[row["id"]] = row
            index["examples"] = list(merged.values())
            current_count = sum(r.get("strategy") == "complete_outfit_single_call" and r.get("status") == "uploaded"
                                and r.get("modelId") in MODEL_IDS for r in merged.values())
            index.update(updatedAt=now(), femaleOneShotBatch={"batchId": BATCH.name, "expected": 288,
                          "uploaded": current_count, "status": "complete" if current_count == 288 else "in_progress",
                          "provider": "vertex_adc_generate_content", "model": "gemini-3.1-flash-image"})
            index["counts"] = {**index.get("counts", {}), "expected": 304, "records": len(merged),
                               "uploaded": sum(r.get("status") == "uploaded" for r in merged.values())}
            write_json_atomic(INDEX, index)
            # Keep numeric review unchanged on the job; semantic review is separate.
            stored = read(path)
            stored.update(status="uploaded", result=row["result"], updatedAt=now())
            write_json_atomic(path, stored)
        print("uploaded " + row["id"], flush=True)
    return {"published": len(rows)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["preflight", "publish", "verify", "finalize"])
    args = parser.parse_args()
    if args.action == "preflight":
        rows = ready_rows()
        result = {"ready": len(rows), "bucket": "selfit", "private": True,
                  "images": [{"id": r["id"], "path": r["result"]["localPath"], "sha256": r["result"]["sha256"]} for _, r in rows]}
        write_json_atomic(BATCH / "publish-preflight.json", result)
        print(json.dumps({"ready": len(rows), "bucket": "selfit", "private": True}))
    elif args.action in {"verify", "finalize"}:
        print(json.dumps(verify_publication(args.action == "finalize")))
    else:
        print(json.dumps(publish()))
