"""Lossless WebP display copies of reviewed female presets; no generation calls."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.material_assets import MaterialRegistry, asset_content_url, write_json_atomic
from scripts.batch_female_nano_presets import BATCH, MODEL_IDS, now, read, sha
from scripts.publish_female_nano_presets import INDEX

WORK = BATCH / "webp-display"


def published_rows():
    return [r for r in read(INDEX)["examples"]
            if r.get("strategy") == "complete_outfit_single_call"
            and r.get("modelId") in MODEL_IDS and r.get("status") == "uploaded"]


def validate_source(row):
    result = row["result"]
    visual = row["visualReview"]
    assert result["verified"] and row["qualityReview"]["status"] == "pass"
    assert visual["verified"] and visual["status"] == "pass"
    assert visual["resultSha256"] == result["sha256"] and visual["reviewedItemIds"] == row["itemIds"]
    source = (ROOT / result["localPath"]).resolve()
    assert source.is_relative_to(BATCH.resolve()) and sha(source) == result["sha256"]
    return source


def verify_pixels(source, target):
    with Image.open(source) as a, Image.open(target) as b:
        assert a.format == "PNG" and b.format == "WEBP" and a.size == b.size
        assert a.convert("RGBA").tobytes() == b.convert("RGBA").tobytes(), "WebP pixels changed"
        return list(a.size)


def convert(source, target):
    """Original dimensions, including exact RGB values beneath transparent pixels."""
    if not target.exists():
        temporary = target.with_suffix(".tmp")
        try:
            with Image.open(source) as im:
                im.save(temporary, "WEBP", lossless=True, quality=100, method=4, exact=True)
            verify_pixels(source, temporary)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
    return verify_pixels(source, target)


def prepare_one(row):
    source = validate_source(row)
    target = WORK / (row["result"]["sha256"] + ".webp")
    dimensions = convert(source, target)
    return {"id": row["id"], "localPath": str(target.relative_to(ROOT)),
            "sourceSha256": row["result"]["sha256"], "sha256": sha(target),
            "contentType": "image/webp", "dimensions": dimensions,
            "bytes": target.stat().st_size, "sourceBytes": source.stat().st_size,
            "pixelIdentical": True, "encoding": "lossless-exact-method4"}


def prepare():
    WORK.mkdir(parents=True, exist_ok=True)
    rows = published_rows()
    snapshot = read(INDEX)
    snapshot_id = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()
    write_json_atomic(WORK / ("before-index-" + snapshot_id[:16] + ".json"), snapshot)
    write_json_atomic(WORK / "before-index.json", snapshot)
    with ThreadPoolExecutor(max_workers=4) as pool:
        entries = list(pool.map(prepare_one, rows))
    report = {"preparedAt": now(), "count": len(entries),
              "sourceBytes": sum(r["sourceBytes"] for r in entries),
              "webpBytes": sum(r["bytes"] for r in entries), "entries": entries}
    write_json_atomic(WORK / "manifest.json", report)
    return {k: v for k, v in report.items() if k != "entries"}


def publish():
    import httpx
    from dotenv import load_dotenv
    from app.material_asset_signing import sign_qiniu_url
    from scripts.qiniu_material_upload import qiniu_client_from_env
    manifest = read(WORK / "manifest.json")
    current = {r["id"]: r for r in published_rows()}
    assert set(current) == {r["id"] for r in manifest["entries"]}, "Re-run prepare for changed presets"
    load_dotenv(ROOT / ".env.qiniu", override=False)
    assert os.environ["QINIU_BUCKET"] == "selfit"
    client = qiniu_client_from_env("selfit")
    assert client.private is True
    registry = MaterialRegistry()
    base = os.environ["QINIU_PUBLIC_BASE"].rstrip("/")
    def publish_one(entry):
        row = current[entry["id"]]
        source = validate_source(row)
        assert entry["sourceSha256"] == row["result"]["sha256"]
        target = ROOT / entry["localPath"]
        assert verify_pixels(source, target) == entry["dimensions"] and sha(target) == entry["sha256"]
        raw = target.read_bytes()
        aid = "asset_" + entry["sha256"]
        key = f"selfit/tryon-examples/{BATCH.name}/webp/{aid}.webp"
        receipt_path = WORK / (entry["sourceSha256"] + ".upload.json")
        receipt = read(receipt_path) if receipt_path.exists() else {}
        if receipt.get("sha256") != entry["sha256"] or receipt.get("verified") is not True:
            client.put_object(Bucket="selfit", Key=key, Body=raw, ContentType="image/webp")
            signed, _ = sign_qiniu_url(base + "/" + key, ttl_seconds=3600)
            with httpx.Client(trust_env=False) as http:
                response = http.get(signed, timeout=90, follow_redirects=False)
            assert response.status_code == 200 and hashlib.sha256(response.content).hexdigest() == entry["sha256"], "WebP readback failed"
            assert response.headers.get("content-type", "").split(";")[0] == "image/webp"
            registry.register(raw, base + "/" + key, "image/webp", storage=client.storage_metadata(key), replace_url=False)
            receipt = {**entry, "assetId": aid, "contentUrl": asset_content_url(aid),
                       "verified": True, "verifiedAt": now(), "storage": client.storage_metadata(key)}
            write_json_atomic(receipt_path, receipt)
        assert registry.get(aid)["sha256"] == entry["sha256"]
        cache = ROOT / "outputs/material-cache" / (aid + ".image")
        if not cache.exists():
            cache.write_bytes(raw)
        assert sha(cache) == entry["sha256"]
        with INDEX.with_suffix(INDEX.suffix + ".lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            index = read(INDEX)
            latest = next(r for r in index["examples"] if r["id"] == row["id"])
            assert latest["result"] == row["result"], "Preset changed during conversion"
            latest["displayResult"] = receipt
            index["updatedAt"] = now()
            write_json_atomic(INDEX, index)
            job_path = BATCH / row["modelId"] / row["key"] / "job.json"
            job = read(job_path)
            assert job["status"] == "uploaded" and job["result"] == row["result"]
            job["displayResult"] = receipt
            write_json_atomic(job_path, job)
        print("webp " + row["id"], flush=True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(publish_one, manifest["entries"]))
    return verify()


def verify():
    from app.selfit_tryon_presets import find_preset
    from app.styling_catalog import adapt_outfit
    from scripts.batch_female_nano_presets import key_for, looks
    baseline = read(WORK / "before-index.json")
    current = read(INDEX)
    before = {r["id"]: r for r in baseline["examples"]}
    assert set(before) == {r["id"] for r in current["examples"]}
    catalog = {key_for(x): x for x in looks()}
    registry = MaterialRegistry()
    checked = []
    for original in current["examples"]:
        row = deepcopy(original)
        display = row.pop("displayResult", None)
        old = deepcopy(before[row["id"]]); old.pop("displayResult", None)
        assert row == old, "Conversion changed generation evidence or unrelated preset"
        if row.get("strategy") != "complete_outfit_single_call" or row.get("modelId") not in MODEL_IDS:
            continue
        assert row["status"] == "uploaded" and display and display["verified"] and display["pixelIdentical"]
        assert display["sourceSha256"] == row["result"]["sha256"]
        assert verify_pixels(validate_source(row), ROOT / display["localPath"]) == display["dimensions"]
        assert sha(ROOT / display["localPath"]) == display["sha256"]
        record = registry.get(display["assetId"])
        assert record["sha256"] == display["sha256"] and record["contentType"] == "image/webp"
        assert record["storage"]["bucket"] == "selfit" and record["storage"]["private"] is True
        assert sha(ROOT / "outputs/material-cache" / (display["assetId"] + ".image")) == display["sha256"]
        assert read(WORK / (display["sourceSha256"] + ".upload.json")) == display
        assert read(BATCH / row["modelId"] / row["key"] / "job.json")["displayResult"] == display
        raw = (ROOT / row["model"]["localPath"]).read_bytes()
        selected = adapt_outfit(catalog[row["key"]])["item_ids"]
        actual = find_preset(row["outfitId"], row["modelId"], raw, selected)
        assert actual and actual["image_path"] == display["contentUrl"]
        for mid, photo, ids in [(row["modelId"], raw + b'changed', selected), ('self', raw, selected), (row["modelId"], raw, selected[:-1])]:
            assert find_preset(row["outfitId"], mid, photo, ids) is None
        checked.append(row["id"])
    report = {"verifiedAt": now(), "webpCount": len(checked), "pixelIdentical": True,
              "originalEvidencePreserved": True, "unrelatedPresetsPreserved": True,
              "actualWebpMatchesAndNegativeChecksPassed": True}
    write_json_atomic(WORK / "verification.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "publish", "verify"])
    args = parser.parse_args()
    WORK.mkdir(parents=True, exist_ok=True)
    with (WORK / "operation.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        print(json.dumps(globals()[args.action](), ensure_ascii=False), flush=True)
