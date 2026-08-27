"""把报告编辑器主数据导入 Selfit 运行时模板与推荐内容池。

输入是已经人工校对的 16 人格主数据；输出：
1. 前端 TYPE 兜底模板 JSON/JS；
2. 后端 SUIT 穿搭重排所需 pool.json。

妆容与发型当前只有人格标签，没有可靠的肤色×地域、肤色×脸型标签，
因此不写入 SUIT 静态矩阵，继续由 TYPE 模板兜底，避免伪造适配结论。
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "app" / "static" / "report-builder" / "data" / "16-personality-templates.json"
RUNTIME_JSON = ROOT / "app" / "static" / "selfit" / "data" / "personality-report-templates.v1.json"
RUNTIME_JS = ROOT / "app" / "static" / "selfit" / "personality-report-templates.js"
POOL_JSON = ROOT / "app" / "static" / "selfit" / "data" / "content-pool.v1.json"
TEMPLATE_VERSION = "2026.08.personality-db-v4"


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def _split_labels(value: Any) -> list[str]:
    return [item.strip() for item in str(value or "").split("|") if item.strip()]


def _style_code(value: str, code_by_name: dict[str, str]) -> str | None:
    upper = value.strip().upper()
    for code in code_by_name.values():
        if re.search(rf"(?:^|\s){re.escape(code)}(?:$|\s)", upper):
            return code
    for name, code in code_by_name.items():
        if name in value:
            return code
    return None


def _image(src: str, alt: str, existing: dict[str, Any] | None = None) -> dict[str, Any]:
    result = dict(existing or {})
    result.update({"src": src, "alt": alt})
    return result


def _card(item: dict[str, Any], *, card_id: str, type_name: str,
          existing: dict[str, Any] | None = None) -> dict[str, Any]:
    prior = existing or {}
    return {
        "id": card_id,
        "name": str(item.get("name") or ""),
        "byline": str(item.get("byline") or ""),
        "sourceUrl": str(item.get("sourceUrl") or ""),
        "image": _image(
            str(item.get("image") or ""),
            f"{type_name} · {item.get('name') or '推荐参考'}",
            prior.get("image") if isinstance(prior.get("image"), dict) else None,
        ),
    }


def build_runtime(master: dict[str, Any], existing: dict[str, Any]) -> dict[str, Any]:
    old_types = existing.get("types") if isinstance(existing.get("types"), dict) else {}
    types: dict[str, Any] = {}
    for template in master.get("templates") or []:
        type_id = str((template.get("masterData") or {}).get("typeId") or "").lower()
        if not type_id:
            continue
        previous = old_types.get(type_id) if isinstance(old_types, dict) else {}
        previous = previous if isinstance(previous, dict) else {}
        name = str(template.get("name") or "").removesuffix("型人格")
        code = str(template.get("code") or type_id.upper())
        old_recommendations = previous.get("recommendations") or {}
        old_makeup = old_recommendations.get("makeup") or []
        old_hair = old_recommendations.get("hair") or []
        old_outfits = (old_recommendations.get("outfits") or {}).get("items") or []

        makeup = [
            _card(item, card_id=f"makeup-{index:02d}", type_name=name,
                  existing=old_makeup[index - 1] if index <= len(old_makeup) else None)
            for index, item in enumerate(template.get("makeup") or [], 1)
        ]
        hair = [
            _card(item, card_id=f"hair-{index:02d}", type_name=name,
                  existing=old_hair[index - 1] if index <= len(old_hair) else None)
            for index, item in enumerate(template.get("hair") or [], 1)
        ]
        outfits = [
            _card(item, card_id=f"outfits-{index:02d}", type_name=name,
                  existing=old_outfits[index - 1] if index <= len(old_outfits) else None)
            for index, item in enumerate(template.get("outfits") or [], 1)
        ]
        old_hero = (previous.get("hero") or {}).get("image") or {}
        hero_image = _image(str(template.get("hero") or ""), f"{name} {code} 人格封面", old_hero)
        hero_image.update({"width": 1484, "height": 1072, "placeholder": False})
        old_colors = previous.get("colors") or {}
        old_color_items = old_colors.get("items") or []
        master_colors = template.get("colors") or []
        color_items = []
        color_count = max(len(old_color_items), len(master_colors))
        for index in range(color_count):
            prior_color = old_color_items[index] if index < len(old_color_items) else {}
            master_color = master_colors[index] if index < len(master_colors) else {}
            color_items.append({
                **prior_color,
                "id": str(prior_color.get("id") or f"color-{index + 1:02d}"),
                "name": str(master_color.get("name") or prior_color.get("name") or ""),
                "value": str(master_color.get("value") or prior_color.get("value") or ""),
            })
        source = dict(template.get("source") or {})
        types[type_id] = {
            "typeId": type_id,
            "index": int((template.get("masterData") or {}).get("index") or 0),
            "status": "assets-ready",
            "metadata": {"name": name, "code": code},
            "hero": {"image": hero_image},
            "keywords": list(template.get("keywords") or []),
            "summary": str(template.get("summary") or ""),
            "colors": {
                "tagline": " · ".join(str(item) for item in (template.get("keywords") or [])),
                "renderLimit": 5,
                "sourceCard": old_colors.get("sourceCard") or {},
                # 主数据维护前 5 个展示色，原资产模板中的扩展色仍完整保留。
                "items": color_items,
            },
            "recommendations": {
                "makeup": makeup,
                "hair": hair,
                "outfits": {"summary": str(template.get("outfitSummary") or ""), "source": source, "items": outfits},
            },
            "conclusion": {
                "intro": str(template.get("conclusion") or ""),
                "points": list(template.get("advice") or []),
            },
        }
    return {
        "schemaVersion": "2.0",
        "locale": "zh-CN",
        "templateVersion": TEMPLATE_VERSION,
        "renderRules": {"colors": {"limit": 5}, "makeup": {"limit": 2}, "hair": {"limit": 2}, "outfits": {"limit": 4}},
        "types": types,
    }


def build_pool(master: dict[str, Any]) -> dict[str, Any]:
    templates = master.get("templates") or []
    code_by_name = {
        str(template.get("name") or "").removesuffix("型人格"): str(template.get("code") or "").upper()
        for template in templates
    }
    outfits: list[dict[str, Any]] = []
    for template in templates:
        type_id = str((template.get("masterData") or {}).get("typeId") or "").lower()
        code = str(template.get("code") or type_id.upper()).upper()
        type_name = str(template.get("name") or "").removesuffix("型人格")
        # 推荐算法使用完整穿搭候选库；前端报告仍按 renderRules 只展示前 4 张。
        library = template.get("outfitLibrary") or template.get("outfits") or []
        for index, item in enumerate(library, 1):
            image_url = str(item.get("image") or "")
            if not image_url:
                continue
            secondary = []
            for label in _split_labels(item.get("secondaryStyle")):
                secondary_code = _style_code(label, code_by_name)
                if secondary_code and secondary_code != code and secondary_code not in secondary:
                    secondary.append(secondary_code)
            regions = _split_labels(item.get("regionalStyle"))
            body_types = _split_labels(item.get("bodyTypes"))
            styling = str(item.get("styling") or "")
            mood = str(item.get("mood") or "")
            description = "；".join(value for value in (styling, mood) if value)
            outfits.append({
                "id": f"outfit_{type_id}_{index:02d}",
                "title": str(item.get("name") or f"{type_name}穿搭"),
                "description": description,
                "author": str(item.get("byline") or "").removeprefix("@"),
                "badge": "精选",
                "imageUrl": image_url,
                "alt": f"{type_name} · {item.get('name') or '穿搭参考'}",
                "sourceUrl": str(item.get("sourceUrl") or ""),
                "primary_persona": code,
                "secondary_personas": secondary,
                "regional_styles": regions,
                "body_types": body_types,
            })
    return {"outfits": outfits, "makeup": {}, "hair": {}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    args = parser.parse_args()
    master = _read_json(args.source)
    existing = _read_json(RUNTIME_JSON) if RUNTIME_JSON.exists() else {}
    runtime = build_runtime(master, existing)
    pool = build_pool(master)

    RUNTIME_JSON.parent.mkdir(parents=True, exist_ok=True)
    POOL_JSON.parent.mkdir(parents=True, exist_ok=True)
    RUNTIME_JSON.write_text(json.dumps(runtime, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    RUNTIME_JS.write_text(
        "window.__SELFIT_PERSONALITY_TEMPLATES__ = Object.freeze("
        + json.dumps(runtime, ensure_ascii=False, separators=(",", ":"))
        + ");\n",
        encoding="utf-8",
    )
    POOL_JSON.write_text(json.dumps(pool, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[ok] TYPE 模板 {len(runtime['types'])} 种: {RUNTIME_JSON}")
    print(f"[ok] SUIT 可排序真实穿搭 {len(pool['outfits'])} 条: {POOL_JSON}")
    print("[info] 妆容/发型缺少可靠 SUIT 标签，保留 TYPE 兜底，不写入覆盖池")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
