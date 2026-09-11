"""Append the four supplied male personality variants after cutout review and remote readback.

python scripts/register_male_styling_delivery.py --batch outputs/male-delivery/20260910
Original images stay in the ignored batch directory. Only the material registry
holds published private URLs; business catalogs use content IDs and stable URLs.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageChops, ImageOps
from app.material_assets import MaterialRegistry, asset_content_url, asset_id_for_bytes, material_source_url, write_json_atomic
from app.styling_catalog import CATEGORY_SLOTS
from scripts.import_selfit_report_data import build_runtime
from scripts.register_material_assets import browser_catalog_script, register_catalog_images
from scripts.register_inspiration_delivery import child, read_json

CODES = {"ease", "edge", "mute", "wabi"}
MALE_KEYWORDS = {
    # Keep the existing report editor's male identity copy.
    "mute": ["克制", "秩序", "低表达"],
    "edge": ["少年", "反差", "轻叛逆"],
    "wabi": ["天然", "肌理", "手工感"],
}
TARGETS = {
    "delivery": "app/data/styling-delivery.v1.json",
    "source": "app/data/styling-source-assets.v1.json",
    "cutout": "app/data/styling-cutout-assets.v1.json",
    "report": "app/data/styling-report-assets.v1.json",
    "master": "app/static/report-builder/data/16-personality-templates.json",
    "runtime": "app/static/selfit/data/personality-report-templates.v1.json",
    "seed": "app/static/report-builder/seed-templates.js",
    "browser": "app/static/selfit/personality-report-templates.js",
}


def source_looks(batch: Path) -> list[dict]:
    source = batch / "source" / "4男 拆款"
    descriptions = read_json(batch / "descriptions.json")
    looks, seen, all_ids, images, look_ids = [], set(), set(), set(), set()
    for path in sorted(source.glob("*/*/styling.json")):
        code = path.parent.parent.name[:4].lower()
        match = re.search(r"-(\d+)-(.+)-拆款$", path.parent.name)
        if code not in CODES or not path.parent.parent.name.endswith("_male") or not match:
            raise ValueError("Unknown male delivery folder")
        position, title = int(match[1]), match[2]
        if position not in range(1, 5) or (code, position) in seen:
            raise ValueError("Duplicate or invalid male note")
        seen.add((code, position))
        look = read_json(path)
        if not look.get("look_id") or look["look_id"] in look_ids:
            raise ValueError("Missing or duplicate look ID")
        look_ids.add(look["look_id"])
        ids = [item["item_id"] for item in look["items"]]
        if not 1 <= len(ids) <= 16 or len(set(ids)) != len(ids) or all_ids.intersection(ids):
            raise ValueError("Invalid or duplicate item IDs")
        all_ids.update(ids)
        for field in ("source_outfit_item_ids", "layer_sequence_inner_to_outer"):
            if set(look[field]) != set(ids) or len(look[field]) != len(ids):
                raise ValueError("Incomplete layering or item list")
        if look["source_image"] != f"outfits_{position:02d}_{title}.jpg":
            raise ValueError("Source photo does not match the note")
        photos = list((source / "穿搭原图").glob(f"{code.upper()}*/{look['source_image']}"))
        if len(photos) != 1:
            raise ValueError("Missing or ambiguous source photo")
        cover = child(source, photos[0].relative_to(source).as_posix())
        images.add(cover)
        description = descriptions[f"{code}-{position:02d}"]
        if len(description["items"]) != len(ids) or not description["outfit_description"].strip():
            raise ValueError("Description coverage is incomplete")
        for index, item in enumerate(look["items"]):
            if Path(item["asset_filename"]).name != item["asset_filename"]:
                raise ValueError("Item filename must be a basename")
            image = child(source, (path.parent / item["asset_filename"]).relative_to(source).as_posix())
            if image in images or item["category"] not in CATEGORY_SLOTS:
                raise ValueError("Duplicate image or unknown category")
            images.add(image)
            if not set(item.get("paired_with_item_ids", [])).issubset(ids) or item.get("unresolved_paired_with"):
                raise ValueError("Unresolved item pairing")
            item["description"] = description["items"][index]
            if not item["description"].strip():
                raise ValueError("Missing item description")
        original_sequence = look["layer_sequence_inner_to_outer"]
        # Use the supplied numeric layer ordering, keeping ties stable across body regions.
        look["layer_sequence_inner_to_outer"] = [item["item_id"] for item in sorted(look["items"], key=lambda item: item["layer_order"])]
        look.update(source_path=path.relative_to(batch / "source").as_posix(),
                    source_photo_path=cover.relative_to(batch / "source").as_posix(),
                    outfit_description=description["outfit_description"],
                    note_binding={"persona": code, "bodyProfile": "standard", "gender": "male",
                                  "templateId": code + "-male", "noteId": f"outfits-{position:02d}",
                                  "position": position, "name": title, "byline": "", "sourceUrl": "",
                                  "noteLinkStatus": "not_provided"},
                    source_revision={"archive": "4男 拆款.zip", "archive_sha256": read_json(batch / "source-package.json")["sha256"],
                                     "description_basis": "Original outfit and all item images reviewed with garment-describer.",
                                     "original_layer_sequence_inner_to_outer": original_sequence,
                                     "layer_normalization": "Stable ascending order of the supplied layer_order; wearing and pairing fields preserved."})
        looks.append(look)
    if seen != {(code, pos) for code in CODES for pos in range(1, 5)}:
        raise ValueError("Expected four notes for each of the four male personas")
    actual = {p for p in source.rglob("*") if p.suffix.lower() in {".jpg", ".png", ".jpeg", ".webp"}}
    if actual != images:
        raise ValueError("Missing or unreferenced source images")
    return looks


def reviewed_looks(batch: Path, registry: MaterialRegistry) -> tuple[list[dict], dict, dict, dict]:
    looks = source_looks(batch)
    report = read_json(batch / "report.json")
    rows = {r["filename"]: r for r in report["items"]}
    corrections = batch / "cutout-corrections.json"
    if corrections.exists():
        for name, row in read_json(corrections)["items"].items():
            if row["correction"]["baseOutputSha256"] != rows[name]["output_sha256"]:
                raise ValueError("Correction has a stale base image")
            rows[name] = row
    reviews = read_json(batch / "visual-review.json")["items"]
    remote = read_json(batch / "remote-verification.json")["verified"]
    if report["completed"] != 101 or report["errors"] or len(rows) != 101:
        raise ValueError("Incomplete cutout batch")
    assets, originals, cutouts = {}, {}, {}

    def reference(path: Path) -> dict:
        raw = path.read_bytes(); aid = asset_id_for_bytes(raw)
        record = registry.get(aid); verified = remote.get(aid, {})
        if (verified.get("sha256") != aid[6:] or verified.get("bytes") != len(raw)
                or verified.get("sourceUrl") != material_source_url(record)):
            raise ValueError("Image has not passed remote readback")
        return {"assetId": aid, "url": material_source_url(record), "contentUrl": asset_content_url(aid), "storage": record["storage"]}

    for look in looks:
        cover = child(batch / "source", look["source_photo_path"])
        look["source_asset"] = reference(cover)
        with Image.open(cover) as image:
            look["source_asset"].update(width=image.width, height=image.height)
        assets[look["source_photo_path"]] = look["source_asset"]
        originals[look["source_photo_path"]] = {"assetId": look["source_asset"]["assetId"]}
        for item in look["items"]:
            relative = (Path(look["source_path"]).parent / item["asset_filename"]).as_posix()
            row = rows[relative]
            original = child(batch / "source", relative); output = child(batch, row["output"])
            before_ref, after_ref = reference(original), reference(output)
            if (row["status"] != "complete" or not row["rgb_unchanged"]
                    or before_ref["assetId"] != "asset_" + row["source_sha256"]
                    or after_ref["assetId"] != "asset_" + row["output_sha256"]):
                raise ValueError("Cutout provenance mismatch")
            review = reviews.get(relative, {})
            if review.get("decision") != "accepted" or review.get("outputSha256") != row["output_sha256"]:
                raise ValueError("Cutout has not passed visual review")
            with Image.open(original) as before, Image.open(output) as after:
                before, after = ImageOps.exif_transpose(before), ImageOps.exif_transpose(after)
                if after.mode != "RGBA" or after.size != before.size or after.getchannel("A").getextrema() != (0, 255):
                    raise ValueError("Invalid transparent PNG")
                if ImageChops.difference(before.convert("RGB"), after.convert("RGB")).getbbox():
                    raise ValueError("Source RGB was modified")
            item["image_asset"] = {**after_ref, "sourceAssetId": before_ref["assetId"]}
            item["cutout"] = {"method": row["method"], "rgbUnchanged": True, "visualReview": "accepted"}
            if row.get("correction"): item["cutout"]["correction"] = row["correction"]
            assets[relative] = item["image_asset"]
            originals[relative] = {"assetId": before_ref["assetId"]}
            cutouts[relative] = {"assetId": after_ref["assetId"], "sourceAssetId": before_ref["assetId"], "sourceItemId": item["item_id"]}
    return looks, assets, originals, cutouts


def apply(batch: Path) -> dict:
    staged_registry = MaterialRegistry(batch / "material-assets.runtime.json")
    looks, assets, originals, cutouts = reviewed_looks(batch, staged_registry)
    prior = {key: (ROOT / path).read_bytes() for key, path in TARGETS.items()}
    values = {key: json.loads(raw) for key, raw in prior.items() if key not in {"seed", "browser"}}
    if any(l["note_binding"]["templateId"] in {c + "-male" for c in CODES} for l in values["delivery"]["looks"]):
        raise ValueError("Male batch already present; explicit revision required")
    from app.inspiration_catalog import inspiration_looks
    existing_looks = values["delivery"]["looks"] + inspiration_looks()
    if ({l["look_id"] for l in looks} & {l["look_id"] for l in existing_looks}
            or {i["item_id"] for l in looks for i in l["items"]} & {i["item_id"] for l in existing_looks for i in l["items"]}):
        raise ValueError("Male delivery IDs collide with an existing catalog")
    master = values["master"]; runtime = values["runtime"]
    now = datetime.now(timezone.utc).isoformat()
    new_templates = []
    for code in sorted(CODES):
        base = next(t for t in master["templates"] if t.get("templateId") == code)
        template = deepcopy(base)
        template.update(templateId=code + "-male", gender="male", bodyProfile="standard",
                        name=base["name"].removesuffix("型人格") + "-男", makeup=[], hair=[], outfits=[], outfitLibrary=[],
                        updatedAt=now, outfitSummary="四套男性穿搭参考。",
                        hero="/static/selfit/assets/personality/placeholder-hero.svg")
        template["keywords"] = MALE_KEYWORDS.get(code, template["keywords"])
        template["masterData"] = {"typeId": code, "index": base.get("masterData", {}).get("index", 0),
                                  "sourceArchive": "4男 拆款.zip", "sourceCount": 4,
                                  "sourceCounts": {"makeup": 0, "hair": 0, "outfits": 4}}
        template["source"] = {"archive": "4男 拆款.zip", "copy": "已整理 4 条男性穿搭素材", "noteLinkStatus": "not_provided"}
        for look in sorted((l for l in looks if l["note_binding"]["persona"] == code), key=lambda l: l["note_binding"]["position"]):
            binding = look["note_binding"]; image = look["source_asset"]
            template["outfits"].append({"name": binding["name"], "position": binding["position"],
                "image": image["contentUrl"], "assetId": image["assetId"], "imageWidth": image["width"], "imageHeight": image["height"],
                "byline": "", "sourceUrl": "", "fileName": look["source_image"], "assetPath": look["source_photo_path"],
                "noteLinkStatus": "not_provided", "styling": look["outfit_description"], "primaryStyle": code.upper(),
                "secondaryStyle": "", "regionalStyle": "", "bodyTypes": "", "mood": "", "notes": "2026-09-10 男性拆款；原包未提供笔记链接与作者。"})
        new_templates.append(template)
    master["templates"].extend(new_templates)
    registry = MaterialRegistry()
    # Add only new content IDs; existing object locations and signatures are preserved.
    with registry.path.with_suffix(registry.path.suffix + ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        payload = read_json(registry.path)
        backup = batch / "backup" / "app/data/material-assets.v1.json"
        if not backup.exists():
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_bytes(registry.path.read_bytes())
        for aid, record in read_json(staged_registry.path)["assets"].items():
            if aid not in payload["assets"]:
                # Keep the operator-published private URL so a cold cache can load it.
                payload["assets"][aid] = deepcopy(record)
        payload["assets"] = dict(sorted(payload["assets"].items()))
        write_json_atomic(registry.path, payload)
    new_runtime = register_catalog_images(build_runtime({"templates": new_templates}, runtime), registry)
    runtime.setdefault("variants", {}).update(new_runtime["variants"])
    delivery = values["delivery"]
    delivery["looks"].extend(looks); delivery["assets"].update(assets)
    values["source"]["files"].update(originals); values["cutout"]["files"].update(cutouts)
    for look in looks: values["report"]["files"][look["source_photo_path"]] = {"assetId": look["source_asset"]["assetId"]}
    delivery["counts"].update(groups=len({l["note_binding"]["templateId"] for l in delivery["looks"]}),
        looks=len(delivery["looks"]), items=sum(len(l["items"]) for l in delivery["looks"]),
        imageFiles=len(delivery["assets"]), uploadedImageFiles=len(delivery["assets"]),
        uniqueImages=len({a["assetId"] for a in delivery["assets"].values()}))
    revision = {"id": "male-styling-20260910", "appliedAt": now, "archive": read_json(batch / "source-package.json"),
                "templates": sorted(c + "-male" for c in CODES), "looks": 16, "items": 101,
                "verification": {"originalImages": 117, "finalCutouts": 101, "visualReviews": 101,
                                 "rgbUnchanged": True, "remoteReadback": "bytes + SHA-256 + object URL"}}
    delivery.setdefault("revisions", []).append(revision)
    master["generatedAt"] = runtime["contentUpdatedAt"] = now
    master["seedVersion"] = int(master.get("seedVersion", 0)) + 1
    texts = {"seed": "window.SELFIT_REPORT_MASTER_DATA = Object.freeze(" + json.dumps(master, ensure_ascii=False, separators=(",", ":")) + ");\n",
             "browser": browser_catalog_script(runtime, registry)}
    for key, path in TARGETS.items():
        if (ROOT / path).read_bytes() != prior[key]: raise ValueError("Concurrent catalog change; retry against the latest files")
    for key, path in TARGETS.items():
        backup = batch / "backup" / path; backup.parent.mkdir(parents=True, exist_ok=True); backup.write_bytes(prior[key])
    # Publish the consumer delivery last, after all metadata and assets are available.
    for key in [k for k in TARGETS if k != "delivery"] + ["delivery"]:
        if key in texts: (ROOT / TARGETS[key]).write_text(texts[key], encoding="utf-8")
        else: write_json_atomic(ROOT / TARGETS[key], values[key])
    write_json_atomic(batch / "applied.json", {"status": "complete", **revision, "counts": delivery["counts"]})
    return delivery["counts"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument("--check-source", action="store_true")
    args = parser.parse_args()
    if args.check_source:
        looks = source_looks(args.batch)
        print(json.dumps({"looks": len(looks), "items": sum(len(l["items"]) for l in looks)}))
    else:
        print(json.dumps(apply(args.batch), ensure_ascii=False))
