#!/usr/bin/env python3
"""Losslessly migrate PNG garment cutouts used by selected P0 anchors to WebP."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from copy import deepcopy
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import closet
from app.recommendation_visual import attach_visual, load_visual
from app.selfit_content_quality import record_fingerprint


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pixel_sha(image: Image.Image) -> str:
    rgba = image.convert("RGBA")
    payload = f"RGBA:{rgba.width}x{rgba.height}:".encode() + rgba.tobytes()
    return hashlib.sha256(payload).hexdigest()


def replace_strings(value: object, replacements: dict[str, str]) -> object:
    if isinstance(value, dict):
        return {key: replace_strings(item, replacements) for key, item in value.items()}
    if isinstance(value, list):
        return [replace_strings(item, replacements) for item in value]
    if isinstance(value, str):
        return replacements.get(value, value)
    return value


def selected_catalog(anchor: dict, staging: dict) -> dict[str, dict]:
    pool, visual = closet.selfit_content_pool(), load_visual()
    published, _ = attach_visual(closet._published_catalog_outfits(), pool.garments, pool.outfits, visual)
    by_id = {row["outfit_id"]: row for row in published}
    by_id.update({entry["outfit_id"]: entry["catalog_record"] for entry in staging["entries"]})
    missing = [row["outfit_id"] for row in anchor["anchors"] if row["outfit_id"] not in by_id]
    if missing:
        raise ValueError("Selected anchors are absent from the catalog: " + ", ".join(missing))
    return {row["outfit_id"]: by_id[row["outfit_id"]] for row in anchor["anchors"]}


def asset_urls(catalog: dict[str, dict]) -> set[str]:
    urls = set()
    for outfit in catalog.values():
        cover = outfit.get("layout_snapshot_path") or outfit.get("cover_path") or outfit.get("cover")
        if cover:
            urls.add(cover)
        for item in outfit.get("items", []):
            assets = item.get("assets") or {}
            path = assets.get("cutout_path") or assets.get("image_url") or assets.get("preview_path")
            if path:
                urls.add(path)
    return urls


def disk_path(url: str) -> Path:
    path = (ROOT / "app" / url.lstrip("/")).resolve()
    allowed = (ROOT / "app/static/selfit/assets").resolve()
    if not path.is_relative_to(allowed):
        raise ValueError(f"Asset is outside the Selfit asset root: {url}")
    return path


def convert_one(url: str) -> dict:
    source = disk_path(url)
    if source.suffix.lower() != ".png" or not source.is_file():
        raise ValueError(f"Expected an existing PNG source: {url}")
    target = source.with_suffix(".webp")
    target_url = url[:-4] + ".webp"
    with Image.open(source) as opened:
        rgba = opened.convert("RGBA")
        source_pixel_sha = pixel_sha(rgba)
        temp = target.with_name(target.name + ".tmp")
        rgba.save(temp, "WEBP", lossless=True, quality=100, method=6, exact=True)
    with Image.open(temp) as converted:
        if converted.format != "WEBP" or converted.mode != "RGBA":
            temp.unlink(missing_ok=True)
            raise ValueError(f"WebP did not preserve RGBA: {url}")
        target_pixel_sha = pixel_sha(converted)
    if source_pixel_sha != target_pixel_sha:
        temp.unlink(missing_ok=True)
        raise ValueError(f"Lossless pixel comparison failed: {url}")
    if target.exists():
        if file_sha(target) != file_sha(temp):
            temp.unlink(missing_ok=True)
            raise ValueError(f"Existing WebP differs; refusing overwrite: {target_url}")
        temp.unlink()
    else:
        os.replace(temp, target)
    return {
        "source_url": url,
        "source_sha256": file_sha(source),
        "target_url": target_url,
        "target_sha256": file_sha(target),
        "pixel_sha256": source_pixel_sha,
        "size": [rgba.width, rgba.height],
        "mode": "RGBA",
        "lossless_pixel_equal": True,
        "source_retained_for_audit": True,
    }


def migrate(anchor_path: Path, staging_path: Path, output_anchor: Path,
            output_staging: Path, output_manifest: Path) -> dict:
    if any(path.exists() for path in (output_anchor, output_staging, output_manifest)):
        raise ValueError("Use new output paths; migration history is immutable")
    anchor = json.loads(anchor_path.read_text())
    staging = json.loads(staging_path.read_text())
    if anchor.get("staging_version") != staging.get("version"):
        raise ValueError("Anchor and staging versions do not match")
    catalog = selected_catalog(anchor, staging)
    png_urls = sorted(url for url in asset_urls(catalog) if Path(url).suffix.lower() == ".png")
    conversions = [convert_one(url) for url in png_urls]
    replacements = {}
    for row in conversions:
        replacements[row["source_url"]] = row["target_url"]
        replacements[row["source_sha256"]] = row["target_sha256"]

    updated_staging = replace_strings(deepcopy(staging), replacements)
    migration_ref = str(output_manifest.resolve().relative_to(ROOT))
    for row in updated_staging.get("staged_garments", []):
        record = row["record"]
        assets = record.get("assets") or {}
        if any(str(path).endswith(".webp") and str(path) in replacements.values()
               for path in assets.values() if isinstance(path, str)):
            row["asset_migration_manifest"] = migration_ref
        row["record_fingerprint"] = record_fingerprint(record)
    updated_staging.pop("version", None)
    updated_staging["version"] = "p0-replacement-staging-" + digest(updated_staging)[:20]

    updated_anchor = deepcopy(anchor)
    updated_anchor["staging_version"] = updated_staging["version"]
    updated_anchor["status"] = "candidate"
    updated_anchor["blind_review_package_id"] = None
    updated_anchor.pop("version", None)
    updated_anchor["version"] = "p0-replacement-candidates-" + digest(updated_anchor)[:20]

    output_staging.write_text(json.dumps(updated_staging, ensure_ascii=False, indent=2) + "\n")
    output_anchor.write_text(json.dumps(updated_anchor, ensure_ascii=False, indent=2) + "\n")

    updated_catalog = selected_catalog(updated_anchor, updated_staging)
    checked_urls = sorted(asset_urls(updated_catalog))
    formats = {}
    missing = []
    non_webp = []
    for url in checked_urls:
        path = disk_path(url)
        if not path.is_file():
            missing.append(url)
            continue
        with Image.open(path) as image:
            formats[image.format] = formats.get(image.format, 0) + 1
            if image.format != "WEBP" or Path(url).suffix.lower() != ".webp":
                non_webp.append(url)
    result = {
        "schema_version": 1,
        "production_approved": False,
        "source_anchor_manifest": str(anchor_path.resolve().relative_to(ROOT)),
        "source_anchor_sha256": file_sha(anchor_path),
        "source_staging": str(staging_path.resolve().relative_to(ROOT)),
        "source_staging_sha256": file_sha(staging_path),
        "output_anchor_manifest": str(output_anchor.resolve().relative_to(ROOT)),
        "output_anchor_sha256": file_sha(output_anchor),
        "output_staging": str(output_staging.resolve().relative_to(ROOT)),
        "output_staging_sha256": file_sha(output_staging),
        "conversions": conversions,
        "selected_asset_audit": {
            "anchor_count": len(updated_anchor["anchors"]),
            "unique_asset_urls": len(checked_urls),
            "formats": formats,
            "missing": missing,
            "non_webp": non_webp,
            "all_webp": not missing and not non_webp,
        },
    }
    result["version"] = "p0-selected-webp-migration-" + digest(result)[:20]
    output_manifest.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("anchor-manifest", "staging", "output-anchor", "output-staging", "output-manifest"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    result = migrate(args.anchor_manifest, args.staging, args.output_anchor,
                     args.output_staging, args.output_manifest)
    print(json.dumps({"version": result["version"],
                      "converted": len(result["conversions"]),
                      **result["selected_asset_audit"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
