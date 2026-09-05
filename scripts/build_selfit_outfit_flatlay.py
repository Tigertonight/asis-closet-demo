#!/usr/bin/env python3
"""Render one Selfit outfit recipe from verified transparent garment PNGs."""

from __future__ import annotations

import argparse
import json
import hashlib
import sys
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.outfit_layout import fit_outfit_image

CATEGORY_BOXES = {
    "outer": [70, 90, 560, 610],
    "top": [170, 120, 470, 520],
    "dress": [110, 120, 610, 930],
    "bottom": [170, 610, 500, 680],
    "skirt": [150, 610, 540, 630],
    "hat": [820, 110, 260, 240],
    "bag": [780, 360, 330, 400],
    "scarf": [790, 760, 300, 270],
    "accessory": [820, 760, 250, 250],
    "shoes": [700, 1050, 420, 310],
}


def _asset_path(value: str) -> Path:
    if value.startswith("/static/"):
        return ROOT / "app" / value.lstrip("/")
    return ROOT / value.lstrip("/")


def _fit(image: Image.Image, box: list[int]) -> tuple[Image.Image, tuple[int, int]]:
    x, y, width, height = box
    scale = min(width / image.width, height / image.height)
    size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    resized = image.resize(size, Image.Resampling.LANCZOS)
    return resized, (x + (width - size[0]) // 2, y + (height - size[1]) // 2)


def build(manifest_path: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    outfit = manifest["outfit"]
    canvas_config = outfit.get("canvas") or {}
    width = int(canvas_config.get("width") or 1200)
    height = int(canvas_config.get("height") or 1500)
    background = str(canvas_config.get("background") or "#fcfafa")
    canvas = Image.new("RGBA", (width, height), background)
    garments = {str(item["id"]): item for item in manifest.get("garments", [])}
    rendered = []
    for placement in sorted(outfit.get("placements", []), key=lambda item: int(item.get("z") or 0)):
        garment = garments[str(placement["garment_id"])]
        source = _asset_path(str(garment["assets"]["image_url"]))
        if not source.exists():
            raise FileNotFoundError(source)
        image = Image.open(source).convert("RGBA")
        fitted, position = _fit(image, [int(value) for value in placement["box"]])
        canvas.alpha_composite(fitted, position)
        rendered.append(str(garment["id"]))
    output = _asset_path(str(outfit["assets"]["image_url"]))
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(output, "WEBP", quality=94, method=6)
    expected = [str(value) for value in outfit.get("garment_ids") or []]
    passed = len(rendered) == len(expected) == len(set(rendered)) and set(rendered) == set(expected)
    return {"output": str(output), "size": [width, height], "rendered": rendered, "passed": passed}


def build_from_plan(plan_path: Path, outfit_id: str | None = None, *, designer_approved: bool = False) -> dict[str, Any]:
    """Render one or every ready recipe from the expansion production plan."""

    if designer_approved:
        raise ValueError("--designer-approved cannot certify an image; record revision-bound technical/aesthetic/persona/context reviews separately")

    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    garments = {job["record_template"]["id"]: job["record_template"] for job in plan.get("garmentJobs", [])}
    outfits = [*plan.get("masterOutfits", []), *plan.get("variantOutfits", [])]
    if outfit_id:
        outfits = [outfit for outfit in outfits if outfit.get("id") == outfit_id]
        if not outfits:
            raise KeyError(f"unknown outfit id: {outfit_id}")
    completed = []
    skipped = []
    for outfit in outfits:
        records = [garments[item_id] for item_id in outfit.get("garment_ids", [])]
        missing = [_asset_path(str(item["assets"]["image_url"])) for item in records if not _asset_path(str(item["assets"]["image_url"])).exists()]
        if missing:
            skipped.append({"id": outfit["id"], "missing": [str(path) for path in missing]})
            continue
        width, height = 1200, 1500
        canvas = Image.new("RGBA", (width, height), "#fcfafa")
        rendered = []
        placement_checks = []
        slots = [item["category"] for item in records]
        accessory_count = 0
        for z, garment in enumerate(records):
            category = str(garment["category"])
            box = CATEGORY_BOXES.get(category, [760, 760, 300, 300])
            image = Image.open(_asset_path(str(garment["assets"]["image_url"]))).convert("RGBA")
            slot = category
            if category == "accessory":
                accessory_count += 1
                slot = f"accessory_{accessory_count}"
            fitted, position = fit_outfit_image(image, slot, slots)
            bbox = fitted.getchannel("A").getbbox()
            placement_checks.append(bool(bbox) and position[0] + bbox[0] >= 0 and position[1] + bbox[1] >= 0
                                    and position[0] + bbox[2] <= width and position[1] + bbox[3] <= height)
            canvas.alpha_composite(fitted, position)
            rendered.append(str(garment["id"]))
        encoded = BytesIO()
        canvas.convert("RGB").save(encoded, "WEBP", quality=94, method=6)
        image_bytes = encoded.getvalue()
        digest = hashlib.sha256(image_bytes).hexdigest()
        old_public_path = Path(str(outfit["assets"]["image_url"]))
        new_public_path = old_public_path.with_name(f"{outfit['id']}-r{digest[:16]}.webp")
        output = _asset_path(str(new_public_path))
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(image_bytes)
        outfit["assets"]["image_url"] = str(new_public_path)
        outfit["assets"]["sha256"] = digest
        passed = len(rendered) == len(set(rendered)) == len(outfit.get("garment_ids", [])) and set(rendered) == set(outfit.get("garment_ids", []))
        qa_path = output.with_suffix(".qa.json")
        qa_path.write_text(json.dumps({
            "outfit_id": outfit["id"], "size": [width, height], "rendered": rendered,
            "all_items_once": passed, "designer_reviewed": False,
            "asset_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "checks": {"within_canvas": all(placement_checks), "bag_hat_shoes_complete": None, "no_gray_bars": None},
            "review_notes": ["画布内不等于物件完整；遮挡、边缘和搭配需独立视觉审查"],
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        outfit["annotation"] = {
            "status": "machine_draft", "source": "source_record", "confidence": 0.0,
            "review_notes": ["等待平铺视觉审核；此置信度不代表人格命中率"],
        }
        outfit.pop("quality_review", None)
        completed.append({"id": outfit["id"], "output": str(output), "rendered": rendered, "passed": passed})
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"completed": completed, "skipped": skipped, "passed": bool(completed) and all(item["passed"] for item in completed)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--outfit-id")
    parser.add_argument("--production-plan", action="store_true")
    parser.add_argument("--designer-approved", action="store_true")
    args = parser.parse_args()
    result = build_from_plan(args.manifest, args.outfit_id, designer_approved=args.designer_approved) if args.production_plan else build(args.manifest)
    print(json.dumps(result, ensure_ascii=False))
    if not result["passed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
