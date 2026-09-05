"""Build a revision-bound four-gate editorial review packet.

The packet is deliberately pending. Reviewers fill the form and a separate
approved workflow may later apply decisions; generation never approves rows.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import closet
from app.recommendation_visual import attach_visual, load_visual
from app.selfit_content_quality import GATES, record_fingerprint


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build(manifest_path: Path, output: Path, staging_path: Path | None = None) -> dict:
    if output.exists():
        raise ValueError("Use a new output directory; never overwrite review evidence")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    pool = closet.selfit_content_pool()
    catalog, _ = attach_visual(
        closet._published_catalog_outfits(), pool.garments, pool.outfits, load_visual()
    )
    catalog_by_id = {str(row["outfit_id"]): row for row in catalog}
    raw_by_id = {str(row["id"]): row for row in pool.outfits}
    garments = {str(row["id"]): row for row in pool.garments}
    if staging_path:
        staging = json.loads(staging_path.read_text(encoding="utf-8"))
        if manifest.get("staging_version") != staging.get("version"):
            raise ValueError("Editorial packet staging version does not match anchor manifest")
        for row in staging.get("staged_garments") or []:
            record = row.get("record")
            if not isinstance(record, dict) or row.get("record_fingerprint") != record_fingerprint(record):
                raise ValueError("Staged garment record is stale")
            garments[str(record["id"])] = record
        for entry in staging.get("entries") or []:
            raw, adapted = entry.get("raw_record"), entry.get("catalog_record")
            if (not isinstance(raw, dict) or not isinstance(adapted, dict)
                    or entry.get("record_fingerprint") != record_fingerprint(raw)):
                raise ValueError("Staged outfit record is stale")
            raw_by_id[str(raw["id"])] = raw
            catalog_by_id[str(adapted["outfit_id"])] = adapted
    output.mkdir(parents=True)
    sheets = output / "contact-sheets"
    sheets.mkdir()
    reviews, by_persona = [], defaultdict(list)
    for anchor in manifest.get("anchors", []):
        oid = str(anchor.get("outfit_id") or "")
        adapted, raw = catalog_by_id.get(oid), raw_by_id.get(oid)
        if not adapted or not raw or anchor.get("record_fingerprint") != record_fingerprint(raw):
            raise ValueError(f"Missing or stale candidate: {oid}")
        image_path = ROOT / "app" / str(adapted["cover_path"]).lstrip("/")
        if not image_path.is_file():
            raise ValueError(f"Missing outfit image: {oid}")
        item_rows = []
        for gid in raw.get("garment_ids") or []:
            garment = garments.get(str(gid))
            if garment is None:
                raise ValueError(f"Missing garment {gid} for {oid}")
            item_rows.append({
                "garment_id": gid,
                "category": garment.get("category"),
                "role": (raw.get("slot_roles") or {}).get(gid),
                "record_fingerprint": record_fingerprint(garment),
            })
        row = {
            "outfit_id": oid,
            "persona": anchor.get("persona"),
            "expression": anchor.get("expression"),
            "structure": anchor.get("structure"),
            "user_title": anchor.get("user_title"),
            "record_fingerprint": record_fingerprint(raw),
            "image_path": str(image_path.relative_to(ROOT)),
            "image_sha256": digest(image_path),
            "items": item_rows,
            "gates": {
                gate: {"status": "pending", "reviewer": "", "evidence": "", "notes": ""}
                for gate in GATES
            },
            "final_decision": "pending",
        }
        reviews.append(row)
        by_persona[str(anchor.get("persona"))].append((row, image_path))

    for persona, rows in sorted(by_persona.items()):
        cell_w, cell_h, columns = 320, 430, 5
        canvas = Image.new("RGB", (cell_w * columns, cell_h * 2), "#f8f3ef")
        draw = ImageDraw.Draw(canvas)
        for index, (row, path) in enumerate(rows):
            with Image.open(path) as source:
                thumb = ImageOps.contain(source.convert("RGB"), (280, 350))
            x, y = (index % columns) * cell_w, (index // columns) * cell_h
            canvas.paste(thumb, (x + (cell_w - thumb.width) // 2, y + 42))
            draw.text((x + 14, y + 12), f"{index + 1:02d} {row['outfit_id']}", fill="#2b2020")
            draw.text((x + 14, y + 397), f"{row['expression']} / {row['structure']}", fill="#7b3848")
        canvas.save(sheets / f"{persona}.jpg", quality=92)

    package = {
        "schema_version": 1,
        "status": "pending_editorial_review",
        "anchor_manifest_sha256": digest(manifest_path),
        "content_version": manifest.get("content_version"),
        "visual_version": manifest.get("visual_version"),
        "family_registry_sha256": manifest.get("family_registry_sha256"),
        "samples": len(reviews),
        "reviews": reviews,
    }
    save(output / "review-form.json", package)
    (output / "README.md").write_text(
        "# Selfit P0 四门内容审核\n\n"
        "逐套查看原图和人格联系表，分别完成 technical / aesthetic / persona / context 四门。\n"
        "status 只允许 passed / needs_review / reject；reviewer、evidence、notes 均需按真实结论填写。\n"
        "本包默认全部 pending，不会因 AI 视觉候选记录自动通过。任一图片或配方变化后必须重审。\n",
        encoding="utf-8",
    )
    return package


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--anchor-manifest", type=Path, required=True)
    parser.add_argument("--staging", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build(args.anchor_manifest, args.output, args.staging)
    print(json.dumps({"status": result["status"], "samples": result["samples"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
