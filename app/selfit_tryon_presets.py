"""Resolve an unchanged delivered outfit and fixed model to a published result."""
import hashlib
import json
from pathlib import Path

from fastapi import HTTPException

from app.material_assets import MaterialRegistry, asset_content_url, material_download_url
from app.styling_catalog import delivery_looks, outfit_id, adapt_outfit

INDEX_PATH = Path(__file__).resolve().parent / "data/tryon-examples.v1.json"


def find_preset(outfit_key: str, model_id: str | None, person_raw: bytes,
                selected_ids: list[str] | None) -> dict | None:
    if not model_id or model_id == "self" or not outfit_key.startswith("report_"):
        return None
    from app.selfit_studio import model_library
    from app.tryon import TRYON_MODEL_FIXTURE_DIR

    if not any(m["id"] == model_id for m in model_library()["items"]):
        return None
    try:
        index = json.loads(INDEX_PATH.read_text())
        look = next((row for row in delivery_looks() if outfit_id(row) == outfit_key), None)
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
        # Failed/adjusted outputs never stand in for the requested original outfit.
        if example.get("status") != "uploaded" or result.get("verified") is not True:
            return None
        source_ids = [item["item_id"] for item in look["items"]]
        if (example.get("sourceAssetId") != look["source_asset"]["assetId"]
                or example.get("itemIds") != source_ids):
            return None
        model = example["model"]
        root = TRYON_MODEL_FIXTURE_DIR.resolve()
        model_path = (root / model["file"]).resolve()
        digest = hashlib.sha256(person_raw).hexdigest()
        if (model_path.parent != root or not model_path.is_file()
                or digest != model.get("sha256")
                or hashlib.sha256(model_path.read_bytes()).hexdigest() != digest):
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
