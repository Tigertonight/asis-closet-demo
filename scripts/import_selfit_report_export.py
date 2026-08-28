"""Import a Cowork report-builder export and materialize its private images.

The report builder stores edited images behind authenticated ``/api/assets``
URLs. Those URLs are not valid in the standalone onboarding application, so
this importer downloads every selected report image and rewrites the export to
versioned, project-local static paths before regenerating the builder seed.
"""

from __future__ import annotations

import argparse
import io
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[1]
MASTER_PATH = ROOT / "app/static/report-builder/data/16-personality-templates.json"
SEED_JS_PATH = ROOT / "app/static/report-builder/seed-templates.js"
ASSET_ROOT = ROOT / "app/static/selfit/assets/personality"
ASSET_VERSION = "20260828-config-v1"
LIBRARY_ASSET_VERSION = "20260826-db-v3"
GROUPS = ("makeup", "hair", "outfits")


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def _type_id(template: dict[str, Any]) -> str:
    return str(
        template.get("templateId")
        or (template.get("masterData") or {}).get("typeId")
        or ""
    ).strip().lower()


def _asset_url(origin: str, source: str) -> str:
    if not source.startswith("/api/assets/"):
        raise ValueError(f"Expected Cowork asset URL, got: {source}")
    return f"{origin.rstrip('/')}{source}"


def _download(url: str, cookie: str) -> bytes:
    last_error: Exception | None = None
    for attempt in range(4):
        request = urllib.request.Request(
            url,
            headers={"Cookie": cookie, "User-Agent": "selfit-report-importer/1.0"},
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                content_type = response.headers.get_content_type()
                if not content_type.startswith("image/"):
                    raise ValueError(f"Asset returned {content_type}: {url}")
                return response.read()
        except (OSError, EOFError) as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"download failed after retries: {last_error}")


def _save_image(raw: bytes, target: Path, *, hero: bool) -> tuple[int, int]:
    target.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(io.BytesIO(raw)) as source:
        image = ImageOps.exif_transpose(source)
        if hero:
            image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
            image.save(target, "PNG", optimize=True)
        else:
            image = image.convert("RGB")
            image.save(target, "WEBP", quality=90, method=6)
        return image.size


def _library_items(
    exported: list[dict[str, Any]],
    previous: list[dict[str, Any]],
    *,
    type_id: str,
    group: str,
) -> list[dict[str, Any]]:
    old_by_asset = {
        str(item.get("assetPath") or item.get("fileName") or ""): item
        for item in previous
        if item.get("assetPath") or item.get("fileName")
    }
    result: list[dict[str, Any]] = []
    for index, item in enumerate(exported, 1):
        key = str(item.get("assetPath") or item.get("fileName") or "")
        prior = old_by_asset.get(key) or (previous[index - 1] if index <= len(previous) else {})
        merged = {**prior, **item}
        position = int(merged.get("position") or index)
        local = ASSET_ROOT / type_id / f"{group}-{position:02d}.webp"
        if local.is_file():
            merged["image"] = (
                f"/static/selfit/assets/personality/{type_id}/{group}-{position:02d}.webp"
                f"?v={LIBRARY_ASSET_VERSION}"
            )
        elif not merged.get("image"):
            merged["image"] = str(prior.get("image") or "")
        merged["position"] = position
        result.append(merged)
    return result


