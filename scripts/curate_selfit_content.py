#!/usr/bin/env python3
"""Build an idempotent, reversible editorial overlay; never overwrite assets.

Opaque image pixels provide measured color evidence, NOT fabric/fit/temperature
truth. Semantic labels remain pending until image-level review is recorded.
"""
from __future__ import annotations

import argparse
import colorsys
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from app.selfit_content_quality import CURATION_PATH, record_fingerprint

POOL = ROOT / "app/static/selfit/data/content-pool.v2.published.json"
AUDIT = ROOT / "docs/SELFIT_V2_FASHION_DESIGN_AUDIT_20260903.json"
REPORT = ROOT / "docs/SELFIT_CONTENT_CURATION_STATUS.json"
UNKNOWN_COLOR = {"temperature": "未判断", "lightness": "未判断", "saturation": "未判断", "harmony": "未判断", "palette": []}


def color_family(rgb: list[int]) -> str:
    h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))
    if v < .19:
        return "黑"
    if s < .13:
        return "白" if v > .8 else "灰"
    degrees = h * 360
    if degrees < 18 or degrees >= 340:
        return "粉" if v > .65 and s < .5 else "红"
    if degrees < 52:
        return "奶油白" if v > .83 and s < .24 else "棕" if v < .75 else "黄"
    if degrees < 75:
        return "黄"
    if degrees < 170:
        return "绿"
    if degrees < 260:
        return "蓝"
    return "粉" if v > .65 and s < .45 else "紫"


def measure_color(path: Path) -> dict:
    with Image.open(path) as source:
        image = source.convert("RGBA")
        image.thumbnail((180, 180))
        pixels = [(r, g, b) for r, g, b, a in image.get_flattened_data() if a >= 240]
    if not pixels:
        raise ValueError(f"no opaque garment pixels: {path}")
    strip = Image.new("RGB", (len(pixels), 1))
    strip.putdata(pixels)
    quantized = strip.quantize(colors=5, method=Image.Quantize.MEDIANCUT)
    palette = quantized.getpalette()
    swatches = []
    for count, index in sorted(quantized.getcolors(), reverse=True):
        rgb = palette[index * 3:index * 3 + 3]
        swatches.append({"hex": "#" + "".join(f"{c:02x}" for c in rgb), "weight": round(count / len(pixels), 4), "family": color_family(rgb)})
    hsv = [colorsys.rgb_to_hsv(r / 255, g / 255, b / 255) for r, g, b in pixels]
    saturation = sum(s for _, s, _ in hsv) / len(hsv)
    brightness = sum(v for _, _, v in hsv) / len(hsv)
    return {
        "source": "opaque_pixel_quantization_v1", "status": "measured_not_semantic_review",
        "asset_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "swatches": swatches,
        "palette_names": list(dict.fromkeys(s["family"] for s in swatches if s["weight"] >= .12))[:3],
        "color": {**UNKNOWN_COLOR, "palette": [s["hex"] for s in swatches],
                  "lightness": "浅色" if brightness > .72 else "深色" if brightness < .36 else "中等",
                  "saturation": "无彩" if saturation < .07 else "低饱和" if saturation < .27 else "中饱和" if saturation < .52 else "高饱和"},
        "limitations": "渲染光照会影响色值；不据此推断面料成分、真实冷暖或人体适配。",
    }


