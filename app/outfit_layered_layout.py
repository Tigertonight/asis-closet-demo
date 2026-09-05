"""Non-overlapping, versioned previews; never change a recipe or its source assets."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image

LAYERED_LAYOUT_VERSION = "layered-side-by-side-v1"
LAYERED_CANVAS = (1200, 1500)


def is_layered(slots) -> bool:
    slots = set(slots)
    return "outer" in slots and bool(slots & {"top", "dress"})


def layered_box(slot: str, size=LAYERED_CANVAS) -> tuple[int, int, int, int]:
    """Outer at left, inner/lower in the middle, a fixed accessory rail at right.

    Coordinates describe disjoint safe regions, not source-image canvases.
    Shoes sit above the bottom-right model selector in the detail preview.
    """
    boxes = {
        "outer": (70, 160, 420, 1230),
        "top": (450, 160, 800, 640),
        "bottom": (450, 664, 800, 1330),
        "skirt": (450, 664, 800, 1330),
        "dress": (450, 160, 800, 1330),
        "hat": (850, 90, 1130, 260),
        "scarf": (850, 280, 1130, 390),
        "bag": (850, 410, 1130, 730),
        "accessory_1": (860, 750, 1120, 850),
        "shoes": (840, 880, 1130, 1080),
        "socks": (860, 1100, 1120, 1200),
        "accessory_2": (860, 1220, 1120, 1330),
    }
    box = boxes[slot]
    return tuple(round(value * size[index % 2] / LAYERED_CANVAS[index % 2]) for index, value in enumerate(box))


def layered_preview_url(garments: list[dict]) -> str | None:
    if not is_layered(item["category"] for item in garments):
        return None
    signature = [(item["id"], item["category"], item["assets"]["image_url"], item["assets"].get("sha256")) for item in garments]
    digest = hashlib.sha256(json.dumps([LAYERED_LAYOUT_VERSION, sorted(signature)], sort_keys=True).encode()).hexdigest()[:24]
    return f"/static/selfit/assets/content_v2/layouts/{LAYERED_LAYOUT_VERSION}/{digest}.webp"


def fit_layered_image(image: Image.Image, slot: str, size=LAYERED_CANVAS):
    box = layered_box(slot, size)
    cutout = image.convert("RGBA")
    bbox = cutout.getchannel("A").getbbox()
    if not bbox:
        raise ValueError("Empty cutout")
    cutout = cutout.crop(bbox)
    cutout.thumbnail((box[2] - box[0], box[3] - box[1]), Image.Resampling.LANCZOS)
    x = box[0] + (box[2] - box[0] - cutout.width) // 2
    y = box[3] - cutout.height if slot == "top" else box[1] if slot in {"outer", "bottom", "skirt", "dress"} else box[1] + (box[3] - box[1] - cutout.height) // 2
    return cutout, (x, y)


def render_layered_preview(garments: list[dict], root: Path) -> dict:
    url = layered_preview_url(garments)
    if not url:
        raise ValueError("A layered preview needs an outer and an inner garment")
    if len({item["id"] for item in garments}) != len(garments):
        raise ValueError("Duplicate garment in recipe")
    canvas = Image.new("RGBA", LAYERED_CANVAS, "#fcfafa")
    placements, used = [], set()
    accessory_count = 0
    for item in garments:
        slot = item["category"]
        if slot == "accessory":
            accessory_count += 1
            slot = f"accessory_{accessory_count}"
        if (slot in used
                or (slot == "dress" and used & {"top", "bottom", "skirt"})
                or (slot in {"top", "bottom", "skirt"} and "dress" in used)
                or (slot in {"bottom", "skirt"} and used & {"bottom", "skirt"})):
            raise ValueError(f"Conflicting slot: {slot}")
        used.add(slot)
        source_url = item["assets"]["image_url"]
        if not source_url.startswith("/static/"):
            raise ValueError("Only local published cutouts may be composited")
        source = (root / "app" / source_url.lstrip("/")).resolve()
        if not source.is_relative_to((root / "app/static").resolve()):
            raise ValueError("Asset escapes static directory")
        with Image.open(source) as original:
            cutout = original.convert("RGBA")
        cutout, (x, y) = fit_layered_image(cutout, slot)
        canvas.alpha_composite(cutout, (x, y))
        placements.append({"garment_id": item["id"], "slot": slot, "box": [x, y, x + cutout.width, y + cutout.height]})
    output = root / "app" / url.lstrip("/")
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(output, "WEBP", quality=94, method=4)
    report = {"layout_version": LAYERED_LAYOUT_VERSION, "image_url": url, "placements": placements}
    output.with_suffix(".qa.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
