"""Canonical white-tee recipes, shared by offline generation and preset lookup."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from fastapi import HTTPException

from app.material_assets import material_image_path
from app.selfit_outfit_match import CURATED_WHITE_TEE_PATH, _build_match
from app.styling_catalog import delivery_looks
from app.inspiration_catalog import inspiration_looks

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "app/static/selfit-tryon/assets/default-items/catalog.json"
DESCRIPTION = ROOT / "app/static/selfit-tryon/assets/default-items/white-tee-v1.description.md"
INDEX = ROOT / "app/data/white-tee-tryon-presets.v1.json"


def digest_json(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def anchor_item():
    data = json.loads(CURATED_WHITE_TEE_PATH.read_text())
    return deepcopy(next(x for x in json.loads(CATALOG.read_text())["items"]
                         if x["item_id"] == data["anchor_item_id"] and x.get("is_default")))


def anchor_path(anchor):
    path = anchor["assets"]["cutout_path"]
    if not path.startswith("/static/"):
        raise ValueError("Unexpected default garment path")
    target = (ROOT / "app" / path.lstrip("/")).resolve()
    if not target.is_relative_to((ROOT / "app/static").resolve()):
        raise ValueError("Invalid default garment path")
    return target


def recipes():
    data = json.loads(CURATED_WHITE_TEE_PATH.read_text())
    looks = {x["look_id"]: x for x in delivery_looks() + inspiration_looks()}
    anchor = anchor_item()
    output = {}
    for gender, catalog in (("female", data), ("male", data["male"])):
        groups = [g for variants in catalog["persona_groups"].values() for g in variants.values()]
        groups += list(catalog["library_groups"].values())
        for group in groups:
            for pick in group["matches"]:
                key = "white-tee-" + digest_json([gender, pick["candidate_id"], pick["replace_item_id"]])[:16]
                if key in output:
                    continue
                look = looks[pick["candidate_id"]]
                if (look["note_binding"].get("gender") == "male") != (gender == "male"):
                    raise ValueError("White-tee recipe gender mismatch")
                outfit, note = _build_match(anchor, look, pick["replace_item_id"], pick["reason"])
                output[key] = {"key": key, "gender": gender, "pick": pick, "look": look,
                               "outfit": outfit, "note": note,
                               "fingerprint": digest_json({"look": look, "replace": pick["replace_item_id"],
                                   "anchor": anchor, "anchorSha256": hashlib.sha256(anchor_path(anchor).read_bytes()).hexdigest(),
                                   "anchorDescription": DESCRIPTION.read_text()})}
    return list(output.values())


def recipe_plan(recipe):
    outfit = deepcopy(recipe["outfit"])
    anchor = anchor_item()
    items = []
    for item in outfit["items"]:
        if item["item_id"] == anchor["item_id"]:
            path = anchor_path(anchor)
            item.update(image_id="default-white-tee", wearing_instruction="以所给白 T 实物图为准，白色圆领短袖，无图案；保留自然布料褶皱。", note=DESCRIPTION.read_text())
        else:
            path = material_image_path(item["image_id"])
        items.append({**item, "image_path": str(path), "public_image_path": item["assets"]["cutout_path"]})
    return {"source_mode": "from_outfit", "source_catalog": "styling_delivery", "outfit_id": recipe["key"],
            "title": "白 T · " + recipe["note"]["title"], "model_photo_mode": "standard", "scene_label": "",
            "style_reference": {"image_id": recipe["look"]["source_asset"]["assetId"],
                                "image_path": str(material_image_path(recipe["look"]["source_asset"]["assetId"])),
                                "role": "overall_outfit_reference"},
            "items": items, "layer_sequence_inner_to_outer": outfit["layer_sequence_inner_to_outer"],
            "style_brief": "本图是白 T 替换版，并非还原原套装。只把原套装中的「" + recipe["note"]["replaced_item_name"]
                + "」替换为单品参考中纯白色圆领短袖 T 恤。整体参考图中被替换上衣的颜色、图案、领型不可沿用。"
                "其余每件衣物和配饰保留参考款式，按单品顺序叠穿；白 T 如果为内搭则保留外层衣物，露出合理的白 T 部分。"
                "保留模特原来的脸、体型、姿势、人物高度、脚的位置和背景。"}, outfit


def item_identity(item):
    """Ignore collection UI state; compare image identity and wearing semantics."""
    styling = deepcopy(item.get("styling") or {})
    # Saved public pieces retain the source pairing ID, while the matcher remaps
    # that ID to the tee. The full ordered composition is checked separately.
    styling.pop("paired_with_item_ids", None)
    return {"image_id": item.get("image_id"), "assets": item.get("assets"),
            "category": item.get("category"), "slot": item.get("slot") or item.get("category"), "source": item.get("source"),
            "attributes": item.get("attributes") or {}, "note": item.get("note") or "",
            "wearing_instruction": item.get("wearing_instruction") or "",
            "wear_region": item.get("wear_region") or "", "styling": styling}


def find_white_tee_preset(outfit_key, model_id, person_raw, selected_ids):
    """Match an account-owned saved composition, never a client's recipe claim."""
    from app.closet import get_outfit
    from app.material_assets import MaterialRegistry, asset_content_url, material_download_url
    from app.selfit_tryon_presets import _model_matches
    from app.selfit_studio import model_library
    from app.tryon import TRYON_MODEL_FIXTURE_DIR

    if not model_id or model_id == "self" or outfit_key.startswith("report_") or not INDEX.is_file():
        return None
    try:
        outfit = get_outfit(outfit_key)  # Current authenticated storage context.
        if not any(m["id"] == model_id for m in model_library()["items"]):
            return None
        ids = outfit["item_ids"]
        if selected_ids is not None and set(selected_ids) != set(ids):
            return None
        tee = anchor_item()
        if tee["item_id"] not in ids or len(set(ids)) != len(ids):
            return None
        candidates = [r for r in recipes() if r["outfit"]["item_ids"] == ids]
        if len(candidates) != 1:
            return None
        recipe = candidates[0]
        expected = {i["item_id"]: i for i in recipe["outfit"]["items"]}
        if len(outfit["items"]) != len(expected) or any(item_identity(i) != item_identity(expected[i["item_id"]]) for i in outfit["items"]):
            return None
        rows = [r for r in json.loads(INDEX.read_text())["examples"] if r.get("key") == recipe["key"] and r.get("modelId") == model_id]
        if len(rows) != 1:
            return None
        row = rows[0]
        result = row.get("result") or {}
        if (row.get("status") != "uploaded" or result.get("verified") is not True
                or row.get("qualityReview", {}).get("status") != "pass"
                or row.get("visualReview", {}).get("resultSha256") != result.get("sha256")
                or row.get("recipeFingerprint") != recipe["fingerprint"]
                or row.get("itemIds") != ids or row.get("gender") != recipe["gender"]
                or row.get("model", {}).get("gender") != recipe["gender"]
                or not _model_matches(TRYON_MODEL_FIXTURE_DIR.resolve(), model_id, row["model"], person_raw)):
            return None
        record = MaterialRegistry().get(result["assetId"])
        if record["sha256"] != result["sha256"]:
            return None
        material_download_url(record)
        return {"example_id": row["id"], "model_id": model_id, "outfit": outfit,
                "image_path": asset_content_url(result["assetId"]), "quality_review": row.get("qualityReview", {})}
    except (OSError, ValueError, KeyError, TypeError, HTTPException):
        return None
