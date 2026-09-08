"""Record the delivery's original styling metadata and its reusable asset bindings.

Run again after upload_content_pool.py to snapshot the registered OSS URLs.
Use --require-uploaded to reject incomplete uploads before marking a delivery ready.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.material_assets import MaterialRegistry, asset_content_url, asset_id_for_bytes, write_json_atomic
from app.report_template_identity import template_identity

DESTINATION = ROOT / "app/data/styling-delivery.v1.json"
MASTER = ROOT / "app/static/report-builder/data/16-personality-templates.json"


def build_delivery(source: Path, master: dict, registry: MaterialRegistry, *, require_uploaded: bool = False) -> dict:
    templates = {template_identity(t)[3]: t for t in master["templates"]}
    refs = {}

    def asset(path: Path) -> dict:
        if not path.resolve().is_relative_to(source.resolve()) or path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
            raise ValueError("Styling image must be inside the delivery directory")
        asset_id = asset_id_for_bytes(path.read_bytes())
        try:
            record = registry.get(asset_id)
            url = record["url"]
        except KeyError:
            record = {}
            url = None
        reference = {"assetId": asset_id, "url": url, "contentUrl": asset_content_url(asset_id)}
        if record.get("storage"):
            reference["storage"] = record["storage"]
        refs[path.relative_to(source).as_posix()] = reference
        return reference

    # Preserve every delivered image, including foundation images and spare assets.
    for path in sorted(source.rglob("*")):
        if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
            asset(path)
    looks = []
    seen = set()
    for path in sorted(source.glob("*/*/styling.json")):
        parent = path.parent.parent.name
        if not re.match(r"^[A-Z]{4}_", parent):
            continue
        persona = parent[:4].lower()
        body = "curvy" if "微胖" in parent else "standard"
        key = persona + ("-curvy" if body == "curvy" else "")
        matched = re.search(r"-(\d+)-(.+)-拆款$", path.parent.name)
        if not matched:
            raise ValueError(f"Invalid look directory: {path.parent.name}")
        position, title = int(matched[1]), matched[2]
        note_id = f"outfits-{position:02d}"
        binding = (key, note_id)
        if binding in seen:
            raise ValueError(f"Duplicate note binding: {binding}")
        seen.add(binding)
        template = templates[key]
        note = template["outfits"][position - 1]
        if note["name"] != title or note["position"] != position:
            raise ValueError(f"Template/delivery mismatch: {binding}")
        look = copy.deepcopy(json.loads(path.read_text()))
        original = [p for p in (source / "穿搭原图").glob(f"{persona.upper()}*/{look['source_image']}")
                    if ("微胖" in p.parent.name) == (body == "curvy")]
        if len(original) != 1:
            raise ValueError(f"Missing/ambiguous original: {binding}")
        look["source_path"] = path.relative_to(source).as_posix()
        look["note_binding"] = {"persona": persona, "bodyProfile": body, "gender": template.get("gender", "unisex"),
                                "templateId": key, "noteId": note_id, "position": position, "name": title,
                                "byline": note.get("byline", ""), "sourceUrl": note.get("sourceUrl", "")}
        look["source_asset"] = asset(original[0])
        for item in look["items"]:
            item["image_asset"] = asset(path.parent / item["asset_filename"])
        looks.append(look)
    grouped = {}
    for key, note in seen:
        grouped.setdefault(key, set()).add(note)
    if any(notes != {f"outfits-{i:02d}" for i in range(1, 5)} for notes in grouped.values()):
        raise ValueError("Each delivered audience must have exactly four notes")
    remote = sum(bool(ref["url"] and ref["url"].startswith(("https://", "http://"))) for ref in refs.values())
    if require_uploaded and remote != len(refs):
        raise ValueError(f"Upload incomplete: {remote}/{len(refs)} image references have remote URLs")
    return {"schemaVersion": "1.0", "sourceDelivery": source.name, "templateSource": master.get("source"),
            "uploadStatus": "complete" if remote == len(refs) else "pending",
            "counts": {"groups": len(grouped), "looks": len(looks), "items": sum(len(l['items']) for l in looks),
                       "imageFiles": len(refs), "uploadedImageFiles": remote,
                       "uniqueImages": len({r['assetId'] for r in refs.values()})},
            "materialRegistry": "app/data/material-assets.v1.json", "assets": refs, "looks": looks}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DESTINATION)
    parser.add_argument("--require-uploaded", action="store_true")
    args = parser.parse_args()
    delivery = build_delivery(args.source, json.loads(MASTER.read_text()), MaterialRegistry(), require_uploaded=args.require_uploaded)
    write_json_atomic(args.output, delivery)
    print(json.dumps({"output": str(args.output), "uploadStatus": delivery["uploadStatus"], **delivery["counts"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
