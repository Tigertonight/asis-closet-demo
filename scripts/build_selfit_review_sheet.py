#!/usr/bin/env python3
"""Build a labeled contact sheet for human review of imagegen garment batches."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def build(items: list[tuple[str, Path]], output: Path, *, columns: int = 4, tile: int = 320) -> None:
    label_height = 44
    rows = math.ceil(len(items) / columns)
    sheet = Image.new("RGB", (columns * tile, rows * (tile + label_height)), "#f6f3f1")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=20)
    for index, (job_id, path) in enumerate(items):
        image = Image.open(path).convert("RGBA")
        image.thumbnail((tile - 28, tile - 28), Image.Resampling.LANCZOS)
        x0 = (index % columns) * tile
        y0 = (index // columns) * (tile + label_height)
        background = Image.new("RGBA", (tile, tile), "#ffffff")
        background.alpha_composite(image, ((tile - image.width) // 2, (tile - image.height) // 2))
        sheet.paste(background.convert("RGB"), (x0, y0))
        draw.text((x0 + 12, y0 + tile + 10), job_id, fill="#242122", font=font)
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, "PNG", optimize=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--columns", type=int, default=4)
    parser.add_argument("items", nargs="+", help="job_id=/absolute/path.png")
    args = parser.parse_args()
    parsed: list[tuple[str, Path]] = []
    for item in args.items:
        job_id, separator, raw_path = item.partition("=")
        if not separator or not job_id or not raw_path:
            raise ValueError(f"invalid review item: {item}")
        path = Path(raw_path)
        if not path.is_file():
            raise FileNotFoundError(path)
        parsed.append((job_id, path))
    build(parsed, args.output, columns=max(1, args.columns))
    print(args.output)


if __name__ == "__main__":
    main()
