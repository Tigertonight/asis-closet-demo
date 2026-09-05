#!/usr/bin/env python3
"""Build a reviewable V2 draft from the current Selfit outfit content pool.

The migration is deliberately conservative: facts found in source records are
copied, simple text-derived labels are marked as machine drafts, and unknown
visual attributes stay ``未判断`` instead of being fabricated. The V2 draft is
not switched into production automatically.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SOURCE_POOL = ROOT / "app/static/selfit/data/content-pool.v1.json"
SOURCE_LIBRARY = ROOT / "app/static/report-builder/data/personality-content-library.v2.json"
OUTPUT_POOL = ROOT / "app/static/selfit/data/content-pool.v2.draft.json"
OUTPUT_AUDIT = ROOT / "docs/SELFIT_CONTENT_POOL_V2_COVERAGE.json"
CAPSULE_DIR = ROOT / "app/static/selfit/data/capsules"

PERSONAS = ("MUTE", "ICED", "HEIR", "EASE", "MELT", "WABI", "FLOU", "NEON", "EDGE", "BOLT", "FILM", "JADE", "LOOP", "NOIR", "VOID", "OOPS")
SEASONS = ("春", "夏", "秋", "冬")
SCENES = ("通勤", "日常", "约会社交", "正式活动", "旅行", "创意表达")

SLOT_TERMS = {
    "top": ("上装", "上衣", "衬衫", "背心", "针织", "卫衣", "T恤"),
    "outer": ("外套", "风衣", "夹克", "大衣", "西装", "皮衣", "开衫"),
    "bottom": ("下装", "裤", "牛仔"),
    "skirt": ("半裙", "短裙", "长裙", "百褶", "纱裙"),
    "dress": ("连衣", "裙装", "旗袍"),
    "shoes": ("鞋", "靴"),
    "bag": ("包",),
    "hat": ("帽",),
    "scarf": ("围巾", "披肩"),
    "accessory": ("配饰", "首饰", "腰带", "领带"),
}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _library_index() -> dict[str, dict[str, Any]]:
    data = _load(SOURCE_LIBRARY)
    index: dict[str, dict[str, Any]] = {}
    for personality in data.get("types", {}).values():
        for item in personality.get("outfits", []):
            for key in (item.get("image"), item.get("name")):
                if key:
                    index[str(key)] = item
    return index


def _parse_seasons(note: str, text: str) -> list[str]:
    match = re.search(r"季节感：([^；\n]+)", note)
    source = match.group(1) if match else text
    values = [season for season in SEASONS if season in source]
    if "春夏" in source:
        values.extend(("春", "夏"))
    if "秋冬" in source:
        values.extend(("秋", "冬"))
    return list(dict.fromkeys(values))


def _parse_presentation(note: str) -> list[str]:
    match = re.search(r"性别呈现：([^；\n]+)", note)
    value = match.group(1) if match else ""
    if "中性" in value or "无性别" in value:
        return ["neutral"]
    if "男" in value:
        return ["masculine"]
    if "女" in value:
        return ["feminine"]
    return []


def _parse_scenes(text: str) -> list[str]:
    rules = {
        "通勤": ("通勤", "职场", "办公室", "上班"),
        "约会社交": ("约会", "聚会", "社交", "派对"),
        "正式活动": ("礼服", "晚宴", "婚礼", "正式", "红毯"),
        "旅行": ("旅行", "度假", "机场", "海边", "出游"),
        "创意表达": ("先锋", "实验", "解构", "撞色", "舞台", "反套路"),
        "日常": ("日常", "休闲", "周末", "生活", "舒服"),
    }
    return [scene for scene, terms in rules.items() if any(term in text for term in terms)]


def _parse_visible_slots(note: str, text: str) -> list[str]:
    match = re.search(r"单品可见性：([^；\n]+)", note)
    source = match.group(1) if match else text
    return [slot for slot, terms in SLOT_TERMS.items() if any(term in source for term in terms)]


def _formality(text: str) -> int:
    if any(term in text for term in ("礼服", "晚宴", "婚礼", "红毯")):
        return 5
    if any(term in text for term in ("西装", "通勤", "花呢", "旗袍")):
        return 4
    if any(term in text for term in ("卫衣", "运动", "睡裤", "休闲")):
        return 2
    return 3


def _draft_outfit(item: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    note = str(source.get("notes") or "")
    text = " ".join(str(value or "") for value in (item.get("title"), item.get("description"), source.get("styling"), source.get("mood"), note))
    seasons = _parse_seasons(note, text)
    scenes = _parse_scenes(text)
    presentation = _parse_presentation(note)
    visible_slots = _parse_visible_slots(note, text)
    secondary = [str(value) for value in item.get("secondary_personas") or []]
    affinity = {str(item.get("primary_persona")): 1.0, **{value: 0.72 for value in secondary}}
    missing: list[str] = []
    for key, value in (("scene_tags", scenes), ("season_tags", seasons), ("presentation", presentation), ("visible_slots", visible_slots)):
        if not value:
            missing.append(key)
    missing.extend(("structure", "color", "garment_ids", "layer_graph"))
    return {
        **item,
        "persona_affinity": affinity,
        "scene_tags": scenes,
        "season_tags": seasons,
        "weather_tags": [],
        "presentation": presentation,
        "intensity": "signature",
        "formality": _formality(text),
        "garment_ids": [],
        "visible_slots": visible_slots,
        "layer_graph": [],
        "structure": {"visual_weight": "未判断", "waistline": "未判断", "tummy_space": "未判断", "line_direction": "未判断"},
        "color": {"temperature": "未判断", "lightness": "未判断", "saturation": "未判断", "harmony": "未判断", "palette": []},
        "recommendation_reasons": [],
        "assets": {
            "image_url": str(item.get("imageUrl") or ""),
            "source_url": str(item.get("sourceUrl") or ""),
            "width": source.get("imageWidth") or source.get("width"),
            "height": source.get("imageHeight") or source.get("height"),
            "alpha_verified": False,
            "rights_status": "source_recorded" if item.get("sourceUrl") else "source_missing",
        },
        "annotation": {
            "status": "machine_draft",
            "source": "source_record" if note else "text_heuristic",
            "confidence": 0.72 if note else 0.42,
            "review_notes": [f"待补：{field}" for field in missing],
        },
    }


def build() -> tuple[dict[str, Any], dict[str, Any]]:
    source_pool = _load(SOURCE_POOL)
    library = _library_index()
    outfits = []
    for item in source_pool.get("outfits", []):
        source = library.get(str(item.get("imageUrl") or "")) or library.get(str(item.get("title") or "")) or {}
        outfits.append(_draft_outfit(item, source))
    garments: list[dict[str, Any]] = []
    generated_capsules: list[str] = []
    existing_outfit_ids = {str(item.get("id") or "") for item in outfits}
    existing_garment_ids: set[str] = set()
    for capsule_path in sorted(CAPSULE_DIR.glob("*.json")):
        capsule = _load(capsule_path)
        for garment in capsule.get("garments", []):
            garment_id = str(garment.get("id") or "")
            if garment_id and garment_id not in existing_garment_ids:
                garments.append(garment)
                existing_garment_ids.add(garment_id)
        outfit = capsule.get("outfit")
        outfit_id = str((outfit or {}).get("id") or "")
        if outfit_id and outfit_id not in existing_outfit_ids:
            outfits.append(outfit)
            existing_outfit_ids.add(outfit_id)
        generated_capsules.append(str(capsule_path.relative_to(ROOT)))

    counts = defaultdict(Counter)
    for outfit in outfits:
        code = str(outfit.get("primary_persona") or "UNKNOWN")
        counts[code]["outfits"] += 1
        for field in ("scene_tags", "season_tags", "presentation", "visible_slots", "body_types", "regional_styles"):
            if outfit.get(field):
                counts[code][f"with_{field}"] += 1

    audit = {
        "generatedAt": datetime.now(UTC).isoformat(),
        "source": str(SOURCE_POOL.relative_to(ROOT)),
        "totalOutfits": len(outfits),
        "totalGarments": len(garments),
        "generatedCapsules": generated_capsules,
        "personaCoverage": {code: dict(counts[code]) for code in PERSONAS},
        "globalCoverage": {
            field: sum(bool(outfit.get(field)) for outfit in outfits)
            for field in ("scene_tags", "season_tags", "presentation", "visible_slots", "body_types", "regional_styles", "garment_ids")
        },
        "publishBlockers": [
            "all structure and color fields require visual designer review",
            "existing outfit images have not been decomposed into garment_ids",
            "asset rights must be confirmed beyond recording source URLs",
            "scene, season, presentation and visible-slot heuristics require spot checks",
        ],
    }
    pool = {
        "schemaVersion": "2.0",
        "contentVersion": "2026.09-v2-draft1",
        "status": "draft",
        "generatedAt": audit["generatedAt"],
        "sourceVersion": "content-pool.v1.json",
        "outfits": outfits,
        "garments": garments,
        "makeup": source_pool.get("makeup", {}),
        "hair": source_pool.get("hair", {}),
    }
    return pool, audit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT_POOL)
    parser.add_argument("--audit", type=Path, default=OUTPUT_AUDIT)
    args = parser.parse_args()
    pool, audit = build()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.audit.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(pool, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.audit.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "audit": str(args.audit), "outfits": len(pool["outfits"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
