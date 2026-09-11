"""Resolve an unchanged delivered outfit and fixed model to a published result."""
import hashlib
import json
from pathlib import Path

from fastapi import HTTPException

from app.material_assets import MaterialRegistry, asset_content_url, material_download_url
from app.styling_catalog import delivery_looks, outfit_id, adapt_outfit
from app.model_assets import load_model_manifest

INDEX_PATH = Path(__file__).resolve().parent / "data/tryon-examples.v1.json"


def _model_matches(root: Path, model_id: str, model: dict, person_raw: bytes) -> bool:
    """Match the current model master record, including models stored as assets."""
    rows = load_model_manifest(root)["items"]
    candidates = [row for row in rows if row.get("active", True)
                  and (row.get("id") or Path(row.get("file", "")).stem) == model_id]
    if len(candidates) != 1:
        return False
    current = candidates[0]
    digest = hashlib.sha256(person_raw).hexdigest()
    if digest != model.get("sha256") or model.get("file") != current.get("file"):
        return False
    if current.get("image_asset_id"):
        return (model.get("image_asset_id") == current["image_asset_id"]
                and MaterialRegistry().get(current["image_asset_id"])["sha256"] == digest)
    path = (root / current["file"]).resolve()
    return (not model.get("image_asset_id") and path.parent == root and path.is_file()
            and hashlib.sha256(path.read_bytes()).hexdigest() == digest)


def find_preset(outfit_key: str, model_id: str | None, person_raw: bytes,
                selected_ids: list[str] | None) -> dict | None:
    if not outfit_key.startswith("report_"):
        from app.white_tee_presets import find_white_tee_preset
        return find_white_tee_preset(outfit_key, model_id, person_raw, selected_ids)
    if not model_id or model_id == "self" or not outfit_key.startswith("report_"):
        return None
    from app.selfit_studio import model_library
    from app.tryon import TRYON_MODEL_FIXTURE_DIR

    if not any(m["id"] == model_id for m in model_library()["items"]):
        return None
    try:
        index = json.loads(INDEX_PATH.read_text())
        if outfit_key.startswith("report_inspiration_"):
            from app.inspiration_catalog import inspiration_looks
            catalog = inspiration_looks()
        else:
            catalog = delivery_looks()
        look = next((row for row in catalog if outfit_id(row) == outfit_key), None)
        if look is None:
            return None
        binding = look["note_binding"]
        candidates = [row for row in index["examples"]
                      if row.get("modelId") == model_id
                      and row.get("noteBinding", {}).get("templateId") == binding["templateId"]
                      and row.get("noteBinding", {}).get("noteId") == binding["noteId"]]
        if len(candidates) != 1:
            return None
        example = candidates[0]
        result = example.get("result") or {}
        # Only published, verified results are usable; rejected attempts stay out.
        if example.get("status") != "uploaded" or result.get("verified") is not True:
            return None
        if example.get("strategy") == "complete_outfit_single_call":
            visual = example.get("visualReview") or {}
            if (example.get("outfitId") != outfit_key
                    or example.get("qualityReview", {}).get("status") != "pass"
                    or visual.get("status") != "pass" or visual.get("verified") is not True
                    or visual.get("resultSha256") != result.get("sha256")
                    or visual.get("reviewedItemIds") != example.get("itemIds")):
                return None
        source_ids = [item["item_id"] for item in look["items"]]
        if (example.get("sourceAssetId") != look["source_asset"]["assetId"]
                or example.get("itemIds") != source_ids):
            return None
        if example.get("inputAssetIds") is not None and example["inputAssetIds"] != [item["image_asset"]["assetId"] for item in look["items"]]:
            return None
        model = example["model"]
        root = TRYON_MODEL_FIXTURE_DIR.resolve()
        if not _model_matches(root, model_id, model, person_raw):
            return None
        outfit = adapt_outfit(look)
        if selected_ids is not None and set(selected_ids) != set(outfit["item_ids"]):
            return None
        asset_id = result["assetId"]
        record = MaterialRegistry().get(asset_id)
        if record["sha256"] != result["sha256"]:
            return None
        material_download_url(record)
        return {"example_id": example["id"], "model_id": model_id, "outfit": outfit,
                "image_path": asset_content_url(asset_id),
                "quality_review": example.get("qualityReview", {})}
    except (OSError, ValueError, KeyError, TypeError, HTTPException):
        # Missing/stale catalog data falls back to the existing generation path.
        return None
