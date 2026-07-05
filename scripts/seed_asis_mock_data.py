from __future__ import annotations

import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import closet


GENERATED_CONTACT_SHEET = Path(
    "/Users/yuanzexiang/.codex/generated_images/019f286a-93e3-75d0-99e4-258da5054f2e/"
    "ig_0126a61782747af2016a47d5f1d7d48191944bdcdd5eecbc5c.png"
)

ITEMS = [
    {
        "item_id": "mock_top_striped_shirt",
        "category": "top",
        "label": "条纹衬衫",
        "colors": ["蓝白"],
        "tags": ["通勤", "清爽", "宽松"],
        "cell": 0,
        "fill": "#dfe8ff",
    },
    {
        "item_id": "mock_top_yellow_jacket",
        "category": "top",
        "label": "淡黄短外套",
        "colors": ["浅黄"],
        "tags": ["甜酷", "短款", "春夏"],
        "cell": 1,
        "fill": "#fff0a8",
    },
    {
        "item_id": "mock_skirt_navy_pleated",
        "category": "skirt",
        "label": "藏蓝百褶裙",
        "colors": ["藏蓝"],
        "tags": ["学院", "显瘦", "半身裙"],
        "cell": 2,
        "fill": "#243a5a",
    },
    {
        "item_id": "mock_bottom_blue_pants",
        "category": "bottom",
        "label": "浅蓝阔腿裤",
        "colors": ["浅蓝"],
        "tags": ["休闲", "长裤", "宽松"],
        "cell": 3,
        "fill": "#d7e7ff",
    },
    {
        "item_id": "mock_shoes_black_slingback",
        "category": "shoes",
        "label": "黑色尖头鞋",
        "colors": ["黑色"],
        "tags": ["通勤", "精致", "高跟"],
        "cell": 4,
        "fill": "#111111",
    },
    {
        "item_id": "mock_shoes_silver_sneaker",
        "category": "shoes",
        "label": "银色运动鞋",
        "colors": ["银色"],
        "tags": ["运动", "轻便", "休闲"],
        "cell": 5,
        "fill": "#d7dbe0",
    },
    {
        "item_id": "mock_dress_cream_sleeveless",
        "category": "dress",
        "label": "米白连衣裙",
        "colors": ["米白"],
        "tags": ["温柔", "连体装", "约会"],
        "cell": 6,
        "fill": "#fff6e6",
    },
    {
        "item_id": "mock_bag_yellow_tote",
        "category": "bag",
        "label": "浅黄手提包",
        "colors": ["浅黄"],
        "tags": ["配饰", "小包", "亮色"],
        "cell": 7,
        "fill": "#ffe68a",
    },
]

