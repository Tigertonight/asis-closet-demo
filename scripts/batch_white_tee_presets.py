"""Resumable built-in image_gen requests for canonical white-tee adaptations.

This script does not call an image model. It freezes inputs, prepares the existing
quality-checked pipeline, imports native tool outputs, and retains provenance.
"""
from copy import deepcopy
from contextlib import contextmanager
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.material_assets import write_json_atomic, MaterialRegistry, material_image_path
from app.white_tee_presets import recipes, recipe_plan
from app.model_assets import load_model_manifest
from scripts import batch_codex_tryon_examples as base
from scripts import batch_male_tryon_presets as male

BATCH = ROOT / "outputs/tryon-examples/white-tee-20260911"
MODEL_IDS = {"male_standard_1"}  # Female generation paused at the user's request.


def read(path):
    return json.loads(Path(path).read_text())


def initialize():
    source = recipes()
    snapshot = BATCH / "recipes.snapshot.json"
    if snapshot.exists() and read(snapshot) != source:
        raise ValueError("Recipe inputs changed; create a new batch")
    write_json_atomic(snapshot, source)
    models = {x.get("id") or Path(x["file"]).stem: x for x in load_model_manifest(base.MODEL_DIR)["items"]}
    for mid in sorted(MODEL_IDS):
        model = models[mid]
        person = material_image_path(model["image_asset_id"]) if model.get("image_asset_id") else base.MODEL_DIR / model["file"]
        sha = base.digest(person)
        if model.get("image_asset_id") and MaterialRegistry().get(model["image_asset_id"])["sha256"] != sha:
            raise ValueError("Model asset mismatch")
        for recipe in source:
            if model["gender"] != recipe["gender"]:
                continue
            folder = BATCH / mid / recipe["key"]
            row = {"id": mid + "--" + recipe["key"], "modelId": mid, "key": recipe["key"],
                   "outfitId": recipe["key"], "recipeFingerprint": recipe["fingerprint"],
                   "gender": recipe["gender"], "pick": recipe["pick"], "noteBinding": recipe["look"]["note_binding"],
                   "itemIds": recipe["outfit"]["item_ids"], "model": {**model, "localPath": str(person.relative_to(ROOT)), "sha256": sha},
                   "provider": base.CodexEffectProvider.mode, "strategy": "white_tee_complete_outfit",
                   "status": "queued", "artifactDir": str(folder.relative_to(ROOT)), "createdAt": base.now()}
            path = folder / "job.json"
            if path.exists():
                old = read(path)
                if any(old[k] != row[k] for k in ("recipeFingerprint", "itemIds", "model")):
                    raise ValueError("Changed input on resume")
            else:
                write_json_atomic(path, row)
    return status()


def status():
    rows = [read(p) for p in BATCH.glob("*/*/job.json")]
    active = [r for r in rows if r["modelId"] in MODEL_IDS]
    return {"total": len(active), "paused": len(rows) - len(active),
            "states": {s: sum(r["status"] == s for r in active) for s in sorted({r["status"] for r in active})}}


def selected(mid, key):
    path = BATCH / mid / key / "job.json"
    if path.resolve().parent.parent.parent != BATCH.resolve():
        raise ValueError("Invalid example path")
    return path, read(path)


@contextmanager
def prepared(row):
    if base.digest(ROOT / row["model"]["localPath"]) != row["model"]["sha256"]:
        raise ValueError("Model changed; start a new batch")
    recipe = next(r for r in read(BATCH / "recipes.snapshot.json") if r["key"] == row["key"])
    plan, outfit = recipe_plan(recipe)
    original_edit = base.CodexEffectProvider.edit
    def edit(provider, person_image, garment_image, mask_image, prompt, output_dir):
        # The male helper already includes its retry instruction.
        note = row.get("stagePromptNotes", {}).get(output_dir.name) if row["gender"] == "female" else None
        if note:
            prompt += "\nOperator retry correction: " + note
        return original_edit(provider, person_image, garment_image, mask_image, prompt, output_dir)
    # The offline preset is generated as a whole outfit in one edit. This keeps
    # the white tee, outer layers, and all accessories in the same reference board.
    # Person detection and geometric/semantic review gates remain unchanged.
    with patch.object(base, "delivered_tryon_plan", return_value=(plan, outfit)), \
            patch.object(base.tryon, "_outfit_generation_groups", side_effect=lambda p: [("white_tee_complete_outfit", p)]), \
            patch.object(base.CodexEffectProvider, "edit", edit):
        yield


