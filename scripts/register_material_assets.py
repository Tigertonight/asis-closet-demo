"""把报告运行时 JSON 中的本地图片改为 assetId，并更新浏览器模板。

    python scripts/register_material_assets.py

只登记公开 /static/ 素材，不上传文件；重复执行不会改变已有 ID 或 CDN URL。
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.material_assets import MaterialRegistry, resolve_image_references, write_json_atomic

DEFAULT_CATALOG = ROOT / "app/static/selfit/data/personality-report-templates.v1.json"
DEFAULT_JS = ROOT / "app/static/selfit/personality-report-templates.js"


def register_catalog_images(value: Any, registry: MaterialRegistry, *, static_root: Path | None = None) -> Any:
    """Replace render image URLs only. Attribution/sourceUrl links are preserved."""
    static_root = (static_root or ROOT / "app/static").resolve()
    if isinstance(value, list):
        return [register_catalog_images(item, registry, static_root=static_root) for item in value]
    if not isinstance(value, dict):
        return value
    result = {key: register_catalog_images(item, registry, static_root=static_root) for key, item in value.items()}
    for url_field, id_field in (("src", "assetId"), ("imageUrl", "imageAssetId")):
        url = result.get(url_field)
        if not isinstance(url, str) or not url:
            continue
        # Older report color cards use ../../static/... references.
        normalized = "/" + url.removeprefix("../../") if url.startswith("../../static/") else url
        parsed = urlsplit(normalized)
        if parsed.scheme or parsed.netloc or not parsed.path.startswith("/static/"):
            raise ValueError(f"Register/upload remote material first and supply {id_field}: {url}")
        path = (static_root / unquote(parsed.path[len('/static/'):])).resolve()
        if not path.is_relative_to(static_root) or not path.is_file():
            raise ValueError(f"Missing public material: {url}")
        result[id_field] = registry.register(path.read_bytes(), normalized,
                                             mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                                             replace_url=False)
        del result[url_field]
    for field in ("assetId", "imageAssetId"):
        if result.get(field):
            registry.get(result[field])
    return result


def browser_catalog_script(catalog: dict[str, Any], registry: MaterialRegistry) -> str:
    # Generated src/imageUrl values contain only ID routes, never storage/CDN URLs.
    runtime = resolve_image_references(catalog, registry)
    return ("// Generated from personality-report-templates.v1.json; URLs resolve through material-assets.\n"
            + "window.__SELFIT_PERSONALITY_TEMPLATES__ = Object.freeze("
            + json.dumps(runtime, ensure_ascii=False, separators=(",", ":")) + ");\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--js", type=Path, default=DEFAULT_JS)
    parser.add_argument("--registry", type=Path)
    args = parser.parse_args()
    registry = MaterialRegistry(args.registry)
    catalog = register_catalog_images(json.loads(args.catalog.read_text(encoding="utf-8")), registry)
    script = browser_catalog_script(catalog, registry)
    write_json_atomic(args.catalog, catalog)
    args.js.write_text(script, encoding="utf-8")
    print(f"[ok] 素材 ID 已写入 {args.catalog}；清单: {registry.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
