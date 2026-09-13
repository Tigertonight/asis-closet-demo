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
from scripts.female_nano_quality import review_worn_hat

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
RATE_LOCK = threading.Lock()
# Observed short-window 429 bursts occurred on a third request within a minute.
MIN_DISPATCH_INTERVAL_SECONDS = 35
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
    assert all_looks
    BATCH.mkdir(parents=True, exist_ok=True)
    snapshot = BATCH / "source-snapshot.json"
    if snapshot.exists():
        original = {key_for(look): look for look in read(snapshot)["looks"]}
        if any(original.get(key_for(look)) != look for look in all_looks):
            raise ValueError("Catalog changed since batch initialization")
    else:
        write_json_atomic(snapshot, {"looks": all_looks, "createdAt": now(), "expected": len(all_looks) * len(MODEL_IDS)})
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
        emit({"prepared": n, "of": len(all_looks), "key": catalog["key"], "images": len(catalog["references"]) + 1})
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


def request_item_context(catalog, overrides=None):
    """Apply documented visual corrections only to this request, keeping the source intact."""
    items = json.loads(json.dumps(catalog["itemContext"]))
    allowed = {"wearing_method", "closure_state", "overlap", "visible_details", "visible_description"}
    for override in overrides or []:
        matches = [item for item in items if item["name"] == override["name"]]
        fields = override.get("fields", {})
        if len(matches) != 1 or not override.get("reason") or not fields or not set(fields) <= allowed:
            raise ValueError("Item correction needs one existing item, documented evidence and wearing/detail fields")
        matches[0].update(fields)
    return garment_only_context(items)