def advance(path, row):
    with prepared(row), male.fixed_model_face(row):
        return base.advance(path, row)


def ingest(path, row, source):
    with prepared(row):
        return male.ingest_native(path, row, Path(row["requestPath"]).parent.name, source)


def review(path, row, observations):
    if row["status"] != "generated_local" or not observations.strip():
        raise ValueError("Review requires an actual completed image and observations")
    write_json_atomic(path.parent / "visual-review.json", {
        "status": "pass", "verified": True, "reviewer": "codex_visual_inspection",
        "resultSha256": row["result"]["sha256"], "reviewedItemIds": row["itemIds"],
        "observations": observations, "reviewedAt": base.now()})


def retry(path, row, correction):
    if row["status"] == "uploaded":
        raise ValueError("Published examples must use a new version")
    archive = path.parent / "attempts" / base.now().replace(":", "-")
    archive.mkdir(parents=True)
    shutil.copyfile(path, archive / "job.json")
    if row.get("workDir") and (ROOT / row["workDir"]).exists():
        shutil.move(str(ROOT / row["workDir"]), archive / "pipeline")
    for name in ("result.png", "pipeline-result.json", "visual-review.json"):
        if (path.parent / name).exists():
            shutil.move(path.parent / name, archive / name)
    row.pop("result", None)
    row["stagePromptNotes"] = {"stage_1_white_tee_complete_outfit": correction}
    return advance(path, row)


def validate_row(path, row, current):
    from app.selfit_tryon_presets import _model_matches
    from PIL import Image
    recipe = current[row["key"]]
    if row["recipeFingerprint"] != recipe["fingerprint"] or row["itemIds"] != recipe["outfit"]["item_ids"]:
        raise ValueError("Recipe changed: " + row["id"])
    if not _model_matches(base.MODEL_DIR.resolve(), row["modelId"], row["model"], (ROOT / row["model"]["localPath"]).read_bytes()):
        raise ValueError("Model changed")
    if row["status"] not in {"generated_local", "uploaded"} or row["imageEdit"]["status"] != "pass" or row["qualityReview"]["status"] == "fail":
        raise ValueError("Image did not pass geometry")
    result = row["result"]
    final = ROOT / result["localPath"]
    if final.resolve().parent != path.resolve().parent or base.digest(final) != result["sha256"]:
        raise ValueError("Final image changed")
    with Image.open(final) as image:
        if list(image.size) != result["dimensions"] or image.size != (row["model"]["width"], row["model"]["height"]):
            raise ValueError("Wrong canvas")
        image.verify()
    stages = sorted((ROOT / row["workDir"]).glob("stage_*/codex_request.json"))
    if len(stages) != 1 or stages[0].parent.name != "stage_1_white_tee_complete_outfit":
        raise ValueError("Wrong generation strategy")
    q = read(stages[0]); receipt = read(stages[0].with_name("codex_result.receipt.json"))
    if receipt["requestId"] != q["requestId"] or receipt["tool"] != "image_gen" or receipt["sha256"] != result["sha256"] or receipt["sourceSha256"] != base.digest(ROOT / receipt["nativePath"]):
        raise ValueError("Unverified native tool provenance")
    visual = read(path.parent / "visual-review.json")
    if visual.get("status") != "pass" or visual.get("verified") is not True or visual.get("resultSha256") != result["sha256"] or visual.get("reviewedItemIds") != row["itemIds"] or not visual.get("observations"):
        raise ValueError("No matching visual review")
    quality = deepcopy(row["qualityReview"])
    quality["issues"] = [i for i in quality["issues"] if i["code"] != "semantic.manual_review_required"]
    if quality["issues"]:
        raise ValueError("Unresolved quality issue")
    quality.update(status="pass", suggestions=[])
    quality["evidence"]["semantic_review"] = visual
    return {**deepcopy(row), "qualityReview": quality, "visualReview": visual,
            "generationStages": [{"requestPath": str(stages[0].relative_to(ROOT)), **receipt}]}


