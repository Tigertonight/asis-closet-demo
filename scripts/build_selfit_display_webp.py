"""Rebuild bundled WebP display assets from retained PNG/JPEG originals.

SVG bitmap composites are built by build_selfit_svg_webp.cjs in a browser.
Existing reviewed derivatives are retained unless --force is supplied.
"""
import argparse
import json
from pathlib import Path
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    manifest = json.loads((ROOT / "app/static/selfit/display-assets.json").read_text())
    rows = []
    for name, destination in manifest.items():
        source, target = ROOT / name, ROOT / destination
        if source.suffix == ".svg":
            continue
        if not target.exists() or args.force:
            with Image.open(source) as original:
                image = ImageOps.exif_transpose(original).convert("RGBA")
                image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
                image.save(target, "WEBP", quality=86, method=6)
        rows.append({"source": name, "target": destination, "before": source.stat().st_size, "after": target.stat().st_size})
    print(json.dumps({"count": len(rows), "before": sum(r["before"] for r in rows), "after": sum(r["after"] for r in rows)}))


if __name__ == "__main__":
    main()
