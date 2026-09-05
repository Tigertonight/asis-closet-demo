#!/usr/bin/env python3
"""Create publishable WebP garment assets and refresh runtime references.

The lossless PNG files remain local source masters and are ignored by Git.
Only non-raw, QA-approved 1200px garment outputs are converted. Historical
audit documents and raw-generation references are intentionally untouched.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = ROOT / "app/static/selfit/assets/content_v2"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
RUNTIME_DATA_ROOTS = (
    ROOT / "app/static/selfit/data",
    ROOT / "app/data",
)


def public_url(path: Path) -> str:
    return "/static/selfit/assets/content_v2/" + path.relative_to(ASSET_ROOT).as_posix()


def is_publishable_png(path: Path) -> bool:
    return path.suffix.lower() == ".png" and "-raw-" not in path.stem


def validate_pair(source: Path, target: Path) -> None:
    with Image.open(source) as original, Image.open(target) as optimized:
        if optimized.format != "WEBP":
            raise ValueError(f"not WebP: {target}")
        original_rgba = original.convert("RGBA")
        optimized_rgba = optimized.convert("RGBA")
        if original_rgba.size != optimized_rgba.size:
            raise ValueError(f"dimension mismatch: {source} -> {target}")
        alpha_delta = ImageChops.difference(
            original_rgba.getchannel("A"), optimized_rgba.getchannel("A")
        )
        if alpha_delta.getbbox() is not None:
            raise ValueError(f"alpha channel changed: {source} -> {target}")


def convert_one(source: Path, *, quality: int, force: bool) -> tuple[int, int, bool]:
    target = source.with_suffix(".webp")
    if target.exists() and not force:
        validate_pair(source, target)
        return source.stat().st_size, target.stat().st_size, False

    temporary = target.with_name(target.name + ".tmp")
    cwebp = shutil.which("cwebp")
    try:
        if cwebp:
            subprocess.run(
                [
                    cwebp,
                    "-quiet",
                    "-q",
                    str(quality),
                    "-alpha_q",
                    "100",
                    "-m",
                    "6",
                    "-mt",
                    "-exact",
                    str(source),
                    "-o",
                    str(temporary),
                ],
                check=True,
            )
        else:
            with Image.open(source) as image:
                image.convert("RGBA").save(
                    temporary,
                    "WEBP",
                    quality=quality,
                    method=4,
                    exact=True,
                )
        validate_pair(source, temporary)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return source.stat().st_size, target.stat().st_size, True


def rewrite_runtime_urls(mapping: dict[str, str]) -> list[Path]:
    changed: list[Path] = []
    for data_root in RUNTIME_DATA_ROOTS:
        if not data_root.exists():
            continue
        for path in sorted(data_root.rglob("*.json")):
            text = path.read_text(encoding="utf-8")
            updated = text
            for old, new in mapping.items():
                updated = updated.replace(old, new)
            if updated != text:
                path.write_text(updated, encoding="utf-8")
                changed.append(path)
    return changed


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def rebuild_outfit_covers(workers: int) -> dict[str, int]:
    from app.outfit_layout import outfit_preview_url, render_outfit_preview

    pool_path = ROOT / "app/static/selfit/data/content-pool.v2.published.json"
    pool = json.loads(pool_path.read_text(encoding="utf-8"))
    garments = {row["id"]: row for row in pool.get("garments", [])}
    recipes: dict[str, list[dict]] = {}
    for outfit in pool.get("outfits", []):
        items = [garments[garment_id] for garment_id in outfit.get("garment_ids", [])]
        recipes[outfit_preview_url(items)] = items

    def render(pair: tuple[str, list[dict]]) -> bool:
        url, items = pair
        output = ROOT / "app" / url.lstrip("/")
        qa = output.with_suffix(".qa.json")
        if output.is_file() and qa.is_file():
            return False
        render_outfit_preview(items, ROOT)
        return True

    with ThreadPoolExecutor(max_workers=workers) as executor:
        created = sum(executor.map(render, recipes.items()))
    return {"unique_outfit_covers": len(recipes), "outfit_covers_created": created}


def refresh_revision_bound_metadata() -> list[Path]:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from app.outfit_layout import outfit_preview_url
    from app.selfit_content_quality import apply_curation, record_fingerprint

    changed: list[Path] = []
    pool_path = ROOT / "app/static/selfit/data/content-pool.v2.published.json"
    pool = json.loads(pool_path.read_text(encoding="utf-8"))
    raw_garments = {row["id"]: row for row in pool.get("garments", [])}

    curation_path = ROOT / "app/static/selfit/data/content-curation.v1.json"
    curation: dict = {}
    if curation_path.exists():
        curation = json.loads(curation_path.read_text(encoding="utf-8"))
        for garment_id, entry in curation.get("garments", {}).items():
            garment = raw_garments.get(garment_id)
            if not garment:
                continue
            url = garment["assets"]["image_url"]
            disk_path = ROOT / "app" / url.lstrip("/")
            entry["source_fingerprint"] = record_fingerprint(garment)
            evidence = ((entry.get("patch") or {}).get("color_evidence") or {})
            if evidence:
                evidence["asset_sha256"] = hashlib.sha256(disk_path.read_bytes()).hexdigest()
        write_json(curation_path, curation)
        changed.append(curation_path)

    # Runtime visual evidence and style families bind to the effective garment
    # after the editorial overlay is applied, not to the raw pool record.
    effective_pool = apply_curation(pool, curation)
    garments = {row["id"]: row for row in effective_pool.get("garments", [])}
    outfits = {row["id"]: row for row in effective_pool.get("outfits", [])}

    visual_path = ROOT / "app/data/recommendation-visual.v1.json"
    if visual_path.exists():
        visual = json.loads(visual_path.read_text(encoding="utf-8"))
        for garment_id, observation in visual.get("garments", {}).items():
            garment = garments.get(garment_id)
            if not garment:
                continue
            url = garment["assets"]["image_url"]
            disk_path = ROOT / "app" / url.lstrip("/")
            observation["image_url"] = url
            observation["asset_sha256"] = hashlib.sha256(disk_path.read_bytes()).hexdigest()
            observation["record_fingerprint"] = record_fingerprint(garment)
        for outfit_id, observation in visual.get("outfits", {}).items():
            outfit = outfits.get(outfit_id)
            if not outfit:
                continue
            items = [garments[garment_id] for garment_id in outfit.get("garment_ids", [])]
            url = outfit_preview_url(items)
            disk_path = ROOT / "app" / url.lstrip("/")
            if not disk_path.is_file():
                raise FileNotFoundError(f"missing rebuilt outfit cover: {disk_path}")
            observation["image_url"] = url
            observation["asset_sha256"] = hashlib.sha256(disk_path.read_bytes()).hexdigest()
            observation["record_fingerprint"] = record_fingerprint(outfit)
        write_json(visual_path, visual)
        changed.append(visual_path)

    family_paths = (
        ROOT / "app/data/garment-style-families.v1.json",
        ROOT
        / "docs/audits/20260903-personal-home-visual/family-review/garment-style-families.native-draft.json",
    )
    for families_path in family_paths:
        if not families_path.exists():
            continue
        registry = json.loads(families_path.read_text(encoding="utf-8"))
        for family in registry.get("families", []):
            for garment_id in list((family.get("members") or {}).keys()):
                if garment_id in garments:
                    family["members"][garment_id] = record_fingerprint(garments[garment_id])
                    if isinstance(family.get("asset_sha256"), dict):
                        url = garments[garment_id]["assets"]["image_url"]
                        disk_path = ROOT / "app" / url.lstrip("/")
                        family["asset_sha256"][garment_id] = hashlib.sha256(
                            disk_path.read_bytes()
                        ).hexdigest()
        write_json(families_path, registry)
        changed.append(families_path)

    return changed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quality", type=int, default=86)
    parser.add_argument("--workers", type=int, default=min(8, os.cpu_count() or 4))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--no-rewrite-runtime", action="store_true")
    parser.add_argument("--no-rebuild-covers", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.quality <= 100:
        parser.error("--quality must be between 1 and 100")

    sources = sorted(path for path in ASSET_ROOT.rglob("*.png") if is_publishable_png(path))
    if not sources:
        raise SystemExit("No publishable Content V2 PNG files found")

    def work(path: Path) -> tuple[int, int, bool]:
        return convert_one(path, quality=args.quality, force=args.force)

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        results = list(executor.map(work, sources))

    old_bytes = sum(item[0] for item in results)
    new_bytes = sum(item[1] for item in results)
    created = sum(item[2] for item in results)
    changed_files: list[Path] = []
    cover_stats = {"unique_outfit_covers": 0, "outfit_covers_created": 0}
    if not args.no_rewrite_runtime:
        mapping = {public_url(path): public_url(path.with_suffix(".webp")) for path in sources}
        changed_files.extend(rewrite_runtime_urls(mapping))
        if not args.no_rebuild_covers:
            cover_stats = rebuild_outfit_covers(args.workers)
        changed_files.extend(refresh_revision_bound_metadata())

    print(
        json.dumps(
            {
                "source_pngs": len(sources),
                "webps_created": created,
                "quality": args.quality,
                "source_mb": round(old_bytes / 1024 / 1024, 2),
                "webp_mb": round(new_bytes / 1024 / 1024, 2),
                "saved_percent": round((1 - new_bytes / old_bytes) * 100, 2),
                "runtime_files_updated": len(set(changed_files)),
                **cover_stats,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