def _enrich_selected_items(
    exported: list[dict[str, Any]],
    previous: list[dict[str, Any]],
    library: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep provenance fields that the visual editor does not expose."""
    candidates = [*previous, *library]
    result: list[dict[str, Any]] = []
    for index, item in enumerate(exported):
        prior: dict[str, Any] = {}
        for key in ("sourceUrl", "sourceItemId", "assetPath", "fileName"):
            value = str(item.get(key) or "")
            if not value:
                continue
            prior = next(
                (candidate for candidate in candidates if str(candidate.get(key) or "") == value),
                {},
            )
            if prior:
                break
        if not prior and index < len(previous):
            prior = previous[index]
        result.append({**prior, **item})
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--asset-origin", required=True)
    parser.add_argument("--cookie-file", required=True, type=Path)
    args = parser.parse_args()

    exported = _read_json(args.source)
    previous = _read_json(MASTER_PATH)
    old_by_type = {_type_id(item): item for item in previous.get("templates") or []}
    templates = exported.get("templates") or []
    if len(templates) != 16:
        raise ValueError(f"Expected 16 templates, got {len(templates)}")

    cookie = args.cookie_file.read_text(encoding="utf-8").strip()
    jobs: list[tuple[str, str, Path, bool, dict[str, Any]]] = []
    normalized: list[dict[str, Any]] = []

    for source_template in templates:
        type_id = _type_id(source_template)
        if not type_id or type_id not in old_by_type:
            raise ValueError(f"Unknown personality type: {type_id or '<empty>'}")
        old = old_by_type[type_id]
        template = dict(source_template)
        template.pop("templateId", None)
        template.pop("createdAt", None)
        template["schemaVersion"] = str(old.get("schemaVersion") or "selfit-report-template/1.0")
        template["assetQualityVersion"] = 4
        template["masterData"] = {
            **(old.get("masterData") or {}),
            **(template.get("masterData") or {}),
            "typeId": type_id,
        }

        hero_source = str(template.get("hero") or "")
        hero_target = ASSET_ROOT / type_id / "hero.png"
        jobs.append((_asset_url(args.asset_origin, hero_source), cookie, hero_target, True, template))
        template["hero"] = f"/static/selfit/assets/personality/{type_id}/hero.png?v={ASSET_VERSION}"

        for group in GROUPS:
            library_key = "outfitLibrary" if group == "outfits" else f"{group}Library"
            items = _enrich_selected_items(
                list(template.get(group) or []),
                list(old.get(group) or []),
                list(old.get(library_key) or []),
            )
            template[group] = items
            expected = 4 if group == "outfits" else 2
            if len(items) != expected:
                raise ValueError(f"{type_id}.{group}: expected {expected}, got {len(items)}")
            for index, item in enumerate(items, 1):
                item["position"] = index
                source = str(item.get("image") or "")
                target = ASSET_ROOT / type_id / f"report-{group}-{index:02d}.webp"
                jobs.append((_asset_url(args.asset_origin, source), cookie, target, False, item))
                item["image"] = (
                    f"/static/selfit/assets/personality/{type_id}/report-{group}-{index:02d}.webp"
                    f"?v={ASSET_VERSION}"
                )

        source_block = dict(template.get("source") or {})
        avatars = dict(source_block.get("avatars") or {})
        avatars["imageUrl"] = "/static/selfit/assets/report-user-avatar-stack@4x.png"
        source_block["avatars"] = avatars
        template["source"] = source_block

        for group in ("makeup", "hair"):
            key = f"{group}Library"
            template[key] = list(old.get(key) or [])
        template["outfitLibrary"] = _library_items(
            list(template.get("outfitLibrary") or []),
            list(old.get("outfitLibrary") or []),
            type_id=type_id,
            group="outfits",
        )
        normalized.append(template)

    failures: list[str] = []
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(_download, url, request_cookie): (url, target, hero, owner)
            for url, request_cookie, target, hero, owner in jobs
        }
        for future in as_completed(futures):
            url, target, hero, owner = futures[future]
            try:
                width, height = _save_image(future.result(), target, hero=hero)
                if not hero:
                    owner["imageWidth"] = width
                    owner["imageHeight"] = height
            except Exception as exc:  # noqa: BLE001 - aggregate all failed assets
                failures.append(f"{url}: {exc}")
    if failures:
        raise RuntimeError("Failed to import report assets:\n" + "\n".join(failures))

    master = {
        "schemaVersion": str(exported.get("schemaVersion") or "selfit-report-library/1.0"),
        "seedVersion": int(previous.get("seedVersion") or 0) + 1,
        "generatedAt": str(exported.get("exportedAt") or ""),
        "source": args.source.name,
        "templates": normalized,
    }
    MASTER_PATH.write_text(json.dumps(master, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    SEED_JS_PATH.write_text(
        "window.SELFIT_REPORT_MASTER_DATA = Object.freeze("
        + json.dumps(master, ensure_ascii=False, separators=(",", ":"))
        + ");\n",
        encoding="utf-8",
    )
    print(f"[ok] imported {len(jobs)} private assets across {len(normalized)} personality types")
    print(f"[ok] master templates: {MASTER_PATH}")
    print(f"[ok] report builder seed: {SEED_JS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
