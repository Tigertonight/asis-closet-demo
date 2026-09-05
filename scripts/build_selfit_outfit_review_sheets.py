#!/usr/bin/env python3
"""Build one labeled contact sheet per persona for V2 outfit visual review."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PLAN = ROOT / "app/static/selfit/data/content-production-plan.v2.json"


def _asset_path(value: str) -> Path:
    if value.startswith("/static/"):
        return ROOT / "app" / value.lstrip("/")
    return ROOT / value.lstrip("/")


def build(plan_path: Path, output_dir: Path, columns: int = 5) -> list[str]:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    outfits = [*plan.get("masterOutfits", []), *plan.get("variantOutfits", [])]
    personas = sorted({str(outfit["primary_persona"]).upper() for outfit in outfits})
    output_dir.mkdir(parents=True, exist_ok=True)
    font = ImageFont.load_default()
    written: list[str] = []
    for persona in personas:
        rows = [outfit for outfit in outfits if str(outfit["primary_persona"]).upper() == persona]
        tile_w, image_h, label_h = 220, 275, 42
        row_count = (len(rows) + columns - 1) // columns
        sheet = Image.new("RGB", (tile_w * columns, (image_h + label_h) * row_count), "#f5f2f1")
        draw = ImageDraw.Draw(sheet)
        for index, outfit in enumerate(rows):
            image_path = _asset_path(str(outfit["assets"]["image_url"]))
            image = Image.open(image_path).convert("RGB")
            image.thumbnail((tile_w - 12, image_h - 12), Image.Resampling.LANCZOS)
            x = (index % columns) * tile_w
            y = (index // columns) * (image_h + label_h)
            sheet.paste(image, (x + (tile_w - image.width) // 2, y + (image_h - image.height) // 2))
            short_id = str(outfit["id"]).replace(f"outfit_{persona.lower()}_", "")
            kind = "M" if outfit.get("kind") == "master" else "V"
            draw.text((x + 8, y + image_h + 5), f"{kind} {short_id}", fill="#292526", font=font)
        output = output_dir / f"{persona.lower()}-outfits-review.jpg"
        sheet.save(output, "JPEG", quality=90, optimize=True)
        written.append(str(output))
    return written


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs/selfit-v2-outfit-review")
    parser.add_argument("--columns", type=int, default=5)
    args = parser.parse_args()
    print(json.dumps({"sheets": build(args.plan, args.output_dir, args.columns)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
