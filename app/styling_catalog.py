"""Delivered notebook outfits, resolved by public material ID for display and try-on."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx
from fastapi import HTTPException

from app.material_assets import MaterialRegistry, asset_content_url, material_image_path

ROOT = Path(__file__).resolve().parents[1]
DELIVERY_PATH = ROOT / "app/data/styling-delivery.v1.json"
OUTFIT_PREFIX = "report_"
CATEGORY_SLOTS = {
    "上装内搭": "top", "上装外套": "outer", "下装": "bottom", "连衣裙": "dress",
    "鞋子": "shoes", "包": "bag", "帽子": "hat", "袜子": "socks",
    "配饰": "accessory", "项链": "accessory", "腰带": "accessory", "耳环": "accessory",
    "戒指": "accessory", "手表": "accessory", "手链": "accessory", "手套": "accessory",
}


def delivery_looks() -> list[dict]:
    delivery = json.loads(DELIVERY_PATH.read_text(encoding="utf-8"))
    if delivery.get("schemaVersion") != "1.0" or not isinstance(delivery.get("looks"), list):
        raise ValueError("Invalid styling delivery")
    seen = set()
    for look in delivery["looks"]:
        binding = look["note_binding"]
        identity = (binding["templateId"], binding["noteId"])
        if identity in seen:
            raise ValueError("Duplicate delivered note")
        seen.add(identity)
        ids = [item["item_id"] for item in look["items"]]
        if not ids or len(ids) > 16 or len(set(ids)) != len(ids):
            raise ValueError("Invalid delivered items")
        if set(look["layer_sequence_inner_to_outer"]) != set(ids) or len(look["layer_sequence_inner_to_outer"]) != len(ids):
            raise ValueError("Incomplete layering sequence")
    return delivery["looks"]


def outfit_id(look: dict) -> str:
    # Version the binding so an old URL never silently points at a changed recipe.
    binding = look["note_binding"]
    digest = hashlib.sha256(json.dumps({"source": look["source_asset"]["assetId"],
        "items": [{k: v for k, v in i.items() if k != "image_asset"} | {"assetId": i["image_asset"]["assetId"]}
                  for i in look["items"]], "layers": look["layer_sequence_inner_to_outer"]},
        sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]
    return f"{OUTFIT_PREFIX}{binding['templateId']}_{binding['noteId']}_{digest}"


def _item_id(look: dict, source_id: str) -> str:
    return outfit_id(look) + "_" + hashlib.sha256(source_id.encode()).hexdigest()[:10]


def _asset_url(reference: dict) -> str:
    asset_id = reference["assetId"]
    # Registry is authoritative; delivery URLs may predate a completed upload.
    MaterialRegistry().get(asset_id)
    return asset_content_url(asset_id)


def resolve_saved_item_assets(items: list[dict]) -> list[dict]:
    """Upgrade saved library copies through the exact original-to-cutout mapping.

    Item IDs, personal edits and composition slots remain stable. Only the image
    reference is derived from the current catalog, including for try-on inputs.
    """
    if not any((item.get("source") or {}).get("type") == "styling_delivery" for item in items):
        return items
    try:
        replacements = {
            (raw["item_id"], raw["image_asset"]["sourceAssetId"]): raw["image_asset"]
            for look in delivery_looks() for raw in look["items"]
            if raw.get("image_asset", {}).get("sourceAssetId")
        }
    except (OSError, ValueError, KeyError, TypeError):
        # Saved outfits can still be opened if their source catalog is unavailable.
        return items
    resolved = []
    for item in items:
        source, assets = item.get("source") or {}, item.get("assets") or {}
        reference = replacements.get((source.get("source_item_id"), assets.get("asset_id")))
        if source.get("type") == "styling_delivery" and reference and reference["assetId"] != assets.get("asset_id"):
            try:
                url = _asset_url(reference)
            except (OSError, ValueError, KeyError):
                resolved.append(item)
                continue
            item = {**item, "image_id": reference["assetId"], "assets": {
                **assets, "asset_id": reference["assetId"], "source_asset_id": reference["sourceAssetId"],
                "cutout_path": url, "preview_path": url,
            }}
        resolved.append(item)
    return resolved


def adapt_outfit(look: dict) -> dict:
    binding = look["note_binding"]
    oid = outfit_id(look)
    items = []
    by_id = {item["item_id"]: item for item in look["items"]}
    for order, source_id in enumerate(look["layer_sequence_inner_to_outer"]):
        raw = by_id[source_id]
        slot = CATEGORY_SLOTS[raw["category"]]
        if slot == "bottom" and "裙" in raw["garment_name"]:
            slot = "skirt"
        category = "top" if slot == "outer" else "accessory" if slot in {"hat", "socks"} else slot
        url = _asset_url(raw["image_asset"])
        styling = {k: v for k, v in raw.items() if k not in {"image_asset", "asset_filename", "cutout"}}
        styling.update(source_item_id=source_id, item_id=_item_id(look, source_id),
                       paired_with_item_ids=[_item_id(look, paired) for paired in raw.get("paired_with_item_ids", [])])
        items.append({
            "item_id": _item_id(look, source_id), "image_id": raw["image_asset"]["assetId"],
            "title": raw["garment_name"], "category": category, "category_label": raw["garment_name"],
            "slot": slot, "assets": {"cutout_path": url, "preview_path": url, "asset_id": raw["image_asset"]["assetId"]},
            "wearing_instruction": raw.get("wearing_method", ""), "wear_region": raw.get("body_region", ""),
            "styling": styling, "display_order": order,
            "attributes": {"style_tags": [raw["category"]], "details": raw.get("styling_details", [])},
            "source": {"type": "styling_delivery", "source_item_id": source_id},
            "tryon_ready": True, "favorite": False, "deleted": False,
        })
    return {
        "outfit_id": oid, "title": binding["name"], "items": items,
        "item_ids": [i["item_id"] for i in items], "display_item_ids": [i["item_id"] for i in items],
        "cover_path": _asset_url(look["source_asset"]), "source_asset_id": look["source_asset"]["assetId"],
        "primary_persona": binding["persona"], "template_id": binding["templateId"],
        "source": "styling_delivery", "can_delete": False, "favorite": False, "deleted": False,
        "tryon_ready": True, "scene_tags": list(look.get("scene_tags", [])), "warnings": [],
        "layer_sequence_inner_to_outer": [_item_id(look, source_id) for source_id in look["layer_sequence_inner_to_outer"]],
    }


def get_delivered_outfit(oid: str) -> dict:
    try:
        from app.inspiration_catalog import TEMPLATE_PREFIX, inspiration_looks
        is_inspiration = oid.startswith(OUTFIT_PREFIX + TEMPLATE_PREFIX)
        looks = inspiration_looks() if is_inspiration else delivery_looks()
        look = next((look for look in looks if outfit_id(look) == oid), None)
        if look is None:
            raise HTTPException(404, "这套搭配已更新，请返回灵感库重新选择。" if is_inspiration
                                else "这套报告搭配已更新，请返回报告重新选择。")
        return adapt_outfit(look)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(503, "这套搭配的素材暂时无法加载，请稍后重试。") from exc


def delivered_tryon_plan(oid: str, photo_mode: str | None, scene_label: str | None) -> tuple[dict, dict]:
    outfit = get_delivered_outfit(oid)
    try:
        source = material_image_path(outfit["source_asset_id"])
        items = [{**item, "image_path": str(material_image_path(item["image_id"])),
                  "public_image_path": item["assets"]["cutout_path"]} for item in outfit["items"]]
    except (OSError, ValueError, KeyError, httpx.HTTPError) as exc:
        raise HTTPException(503, "搭配图片暂时无法读取，请稍后重新试穿。") from exc
    return {"source_mode": "from_outfit", "source_catalog": "styling_delivery", "outfit_id": oid, "title": outfit["title"],
            "model_photo_mode": photo_mode or "standard", "scene_label": scene_label or "",
            "style_reference": {"image_id": outfit["source_asset_id"], "image_path": str(source), "role": "overall_outfit_reference"},
            "layer_sequence_inner_to_outer": outfit["layer_sequence_inner_to_outer"], "items": items,
            "style_brief": "按照原穿搭照片及每件单品的穿法、开合、遮挡和叠穿顺序还原整套搭配。"}, outfit
