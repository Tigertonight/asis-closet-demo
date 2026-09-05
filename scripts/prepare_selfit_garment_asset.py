#!/usr/bin/env python3
"""Normalize an AI-generated garment cutout for the Selfit wardrobe.

The script removes low-alpha edge noise, trims the meaningful subject, and
places it on a transparent square canvas with stable padding. It never invents
or repaints garment pixels.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image


def prepare(source: Path, output: Path, *, size: int = 1200, padding: float = 0.10, alpha_noise: int = 8) -> dict[str, object]:
    image = Image.open(source).convert("RGBA")
    alpha = image.getchannel("A")
    cleaned_alpha = alpha.point(lambda value: 0 if value < alpha_noise else value)
    image.putalpha(cleaned_alpha)
    meaningful = cleaned_alpha.point(lambda value: 255 if value >= alpha_noise else 0)
    bbox = meaningful.getbbox()
    if not bbox:
        raise ValueError("image contains no meaningful non-transparent pixels")
    subject = image.crop(bbox)
    usable = max(1, round(size * (1 - padding * 2)))
    scale = min(usable / subject.width, usable / subject.height)
    target_size = (max(1, round(subject.width * scale)), max(1, round(subject.height * scale)))
    subject = subject.resize(target_size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    x = (size - subject.width) // 2
    y = (size - subject.height) // 2
    canvas.alpha_composite(subject, (x, y))
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, "PNG", optimize=True)

    final_alpha = canvas.getchannel("A")
    final_bbox = final_alpha.point(lambda value: 255 if value >= alpha_noise else 0).getbbox()
    total = size * size
    histogram = final_alpha.histogram()
    margins = {
        "left": final_bbox[0] / size,
        "top": final_bbox[1] / size,
        "right": (size - final_bbox[2]) / size,
        "bottom": (size - final_bbox[3]) / size,
    }
    return {
        "source": str(source),
        "output": str(output),
        "size": [size, size],
        "meaningful_bbox": list(final_bbox),
        "margins": {key: round(value, 4) for key, value in margins.items()},
        "transparent_ratio": round(histogram[0] / total, 4),
        "partial_alpha_ratio": round((total - histogram[0] - histogram[255]) / total, 4),
        "alpha_noise_threshold": alpha_noise,
        "passed": min(margins.values()) >= max(0.055, padding - 0.045),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--size", type=int, default=1200)
    parser.add_argument("--padding", type=float, default=0.10)
    parser.add_argument("--alpha-noise", type=int, default=8)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = prepare(args.source, args.output, size=args.size, padding=args.padding, alpha_noise=args.alpha_noise)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    if not result["passed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
