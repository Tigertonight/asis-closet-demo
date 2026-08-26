"""同步 16 人格穿搭、妆容、发型明细与本地图片资源。

表格读取由 Codex spreadsheet artifact-tool 完成，生成的 workbook snapshot
包含三个工作表的 preview 数据。本脚本把 snapshot 转为项目内可版本化的数据源，
更新报告编辑器主模板，并将所有候选图标准化为 WebP。运行时仍按 2/2/4
展示，完整候选库保存在 makeupLibrary / hairLibrary / outfitLibrary。
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[1]
MASTER_PATH = ROOT / "app/static/report-builder/data/16-personality-templates.json"
SEED_JS_PATH = ROOT / "app/static/report-builder/seed-templates.js"
LIBRARY_PATH = ROOT / "app/static/report-builder/data/personality-content-library.v2.json"
HAIR_DISPLAY_NAMES_PATH = ROOT / "app/static/report-builder/data/hair-display-names.v1.json"
ASSET_ROOT = ROOT / "app/static/selfit/assets/personality"
KIND_CONFIG = {
    "makeup": {"folder": "16人格妆容", "name": "妆容名称", "limit": 2},
    "hair": {"folder": "16人格发型", "name": "发型名称", "limit": 2},
    "outfits": {"folder": "16人格穿搭", "name": "穿搭名称", "limit": 4},
}
VERSION = "20260826-db-v3"


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be object: {path}")
    return value


def _preview(snapshot: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    ndjson = str(snapshot[kind]["region"]).strip().splitlines()[0]
    region = json.loads(ndjson)
    rows = region.get("preview") or []
    if len(rows) < 2:
        return []
    headers = [str(item or "") for item in rows[0]]
    return [
        {headers[index]: value for index, value in enumerate(row) if index < len(headers)}
        for row in rows[1:]
        if any(value not in (None, "") for value in row)
    ]


def _text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    # artifact-tool 对这三份工作簿的部分空文本单元格会返回共享样式号 39。
    # 该值不是业务数据；数值列均通过 _number 读取，不受这里影响。
    return "" if text == "39" else text


def _number(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return default


def _code(row: dict[str, Any]) -> str:
    match = re.search(r"\b([A-Z]{4,5})\b", _text(row.get("人格分类")))
    if not match:
        raise ValueError(f"人格分类缺少 code: {row.get('人格分类')!r}")
    return match.group(1)


def _byline(value: Any) -> str:
    text = _text(value)
    return f"@{text.lstrip('@')}" if text else ""


def _hair_display_names(path: Path = HAIR_DISPLAY_NAMES_PATH) -> dict[str, str]:
    """读取人工校对的发型名称，避免把小红书笔记标题当成发型类型。"""
    value = _read(path)
    names: dict[str, str] = {}
    for item in value.get("items") or []:
        name = _text(item.get("name"))
        if not name:
            continue
        source_item_id = _text(item.get("sourceItemId"))
        file_name = _text(item.get("fileName"))
        if source_item_id:
            names[f"item:{source_item_id}"] = name
        if file_name:
            names[f"file:{file_name}"] = name
    return names


def _split(value: Any) -> list[str]:
    return [item.strip() for item in _text(value).split("|") if item.strip()]


def _web_path(type_id: str, kind: str, position: int) -> str:
    return f"/static/selfit/assets/personality/{type_id}/{kind}-{position:02d}.webp?v={VERSION}"


def _asset_path_from_web(web_path: str) -> Path:
    relative = web_path.split("?", 1)[0].removeprefix("/static/selfit/assets/personality/")
    return ASSET_ROOT / relative


def _common_item(
    row: dict[str, Any],
    *,
    type_id: str,
    kind: str,
    hair_names: dict[str, str] | None = None,
) -> dict[str, Any]:
    position = _number(row.get("展示位次"))
    name_key = str(KIND_CONFIG[kind]["name"])
    source_item_id = _text(row.get("笔记ItemID"))
    file_name = _text(row.get("文件名"))
    if kind == "hair":
        calibrated_name = (hair_names or {}).get(f"item:{source_item_id}") or (hair_names or {}).get(f"file:{file_name}")
        # 发型卡首行只允许使用“发型名称”。笔记标题独立保存在 sourceTitle，
        # 即使名称缺失也不再静默回退为笔记标题。
        name = calibrated_name or _text(row.get(name_key)) or f"待补充发型名称 {position:02d}"
    else:
        name = _text(row.get(name_key)) or _text(row.get("笔记标题")) or f"{kind}-{position:02d}"
    item = {
        "position": position,
        "name": name,
        "byline": _byline(row.get("博主")),
        "image": _web_path(type_id, kind, position),
        "assetPath": _text(row.get("导出相对路径")),
        "fileName": file_name,
        "sourceTitle": _text(row.get("笔记标题")),
        "sourceUrl": _text(row.get("笔记链接")),
        "sourceItemId": source_item_id,
        "width": _number(row.get("宽")),
        "height": _number(row.get("高")),
    }
    if kind == "outfits":
        item.update({
            "primaryStyle": _text(row.get("主人格")),
            "secondaryStyle": _text(row.get("次人格")),
            "regionalStyle": _text(row.get("地域美学风格")),
            "bodyTypes": _text(row.get("体型标签")),
            "notes": _text(row.get("备注")),
            "styling": _text(row.get("穿法说明")),
            "mood": _text(row.get("氛围文案")),
        })
    elif kind == "makeup":
        item["tags"] = {
            "skinTones": _split(row.get("适合肤色")),
            "regionalStyles": _split(row.get("来源地域美学风格")),
            "faceShapes": _split(row.get("适合脸型")),
            "makeupType": _text(row.get("妆容类型")),
            "makeupTone": _text(row.get("妆容色调")),
            "makeupFocus": _text(row.get("妆容重点")),
        }
    elif kind == "hair":
        item["tags"] = {
            "regionalStyles": _split(row.get("地域美学风格")),
            "bodyTypes": _split(row.get("体型标签")),
            "length": _text(row.get("发型长度")),
            "curl": _text(row.get("卷度")),
            "color": _text(row.get("发色")),
            "bangs": _text(row.get("刘海")),
            "styling": _text(row.get("发型造型")),
        }
    return item


def _convert(source: Path, target: Path) -> tuple[int, int]:
    target.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        image.thumbnail((1080, 1620), Image.Resampling.LANCZOS)
        image.save(target, "WEBP", quality=90, method=6)
        return image.size


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--workbook-snapshot", required=True, type=Path)
    args = parser.parse_args()

    snapshot = _read(args.workbook_snapshot)
    master = _read(MASTER_PATH)
    templates = master.get("templates") or []
    template_by_code = {str(item.get("code") or "").upper(): item for item in templates}
    type_id_by_code = {
        code: _text((item.get("masterData") or {}).get("typeId")).lower()
        for code, item in template_by_code.items()
    }

    database: dict[str, dict[str, list[dict[str, Any]]]] = {
        type_id: {"makeup": [], "hair": [], "outfits": []}
        for type_id in type_id_by_code.values()
    }
    missing: list[str] = []
    converted = 0
    hair_names = _hair_display_names()

    for kind, config in KIND_CONFIG.items():
        rows = sorted(_preview(snapshot, kind), key=lambda row: (_number(row.get("人格序号")), _number(row.get("展示位次"))))
        for row in rows:
            code = _code(row)
            type_id = type_id_by_code.get(code)
            if not type_id:
                raise ValueError(f"主模板缺少人格 code: {code}")
            item = _common_item(row, type_id=type_id, kind=kind, hair_names=hair_names)
            source = args.source_root / str(config["folder"]) / item["assetPath"]
            if not source.is_file():
                missing.append(str(source))
                continue
            target = _asset_path_from_web(item["image"])
            width, height = _convert(source, target)
            item["imageWidth"] = width
            item["imageHeight"] = height
            database[type_id][kind].append(item)
            converted += 1

    if missing:
        raise FileNotFoundError("明细表引用的素材缺失:\n" + "\n".join(missing))

    today = date.today().isoformat()
    for code, template in template_by_code.items():
        type_id = type_id_by_code[code]
        content = database[type_id]
        for kind, config in KIND_CONFIG.items():
            library_key = "outfitLibrary" if kind == "outfits" else f"{kind}Library"
            template[library_key] = content[kind]
            template[kind] = content[kind][: int(config["limit"])]
        meta = template.setdefault("masterData", {})
        meta.update({
            "sourceWorkbook": "穿搭明细表.xlsx",
            "sourceWorkbooks": {
                "outfits": "穿搭明细表.xlsx",
                "hair": "发型明细表.xlsx",
                "makeup": "妆容明细表.xlsx",
            },
            "sourceCount": len(content["outfits"]),
            "sourceCounts": {kind: len(content[kind]) for kind in KIND_CONFIG},
            "sourceUpdatedAt": today,
        })
        template["assetQualityVersion"] = 3
        template["updatedAt"] = today
        source_block = template.setdefault("source", {})
        source_block["copy"] = f"已整理 {len(content['outfits'])} 条穿搭素材"

    master["seedVersion"] = max(_number(master.get("seedVersion")), 7) + 1
    master["generatedAt"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    master["source"] = "穿搭明细表.xlsx + 发型明细表.xlsx + 妆容明细表.xlsx"

    LIBRARY_PATH.write_text(json.dumps({
        "schemaVersion": "selfit-personality-content-library/2.0",
        "version": VERSION,
        "generatedAt": master["generatedAt"],
        "renderRules": {"makeup": 2, "hair": 2, "outfits": 4},
        "types": database,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    MASTER_PATH.write_text(json.dumps(master, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    SEED_JS_PATH.write_text(
        "window.SELFIT_REPORT_MASTER_DATA = Object.freeze("
        + json.dumps(master, ensure_ascii=False, separators=(",", ":"))
        + ");\n",
        encoding="utf-8",
    )
    print(f"[ok] imported {converted} assets across {len(database)} personality types")
    print(f"[ok] source library: {LIBRARY_PATH}")
    print(f"[ok] master templates: {MASTER_PATH}")
    print(f"[ok] report builder seed: {SEED_JS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
