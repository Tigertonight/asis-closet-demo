"""Sync the 20 delivered persona notebook sets from an export and local originals.

Only personas represented in the delivery are imported; unrelated scene templates
and male placeholders in a batch export are left alone. Existing standard persona
foundations and candidate libraries are preserved. Images use immutable filenames
so historical material IDs keep pointing to their original bytes.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.material_assets import MaterialRegistry, write_json_atomic
from app.report_template_identity import template_identity
from scripts.import_selfit_report_data import build_runtime, RUNTIME_JSON, RUNTIME_JS
from scripts.register_material_assets import register_catalog_images, browser_catalog_script

MASTER = ROOT / "app/static/report-builder/data/16-personality-templates.json"
SEED = ROOT / "app/static/report-builder/seed-templates.js"
ASSETS = ROOT / "app/static/selfit/assets/personality"


def prepare_templates(exported: dict, previous: dict, originals: Path) -> tuple[list[dict], list[tuple[Path, bytes]]]:
    old = {template_identity(t)[3]: t for t in previous["templates"]}
    folders = {}
    for folder in originals.iterdir():
        if not folder.is_dir() or not re.match(r"^[A-Z]{4}_", folder.name):
            continue
        key = folder.name[:4].lower() + ("-curvy" if "微胖" in folder.name else "")
        if key in folders:
            raise ValueError(f"Duplicate delivery group: {key}")
        folders[key] = folder
    incoming = {}
    for t in exported["templates"]:
        if not re.fullmatch(r"[A-Za-z]{4}", str(t.get("code") or "")):
            continue
        persona, body, gender, key = template_identity(t)
        if key not in folders:
            continue
        if key in incoming:
            raise ValueError(f"Duplicate report audience: {key}")
        incoming[key] = t
    if set(incoming) != set(folders):
        raise ValueError(f"Missing report templates: {sorted(set(folders) - set(incoming))}")

    writes = []
    merged = dict(old)
    for key, source in incoming.items():
        persona, body, gender, _ = template_identity(source)
        prior = old.get(key)
        template = copy.deepcopy(prior or source)
        template.update(templateId=key, bodyProfile=body, gender=gender, updatedAt=source.get("updatedAt", ""))
        template["masterData"] = {**template.get("masterData", {}), "typeId": persona}
        # The standard foundation was already calibrated in the project. This
        # delivery changes its four notes; new curvy sets need all nine images.
        groups = [("outfits", 4)] if prior else [("hero", 1), ("makeup", 2), ("hair", 2), ("outfits", 4)]
        if not prior:
            template["source"] = copy.deepcopy(template.get("source") or {})
            template["source"]["avatars"] = {"imageUrl": "/static/selfit/assets/report-user-avatar-stack@4x.png", "alt": "真实用户素材来源"}
        if body == "curvy":
            template.setdefault("source", {})["copy"] = "已整理 4 条穿搭素材"
            template["masterData"]["sourceCount"] = 4
        for group, count in groups:
            if group != "hero":
                template[group] = copy.deepcopy(source.get(group) or [])
                if len(template[group]) != count:
                    raise ValueError(f"{key}.{group}: expected {count} cards")
            for position in range(1, count + 1):
                matches = list(folders[key].glob(f"{group}_{position:02d}_*"))
                if len(matches) != 1:
                    raise ValueError(f"{key}.{group}.{position}: expected exactly one original")
                image = matches[0]
                if group == "outfits" and image.stem != f"outfits_{position:02d}_{template[group][position - 1]['name']}":
                    raise ValueError(f"Notebook title/order mismatch: {image.name}")
                raw = image.read_bytes()
                digest = hashlib.sha256(raw).hexdigest()[:16]
                filename = f"report-{group}-{position:02d}-{digest}{image.suffix.lower()}"
                target = ASSETS / key / filename
                with Image.open(image) as opened:
                    width, height = opened.size
                    opened.verify()
                writes.append((target, raw))
                url = f"/static/selfit/assets/personality/{key}/{filename}"
                if group == "hero":
                    template["hero"] = url
                else:
                    template[group][position - 1].update(position=position, image=url, imageWidth=width, imageHeight=height)
        merged[key] = template
    return list(merged.values()), writes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--originals", type=Path, required=True)
    args = parser.parse_args()
    exported = json.loads(args.source.read_text())
    previous = json.loads(MASTER.read_text())
    templates, writes = prepare_templates(exported, previous, args.originals)
    master = {**previous, "seedVersion": max(14, previous.get("seedVersion", 0)),
              "source": args.source.name, "generatedAt": exported.get("exportedAt", ""), "templates": templates}
    runtime = build_runtime(master, json.loads(RUNTIME_JSON.read_text()))
    runtime["contentUpdatedAt"] = master["generatedAt"]
    for target, raw in writes:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() != raw:
            raise ValueError(f"Immutable image collision: {target}")
        if not target.exists():
            target.write_bytes(raw)
    registry = MaterialRegistry()
    runtime = register_catalog_images(runtime, registry)
    browser = browser_catalog_script(runtime, registry)
    write_json_atomic(MASTER, master)
    SEED.write_text("window.SELFIT_REPORT_MASTER_DATA = Object.freeze(" + json.dumps(master, ensure_ascii=False, separators=(",", ":")) + ");\n")
    write_json_atomic(RUNTIME_JSON, runtime)
    RUNTIME_JS.write_text(browser)
    print(f"Synced {len(templates)} templates, {len(writes)} image references; runtime defaults={len(runtime['types'])}, variants={len(runtime.get('variants', {}))}")


if __name__ == "__main__":
    main()
