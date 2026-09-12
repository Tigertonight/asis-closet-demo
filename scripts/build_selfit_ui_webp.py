#!/usr/bin/env python3
"""Build lightweight UI artwork from the retained PNG masters (no uploads)."""
from pathlib import Path

from PIL import Image


ASSETS = Path(__file__).resolve().parents[1] / "app/static/selfit/assets"
FEMALE = (
    "face-diamond", "face-square", "face-round", "face-oval", "face-heart",
    "body-pear", "body-inverted-triangle", "body-hourglass", "body-rectangle", "body-apple",
)
MALE_FACE = ("square", "diamond", "inverted-triangle", "oval", "round")
MALE_BODY = ("trapezoid", "triangle", "inverted-triangle", "rectangle", "oval")


def main() -> None:
    jobs = [(f"manual-selection/{name}@4x.png", None, 90) for name in FEMALE]
    jobs += [(f"manual-selection/male/face-{name}.png", None, 85) for name in MALE_FACE]
    jobs += [(f"manual-selection/male/body-{name}-no-label.png", (360, 900), 85) for name in MALE_BODY]
    jobs += [
        ("onboarding-splash@2x.png", None, 88),
        ("login-persona-board@2x.png", (900, 1100), 88),
    ]
    before = after = 0
    for relative, bounds, quality in jobs:
        source = ASSETS / relative
        target = source.with_suffix(".webp")
        with Image.open(source) as original:
            artwork = original.convert("RGBA")
            if bounds:
                artwork.thumbnail(bounds, Image.Resampling.LANCZOS)
            artwork.save(target, "WEBP", quality=quality, method=6)
        before += source.stat().st_size
        after += target.stat().st_size
        print(f"{target.relative_to(ASSETS)}: {source.stat().st_size:,} -> {target.stat().st_size:,} bytes")
    print(f"Total: {len(jobs)} images; {before:,} -> {after:,} bytes ({1 - after / before:.1%} smaller)")


if __name__ == "__main__":
    main()
