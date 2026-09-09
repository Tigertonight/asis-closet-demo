"""Register scene/trend styling only after cutout review and Qiniu readback.

Run with --batch outputs/inspiration-delivery/20260909. The source/, cutouts/,
report.json, visual-review.json and remote-verification.json belong to that batch.
No upload credentials or temporary download URLs are copied into business data.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageChops, ImageOps

from app.material_assets import (MaterialRegistry, asset_content_url, asset_id_for_bytes,
                                 material_source_url, write_json_atomic)
from app.styling_catalog import CATEGORY_SLOTS

GROUPS = {
    "COMMUTE": ("通勤场景", "scene", "通勤"),
    "DATE": ("约会场景", "scene", "约会"),
    "VACATION": ("度假场景", "scene", "度假"),
    "TREND": ("潮流趋势", "trend", None),
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def child(root: Path, relative: str) -> Path:
    path = root / relative
    if not path.resolve().is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError(f"Missing or unsafe source path: {relative}")
    return path


def source_looks(source: Path) -> list[dict]:
    """Check all references and pairings before uploading or changing catalog data."""
    looks, identities, all_ids, all_images = [], set(), set(), set()
    for path in sorted(source.glob("*/*/styling.json")):
        code = path.parent.parent.name.split("_", 1)[0]
        if code not in GROUPS:
            raise ValueError(f"Unknown inspiration group: {code}")
        match = re.fullmatch(rf"{code}_.+-(\d+)-(.+)-拆款", path.parent.name)
        if not match:
            raise ValueError(f"Unrecognized look folder: {path.parent.name}")
        position, title = int(match[1]), match[2]
        if position not in range(1, 5) or (code, position) in identities:
            raise ValueError("Duplicate or invalid look position")
        identities.add((code, position))
        look = read_json(path)
        ids = [item["item_id"] for item in look["items"]]
        if not 1 <= len(ids) <= 16 or len(set(ids)) != len(ids) or all_ids.intersection(ids):
            raise ValueError("Duplicate or invalid item IDs")
        all_ids.update(ids)
        for field in ("source_outfit_item_ids", "layer_sequence_inner_to_outer"):
            if set(look[field]) != set(ids) or len(look[field]) != len(ids):
                raise ValueError(f"Incomplete {field}: {look['look_id']}")
        if look["source_image"] != f"outfits_{position:02d}_{title}.jpg":
            raise ValueError("Source photo does not match look position/title")
        photos = list((source / "穿搭原图").glob(f"{code}_*/{look['source_image']}"))
        if len(photos) != 1:
            raise ValueError("Missing or ambiguous original outfit photo")
        cover = child(source, photos[0].relative_to(source).as_posix())
        all_images.add(cover)
        for item in look["items"]:
            if Path(item["asset_filename"]).name != item["asset_filename"]:
                raise ValueError("Item filename must be a basename")
            image = child(path.parent, item["asset_filename"])
            if image in all_images:
                raise ValueError("Multiple items reference the same source path")
            all_images.add(image)
            if item["category"] not in CATEGORY_SLOTS:
                raise ValueError(f"Unknown item category: {item['category']}")
            if not set(item.get("paired_with_item_ids", [])).issubset(ids) or item.get("unresolved_paired_with"):
                raise ValueError("Unresolved item pairing")
        look.update(source_path=path.relative_to(source).as_posix(),
                    source_photo_path=cover.relative_to(source).as_posix(),
                    note_binding={"templateId": f"inspiration_{code.lower()}", "noteId": f"outfits-{position:02d}",
                                  "position": position, "name": title, "persona": None, "gender": "female",
                                  "byline": "", "sourceUrl": ""},
                    inspiration_binding={"topicId": code.lower(), "kind": GROUPS[code][1], "code": code,
                                         "gender": "female", "noteLinkStatus": "not_provided"},
                    scene_tags=[GROUPS[code][2]] if GROUPS[code][2] else [])
        looks.append(look)
    expected = {(code, pos) for code in GROUPS for pos in range(1, 5)}
    if identities != expected:
        raise ValueError("Expected four looks in each of four inspiration groups")
    actual_images = {path for path in source.rglob("*") if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}}
    if actual_images != all_images:
        raise ValueError("Unreferenced source images or missing referenced files")
    return looks


def build_delivery(batch: Path, registry: MaterialRegistry) -> tuple[dict, dict, dict]:
    source = batch / "source"
    looks = source_looks(source)
    report = read_json(batch / "report.json")
    reviews = read_json(batch / "visual-review.json")["items"]
    remote = read_json(batch / "remote-verification.json")["verified"]
    rows = {row["filename"]: row for row in report["items"]}
    corrections_path = batch / "cutout-corrections.json"
    corrections = read_json(corrections_path)["items"] if corrections_path.exists() else {}
    for filename, correction in corrections.items():
        if (filename not in rows or correction["correction"]["baseOutputSha256"] != rows[filename]["output_sha256"]):
            raise ValueError("Reviewed correction does not match the original batch")
        rows[filename] = correction
    expected_items = sum(len(look["items"]) for look in looks)
    if report["errors"] or report["completed"] != expected_items or len(rows) != expected_items:
        raise ValueError("Cutout batch is incomplete")
    assets, originals, cutouts = {}, {}, {}

    def reference(path: Path) -> dict:
        raw = path.read_bytes()
        asset_id = asset_id_for_bytes(raw)
        record = registry.get(asset_id)
        verified = remote.get(asset_id, {})
        if (record.get("storage", {}).get("provider") != "qiniu"
                or verified.get("sha256") != asset_id[6:] or verified.get("bytes") != len(raw)
                or verified.get("sourceUrl") != material_source_url(record)):
            raise ValueError(f"Image has not passed remote readback: {path.name}")
        return {"assetId": asset_id, "url": material_source_url(record),
                "contentUrl": asset_content_url(asset_id), "storage": record["storage"]}

    for look in looks:
        cover_path = child(source, look["source_photo_path"])
        cover = reference(cover_path)
        with Image.open(cover_path) as image:
            cover.update(width=image.width, height=image.height)
        look["source_asset"] = cover
        assets[look["source_photo_path"]] = cover
        originals[look["source_photo_path"]] = {"assetId": cover["assetId"]}
        for item in look["items"]:
            relative = (Path(look["source_path"]).parent / item["asset_filename"]).as_posix()
            original = child(source, relative)
            row = rows[relative]
            output = child(batch, row["output"])
            source_ref = reference(original)
            result_ref = reference(output)
            if (source_ref["assetId"] != "asset_" + row["source_sha256"]
                    or result_ref["assetId"] != "asset_" + row["output_sha256"]
                    or row["status"] != "complete" or not row["rgb_unchanged"]):
                raise ValueError("Cutout provenance mismatch")
            review = reviews.get(relative, {})
            if review.get("decision") != "accepted" or review.get("outputSha256") != result_ref["assetId"][6:]:
                raise ValueError(f"Cutout needs visual review: {relative}")
            with Image.open(original) as before, Image.open(output) as after:
                before, after = ImageOps.exif_transpose(before), ImageOps.exif_transpose(after)
                if after.mode != "RGBA" or after.size != before.size or after.getchannel("A").getextrema() != (0, 255):
                    raise ValueError(f"Invalid transparent PNG: {relative}")
                if ImageChops.difference(before.convert("RGB"), after.convert("RGB")).getbbox():
                    raise ValueError(f"Cutout changed original RGB: {relative}")
            result_ref["sourceAssetId"] = source_ref["assetId"]
            item["image_asset"] = result_ref
            item["cutout"] = {"method": row["method"], "rgbUnchanged": True, "visualReview": "accepted"}
            if row.get("correction"):
                item["cutout"]["correction"] = row["correction"]
            assets[relative] = result_ref
            originals[relative] = {"assetId": source_ref["assetId"]}
            cutouts[relative] = {"assetId": result_ref["assetId"], "sourceAssetId": source_ref["assetId"],
                                 "sourceItemId": item["item_id"]}
    topics = [{"id": code.lower(), "title": label, "kind": kind, "gender": "female",
               "lookCount": 4, "coverAssetId": next(look["source_asset"]["assetId"] for look in looks
                   if look["inspiration_binding"]["code"] == code and look["note_binding"]["position"] == 1)}
              for code, (label, kind, _) in GROUPS.items()]
    metadata = read_json(batch / "source-package.json")
    delivery = {"schemaVersion": "1.0", "sourceDelivery": metadata["name"],
                "sourceArchiveSha256": metadata["sha256"], "uploadStatus": "verified",
                "materialRegistry": "app/data/material-assets.v1.json",
                "sourceManifest": "app/data/inspiration-source-assets.v1.json",
                "cutoutManifest": "app/data/inspiration-cutout-assets.v1.json",
                "counts": {"topics": len(topics), "looks": len(looks), "items": expected_items,
                           "imageFiles": len(assets), "uniqueImages": len({ref["assetId"] for ref in assets.values()}),
                           "uploadedImageFiles": len(assets), "reviewedCutoutCorrections": len(corrections)},
                "topics": topics, "assets": assets, "looks": looks}
    return (delivery, {"schemaVersion": "1.0", "files": originals},
            {"schemaVersion": "1.0", "sourceManifest": delivery["sourceManifest"],
             "method": "birefnet_two_pass_conservative_union_or_existing_alpha", "files": cutouts})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument("--destination", type=Path, default=ROOT / "app/data")
    parser.add_argument("--registry", type=Path)
    args = parser.parse_args()
    delivery, originals, cutouts = build_delivery(args.batch, MaterialRegistry(args.registry))
    # The consumer catalog is written last; partially verified data is never exposed.
    write_json_atomic(args.destination / "inspiration-source-assets.v1.json", originals)
    write_json_atomic(args.destination / "inspiration-cutout-assets.v1.json", cutouts)
    write_json_atomic(args.destination / "inspiration-styling-delivery.v1.json", delivery)
    print(json.dumps(delivery["counts"], ensure_ascii=False))


if __name__ == "__main__":
    main()
