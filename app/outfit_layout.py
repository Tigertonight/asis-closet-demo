"""Canonical flat-lays shared by catalog production and private wardrobes.

Only transparent padding is trimmed. Recipes and approved source assets stay
unchanged; catalog covers are disposable, versioned derivatives.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image

from app.outfit_layered_layout import is_layered, layered_box

LAYOUT_VERSION = "unified-flatlay-v1"
CANVAS = (1200, 1500)
BACKGROUND = "#fcfafa"
MAIN_SPAN = (160, 1330)
MAIN_GAP = 24


def outfit_box(slot: str, slots, size=CANVAS):
    slots = set(slots)
    if is_layered(slots) or slot not in {"top", "bottom", "skirt", "dress", "outer"}:
        return layered_box(slot, size)
    # The dress occupies exactly the combined upper/lower span. Waist edges
    # face each other across one small, fixed gap instead of centering in cells.
    boxes = {
        "top": (130, 160, 770, 620),
        "bottom": (150, 644, 750, 1330),
        "skirt": (130, 644, 770, 1330),
        "dress": (100, 160, 800, 1330),
        "outer": (100, 160, 800, 620 if slots & {"bottom", "skirt"} else 1330),
    }
    return tuple(round(v * size[i % 2] / CANVAS[i % 2]) for i, v in enumerate(boxes[slot]))


def vertical_align(slot, slots):
    if slot == "top" or (slot == "outer" and not is_layered(slots) and set(slots) & {"bottom", "skirt"}):
        return "end"
    return "start" if slot in {"outer", "dress", "bottom", "skirt"} else "center"


def fit_outfit_image(image, slot, slots, size=CANVAS):
    x1, y1, x2, y2 = outfit_box(slot, slots, size)
    image = image.convert("RGBA")
    bbox = image.getchannel("A").getbbox()
    if not bbox:
        raise ValueError("Empty cutout")
    image = image.crop(bbox)
    scale = min((x2 - x1) / image.width, (y2 - y1) / image.height)
    image = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.Resampling.LANCZOS)
    align = vertical_align(slot, slots)
    y = y2 - image.height if align == "end" else y1 if align == "start" else y1 + (y2 - y1 - image.height) // 2
    return image, (x1 + (x2 - x1 - image.width) // 2, y)


def outfit_preview_url(garments):
    signature = sorted((g["id"], g["category"], g["assets"]["image_url"], g["assets"].get("sha256", "")) for g in garments)
    digest = hashlib.sha256(json.dumps([LAYOUT_VERSION, signature], sort_keys=True).encode()).hexdigest()[:24]
    return f"/static/selfit/assets/content_v2/layouts/{LAYOUT_VERSION}/{digest}.webp"


def render_outfit_preview(garments: list[dict], root: Path):
    if not garments or len({g["id"] for g in garments}) != len(garments):
        raise ValueError("Empty recipe or duplicate garment")
    slots = [g["category"] for g in garments]
    canvas = Image.new("RGBA", CANVAS, BACKGROUND)
    placements, used = [], set()
    accessory_count = 0
    for garment in garments:
        slot = garment["category"]
        if slot == "accessory":
            accessory_count += 1
            slot = f"accessory_{accessory_count}"
        if (slot in used or (slot == "dress" and used & {"top", "bottom", "skirt"})
                or (slot in {"top", "bottom", "skirt"} and "dress" in used)
                or (slot in {"bottom", "skirt"} and used & {"bottom", "skirt"})):
            raise ValueError(f"Conflicting slot: {slot}")
        used.add(slot)
        url = garment["assets"]["image_url"]
        source = (root / "app" / url.lstrip("/")).resolve()
        if not url.startswith("/static/") or not source.is_relative_to((root / "app/static").resolve()):
            raise ValueError("Only local published assets may be composited")
        with Image.open(source) as original:
            image, (x, y) = fit_outfit_image(original, slot, slots)
        canvas.alpha_composite(image, (x, y))
        placements.append({"garment_id": garment["id"], "slot": slot, "box": [x, y, x + image.width, y + image.height]})
    url = outfit_preview_url(garments)
    output = root / "app" / url.lstrip("/")
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(output, "WEBP", quality=94, method=4)
    report = {"layout_version": LAYOUT_VERSION, "image_url": url, "size": list(CANVAS), "placements": placements}
    output.with_suffix(".qa.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
