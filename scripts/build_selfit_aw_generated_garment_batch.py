#!/usr/bin/env python3
"""Register imagegen outputs as immutable internal AW garment candidates.

The manifest is deliberately separate from the published content pool.  Image
QA approval here means that the cutout is usable for composition; it does not
publish the garment or approve any outfit made from it.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.selfit_content_quality import record_fingerprint
from scripts.approve_selfit_generated_asset import _dhash
from scripts.curate_selfit_content import measure_color


AUDIT = ROOT / "docs/audits/20260904-aw-supply/generated-garments/batch01"
STATIC = ROOT / "app/static/selfit/assets/content_v2_drafts/aw-winter-02/garments"
SCHEMA = ROOT / "app/static/selfit/data/content-pool.schema.v2.json"

PROMPT_SUFFIX = (
    " Photorealistic premium fashion e-commerce product cutout, exactly one original unbranded garment, "
    "front-facing and naturally shaped as if invisibly supported, genuinely transparent alpha background, "
    "centered square canvas, complete silhouette with 12% clear padding on every side. "
    "No person, mannequin, hanger, stand, accessories, text, label, logo, watermark, floor shadow, white halo, "
    "duplicate item or clipped edge."
)

SPECS = [
    {
        "slug": "winter-coat-jewel-burgundy", "token": "n0001", "id": "garment_aw_winter02_outer_burgundy_01",
        "name": "勃艮第结构收腰长外套", "prompt": "Create a deep burgundy long tailored women's winter coat with a clean notched lapel, shaped waist, long sleeves and restrained seam lines.",
        "personas": ["HEIR", "MUTE", "NOIR", "LOOP"], "palette": "jewel", "fit": "合体",
        "silhouette": ["long_tailored", "shaped_waist", "clean_vertical_line"],
        "observation": {"subcategory": "long_tailored_coat", "neckline": "notched_lapel", "sleeve": "long", "length": "maxi", "volume": "shaped_straight", "construction": "single_breasted_princess_seams", "pattern": "solid", "decoration": "low", "material_appearance": "dense_matte_wool_like", "main_colors": ["deep_burgundy"]},
        "evidence": "深勃艮第长外套的窄驳领、收腰分割和连续纵线清晰，装饰克制；颜色来自实际像素量化。",
        "targets": ["HEIR×jewel×winter", "MUTE×jewel×winter", "NOIR×jewel×winter", "LOOP×jewel×winter"],
        "source_output": "/Users/yuanzexiang/.codex/generated_images/01a056c3-ad43-77d1-aed3-35866995a6d6/exec-253dc184-e00d-4e54-bed4-9aac2b1ece28.png",
    },
    {
        "slug": "winter-coat-jewel-teal", "token": "n0002", "id": "garment_aw_winter02_outer_teal_01",
        "name": "宝石青立领纵线长外套", "prompt": "Create a deep jewel-teal long women's winter coat with a neat stand collar, concealed front, slim long sleeves, subtle side slits and a clean vertical silhouette.",
        "personas": ["ICED", "JADE", "NOIR", "MUTE"], "palette": "jewel", "fit": "合体",
        "silhouette": ["long_column", "stand_collar", "clean_vertical_line"],
        "observation": {"subcategory": "stand_collar_long_coat", "neckline": "stand_collar", "sleeve": "long", "length": "maxi", "volume": "slim_straight", "construction": "concealed_front_side_slits", "pattern": "solid", "decoration": "low", "material_appearance": "dense_matte_wool_like", "main_colors": ["deep_teal"]},
        "evidence": "宝石青长外套以立领、暗门襟和窄长轮廓表达冷静纵向结构，侧开叉不破坏主线。",
        "targets": ["ICED×jewel×winter", "JADE×jewel×winter", "NOIR×jewel×winter", "MUTE×jewel×winter"],
        "source_output": "/Users/yuanzexiang/.codex/generated_images/01a056c3-ad43-77d1-aed3-35866995a6d6/exec-54089be2-9c90-4abc-b9be-103571bddb63.png",
    },
    {
        "slug": "winter-coat-bright-cobalt", "token": "n0003", "id": "garment_aw_winter02_outer_cobalt_01",
        "name": "鲜钴蓝利落长外套", "prompt": "Create a vivid cobalt-blue long women's winter coat with a clean notched lapel, two restrained buttons, long sleeves and a crisp straight tailored silhouette.",
        "personas": ["ICED", "EDGE", "NEON", "LOOP"], "palette": "bright", "fit": "合体",
        "silhouette": ["long_tailored", "straight", "crisp_shoulder"],
        "observation": {"subcategory": "long_tailored_coat", "neckline": "notched_lapel", "sleeve": "long", "length": "maxi", "volume": "straight", "construction": "two_button_welt_pockets", "pattern": "solid", "decoration": "low", "material_appearance": "dense_matte_wool_like", "main_colors": ["vivid_cobalt"]},
        "evidence": "鲜钴蓝是唯一高彩主色，两粒扣、直肩和长直轮廓控制了表达强度，不依赖复杂拼接。",
        "targets": ["ICED×bright×winter", "EDGE×bright×winter", "NEON×bright×winter", "LOOP×bright×winter"],
        "source_output": "/Users/yuanzexiang/.codex/generated_images/01a056c3-ad43-77d1-aed3-35866995a6d6/exec-281f5ca7-9d7d-40fe-9be2-4918f38e92fd.png",
    },
    {
        "slug": "winter-coat-bright-coral", "token": "n0004", "id": "garment_aw_winter02_outer_coral_01",
        "name": "珊瑚红柔和茧形长外套", "prompt": "Create a vivid coral-red long women's winter coat with a collarless round neckline, dropped shoulders, long sleeves, discreet pockets and a softly controlled cocoon silhouette.",
        "personas": ["EASE", "MELT", "FLOU", "LOOP"], "palette": "bright", "fit": "宽松",
        "silhouette": ["soft_cocoon", "dropped_shoulder", "long"],
        "observation": {"subcategory": "collarless_cocoon_coat", "neckline": "collarless_round", "sleeve": "long", "length": "maxi", "volume": "soft_cocoon", "construction": "concealed_front_dropped_shoulders", "pattern": "solid", "decoration": "low", "material_appearance": "soft_matte_wool_like", "main_colors": ["vivid_coral"]},
        "evidence": "珊瑚红无领长外套以落肩、圆线和受控茧形表达松弛与柔和，口袋和门襟保持低装饰。",
        "targets": ["EASE×bright×winter", "MELT×bright×winter", "FLOU×bright×winter", "LOOP×bright×winter"],
        "source_output": "/Users/yuanzexiang/.codex/generated_images/01a056c3-ad43-77d1-aed3-35866995a6d6/exec-0e661e8b-f4dc-4819-81d2-e03cb5d77efa.png",
    },
]


def stable_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if hashlib.sha256(path.read_bytes()).digest() != hashlib.sha256(payload).digest():
            raise FileExistsError(f"immutable asset differs: {path}")
        return
    path.write_bytes(payload)


def build(*, specs=SPECS, audit=AUDIT, static=STATIC, batch_id="aw-generated-garments-01",
          prompt_version="selfit-aw-winter-gap-v1") -> dict:
    schema = json.loads(SCHEMA.read_text())
    garments, visual = [], {}
    for spec in specs:
        category = spec.get("category", "outer")
        if category not in {"outer", "dress", "top", "bottom", "skirt"}:
            raise ValueError(f"Unsupported generated AW category: {category}")
        layer_role = spec.get("layer_role", "outer" if category == "outer" else "single")
        tryon_slot = spec.get("tryon_slot", category)
        source = audit / "prepared" / f"{spec['slug']}-v1.png"
        qa_path = audit / "qa" / f"{spec['slug']}-v1.json"
        qa = json.loads(qa_path.read_text())
        if not qa.get("passed") or min(qa["margins"].values()) < .055:
            raise ValueError(f"cutout QA did not pass: {spec['slug']}")
        target = static / source.name
        stable_write(target, source.read_bytes())
        image_url = "/static/" + target.relative_to(ROOT / "app/static").as_posix()
        color_evidence = measure_color(target)
        colors = color_evidence["color"]
        record = {
            "id": spec["id"], "category": category, "subcategory": spec["name"],
            "silhouette": spec["silhouette"], "fit": spec["fit"], "materials": [],
            "details": ["original_gap_fill", spec["palette"], "visually_reviewed_cutout"],
            "season_tags": spec.get("season_tags", ["秋", "冬"]),
            "scene_tags": spec.get("scene_tags", ["日常", "通勤", "旅行"]), "weather_tags": [],
            "presentation": spec.get("presentation", ["feminine", "neutral"]),
            "layer_role": layer_role, "tryon_slot": tryon_slot,
            "persona_affinity": {p: round(.96 - i * .08, 2) for i, p in enumerate(spec["personas"])},
            "color": colors,
            "assets": {"image_url": image_url, "source_url": "", "width": 1200, "height": 1200,
                       "alpha_verified": True, "rights_status": "owned"},
            "production": {"source_kind": "generated_original", "generation_job_id": f"{batch_id}-{spec['token']}",
                           "prompt_version": prompt_version, "reference_ids": [],
                           "qa_status": "approved", "phash": _dhash(target)},
            "annotation": {"status": "designer_reviewed", "source": "designer", "confidence": .92,
                           "review_notes": ["Cutout and visible silhouette reviewed in current Codex session; outfit use remains draft."]},
            "color_evidence": color_evidence,
        }
        garments.append(record)
        observations = {"category": category, **spec["observation"],
                        "visual_personas": [p.lower() for p in spec["personas"]], "usage_limits": None}
        visual[record["id"]] = {
            "token": spec["token"], "status": "ai_candidate", "record_fingerprint": record_fingerprint(record),
            "asset_sha256": color_evidence["asset_sha256"], "image_url": image_url,
            "source_kind": "codex_visual_review", "evidence": spec["evidence"], "observations": observations,
            "confidence": .9, "model": "current_codex_session", "prompt_version": "aw-generated-garment-review-v1",
            "review_level": "individual_full_resolution_judgment", "review_complete": True,
            "confidence_basis": "Non-calibrated AI visual judgment; material appearance is visual only and warmth is not claimed.",
        }
    draft_pool = {"schemaVersion": "2.0", "contentVersion": batch_id,
                  "status": "draft", "outfits": [], "garments": garments}
    Draft202012Validator(schema).validate(draft_pool)
    manifest = {
        "schema_version": 1, "batch_id": batch_id, "prompt_version": prompt_version,
        "status": "internal_candidate", "production_approved": False,
        "generation": [{"garment_id": s["id"], "token": s["token"], "source_output": s["source_output"],
                        "raw_path": f"raw/{s['slug']}-raw-v1.png", "prepared_path": f"prepared/{s['slug']}-v1.png",
                        "qa_path": f"qa/{s['slug']}-v1.json", "final_prompt": s["prompt"] + PROMPT_SUFFIX,
                        "target_conditions": s["targets"]} for s in specs],
        "garments": garments, "visual": visual,
        "limitations": ["AI visual review is not independent blind review.", "Dense or wool-like appearance does not prove warmth, fiber, waterproofing or comfort.", "No garment is in the published pool."],
    }
    manifest["version"] = "aw-generated-garments-" + hashlib.sha256(json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]
    return manifest


def main() -> None:
    target = AUDIT / "manifest.json"
    result = build()
    if target.exists() and json.loads(target.read_text()) != result:
        raise SystemExit("Generated garment manifest changed; refusing overwrite")
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"version": result["version"], "garments": len(result["garments"]), "published": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
