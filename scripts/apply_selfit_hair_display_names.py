"""把人工校对的发型名称同步到报告主数据与完整候选库。"""

from __future__ import annotations

import json
from typing import Any

from sync_selfit_personality_database import (
    LIBRARY_PATH,
    MASTER_PATH,
    SEED_JS_PATH,
    _hair_display_names,
    _read,
    _text,
)


def _calibrated_name(item: dict[str, Any], names: dict[str, str]) -> str:
    source_item_id = _text(item.get("sourceItemId"))
    file_name = _text(item.get("fileName"))
    return names.get(f"item:{source_item_id}") or names.get(f"file:{file_name}") or ""


def _apply(items: list[dict[str, Any]], names: dict[str, str]) -> int:
    changed = 0
    for item in items:
        name = _calibrated_name(item, names)
        if name and item.get("name") != name:
            item["name"] = name
            changed += 1
    return changed


def main() -> int:
    names = _hair_display_names()
    master = _read(MASTER_PATH)
    library = _read(LIBRARY_PATH)
    master_changed = 0
    library_changed = 0

    for template in master.get("templates") or []:
        master_changed += _apply(template.get("hair") or [], names)
        master_changed += _apply(template.get("hairLibrary") or [], names)

    for content in (library.get("types") or {}).values():
        library_changed += _apply(content.get("hair") or [], names)

    MASTER_PATH.write_text(json.dumps(master, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    LIBRARY_PATH.write_text(json.dumps(library, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    SEED_JS_PATH.write_text(
        "window.SELFIT_REPORT_MASTER_DATA = Object.freeze("
        + json.dumps(master, ensure_ascii=False, separators=(",", ":"))
        + ");\n",
        encoding="utf-8",
    )
    print(f"[ok] 报告主数据更新 {master_changed} 处发型名称")
    print(f"[ok] 完整候选库更新 {library_changed} 条发型名称")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
