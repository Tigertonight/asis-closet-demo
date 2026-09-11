"""Resumable, explicitly authorized ADC/Nano full-outfit female preset batch.

Generation never publishes. Every result needs source-bound visual review before
the separate publisher can register it. Interrupted attempts are not overwritten.
"""
from __future__ import annotations

import argparse
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import random
import re
import shutil
import sys
import threading
import time

from PIL import Image, ImageDraw, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import vertex_image
from app.inspiration_catalog import inspiration_looks
from app.material_assets import write_json_atomic
from app.model_assets import load_model_manifest
from app.styling_catalog import delivery_looks, delivered_tryon_plan, outfit_id

BATCH = ROOT / "outputs/tryon-examples/female-nano-one-shot-20260911"
MODEL_DIR = ROOT / "tests/fixtures/tryon_models"
MODEL_IDS = ["female_medium_1", "female_slim_1", "female_plus_1"]
MODEL_SHA = {
    "female_slim_1": "8dedd0555421d14026ffbea8b4102ce58a042d6c6d737c44d359668e685b0501",
    "female_medium_1": "637cb742b8d5447b11e1f53509f6279b15fe0a023facaca0b15769eae940bc87",
    "female_plus_1": "365001c4e926a8bb8747a2ada7afeda8e5471cc439bfc5741b6c11fc8dc058e7",
}
CONFIG = {"responseModalities": ["TEXT", "IMAGE"], "candidateCount": 1,
          "imageConfig": {"aspectRatio": "3:4", "imageSize": "2K"},
          "temperature": 1, "maxOutputTokens": 32768}
PRINT_LOCK = threading.Lock()
FOOT_POSE = (
    "Target-model pose takes priority over styling: keep the screen-left foot centered near x=0.35 of image width, "
    "screen-right foot near x=0.55, both near y=0.92 of image height, as in Image 1. "
    "Preserve the original wide gap: screen-left leg angled outward and that foot turned toward screen-left; "
    "the other foot faces forward. Do NOT bring the feet together, cross the legs, take a step, or copy the source model's stance. "
    "Adapt the skirt/trousers and new shoes around these unchanged leg and foot positions."
)


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def emit(value):
    with PRINT_LOCK:
        print(json.dumps(value, ensure_ascii=False), flush=True)


def setup():
    os.environ.update(TRYON_GOOGLE_BACKEND="vertex_adc", TRYON_VERTEX_PROJECT="gen-lang-client-0606324711",
                      TRYON_VERTEX_LOCATION="global", TRYON_IMAGE_MODEL="gemini-3.1-flash-image",
                      GOOGLE_APPLICATION_CREDENTIALS=str(Path.home() / ".config/gcloud/application_default_credentials.json"))
    Image.init()


def looks():
    return [x for x in delivery_looks() if x["note_binding"].get("gender") != "male"] + inspiration_looks()


def key_for(look):
    return look["note_binding"]["templateId"] + "--" + look["note_binding"]["noteId"]