def prompt_for(catalog, correction="", item_overrides=None, *, reviewed_candidate=False):
    if reviewed_candidate:
        opening = ("Use case: identity-preserve. Edit Image 2, the previously generated full-outfit candidate "
                   "for this SAME adult woman, to fix the targeted errors below. Keep its already-correct "
                   "outfit details. Return ONE complete seamless full-body photograph.\n")
        image_two_role = ("Image 2 is the dressed editing base, not an accepted preset. Correct all known "
                          "errors using Image 1 and the exact-item references. Image 1 overrides Image 2 "
                          "for identity, hair placement, anatomy, phone, pose and canvas. Restore any drift "
                          "in those regions from Image 1. Do not recreate already-correct garment details. ")
    else:
        opening = ("Use case: identity-preserve. Create ONE photorealistic full-outfit virtual try-on photo "
                   "by editing Image 1.\n")
        image_two_role = ("Image 2 provides clothing layering and wearing relationships ONLY. Never copy "
                          "its person, face, hairstyle, anatomy, pose, scene, lettering, watermark or other "
                          "people. Do not use the source person's proportions as the target body. ")
    return opening + """This is a single complete outfit edit: include clothing AND footwear and ALL listed visible accessories in the SAME final image.
Image 1 is the sole authority for the adult woman's identity, anatomy, face, hair, skin tone, body shape, framing, lighting, white background, phone and pose. Preserve these with minimal pixel changes. This is the same woman trying on clothes, not a new model.
""" + image_two_role + """All later images are individually labeled exact-item references. Use the structured instructions below for wearing relationships. Preserve item color, material, texture, construction, pattern and recognizable details.

FIXED SELFIE POSE: keep the phone and raised phone hand exactly at the original coordinates. The other arm hangs straight DOWN beside the body, with the hand at its original height. Do NOT put it in a pocket, bend it onto the waist, cross the arms or copy a pose from the outfit notes. Fit sleeves to the existing arm positions. Keep the leg stance and both feet at the original positions and orientations. Do not narrow the waist, slim or enlarge the body, lengthen legs, change head scale, move the face, change expression or retouch the face. Preserve existing hair lengths, hairline, parting, and hair hanging in FRONT of each shoulder. Put clothes under existing front hair; do not tuck hair back just to show a collar or accessory. Preserve exposed hands, fingers and skin. Accommodate the garments on this exact body.
Put each item only on its intended body region. Respect inner-to-outer layering: if a skirt is worn over trousers, show both and do not merge them. Preserve scarves, bows, socks, belts, jewelry and shoes where visible. Replace original white shoes with the referenced shoes when supplied. Don't leave the original white T-shirt or shorts exposed when they should be replaced/covered. Do not invent extra accessories. A hidden underlayer may be occluded according to the outfit instructions.
For a jacket or coat worn normally, BOTH arms go THROUGH its sleeves; fit the raised sleeve around the bent phone arm and the other sleeve around the straight lowered arm. Never turn normal outerwear into a cape with empty hanging sleeves. Only leave sleeves empty when that specific item's wearing instructions explicitly say to drape it over the shoulders without wearing the sleeves. Keep the original plain phone back free of any added portrait, miniature person, screen image or sticker.
REFERENCE COUNTING: the styling photograph and an item cutout show the SAME physical item, not two items to add together. Use each listed item once, respecting explicitly paired shoes/socks/earrings and explicitly described multi-piece sets. A single plain ring means ONE ring TOTAL on one finger, not one per hand or multiple fingers. Keep all other fingers and wrists bare unless the catalog explicitly lists their jewelry. Do not copy unlisted bracelets or other accessories from the styling photograph. Keep built-in garment trim distinct from a separately listed accessory when their actual reference images differ.
Keep bags physically attached: shoulder bag on shoulder, crossbody strap continuously across the torso to its hip bag; handheld bag may be held by the already lowered hand without moving the arm. Do not float a bag or intersect it with fingers. Hat/head accessories may be added over the existing hair but must not reshape the head or face. Scarf stays clear of the face and phone. Detailed outfit wearing instructions below describe garments, never authorize changing the model pose.

OUTFIT AND ITEM REFERENCES:
""" + json.dumps({"title": catalog["plan"]["title"], "items": request_item_context(catalog, item_overrides)}, ensure_ascii=False, indent=2) + """

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


def save_private_continuation(response, folder):
    """Retain the native model turn, including opaque signatures, locally only."""
    candidates = response.get("candidates", [])
    if len(candidates) != 1 or not candidates[0].get("content"):
        return None
    target = folder / "continuation-response.json"
    write_json_atomic(target, candidates[0]["content"])
    target.chmod(0o600)
    return {"localPath": str(target.relative_to(ROOT)), "sha256": sha(target)}


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
    raw_quality = tryon._review_tryon_quality(original, result, face, Path(mask["evidence"]["mask_path"]))
    quality = review_worn_hat(original, normalized, raw_quality, catalog["itemContext"],
                              face["evidence"]["primary_face"]["box"], allow_forehead_occlusion=True)
    write_json_atomic(folder / "quality-report.json", {"qualityReview": quality, "normalization": normalization,
                      "originalExpandedQualityReview": raw_quality,
                      "modelSha256": row["model"]["sha256"], "nativeSha256": sha(native), "resultSha256": sha(result)})
    return quality, {"localPath": str(result.relative_to(ROOT)), "sha256": sha(result),
                     "bytes": result.stat().st_size, "dimensions": list(normalized.size), "verified": False}


def identity_detail_reference(model_path, model_sha, folder, image_number, *, include_hair=False):
    """A lossless input crop of the same target, never a change to the output."""
    assert sha(model_path) == model_sha
    crop_box = (690, 80, 1140, 700) if include_hair else (760, 160, 1120, 540)
    target = folder / "identity-detail.png"
    with Image.open(model_path) as original:
        assert original.size == (1792, 2400)
        original.crop(crop_box).save(target)
    label = ("unedited head and BOTH shoulder-front hair locks cropped from Image 1; "
             "preserve this exact face, hair length, parting and front hair placement; "
             "identity and hair ONLY, ignore the original white shirt, not framing") if include_hair else (
             "unedited face detail cropped from Image 1; "
             "same target woman, exact nose, cheeks, mouth and original expression; identity only, not framing")
    ref = image_ref(target, f"IMAGE {image_number}: " + label)
    ref["derivation"] = {"sourcePath": str(model_path), "sourceSha256": model_sha,
                         "operation": "lossless_crop", "cropBox": list(crop_box)}
    return ref


def focused_item_references(catalog, item_ids, image_number, available_slots):
    """Repeat exact catalog-bound cutouts at full detail without replacing any item."""
    if not isinstance(item_ids, list) or len(item_ids) != len(set(item_ids)) or len(item_ids) > available_slots:
        raise ValueError("Item details must be unique and fit the reference limit")
    refs = []
    packed_ids = {iid for ref in catalog["references"] for iid in ref.get("itemIds", [])}
    for item_id in item_ids:
        candidates = [ref for ref in catalog["sourceReferences"] if ref.get("itemIds") == [item_id]]
        if item_id not in packed_ids or len(candidates) != 1:
            raise ValueError("Item detail must belong to this outfit's existing references")
        source = candidates[0]
        if sha(Path(source["path"])) != source["sha256"]:
            raise ValueError("Item detail source hash changed")
        ref = image_ref(Path(source["path"]),
                        f"IMAGE {image_number + len(refs)}: exact full-detail {source['label']}; "
                        "the SAME item already shown in the accessory references, use it once", [item_id])
        ref["derivation"] = {"operation": "unmodified_catalog_item_detail", "outfitId": catalog["outfitId"],
                             "sourceSha256": source["sha256"]}
        refs.append(ref)
    return refs


def garment_style_reference(source, crop_box, folder):
    """Optional outfit-only input crop to avoid copying a source hairstyle."""
    assert sha(source["path"]) == source["sha256"]
    assert len(crop_box) == 4 and all(isinstance(v, int) for v in crop_box)
    target = folder / "garment-style-reference.png"
    with Image.open(source["path"]) as original:
        left, top, right, bottom = crop_box
        assert 0 <= left < right <= original.width and 0 <= top < bottom <= original.height
        original.crop(crop_box).save(target)
    ref = image_ref(target, "IMAGE 2: clothing-only crop of original styling source; "
                    "clothing layering only, never identity, hairstyle or pose")
    ref["derivation"] = {"sourcePath": source["path"], "sourceSha256": source["sha256"],
                         "operation": "lossless_crop", "cropBox": list(crop_box)}
    return ref


def reviewed_outfit_reference(row):
    """Reuse a viewed near-complete outfit as input, never as an accepted output."""
    selected = row["retryOutfitReference"]
    attempt = next((a for a in row["attempts"] if a["path"] == selected["attemptPath"]), None)
    if row["status"] == "blocked_moderation" or not attempt:
        raise ValueError("Retry reference must belong to this unblocked job")
    result = attempt.get("result", {})
    review = attempt.get("visualReview", {})
    digest = selected["sha256"]
    if (attempt.get("qualityReview", {}).get("status") != "pass"
            or review.get("status") != "fail" or not review.get("observations")
            or review.get("modelId") != row["modelId"] or review.get("key") != row["key"]
            or review.get("resultSha256") != digest or result.get("sha256") != digest
            or not row.get("retryCorrection")):
        raise ValueError("Retry reference requires an exact hash-bound visual failure and numeric pass")
    source = ROOT / result["localPath"]
    if sha(source) != digest:
        raise ValueError("Retry reference bytes changed")
    ref = image_ref(source, "IMAGE 2: previously viewed near-complete outfit for this SAME model; "
                    "retain correct garments but fix ALL stated errors; Image 1 remains the identity and pose authority")
    ref["derivation"] = {"operation": "unmodified_reviewed_attempt_reference", "jobId": row["id"],
                         "attemptPath": attempt["path"], "sourceSha256": digest,
                         "reviewedAt": review["reviewedAt"], "knownIssues": review["observations"]}
    return ref


def correction_detail_reference(row, folder, image_number):
    """Show a local defect at native detail, using only an audited input crop."""
    source = reviewed_outfit_reference(row)
    box = row.get("correctionDetailBox")
    if not isinstance(box, list) or len(box) != 4 or not all(type(v) is int for v in box):
        raise ValueError("Correction detail requires an explicit four-integer crop box")
    with Image.open(source["path"]) as original:
        left, top, right, bottom = box
        if not (0 <= left < right <= original.width and 0 <= top < bottom <= original.height):
            raise ValueError("Correction detail box is outside its verified candidate")
        target = folder / "correction-detail.png"
        original.crop(tuple(box)).save(target)
    ref = image_ref(target, f"IMAGE {image_number}: unedited local detail of the defect in Image 2; "
                    "apply the requested correction HERE in the full dressed photo, not a separate output or identity reference")
    ref["derivation"] = {"operation": "lossless_reviewed_candidate_crop", "sourcePath": source["path"],
                         "sourceSha256": source["sha256"], "cropBox": box,
                         "candidateAudit": source["derivation"]}
    return ref


def candidate_first_request(references, prompt):
    """Keep a reviewed editing canvas first without changing any input bytes."""
    if (len(references) < 2 or references[0].get("sha256") not in MODEL_SHA.values()
            or references[1].get("derivation", {}).get("operation") != "unmodified_reviewed_attempt_reference"):
        raise ValueError("Candidate-first editing requires the exact original and a verified same-job candidate")
    refs = json.loads(json.dumps(references))
    refs[0], refs[1] = refs[1], refs[0]

    def swap(text):
        return re.sub(r"\b(image\s+)([12])(?!\d)",
                      lambda match: match[1] + ("2" if match[2] == "1" else "1"), text, flags=re.I)

    for ref in refs:
        ref["label"] = swap(ref["label"])
    return refs, swap(prompt) + ("\nImage 1 is the dressed editing canvas. Retain its already-correct garment pixels. "
                               "Make the stated correction, preserving identity and pose from Image 2. "
                               "Do not rebuild the outfit from the item cutouts when its details are already correct.")


def reviewed_conversation_request(row, correction):
    """Reconstruct one authentic prior model turn; never invent a signature."""
    reviewed_outfit_reference(row)
    attempt = next(a for a in row["attempts"] if a["path"] == row["retryOutfitReference"]["attemptPath"])
    folder = ROOT / attempt["path"]
    previous = read(folder / "request.json")
    previous_id = previous.pop("requestId")
    if (hashlib.sha256(json.dumps(previous, sort_keys=True, ensure_ascii=False).encode()).hexdigest() != previous_id
            or previous_id != attempt["requestId"] or previous.get("conversation")
            or previous["model"] != row["generationModel"] or previous["model"] != vertex_image.model()):
        raise ValueError("Continuation requires an authentic same-model single-turn source")
    refs = previous["images"]
    catalog = read(BATCH / "catalog" / row["key"] / "catalog.json")
    expected_items = {(item_id, ref["sha256"]) for ref in catalog["references"] for item_id in ref.get("itemIds", [])}
    actual_items = {(item_id, ref["sha256"]) for ref in refs for item_id in ref.get("itemIds", [])}
    if (row["model"]["sha256"] not in {r["sha256"] for r in refs}
            or catalog["outfitId"] != row["outfitId"]
            or row["itemIds"] != [item["item_id"] for item in catalog["look"]["items"]]
            or not expected_items or not expected_items <= actual_items
            or any(sha(r["path"]) != r["sha256"] for r in refs)):
        raise ValueError("Continuation lost an original model or item reference")
    previous_prompt = (folder / "prompt.txt").read_text()
    if hashlib.sha256(previous_prompt.encode()).hexdigest() != previous["promptSha256"]:
        raise ValueError("Continuation source prompt changed")
    receipt = attempt.get("continuationResponse", {})
    response_path = ROOT / receipt.get("localPath", "")
    if response_path.parent != folder or not response_path.is_file() or sha(response_path) != receipt.get("sha256"):
        raise ValueError("Continuation response is missing or changed")
    model_content = read(response_path)
    images = [p for p in model_content.get("parts", []) if p.get("inlineData", p.get("inline_data"))]
    if (model_content.get("role") != "model" or len(images) != 1
            or not images[0].get("thoughtSignature", images[0].get("thought_signature"))):
        raise ValueError("Native image continuation requires the original provider signature")
    block = images[0].get("inlineData", images[0].get("inline_data"))
    if hashlib.sha256(base64.b64decode(block["data"])).hexdigest() != attempt["nativeSha256"]:
        raise ValueError("Continuation model image differs from the audited native result")
    native = ROOT / attempt["nativePath"]
    if sha(native) != attempt["nativeSha256"]:
        raise ValueError("Continuation native image changed")
    previous_parts = []
    for ref in refs:
        previous_parts.extend([{"text": ref["label"]}, {"inlineData": {
            "mimeType": Image.MIME[ref["format"]], "data": base64.b64encode(Path(ref["path"]).read_bytes()).decode()}}])
    previous_parts.append({"text": previous_prompt})
    prompt = ("Continue editing your last full-body photograph of this same adult woman. Make ONLY this correction: "
              + correction + "\nKeep every other garment and accessory unchanged. The original woman in the white shirt "
              "and her original detail crop in the preceding user message remain the exact face, hair, body and pose authority. "
              "Return one complete full-body image with identical framing; no side-by-side panels or close-up output.")
    contents = [{"role": "user", "parts": previous_parts}, model_content, {"role": "user", "parts": [{"text": prompt}]}]
    return {"images": refs + [image_ref(native, "Previous native model output in conversation history")],
            "prompt": prompt, "contents": contents,
            "metadata": {"sourceAttempt": attempt["path"], "sourceRequestId": previous_id,
                         "sourceResponse": receipt, "nativeSha256": attempt["nativeSha256"],
                         "contentsSha256": hashlib.sha256(json.dumps(contents, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
                         "rule": "authentic_single_turn_followup_v1"}}


def generate_attempt(path, row, correction=""):
    catalog = read(BATCH / "catalog" / row["key"] / "catalog.json")
    if catalog["outfitId"] != row["outfitId"]:
        raise ValueError("Catalog binding drift")
    folder = path.parent / "attempts" / f"{len(row['attempts']) + 1:02d}"
    folder.mkdir(parents=True, exist_ok=False)
    model_path = ROOT / row["model"]["localPath"]
    assert sha(model_path) == row["model"]["sha256"] == MODEL_SHA[row["modelId"]]
    refs = [image_ref(model_path, "IMAGE 1: exact target model; ONLY identity/pose/body/canvas authority")] + catalog["references"]
    prompt = prompt_for(catalog, correction, row.get("itemContextOverrides"),
                        reviewed_candidate=bool(row.get("retryOutfitReference")))
    if row.get("retryOutfitReference"):
        refs[1] = reviewed_outfit_reference(row)
        prompt += ("\nImage 2 is a PREVIOUSLY GENERATED candidate for this exact same model and outfit, "
                   "not an accepted preset. Keep its already-correct garment construction and placement, "
                   "but correct every stated issue using the exact item cutouts and instructions. "
                   "Do not copy any changed hair, face or extra limbs from Image 2: Image 1 and the original "
                   "identity detail remain the only authority for those. Return one complete seamless outfit photo. "
                   "Known errors in Image 2: " + refs[1]["derivation"]["knownIssues"])
    elif row.get("styleCropBox"):
        refs[1] = garment_style_reference(refs[1], row["styleCropBox"], folder)
        prompt += ("\nImage 2 is cropped below the source person's head to show outfit layering only. "
                   "All head accessories still have their exact individual references. "
                   "Retain Image 1's original hairstyle and front locks while adding those accessories.")
    if row.get("correctionDetailBox"):
        if not row.get("retryOutfitReference") or len(refs) >= 13:
            raise ValueError("Correction detail requires a verified candidate and room for identity detail")
        refs.append(correction_detail_reference(row, folder, len(refs) + 1))
        prompt += ("\nThe additional correction-detail image is an unedited crop of the defect in Image 2. "
                   "Use it to locate and fix the stated problem in the FULL original-size dressed image. "
                   "It shows the BEFORE state to change, not a new item or a separate person. "
                   "Do not return the crop or add a close-up panel.")
    if row.get("focusItemIds"):
        if row.get("continueReviewedAttempt"):
            raise ValueError("New item detail inputs require a fresh request")
        reserved = int(bool(row.get("useIdentityDetail") or row.get("useIdentityHairDetail")))
        refs.extend(focused_item_references(catalog, row["focusItemIds"], len(refs) + 1, 14 - len(refs) - reserved))
    if row.get("useIdentityDetail") or row.get("useIdentityHairDetail"):
        assert len(refs) < 14, "Identity detail must fit the existing reference limit"
        refs.append(identity_detail_reference(model_path, row["model"]["sha256"], folder, len(refs) + 1,
                                              include_hair=bool(row.get("useIdentityHairDetail"))))
        prompt += ("\nThe LAST image is an unedited detail crop of the face in Image 1, not a new person. "
                   "Use it to retain the exact original expression, closed-mouth shape, mouth corners, nose and cheek contours. "
                   "Do not turn a neutral expression into a smile or add lipstick, blush or facial beautification. "
                   "Keep the original full-body canvas and all coordinates from Image 1. "
                   "Fit any required eyewear onto the unchanged original face; preserve visible features beneath it.")
        if row.get("useIdentityHairDetail"):
            prompt += ("\nThis last original detail also shows BOTH front hair locks. Keep their exact length, "
                       "shape and placement over the front of both shoulders, even if they partly obscure "
                       "necklaces, shoulder bows or collars. Do not tuck the hair behind the shoulders. "
                       "The white shirt in this identity detail is not part of the requested outfit.")
    if row.get("candidateFirst"):
        if not row.get("retryOutfitReference"):
            raise ValueError("Candidate-first editing cannot be used without a reviewed outfit reference")
        refs, prompt = candidate_first_request(refs, prompt)
    conversation = reviewed_conversation_request(row, correction) if row.get("continueReviewedAttempt") else None
    if conversation:
        refs, prompt = conversation["images"], conversation["prompt"]
    (folder / "prompt.txt").write_text(prompt)
    request = {"model": vertex_image.model(), "endpoint": vertex_image.endpoint(), "provider": vertex_image.MODE,
               "images": refs, "generationConfig": CONFIG, "timeoutSeconds": 600,
               "promptSha256": hashlib.sha256(prompt.encode()).hexdigest()}
    if row.get("itemContextOverrides"):
        request["itemContextOverrides"] = row["itemContextOverrides"]
    if row.get("candidateFirst"):
        request["referenceOrder"] = "reviewed_candidate_then_exact_original"
    if conversation:
        request["conversation"] = conversation["metadata"]
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
    # A new image cannot reuse a prior attempt's numeric recheck receipt.
    row.pop("qualityReportPath", None)
    row.update(status="running", updatedAt=now())
    write_json_atomic(path, row)
    write_json_atomic(folder / "attempt.json", attempt)
    started = time.monotonic()
    try:
        contents = conversation["contents"] if conversation else [{"role": "user", "parts": parts}]
        response = vertex_image.generate_content({"contents": contents, "generationConfig": CONFIG}, timeout=600)
        attempt["apiSeconds"] = round(time.monotonic() - started, 2)
        write_json_atomic(folder / "response.json", sanitize(response))
        if row.get("saveContinuation"):
            # Opaque provider signatures are required for native conversational
            # edits. Keep them private in ignored runtime data, never in logs or
            # the public registry. The standard sanitized response stays intact.
            continuation = save_private_continuation(response, folder)
            if continuation:
                attempt["continuationResponse"] = continuation
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


def record_rate_result(attempt):
    """Carry service backoff across jobs, including previously unstarted jobs."""
    path = BATCH / "rate-limit.json"
    with RATE_LOCK:
        state = read(path) if path.exists() else {}
        if "HTTP 429" in attempt.get("error", ""):
            failures = state.get("consecutive429", 0) + 1
            delay = min(300, 60 * 2 ** min(failures - 1, 3))
            state.update(consecutive429=failures, resumeAfter=time.time() + delay,
                         last429At=now(), updatedAt=now())
            write_json_atomic(path, state)
            emit({"sharedRateLimitBackoffSeconds": delay, "consecutive429": failures})
        elif attempt.get("nativePath") and state:
            # An already in-flight success must not cancel another request's cooldown.
            state.update(consecutive429=0, updatedAt=now())
            write_json_atomic(path, state)


def wait_for_rate_limit():
    path = BATCH / "rate-limit.json"
    while not (BATCH / "STOP").exists():
        with RATE_LOCK:
            state = read(path) if path.exists() else {}
            remaining = max(state.get("resumeAfter", 0), state.get("nextDispatchAfter", 0)) - time.time()
            if remaining <= 0:
                # Claim the next slot under the same lock, including with two workers.
                state.update(nextDispatchAfter=time.time() + MIN_DISPATCH_INTERVAL_SECONDS,
                             minDispatchIntervalSeconds=MIN_DISPATCH_INTERVAL_SECONDS, updatedAt=now())
                write_json_atomic(path, state)
                return True
        time.sleep(min(2, remaining))
    return False


def worker(path, max_attempts):
    row = read(path)
    while len(row["attempts"]) < max_attempts and not (BATCH / "STOP").exists():
        if row["status"] in {"generated_local", "reviewed", "uploaded", "blocked_moderation"}:
            break
        correction = row.get("retryCorrection", "")
        if not correction and any(a["status"] == "failed_quality" for a in row["attempts"]):
            correction = "The earlier attempt shifted protected regions. Reuse the ORIGINAL Image 1 face, phone and white background with minimal pixel change. Fit only clothing to the unchanged body. Preserve all original head and feet coordinates."
        if not wait_for_retry(row):
            break
        if not wait_for_rate_limit():
            break
        row = generate_attempt(path, row, correction)
        record_rate_result(row["attempts"][-1])
    return row["status"]


def wait_for_retry(row):
    """Count elapsed time since the last response toward the retry delay."""
    if not row["attempts"]:
        return not (BATCH / "STOP").exists()
    delay = min(60, 15 * 2 ** min(len(row["attempts"]) - 1, 3) + random.random() * 10)
    try:
        finished = datetime.fromisoformat(row["attempts"][-1]["finishedAt"]).timestamp()
    except (KeyError, TypeError, ValueError):
        finished = time.time()
    deadline = min(time.time(), finished) + delay
    while not (BATCH / "STOP").exists():
        remaining = deadline - time.time()
        if remaining <= 0:
            return True
        time.sleep(min(2, remaining))
    return False


def job_paths():
    # Group all three body types of an outfit together for visual review.
    # Retired notes remain in historical evidence but cannot re-enter the queue.
    original = {key_for(x): x for x in read(BATCH / "source-snapshot.json")["looks"]}
    current = looks()
    if not current or any(original.get(key_for(look)) != look for look in current):
        raise ValueError("Active catalog differs from the batch input snapshot")
    keys = [key_for(x) for x in current]
    return [BATCH / mid / key / "job.json" for key in keys for mid in MODEL_IDS]


def status():
    paths = job_paths()
    rows = [read(p) for p in paths]
    states = {s: sum(r["status"] == s for r in rows) for s in sorted({r["status"] for r in rows})}
    attempts = [a for r in rows for a in r["attempts"]]
    stats = {"updatedAt": now(), "expected": len(paths), "jobs": len(rows), "states": states,
             "dispatchPaused": (BATCH / "STOP").exists(), "inFlight": states.get("running", 0),
             "apiAttempts": sum(not a.get("reused") for a in attempts),
             "successfulImages": sum(a["status"] in {"generated_local", "failed_quality"} for a in attempts),
             "apiSecondsTotal": round(sum(a.get("apiSeconds", 0) for a in attempts), 2)}
    write_json_atomic(BATCH / "progress.json", stats)
    return stats


def run(concurrency, max_attempts, limit=None, max_additional_attempts=None, api_first=False):
    if concurrency not in {1, 2}:
        raise ValueError("Use one or two concurrent requests")
    if max_additional_attempts is not None and max_additional_attempts < 1:
        raise ValueError("Additional attempt budget must be positive")
    if (BATCH / "STOP").exists():
        emit({"dispatchPaused": True, "reason": "STOP exists; no generation requests will be sent"})
        return status()
    with (BATCH / "runner.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        paths = [p for p in job_paths() if read(p)["status"] not in {"generated_local", "reviewed", "uploaded", "blocked_moderation"}
                 and len(read(p)["attempts"]) < max_attempts]
        if api_first:
            # Stable within each group; failed requests get a fresh queue position.
            paths.sort(key=lambda p: read(p)["status"] != "failed_api")
        if limit:
            paths = paths[:limit]
        emit({"starting": len(paths), "concurrency": concurrency, "maxAttempts": max_attempts,
              "maxAdditionalAttempts": max_additional_attempts, "apiFirst": api_first})
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = {pool.submit(worker, p, min(max_attempts, len(read(p)["attempts"]) + max_additional_attempts)
                                   if max_additional_attempts is not None else max_attempts): p for p in paths}
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
    parser.add_argument("--max-additional-attempts", type=int,
                        help="Per-job new request limit for this run, still bounded by --max-attempts")
    parser.add_argument("--api-first", action="store_true",
                        help="Prioritize failed API requests before other unfinished jobs")
    args = parser.parse_args()
    setup()
    actions = {"init": initialize, "status": status, "reuse-pilot": reuse_pilot,
               "run": lambda: run(args.concurrency, args.max_attempts, args.limit, args.max_additional_attempts, args.api_first)}
    emit(actions[args.action]())
