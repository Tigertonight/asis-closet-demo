"""Save a personal outfit assembled from owned wardrobe or published library pieces."""
from copy import deepcopy
from threading import RLock
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import get_current_user
from app.storage import user_storage

router = APIRouter(prefix="/selfit/try-on", tags=["selfit-studio"])
_save_lock = RLock()


class StudioOutfit(BaseModel):
    item_ids: list[str] = Field(min_length=1, max_length=8)
    title: str = Field(default="我的搭配", max_length=48)
    favorite: bool = False


def save_studio_outfit(payload: StudioOutfit) -> dict[str, Any]:
    from app import closet

    with _save_lock:
        ids = list(dict.fromkeys(payload.item_ids))
        manifest = closet._ensure_manifest()
        owned = {x["item_id"]: x for x in manifest["items"] if not x.get("deleted")}
        published = {
            x["item_id"]: x
            for outfit in closet._published_catalog_outfits()
            for x in outfit.get("items", [])
        }
        missing = [key for key in ids if key not in owned and key not in published]
        if missing:
            raise HTTPException(404, "部分单品已不可用，请重新选择穿搭。")
        # Validate the complete selection before persisting any catalog copy.
        additions = [deepcopy(published[key]) for key in ids if key not in owned]
        for item in additions:
            item.update(user_id=closet.storage_context().user_id, created_at=closet._now_iso())
            manifest["items"] = [x for x in manifest["items"] if x.get("item_id") != item["item_id"]]
            manifest["items"].append(item)
        if additions:
            closet._write_manifest(manifest)
        # Retries and repeated saves of the same ordered selection reuse the outfit.
        for outfit in closet.list_outfits()["outfits"]:
            if outfit.get("item_ids") == ids:
                if payload.favorite and not outfit.get("favorite"):
                    return closet.update_outfit(outfit["outfit_id"], {"favorite": True})
                return outfit
        return closet.create_outfit({"item_ids": ids, "title": payload.title, "favorite": payload.favorite})


@router.post("/outfits")
def studio_outfit_create(payload: StudioOutfit, user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    with user_storage(user["user_id"]):
        return save_studio_outfit(payload)


def model_library() -> dict[str, Any]:
    """Read the existing model master data; never maintain a second UI catalog."""
    import json
    from pathlib import Path
    from urllib.parse import quote
    from app import tryon

    root = tryon.TRYON_MODEL_FIXTURE_DIR.resolve()
    manifest = root / "manifest.json"
    if not manifest.is_file():
        return {"items": [], "total": 0}
    try:
        rows = json.loads(manifest.read_text()).get("items", [])
    except (ValueError, AttributeError):
        raise HTTPException(503, "模特库暂时无法读取，请稍后重试。")
    items = []
    for row in rows:
        if not isinstance(row, dict) or row.get("active") is False:
            continue
        filename = str(row.get("file") or "")
        path = (root / filename).resolve()
        if not filename or path.parent != root or not path.is_file() or path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            continue
        items.append({
            "id": str(row.get("id") or Path(filename).stem),
            "name": row.get("display_name") or Path(filename).stem,
            "gender": row.get("gender"), "gender_label": row.get("gender_label"),
            "body_type": row.get("body_type"), "body_type_label": row.get("body_type_label"),
            "sort_order": row.get("sort_order") if isinstance(row.get("sort_order"), (int, float)) else 999,
            "image_url": f"/tryon-models/{quote(filename)}?v={path.stat().st_mtime_ns}",
        })
    items.sort(key=lambda x: (x["sort_order"], x["id"]))
    return {"items": items, "total": len(items)}


@router.get("/models")
def studio_models() -> dict[str, Any]:
    return model_library()


class ModelSelection(BaseModel):
    model_id: str = Field(min_length=1, max_length=80)


@router.put("/model")
def studio_model_select(payload: ModelSelection, user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    from app import closet
    model = next((x for x in model_library()["items"] if x["id"] == payload.model_id), None)
    if payload.model_id != "self" and model is None:
        raise HTTPException(404, "这位模特已不可用，请重新选择。")
    with user_storage(user["user_id"]):
        closet.update_user_preferences({"current_model_id": payload.model_id})
    return {"current_model_id": payload.model_id, "model": model}