OUTFITS = [
    {
        "outfit_id": "mock_outfit_office_monday",
        "title": "周一清爽通勤",
        "item_ids": ["mock_top_striped_shirt", "mock_bottom_blue_pants", "mock_shoes_black_slingback", "mock_bag_yellow_tote"],
        "scene_tags": ["通勤", "面试"],
        "favorite_count": 36,
    },
    {
        "outfit_id": "mock_outfit_weekend_yellow",
        "title": "周末淡黄灵感",
        "item_ids": ["mock_top_yellow_jacket", "mock_skirt_navy_pleated", "mock_shoes_silver_sneaker", "mock_bag_yellow_tote"],
        "scene_tags": ["周末", "生日派对"],
        "favorite_count": 40,
    },
    {
        "outfit_id": "mock_outfit_date_cream",
        "title": "二人世界温柔套装",
        "item_ids": ["mock_dress_cream_sleeveless", "mock_shoes_black_slingback", "mock_bag_yellow_tote"],
        "scene_tags": ["约会", "婚礼"],
        "favorite_count": 48,
    },
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return fallback
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    return fallback


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def _public(path: Path) -> str:
    return closet._public_closet_path(path) or str(path)


def _load_or_create_contact_sheet(seed_dir: Path) -> Image.Image:
    target = seed_dir / "source_contact_sheet.png"
    if GENERATED_CONTACT_SHEET.exists():
        shutil.copyfile(GENERATED_CONTACT_SHEET, target)
        return Image.open(target).convert("RGB")

    sheet = Image.new("RGB", (2000, 1000), "#f6f7f9")
    for item in ITEMS:
        crop = _draw_placeholder_item(item, (460, 460)).convert("RGB")
        index = int(item["cell"])
        x = (index % 4) * 500 + 20
        y = (index // 4) * 500 + 20
        sheet.paste(crop, (x, y))
    sheet.save(target)
    return sheet


def _crop_contact_cell(sheet: Image.Image, cell: int) -> Image.Image:
    cols = 4
    rows = 2
    cell_w = sheet.width // cols
    cell_h = sheet.height // rows
    left = (cell % cols) * cell_w
    top = (cell // cols) * cell_h
    return sheet.crop((left, top, left + cell_w, top + cell_h))


def _remove_light_background(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    pixels = rgba.load()
    for y in range(rgba.height):
        for x in range(rgba.width):
            r, g, b, a = pixels[x, y]
            spread = max(r, g, b) - min(r, g, b)
            is_soft_white_bg = r > 225 and g > 225 and b > 225 and spread < 14
            is_near_white_bg = r > 242 and g > 242 and b > 242
            if is_soft_white_bg or is_near_white_bg:
                pixels[x, y] = (255, 255, 255, 0)
            elif r > 218 and g > 218 and b > 218 and spread < 18:
                pixels[x, y] = (r, g, b, int(a * 0.38))
    return rgba


def _trim_light_margins(image: Image.Image) -> Image.Image:
    transparent = _remove_light_background(image)
    bbox = transparent.getchannel("A").getbbox()
    if not bbox:
        return image
    left, top, right, bottom = bbox
    pad_x = max(10, int((right - left) * 0.10))
    pad_y = max(10, int((bottom - top) * 0.10))
    left = max(0, left - pad_x)
    top = max(0, top - pad_y)
    right = min(image.width, right + pad_x)
    bottom = min(image.height, bottom + pad_y)
    return image.crop((left, top, right, bottom))


def _draw_placeholder_item(item: dict[str, Any], size: tuple[int, int] = (900, 900)) -> Image.Image:
    image = Image.new("RGBA", size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)
    w, h = size
    fill = str(item["fill"])
    category = item["category"]
    if category == "top":
        draw.polygon([(w * .36, h * .18), (w * .64, h * .18), (w * .78, h * .44), (w * .66, h * .52), (w * .62, h * .82), (w * .38, h * .82), (w * .34, h * .52), (w * .22, h * .44)], fill=fill)
        if "striped" in item["item_id"]:
            for x in range(int(w * .38), int(w * .62), 22):
                draw.line((x, h * .2, x + 26, h * .82), fill="#7d95c5", width=8)
    elif category == "bottom":
        draw.polygon([(w * .38, h * .14), (w * .62, h * .14), (w * .72, h * .86), (w * .56, h * .86), (w * .50, h * .32), (w * .44, h * .86), (w * .28, h * .86)], fill=fill)
    elif category == "skirt":
        draw.polygon([(w * .34, h * .2), (w * .66, h * .2), (w * .78, h * .82), (w * .22, h * .82)], fill=fill)
        for x in range(int(w * .30), int(w * .72), 34):
            draw.line((x, h * .24, x - 22, h * .8), fill="#526681", width=4)
    elif category == "dress":
        draw.polygon([(w * .42, h * .14), (w * .58, h * .14), (w * .68, h * .42), (w * .82, h * .86), (w * .18, h * .86), (w * .32, h * .42)], fill=fill)
    elif category == "shoes":
        draw.ellipse((w * .18, h * .48, w * .84, h * .68), fill=fill)
        draw.polygon([(w * .58, h * .58), (w * .92, h * .62), (w * .70, h * .72)], fill=fill)
    elif category == "bag":
        draw.rounded_rectangle((w * .30, h * .34, w * .70, h * .78), radius=24, fill=fill)
        draw.arc((w * .38, h * .16, w * .62, h * .48), 180, 360, fill="#c7a44a", width=12)
    else:
        draw.ellipse((w * .3, h * .3, w * .7, h * .7), fill=fill)
    return image


def _resize_for_product_card(image: Image.Image, max_side: int = 760) -> Image.Image:
    scale = min(max_side / image.width, max_side / image.height)
    target_size = (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
    return image.resize(target_size, Image.Resampling.LANCZOS)


def _prepare_item_assets(sheet: Image.Image, seed_dir: Path) -> list[dict[str, Any]]:
    now = _now_iso()
    source_path = seed_dir / "source_contact_sheet.png"
    prepared = []
    for item in ITEMS:
        item_dir = closet.CLOSET_ITEM_DIR / str(item["item_id"])
        item_dir.mkdir(parents=True, exist_ok=True)
        cropped = _trim_light_margins(_crop_contact_cell(sheet, int(item["cell"]))).convert("RGBA")
        cutout = _remove_light_background(cropped)
        preview_path = item_dir / "preview.png"
        cutout_path = item_dir / "cutout.png"
        mask_path = item_dir / "mask.png"
        cropped = _resize_for_product_card(cropped)
        preview = Image.new("RGBA", (900, 900), (255, 255, 255, 0))
        preview.paste(cropped, ((900 - cropped.width) // 2, (900 - cropped.height) // 2))
        preview.save(preview_path)
        cutout = _resize_for_product_card(cutout)
        cutout_canvas = Image.new("RGBA", (900, 900), (255, 255, 255, 0))
        cutout_canvas.paste(cutout, ((900 - cutout.width) // 2, (900 - cutout.height) // 2), cutout)
        cutout = cutout_canvas
        cutout.save(cutout_path)
        cutout.getchannel("A").save(mask_path)
        prepared.append(
            {
                "item_id": item["item_id"],
                "category": item["category"],
                "category_label": item["label"],
                "source": {
                    "type": "mock_seed",
                    "filename": source_path.name,
                    "image_index": item["cell"],
                    "source_path": _public(source_path),
                    "width": sheet.width,
                    "height": sheet.height,
                    "crop_box": [],
                },
                "assets": {
                    "cutout_path": _public(cutout_path),
                    "mask_path": _public(mask_path),
                    "preview_path": _public(preview_path),
                },
                "attributes": {
                    "colors": item["colors"],
                    "material": [],
                    "fit": [],
                    "sleeve": [],
                    "neckline": [],
                    "pattern": [],
                    "style_tags": item["tags"],
                },
                "quality": {"status": "usable", "score": 0.92, "reasons": ["mock_seed"]},
                "pipeline": {"detector": {"provider": "mock_seed", "status": "generated"}},
                "favorite": False,
                "note": "asis 风格 demo 基础物料",
                "created_at": now,
                "updated_at": now,
                "user_edits": {},
                "deleted": False,
            }
        )
    return prepared


def _upsert_items(items: list[dict[str, Any]]) -> None:
    manifest = _read_json(closet.CLOSET_MANIFEST_PATH, {"version": 1, "items": []})
    seed_ids = {item["item_id"] for item in items}
    now = _now_iso()
    for existing_item in manifest.setdefault("items", []):
        if existing_item.get("item_id") not in seed_ids and existing_item.get("source", {}).get("type") in {"reprocess", "upload"}:
            existing_item["deleted"] = True
            existing_item["updated_at"] = now
            existing_item["note"] = "隐藏测试生成的占位单品，避免污染 asis demo"
    existing = {item.get("item_id"): index for index, item in enumerate(manifest.setdefault("items", []))}
    for item in items:
        index = existing.get(item["item_id"])
        if index is None:
            manifest["items"].append(item)
        else:
            created_at = manifest["items"][index].get("created_at") or item["created_at"]
            manifest["items"][index] = {**item, "created_at": created_at}
    _write_json(closet.CLOSET_MANIFEST_PATH, manifest)


def _upsert_outfits() -> list[dict[str, Any]]:
    now = _now_iso()
    manifest = _read_json(closet.OUTFIT_MANIFEST_PATH, {"version": 1, "outfits": [], "plans": []})
    seed_outfit_ids = {outfit["outfit_id"] for outfit in OUTFITS}
    seed_item_ids = {item["item_id"] for item in ITEMS}
    for existing_outfit in manifest.setdefault("outfits", []):
        item_ids = set(existing_outfit.get("item_ids", []))
        if existing_outfit.get("outfit_id") not in seed_outfit_ids and not item_ids.issubset(seed_item_ids):
            existing_outfit["deleted"] = True
            existing_outfit["updated_at"] = now
    existing = {outfit.get("outfit_id"): index for index, outfit in enumerate(manifest.setdefault("outfits", []))}
    created = []
    for outfit in OUTFITS:
        items = [closet.get_closet_item(item_id) for item_id in outfit["item_ids"]]
        layout = closet._build_outfit_cover(outfit["outfit_id"], items)
        row = {
            **outfit,
            "cover_path": _public(layout["path"]),
            "layout_snapshot_path": _public(layout["path"]),
            "layout_version": layout["layout_version"],
            "layout_slots": layout["layout_slots"],
            "display_item_ids": layout["display_item_ids"],
            "overflow_items": layout["overflow_items"],
            "warnings": layout["warnings"],
            "created_at": now,
            "updated_at": now,
            "deleted": False,
        }
        index = existing.get(outfit["outfit_id"])
        if index is None:
            manifest["outfits"].append(row)
        else:
            created_at = manifest["outfits"][index].get("created_at") or row["created_at"]
            manifest["outfits"][index] = {**row, "created_at": created_at}
        created.append(row)
    manifest.setdefault("plans", [])
    _write_json(closet.OUTFIT_MANIFEST_PATH, manifest)
    return created


def _seed_tryon_records(outfits: list[dict[str, Any]]) -> None:
    manifest = _read_json(closet.TRYON_RECORDS_MANIFEST_PATH, {"version": 1, "records": []})
    seed_outfit_ids = {outfit["outfit_id"] for outfit in OUTFITS}
    now = _now_iso()
    for existing_record in manifest.setdefault("records", []):
        if existing_record.get("outfit_id") not in seed_outfit_ids:
            existing_record["deleted"] = True
            existing_record["updated_at"] = now
    existing = {record.get("record_id"): index for index, record in enumerate(manifest.setdefault("records", []))}
    for outfit in outfits[:3]:
        record_id = f"mock_record_{outfit['outfit_id']}"
        resolved = closet.get_outfit(outfit["outfit_id"])
        result_path = closet._build_mock_tryon_image(record_id, resolved)
        now = _now_iso()
        record = {
            "record_id": record_id,
            "mode": "mock_from_outfit",
            "status": "generated",
            "outfit_id": outfit["outfit_id"],
            "outfit_title": outfit["title"],
            "image_path": _public(result_path),
            "scene_tags": outfit.get("scene_tags", []),
            "created_at": now,
            "updated_at": now,
            "deleted": False,
            "note": "初始化模拟试穿记录",
        }
        index = existing.get(record_id)
        if index is None:
            manifest["records"].append(record)
        else:
            created_at = manifest["records"][index].get("created_at") or record["created_at"]
            manifest["records"][index] = {**record, "created_at": created_at}
    _write_json(closet.TRYON_RECORDS_MANIFEST_PATH, manifest)


def seed() -> dict[str, Any]:
    closet.CLOSET_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    closet.CLOSET_SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    closet.CLOSET_ITEM_DIR.mkdir(parents=True, exist_ok=True)
    closet.OUTFIT_DIR.mkdir(parents=True, exist_ok=True)
    closet.TRYON_RECORD_DIR.mkdir(parents=True, exist_ok=True)
    seed_dir = closet.CLOSET_OUTPUT_DIR / "mock_seed"
    seed_dir.mkdir(parents=True, exist_ok=True)
    sheet = _load_or_create_contact_sheet(seed_dir)
    items = _prepare_item_assets(sheet, seed_dir)
    _upsert_items(items)
    outfits = _upsert_outfits()
    _seed_tryon_records(outfits)
    return {
        "status": "seeded",
        "items": len(items),
        "outfits": len(outfits),
        "tryon_records": min(3, len(outfits)),
        "contact_sheet": str(seed_dir / "source_contact_sheet.png"),
        "schema": str(closet.ROOT_DIR / "docs" / "ASIS_DATA_SCHEMA.md"),
        "fingerprint": hashlib.sha256(json.dumps([item["item_id"] for item in items]).encode("utf-8")).hexdigest()[:12],
    }


if __name__ == "__main__":
    print(json.dumps(seed(), ensure_ascii=False, indent=2))