def build(pool: dict, audit: dict, *, measure: bool = True) -> tuple[dict, dict]:
    rows = {row["id"]: row for row in pool["outfits"]}
    garment_entries = {}
    for garment in pool["garments"]:
        path = ROOT / "app" / garment["assets"]["image_url"].lstrip("/")
        observed = measure_color(path) if measure else {"color": dict(UNKNOWN_COLOR)}
        intent_keys = ("color", "materials", "silhouette", "fit", "season_tags", "scene_tags", "persona_affinity")
        garment_entries[garment["id"]] = {
            "source_fingerprint": record_fingerprint(garment),
            "patch": {"design_intent": {k: garment.get(k) for k in intent_keys},
                      "color": observed["color"], "color_evidence": observed,
                      "materials": [], "silhouette": [], "fit": "未判断",
                      "semantic_review": {"status": "pending", "source": "legacy_prompt_is_not_visual_evidence",
                                          "required_fields": ["material_appearance", "fit", "length", "sleeve", "decoration_level", "formality", "temperature_context", "layering"]}},
        }
    entries = {}
    scene_ids = {row["outfit_id"] for row in audit["scene_tag_conflicts_review_only"]}
    winter_ids = set(audit["winter_dresses_without_outer_review_only"])
    for oid, outfit in rows.items():
        hero = next((gid for gid, role in outfit["slot_roles"].items() if role == "hero"), outfit["garment_ids"][0])
        color = dict(garment_entries[hero]["patch"]["color"])
        color["palette"] = list(dict.fromkeys(
            garment_entries[gid]["patch"]["color"]["palette"][0]
            for gid in outfit["garment_ids"] if garment_entries[gid]["patch"]["color"]["palette"]
        ))[:6]
        flags = (["scene_tags_need_review"] if oid in scene_ids else []) + (["winter_layering_context_unknown"] if oid in winter_ids else [])
        entries[oid] = {
            "source_fingerprint": record_fingerprint(outfit), "status": "legacy_allowed",
            "reason_codes": [], "review_flags": flags,
            "gates": {"technical": "legacy_recorded", "aesthetic": "pending", "persona": "pending", "context": "pending"},
            "patch": {"design_intent": {k: outfit.get(k) for k in ("structure", "body_types", "color", "persona_affinity", "recommendation_reasons")},
                      "structure": {k: "未判断" for k in outfit.get("structure", {})}, "body_types": [],
                      "color": color, "color_evidence": {"source": "hero_opaque_pixels", "hero_garment_id": hero, "harmony_review": "pending"},
                      "recommendation_reasons": [f"来自 {outfit['primary_persona']} 风格候选库"]},
        }
    decisions = {item["id"]: item for item in audit["visual_decisions"] if item["decision"] != "retain_as_entry_candidate"}
    blocked_sets = {tuple(sorted(rows[oid]["garment_ids"])): oid for oid in decisions}
    for oid, item in entries.items():
        decision_id = oid if oid in decisions else blocked_sets.get(tuple(sorted(rows[oid]["garment_ids"])))
        parent = rows[oid].get("parent_outfit_id")
        if decision_id:
            item.update(status="hold", reason_codes=[decisions[decision_id]["decision"]], evidence=decisions[decision_id])
        elif parent in decisions:
            item.update(status="hold", reason_codes=["parent_rework_requires_variant_review"],
                        evidence={"parent_id": parent, "reason": "主配方需重配，衍生版先隔离复核；不是已经判定图片不合格"})
    for group in audit["exact_duplicate_groups"]:
        # Prefer a master as canonical; duplicate families retain their own
        # persona metadata in the archive without inflating recommendation count.
        canonical = min(group, key=lambda oid: (bool(rows[oid].get("parent_outfit_id")), oid))
        for oid in group:
            if oid != canonical:
                entries[oid].update(status="alias", canonical_id=canonical)
                entries[oid]["reason_codes"].append("exact_garment_set_duplicate")
    counts = Counter(item["status"] for item in entries.values())
    by_persona = Counter(rows[oid]["primary_persona"] for oid, item in entries.items() if item["status"] == "legacy_allowed")
    overlay = {"schemaVersion": "1.0", "version": "2026.09-editorial1", "source_sha256": audit["source_sha256"],
               "garments": garment_entries, "outfits": entries}
    report = {"version": overlay["version"], "source_outfits": len(rows), "source_garments": len(garment_entries),
              "outfit_status_counts": dict(counts), "recommendable_by_persona": dict(sorted(by_persona.items())),
              "measured_garment_colors": len(garment_entries) if measure else 0,
              "semantic_garment_reviews_pending": len(garment_entries), "strict_four_gate_approved": 0,
              "scene_review_only": sorted(scene_ids), "winter_context_review_only": sorted(winter_ids),
              "unused_garments_to_prioritize": audit["unused_garment_ids"],
              "next": ["逐件补齐真实视觉语义，优先89件未用款和9套问题配方相关款", "先复核每人格10套锚点", "整套约束通过后生成多槽位替换版本"],
              "note": "保留原始图片/清单。legacy_allowed仅维持旧内容连续性，不代表完整审美/盲审通过。"}
    return overlay, report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pool", type=Path, default=POOL)
    parser.add_argument("--audit", type=Path, default=AUDIT)
    parser.add_argument("--output", type=Path, default=CURATION_PATH)
    parser.add_argument("--report", type=Path, default=REPORT)
    args = parser.parse_args()
    raw = args.pool.read_bytes()
    audit = json.loads(args.audit.read_text())
    if hashlib.sha256(raw).hexdigest() != audit["source_sha256"]:
        raise SystemExit("审查源版本已改变，请先复核；不能把旧结论套用到新配方。")
    overlay, report = build(json.loads(raw), audit)
    for path, value in ((args.output, overlay), (args.report, report)):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
    print(json.dumps({k: v for k, v in report.items() if not isinstance(v, list)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