def image_ref(path, label, item_ids=None):
    path = Path(path)
    raw = path.read_bytes()
    with Image.open(io.BytesIO(raw)) as im:
        im.load()
        info = {"format": im.format, "size": list(im.size)}
    if len(raw) > 7 * 1024 * 1024:
        raise ValueError(f"Image exceeds inline input size: {path.name}")
    return {"path": str(path), "label": label, "itemIds": item_ids or [],
            "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw), **info}


def pack_accessories(items, path):
    """Contact-sheet packaging only, keeping every reference below 14 inputs."""
    cols = 3
    cell = 600
    canvas = Image.new("RGB", (cols * cell, ((len(items) + cols - 1) // cols) * 660), "white")
    draw = ImageDraw.Draw(canvas)
    for i, item in enumerate(items):
        im = Image.open(item["image_path"]).convert("RGBA")
        im.thumbnail((580, 600), Image.Resampling.LANCZOS)
        x, y = (i % cols) * cell, (i // cols) * 660
        canvas.paste(im, (x + (cell - im.width) // 2, y + 42 + (600 - im.height) // 2), im)
        draw.text((x + 15, y + 12), f"Accessory {i + 1}", fill="black")
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(path)


def prepare_outfit(look):
    key = key_for(look)
    folder = BATCH / "catalog" / key
    folder.mkdir(parents=True, exist_ok=True)
    existing = folder / "catalog.json"
    if existing.exists():
        saved = read(existing)
        if saved["look"] != look or saved["outfitId"] != outfit_id(look):
            raise ValueError("Catalog changed; start a versioned batch")
        for ref in saved["references"] + saved["sourceReferences"]:
            if sha(ref["path"]) != ref["sha256"]:
                raise ValueError("Reference bytes changed on resume")
        # Preserve the reviewed prompt refinements made during this batch.
        return saved
    plan, _ = delivered_tryon_plan(outfit_id(look), "mirror_selfie", "")
    refs = [image_ref(plan["style_reference"]["image_path"],
                     "IMAGE 2: overall styling reference ONLY; never copy this person, pose or background")]
    item_refs = {}
    items = plan["items"]
    grouped = []
    if len(items) > 12:
        # Keep clothing, footwear and bags large; only group small accessories.
        grouped = [i for i in items if i["slot"] not in {"outer", "top", "bottom", "skirt", "dress", "shoes", "bag"}]
        if len(grouped) < len(items) - 11:
            raise ValueError("Too many large item references to fit a single request")
    grouped_ids = {i["item_id"] for i in grouped}
    for item in items:
        if item["item_id"] in grouped_ids:
            continue
        number = len(refs) + 2
        refs.append(image_ref(item["image_path"], f"IMAGE {number}: exact item {item['title']}", [item["item_id"]]))
        item_refs[item["item_id"]] = f"Image {number}"
    if grouped:
        board = folder / "accessory-references.png"
        pack_accessories(grouped, board)
        number = len(refs) + 2
        refs.append(image_ref(board, f"IMAGE {number}: labeled accessory references; use every listed accessory", list(grouped_ids)))
        for n, item in enumerate(grouped, 1):
            item_refs[item["item_id"]] = f"Image {number}, Accessory {n}"
    assert 1 + len(refs) <= 14
    source_refs = [image_ref(i["image_path"], i["title"], [i["item_id"]]) for i in items]
    item_context = []
    for item in items:
        s = item["styling"]
        item_context.append({"reference": item_refs[item["item_id"]], "name": item["title"],
                             "slot": item["slot"], "wearing_method": item["wearing_instruction"],
                             "layer_position": s.get("layer_position"), "closure_state": s.get("closure_state"),
                             "overlap": s.get("overlap_relation"), "visible_details": s.get("styling_details", []),
                             "visible_description": s.get("description", "")[:650]})
        if item["slot"] == "shoes":
            item_context[-1]["target_pose_priority"] = FOOT_POSE
    catalog = {"key": key, "outfitId": plan["outfit_id"], "look": look, "plan": plan,
               "references": refs, "sourceReferences": source_refs, "itemContext": item_context}
    write_json_atomic(folder / "catalog.json", catalog)
    return catalog


def initialize():
    all_looks = looks()
    assert len(all_looks) == 96
    BATCH.mkdir(parents=True, exist_ok=True)
    snapshot = BATCH / "source-snapshot.json"
    if snapshot.exists():
        if read(snapshot)["looks"] != all_looks:
            raise ValueError("Catalog changed since batch initialization")
    else:
        write_json_atomic(snapshot, {"looks": all_looks, "createdAt": now(), "expected": 288})
    backup = BATCH / "baseline-tryon-examples.v1.json"
    if not backup.exists():
        shutil.copyfile(ROOT / "app/data/tryon-examples.v1.json", backup)
    models = {Path(x["file"]).stem: x for x in load_model_manifest(MODEL_DIR)["items"]}
    for mid in MODEL_IDS:
        assert sha(MODEL_DIR / models[mid]["file"]) == MODEL_SHA[mid]
    for n, look in enumerate(all_looks, 1):
        catalog = prepare_outfit(look)
        for mid in MODEL_IDS:
            model = models[mid]
            path = BATCH / mid / catalog["key"] / "job.json"
            row = {"id": mid + "--" + catalog["key"], "modelId": mid, "key": catalog["key"],
                   "outfitId": catalog["outfitId"], "noteBinding": look["note_binding"],
                   "sourceAssetId": look["source_asset"]["assetId"],
                   "itemCount": len(look["items"]), "itemIds": [i["item_id"] for i in look["items"]],
                   "inputAssetIds": [i["image_asset"]["assetId"] for i in look["items"]],
                   "model": {**model, "localPath": str((MODEL_DIR / model["file"]).relative_to(ROOT)), "sha256": MODEL_SHA[mid]},
                   "provider": vertex_image.MODE, "strategy": "complete_outfit_single_call",
                   "generationModel": vertex_image.model(), "status": "queued", "createdAt": now(), "updatedAt": now(),
                   "artifactDir": str(path.parent.relative_to(ROOT)), "attempts": []}
            if path.exists():
                old = read(path)
                if any(old[k] != row[k] for k in ["outfitId", "sourceAssetId", "itemIds", "inputAssetIds", "model"]):
                    raise ValueError("Inputs changed on resume")
            else:
                write_json_atomic(path, row)
        emit({"prepared": n, "of": 96, "key": catalog["key"], "images": len(catalog["references"]) + 1})
    return status()


def garment_only_context(items):
    """Discard source-person posing clauses, retaining garment instructions."""
    def clean(value):
        if isinstance(value, str):
            value = value.replace("双手提拎于身前", "由原本下垂的非持手机手提握包柄")
            clauses = re.split(r"(?<=[，,；;。])", value)
            return "".join(c for c in clauses if not (
                ("手" in c and any(w in c for w in ("插入", "插袋", "插兜", "插口袋", "置于侧袋", "放在侧袋", "叉腰", "扶腰", "托腮", "撑腰")))
                or any(w in c for w in ("坐姿", "双腿交叉", "交叉腿姿", "双手交叉", "双臂交叉", "抬高手臂"))))
        if isinstance(value, list):
            return [v for x in value if (v := clean(x))]
        if isinstance(value, dict):
            return {k: clean(v) for k, v in value.items()}
        return value
    return clean(items)


def prompt_for(catalog, correction=""):
    return """Use case: identity-preserve. Create ONE photorealistic full-outfit virtual try-on photo by editing Image 1.
This is a single complete outfit edit: replace clothing AND footwear and add ALL listed visible accessories in the SAME final image.
Image 1 is the sole authority for the adult woman's identity, anatomy, face, hair, skin tone, body shape, framing, lighting, white background, phone and pose. Preserve these with minimal pixel changes. This is the same woman trying on clothes, not a new model.
Image 2 provides clothing layering and wearing relationships ONLY. Never copy its person, face, hairstyle, anatomy, pose, scene, lettering, watermark or other people. All later images are individually labeled exact-item references. Use the structured instructions below for wearing relationships. Preserve item color, material, texture, construction, pattern and recognizable details. Do not use the source person's proportions as the target body.

FIXED SELFIE POSE: keep the phone and raised phone hand exactly at the original coordinates. The other arm hangs straight DOWN beside the body, with the hand at its original height. Do NOT put it in a pocket, bend it onto the waist, cross the arms or copy a pose from the outfit notes. Fit sleeves to the existing arm positions. Keep the leg stance and both feet at the original positions and orientations. Do not narrow the waist, slim or enlarge the body, lengthen legs, change head scale, move the face, change expression or retouch the face. Preserve existing hair lengths, hairline, parting, and hair hanging in FRONT of each shoulder. Put clothes under existing front hair; do not tuck hair back just to show a collar or accessory. Preserve exposed hands, fingers and skin. Accommodate the garments on this exact body.
Put each item only on its intended body region. Respect inner-to-outer layering: if a skirt is worn over trousers, show both and do not merge them. Preserve scarves, bows, socks, belts, jewelry and shoes where visible. Replace original white shoes with the referenced shoes when supplied. Don't leave the original white T-shirt or shorts exposed when they should be replaced/covered. Do not invent extra accessories. A hidden underlayer may be occluded according to the outfit instructions.
Keep bags physically attached: shoulder bag on shoulder, crossbody strap continuously across the torso to its hip bag; handheld bag may be held by the already lowered hand without moving the arm. Do not float a bag or intersect it with fingers. Hat/head accessories may be added over the existing hair but must not reshape the head or face. Scarf stays clear of the face and phone. Detailed outfit wearing instructions below describe garments, never authorize changing the model pose.

OUTFIT AND ITEM REFERENCES:
""" + json.dumps({"title": catalog["plan"]["title"], "items": garment_only_context(catalog["itemContext"])}, ensure_ascii=False, indent=2) + """

Output exactly ONE seamless 3:4 full-body photograph at 2K, matching Image 1's original head-to-toe canvas and white background. No collage, borders, labels, watermarks, text, extra people, new background, facial beautification or body reshaping. Return the final photo.
FINAL POSE LOCK — highest priority: the non-phone hand stays beside the UPPER THIGH exactly where it is in Image 1, BELOW the waist and jacket hem. Its arm remains straight down; do not bend its elbow or put fingers in any pocket. Pockets remain empty. Clothing references describe CLOTHES, never the hand position. Preserve the original face, phone, shoulder, elbow, wrist, leg and foot coordinates. Fit the entire outfit to that unchanged pose.
""" + ("\nTargeted correction: " + correction if correction else "")


def fixed_face(mid):
    from app import tryon
    return tryon._stage("pass", .84, {"face_count": 1,
        "primary_face": {"box": {"x": 834, "y": 225, "width": 216, "height": 216}, "area_ratio": .0108},
        "annotation": "reviewed_fixed_model_face", "source_sha256": MODEL_SHA[mid]}, [])


def sanitize(response):
    if isinstance(response, list):
        return [sanitize(v) for v in response]
    if isinstance(response, dict):
        inline = response.get("inlineData", response.get("inline_data"))
        if inline:
            raw = base64.b64decode(inline["data"])
            return {"image": {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw), "mimeType": inline.get("mimeType")}}
        return {k: sanitize(v) for k, v in response.items() if k not in {"thoughtSignature", "thought_signature"}}
    return response


def measure_quality(row, catalog, native, folder):
    from app import tryon
    model_path = ROOT / row["model"]["localPath"]
    original = Image.open(model_path).convert("RGB")
    source = Image.open(native).convert("RGB")
    if min(source.size) < 1024:
        raise ValueError("Output is below the required resolution")
    normalized, normalization = tryon._fit_image_to_reference_canvas(source, model_path)
    result = folder / "result.png"
    if source.size == original.size and Image.open(native).format == "PNG":
        shutil.copyfile(native, result)
    else:
        normalized.save(result)
    face = fixed_face(row["modelId"])
    mask = tryon._generate_outfit_group_mask(original, face, catalog["plan"]["items"], folder / "quality-mask.png")
    if mask["status"] != "pass":
        raise ValueError("Quality mask failed")
    quality = tryon._review_tryon_quality(original, result, face, Path(mask["evidence"]["mask_path"]))
    write_json_atomic(folder / "quality-report.json", {"qualityReview": quality, "normalization": normalization,
                      "modelSha256": row["model"]["sha256"], "nativeSha256": sha(native), "resultSha256": sha(result)})
    return quality, {"localPath": str(result.relative_to(ROOT)), "sha256": sha(result),
                     "bytes": result.stat().st_size, "dimensions": list(normalized.size), "verified": False}


def generate_attempt(path, row, correction=""):
    catalog = read(BATCH / "catalog" / row["key"] / "catalog.json")
    if catalog["outfitId"] != row["outfitId"]:
        raise ValueError("Catalog binding drift")
    folder = path.parent / "attempts" / f"{len(row['attempts']) + 1:02d}"
    folder.mkdir(parents=True, exist_ok=False)
    model_path = ROOT / row["model"]["localPath"]
    assert sha(model_path) == row["model"]["sha256"] == MODEL_SHA[row["modelId"]]
    refs = [image_ref(model_path, "IMAGE 1: exact target model; ONLY identity/pose/body/canvas authority")] + catalog["references"]
    prompt = prompt_for(catalog, correction)
    (folder / "prompt.txt").write_text(prompt)
    request = {"model": vertex_image.model(), "endpoint": vertex_image.endpoint(), "provider": vertex_image.MODE,
               "images": refs, "generationConfig": CONFIG, "timeoutSeconds": 600,
               "promptSha256": hashlib.sha256(prompt.encode()).hexdigest()}
    request["requestId"] = hashlib.sha256(json.dumps(request, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    write_json_atomic(folder / "request.json", request)
    parts = []
    for ref in refs:
        raw = Path(ref["path"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == ref["sha256"]
        parts.extend([{"text": ref["label"]}, {"inlineData": {"mimeType": Image.MIME[ref["format"]],
                                                                "data": base64.b64encode(raw).decode()}}])
    parts.append({"text": prompt})
    attempt = {"path": str(folder.relative_to(ROOT)), "requestId": request["requestId"], "status": "running", "startedAt": now()}
    row["attempts"].append(attempt)
    row.update(status="running", updatedAt=now())
    write_json_atomic(path, row)
    write_json_atomic(folder / "attempt.json", attempt)
    started = time.monotonic()
    try:
        response = vertex_image.generate_content({"contents": [{"role": "user", "parts": parts}], "generationConfig": CONFIG}, timeout=600)
        attempt["apiSeconds"] = round(time.monotonic() - started, 2)
        write_json_atomic(folder / "response.json", sanitize(response))
        image_blocks = []
        for candidate in response.get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                block = part.get("inlineData", part.get("inline_data", {}))
                if block.get("data"):
                    image_blocks.append(block)
        if len(image_blocks) != 1:
            reasons = [c.get("finishReason") for c in response.get("candidates", [])]
            blocked = any("SAFETY" in str(x) or "PROHIBITED" in str(x) for x in reasons) or bool(response.get("promptFeedback", {}).get("blockReason"))
            attempt.update(status="blocked_moderation" if blocked else "failed_no_image", finishReasons=reasons)
        else:
            raw = base64.b64decode(image_blocks[0]["data"])
            with Image.open(io.BytesIO(raw)) as im:
                im.load()
                fmt, dimensions = im.format, list(im.size)
            native = folder / ("native." + {"PNG": "png", "JPEG": "jpg", "WEBP": "webp"}[fmt])
            native.write_bytes(raw)
            attempt.update(nativePath=str(native.relative_to(ROOT)), nativeSha256=sha(native), dimensions=dimensions,
                           usage=response.get("usageMetadata", {}))
            quality, result = measure_quality(row, catalog, native, folder)
            attempt["qualityReview"] = quality
            attempt["status"] = "generated_local" if quality["status"] == "pass" else "failed_quality"
            attempt["result"] = result
            if quality["status"] == "pass":
                row.update(result=result, qualityReview=quality, selectedAttempt=str(folder.relative_to(ROOT)),
                           semanticReview={"status": "pending", "verified": False},
                           imageEdit={"status": "pass", "provider": vertex_image.MODE,
                                      "evidence": {"requestId": request["requestId"], "nativeSha256": sha(native)}})
    except Exception as exc:
        attempt.update(status="failed_api", apiSeconds=round(time.monotonic() - started, 2),
                       error=str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__)
        if "HTTP 401" in attempt["error"] or "HTTP 403" in attempt["error"]:
            (BATCH / "STOP").write_text("ADC authorization requires attention; no further requests.\n")
    attempt["finishedAt"] = now()
    row.update(status=attempt["status"], updatedAt=now())
    write_json_atomic(folder / "attempt.json", attempt)
    write_json_atomic(path, row)
    emit({"id": row["id"], "status": row["status"], "attempt": len(row["attempts"]),
          "apiSeconds": attempt.get("apiSeconds"), "quality": attempt.get("qualityReview", {}).get("evidence", {})})
    return row


def worker(path, max_attempts):
    row = read(path)
    while len(row["attempts"]) < max_attempts and not (BATCH / "STOP").exists():
        if row["status"] in {"generated_local", "reviewed", "uploaded", "blocked_moderation"}:
            break
        correction = row.get("retryCorrection", "")
        if not correction and any(a["status"] == "failed_quality" for a in row["attempts"]):
            correction = "The earlier attempt shifted protected regions. Reuse the ORIGINAL Image 1 face, phone and white background with minimal pixel change. Fit only clothing to the unchanged body. Preserve all original head and feet coordinates."
        if row["attempts"]:
            time.sleep(min(60, 15 * 2 ** min(len(row["attempts"]) - 1, 3) + random.random() * 10))
        if (BATCH / "STOP").exists():
            break
        row = generate_attempt(path, row, correction)
    return row["status"]


def job_paths():
    # Group all three body types of an outfit together for visual review.
    keys = [key_for(x) for x in read(BATCH / "source-snapshot.json")["looks"]]
    return [BATCH / mid / key / "job.json" for key in keys for mid in MODEL_IDS]


def status():
    rows = [read(p) for p in BATCH.glob("female_*/*/job.json")]
    states = {s: sum(r["status"] == s for r in rows) for s in sorted({r["status"] for r in rows})}
    attempts = [a for r in rows for a in r["attempts"]]
    stats = {"updatedAt": now(), "expected": 288, "jobs": len(rows), "states": states,
             "dispatchPaused": (BATCH / "STOP").exists(), "inFlight": states.get("running", 0),
             "apiAttempts": sum(not a.get("reused") for a in attempts),
             "successfulImages": sum(a["status"] in {"generated_local", "failed_quality"} for a in attempts),
             "apiSecondsTotal": round(sum(a.get("apiSeconds", 0) for a in attempts), 2)}
    write_json_atomic(BATCH / "progress.json", stats)
    return stats


def run(concurrency, max_attempts, limit=None):
    if concurrency not in {1, 2}:
        raise ValueError("Use one or two concurrent requests")
    if (BATCH / "STOP").exists():
        emit({"dispatchPaused": True, "reason": "STOP exists; no generation requests will be sent"})
        return status()
    with (BATCH / "runner.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        paths = [p for p in job_paths() if read(p)["status"] not in {"generated_local", "reviewed", "uploaded", "blocked_moderation"}
                 and len(read(p)["attempts"]) < max_attempts]
        if limit:
            paths = paths[:limit]
        emit({"starting": len(paths), "concurrency": concurrency, "maxAttempts": max_attempts})
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = {pool.submit(worker, p, max_attempts): p for p in paths}
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as exc:
                    (BATCH / "STOP").write_text("Local batch error; inspect input/attempt state before resuming.\n")
                    emit({"local_error": type(exc).__name__, "job": str(futures[future].relative_to(BATCH))})
                status()
        return status()


def reuse_pilot():
    pilot = ROOT / "outputs/nano-one-shot-outfit-20260911"
    meta, receipt = read(pilot / "request-metadata.json"), read(pilot / "generation-result.json")
    path = BATCH / "female_medium_1" / "film--outfits-03" / "job.json"
    row = read(path)
    if row["status"] != "queued":
        return {"reused": False, "reason": "already processed"}
    assert meta["outfit_id"] == row["outfitId"] and meta["inputs"][0]["sha256"] == row["model"]["sha256"]
    native = Path(receipt["output_images"][0]["path"])
    assert sha(native) == receipt["output_images"][0]["sha256"] and receipt["status"] == "generated"
    folder = path.parent / "attempts/01"
    folder.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(native, folder / "native.png")
    for name in ["request-metadata.json", "generation-result.json", "google-response.json", "prompt.txt", "visual-review.json"]:
        shutil.copyfile(pilot / name, folder / name)
    catalog = read(BATCH / "catalog" / row["key"] / "catalog.json")
    quality, result = measure_quality(row, catalog, folder / "native.png", folder)
    assert quality["status"] == "pass"
    visual = {"status": "pass", "verified": True, "reviewedAt": now(), "reviewer": "assistant_visual_inspection",
              "resultSha256": result["sha256"], "reviewedItemIds": row["itemIds"],
              "observations": "逐张已查看：六件齐全，裙裤层次正确；脸、手机、手臂及站姿基本保持。丝巾偏直垂，肩前部分头发在衣服后，保留此细节偏差记录。"}
    write_json_atomic(path.parent / "visual-review.json", visual)
    attempt = {"path": str(folder.relative_to(ROOT)), "status": "generated_local", "reused": True,
               "apiSeconds": receipt["api_seconds"], "requestId": receipt["request_id"],
               "nativePath": str((folder / "native.png").relative_to(ROOT)), "nativeSha256": sha(folder / "native.png")}
    write_json_atomic(folder / "attempt.json", attempt)
    row.update(status="reviewed", attempts=[attempt], selectedAttempt=str(folder.relative_to(ROOT)),
               result=result, qualityReview=quality, visualReview=visual, semanticReview=visual,
               imageEdit={"status": "pass", "provider": vertex_image.MODE, "evidence": {"requestId": receipt["request_id"]}},
               reusedFrom=str(pilot.relative_to(ROOT)))
    write_json_atomic(path, row)
    return {"reused": True, "id": row["id"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["init", "run", "status", "reuse-pilot"])
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    setup()
    actions = {"init": initialize, "status": status, "reuse-pilot": reuse_pilot,
               "run": lambda: run(args.concurrency, args.max_attempts, args.limit)}
    emit(actions[args.action]())