def publish():
    import fcntl
    import httpx
    from dotenv import load_dotenv
    from app.white_tee_presets import INDEX
    from app.material_assets import asset_id_for_bytes, asset_content_url, material_download_url
    from scripts.qiniu_material_upload import qiniu_client_from_env
    current = {r["key"]: r for r in recipes()}
    ready = []
    for path in sorted(BATCH.glob("*/*/job.json")):
        row = read(path)
        if row["modelId"] not in MODEL_IDS:
            continue
        if row["status"] in {"generated_local", "uploaded"} and (path.parent / "visual-review.json").exists():
            ready.append((path, validate_row(path, row, current)))
    if not ready:
        raise ValueError("No reviewed images to publish")
    load_dotenv(ROOT / ".env.qiniu", override=False)
    client = qiniu_client_from_env(os.environ["QINIU_BUCKET"]); registry = MaterialRegistry()
    published = []
    for path, row in ready:
        result = row["result"]; source = ROOT / result["localPath"]; raw = source.read_bytes()
        aid = asset_id_for_bytes(raw); receipt_path = path.parent / "upload.json"
        receipt = read(receipt_path) if receipt_path.exists() else {}
        if receipt.get("assetId") != aid or receipt.get("verified") is not True:
            key = "selfit/tryon-examples/" + BATCH.name + "/" + aid + ".png"
            url = os.environ["QINIU_PUBLIC_BASE"].rstrip("/") + "/" + key
            client.put_object(Bucket=client.bucket, Key=key, Body=raw, ContentType="image/png")
            registry.register(raw, url, "image/png", storage=client.storage_metadata(key))
            response = httpx.get(material_download_url(registry.get(aid)), timeout=60, follow_redirects=False)
            if response.status_code != 200 or hashlib.sha256(response.content).hexdigest() != result["sha256"]:
                raise RuntimeError("Uploaded bytes differ")
            cache = ROOT / "outputs/material-cache" / (aid + ".image"); cache.parent.mkdir(parents=True, exist_ok=True); cache.write_bytes(raw)
            receipt = {"assetId": aid, "contentUrl": asset_content_url(aid), "sha256": result["sha256"], "verified": True, "verifiedAt": base.now()}
            write_json_atomic(receipt_path, receipt)
        elif registry.get(aid)["sha256"] != result["sha256"]:
            raise ValueError("Registered image changed")
        row["result"].update(receipt); row["status"] = "uploaded"
        write_json_atomic(path, row); published.append(row)
        print("verified " + row["id"], flush=True)
    with (BATCH / "publish.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        index = read(INDEX) if INDEX.exists() else {"schemaVersion": 1, "kind": "white_tee_adaptation", "examples": []}
        merged = {r["id"]: r for r in index["examples"]}
        for row in published:
            if row["id"] in merged and merged[row["id"]]["result"]["sha256"] != row["result"]["sha256"]:
                raise ValueError("Existing preset differs; publish a new version")
            merged[row["id"]] = row
        models = {r["modelId"]: r["gender"] for r in merged.values()}
        models.update({read(p)["modelId"]: read(p)["gender"] for p in BATCH.glob("*/*/job.json") if read(p)["modelId"] in MODEL_IDS})
        expected_by_gender = {gender: sum(r["gender"] == gender for r in current.values()) * sum(g == gender for g in models.values()) for gender in ("female", "male")}
        uploaded_by_gender = {gender: sum(r["gender"] == gender for r in merged.values()) for gender in ("female", "male")}
        expected = sum(expected_by_gender.values())
        index.update(examples=list(merged.values()), counts={"expected": expected, "uploaded": len(merged)},
                     activeModelIds=sorted(models), countsByGender={g: {"expected": expected_by_gender[g], "uploaded": uploaded_by_gender[g]} for g in expected_by_gender},
                     femaleStatus=("complete" if uploaded_by_gender["female"] == expected_by_gender["female"] else "in_progress") if expected_by_gender["female"] else "paused_by_user",
                     status="complete" if len(merged) == expected else "in_progress", updatedAt=base.now())
        write_json_atomic(INDEX, index)
    return index["counts"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["init", "status", "advance", "ingest", "publish"])
    parser.add_argument("--model")
    parser.add_argument("--key")
    parser.add_argument("--result", type=Path)
    args = parser.parse_args()
    if args.action == "init":
        result = initialize()
    elif args.action == "status":
        result = status()
    elif args.action == "publish":
        result = publish()
    else:
        path, row = selected(args.model, args.key)
        result = advance(path, row) if args.action == "advance" else ingest(path, row, args.result)
        result = {k: result[k] for k in ("id", "status", "requestPath", "qualityReview", "result") if k in result}
    print(json.dumps(result, ensure_ascii=False))
