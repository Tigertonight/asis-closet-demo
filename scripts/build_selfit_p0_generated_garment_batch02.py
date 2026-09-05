#!/usr/bin/env python3
"""Register the BOLT medium-expression repair dress as an internal candidate."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_selfit_aw_generated_garment_batch import build, stable_write
from scripts.prepare_selfit_garment_asset import prepare

AUDIT = ROOT / "docs/audits/20260904-p0-acceptance/generated-garments/batch02"
STATIC = ROOT / "app/static/selfit/assets/content_v2_drafts/p0-medium-expression-02/garments"
SOURCE = Path("/Users/yuanzexiang/.codex/generated_images/01a06b62-ef79-7533-88b0-79111246bf6f/exec-50612541-6c76-4f04-bff2-a8bc5db1eb09.png")


def spec() -> dict:
    return {
        "slug": "bolt-wine-typical-dress",
        "token": "n0099",
        "id": "garment_p0_typical_bolt_dress_n0099",
        "name": "酒红丝绒象牙领珍珠扣连衣裙",
        "category": "dress",
        "prompt": "酒红丝绒象牙领珍珠扣中强度日常连衣裙，原创无品牌透明背景独立主衣。",
        "personas": ["BOLT"],
        "palette": "p0_persona_not_color_test",
        "fit": "合体",
        "silhouette": ["daily_midi", "shaped_waist", "controlled_puff_sleeve"],
        "observation": {
            "subcategory": "wine_velvet_pearl_typical_midi_dress",
            "neckline": "ivory_peter_pan_collar",
            "sleeve": "long_soft_puff",
            "length": "midi",
            "volume": "controlled_a_line",
            "construction": "shaped_waist_single_ribbon_band",
            "pattern": "solid",
            "decoration": "medium",
            "material_appearance": "velvet_and_crepe_as_observed",
            "main_colors": ["wine_red", "ivory", "champagne"],
        },
        "evidence": "酒红丝绒、象牙领、珍珠扣与收腰线构成明确精致贵气，装饰集中且仍为日常中强度。",
        "targets": ["BOLT×typical×daily"],
        "source_output": str(SOURCE),
    }


def main() -> None:
    row = spec()
    raw = AUDIT / "raw" / "bolt-wine-typical-dress-raw-v1.png"
    prepared = AUDIT / "prepared" / "bolt-wine-typical-dress-v1.png"
    qa = AUDIT / "qa" / "bolt-wine-typical-dress-v1.json"
    stable_write(raw, SOURCE.read_bytes())
    if not prepared.exists():
        report = prepare(raw, prepared)
        qa.parent.mkdir(parents=True, exist_ok=True)
        qa.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    result = build(
        specs=[row], audit=AUDIT, static=STATIC,
        batch_id="p0-generated-medium-expression-02",
        prompt_version="selfit-p0-bolt-typical-v1",
    )
    result["binding_method"] = "individual_output_binding_verified_visually_and_by_filename"
    result["limitations"] = [
        "Generated cutout approval is not outfit approval, four-gate editorial approval, or blind review.",
        "Color testing is outside this P0 scope.",
    ]
    target = AUDIT / "manifest.json"
    if target.exists() and json.loads(target.read_text()) != result:
        raise SystemExit("P0 garment batch02 changed; refusing overwrite")
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"version": result["version"], "garments": 1, "published": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
