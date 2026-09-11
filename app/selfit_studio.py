"""Save a personal outfit assembled from owned wardrobe or published library pieces."""
from copy import deepcopy
from threading import RLock
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import get_current_user
from app.storage import user_storage

router = APIRouter(prefix="/selfit/try-on", tags=["selfit-studio"])
_save_lock = RLock()


@router.get("/inspiration-topics")
def studio_inspiration_topics(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    from app.inspiration_catalog import inspiration_topics

    try:
        return inspiration_topics()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(503, "主题穿搭暂时无法加载，请稍后重试。") from exc


def personal_wardrobe() -> dict[str, Any]:
    """A library copy used for try-on does not imply wardrobe ownership."""
    from app import closet

    items = closet.list_closet_items()["items"]
    personal = [item for item in items if item.get("is_default") or item.get("favorite") or
                item.get("source", {}).get("type") in {"upload", "xhs_link", "web_link", "reprocess"} or
                item.get("source", {}).get("upload")]
    owned_ids = {item["item_id"] for item in personal}
    outfits = [outfit for outfit in closet.list_outfits()["outfits"]
               if outfit.get("favorite") or owned_ids.intersection(outfit.get("item_ids", []))]
    return {"items": personal, "outfits": outfits}


@router.get("/wardrobe")
def studio_wardrobe(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    with user_storage(user["user_id"]):
        return personal_wardrobe()


@router.post("/items/{item_id}/outfits")
def studio_item_outfits(item_id: str, user: dict[str, Any] = Depends(get_current_user),
                       body_profile: Literal["standard", "curvy"] = "standard") -> dict[str, Any]:
    from app import closet
    from app.selfit_outfit_match import match_notebook_outfit

    with user_storage(user["user_id"]):
        anchor = closet.get_closet_item(item_id)
        gender = "male" if user.get("gender") == "male" else "female"
        return match_notebook_outfit(anchor, user["user_id"], body_profile, gender=gender)


class StudioOutfit(BaseModel):
    item_ids: list[str] = Field(min_length=1, max_length=16)
    title: str = Field(default="我的搭配", max_length=48)
    favorite: bool = False
    canvas_layout: list[dict[str, Any]] | None = Field(default=None, max_length=16)


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
        # Notebook cutouts are public library assets too, but are copied only on save.
        from app.styling_catalog import OUTFIT_PREFIX, get_delivered_outfit
        for oid in {key.rsplit("_", 1)[0] for key in ids if key not in owned and key.startswith(OUTFIT_PREFIX)}:
            for item in get_delivered_outfit(oid)["items"]:
                published[item["item_id"]] = item
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
        return closet.create_outfit({"item_ids": ids, "title": payload.title, "favorite": payload.favorite, "canvas_layout": payload.canvas_layout})


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
    from app.material_assets import MaterialRegistry, asset_content_url
    from app.model_assets import load_model_manifest

    root = tryon.TRYON_MODEL_FIXTURE_DIR.resolve()
    manifest = root / "manifest.json"
    if not manifest.is_file():
        return {"items": [], "total": 0}
    try:
        rows = load_model_manifest(root).get("items", [])
    except (ValueError, AttributeError):
        raise HTTPException(503, "模特库暂时无法读取，请稍后重试。")
    items = []
    for row in rows:
        if not isinstance(row, dict) or row.get("active") is False:
            continue
        filename = str(row.get("file") or "")
        path = (root / filename).resolve()
        if row.get("image_asset_id"):
            try:
                MaterialRegistry().get(row["image_asset_id"])
                image_url = asset_content_url(row["image_asset_id"])
            except (KeyError, ValueError):
                continue
            if not row.get("id"):
                continue
        else:
            if not filename or path.parent != root or not path.is_file() or path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
                continue
            image_url = f"/tryon-models/{quote(filename)}?v={path.stat().st_mtime_ns}"
        items.append({
            "id": str(row.get("id") or Path(filename).stem),
            "name": row.get("display_name") or Path(filename).stem,
            "gender": row.get("gender"), "gender_label": row.get("gender_label"),
            "body_type": row.get("body_type"), "body_type_label": row.get("body_type_label"),
            "sort_order": row.get("sort_order") if isinstance(row.get("sort_order"), (int, float)) else 999,
            "image_url": image_url,
            "default_for_gender": row.get("default_for_gender") is True,
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
