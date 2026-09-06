"""Register two visually inspected, user-authorized normalized BOLT drafts."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.build_selfit_aw_generated_garment_batch import build, stable_write
from app.selfit_content_quality import record_fingerprint

AUDIT = ROOT / "docs/audits/20260904-p0-acceptance/generated-garments/batch04"
STATIC = ROOT / "app/static/selfit/assets/content_v2_drafts/p0-bolt-structure-04/garments"


def main():
    prompts = json.loads((AUDIT / "prompts.json").read_text())["prompts"]
    specs = [
        {"slug": "bolt-shaped-tweed-jacket", "token": "n0100",
         "id": "garment_p0_bolt_shaped_tweed_n0100", "name": "细滚边收腰短外套",
         "category": "outer", "personas": ["BOLT", "HEIR"], "fit": "合体",
         "silhouette": ["shaped_waist", "short_jacket", "raised_rounded_shoulder"],
         "observation": {"subcategory": "shaped_collarless_tweed_jacket", "neckline": "rounded_square_collarless",
             "sleeve": "long_slightly_raised_head", "length": "waist", "volume": "fitted_slight_hem_flare",
             "construction": "princess_seams_four_round_buttons_welt_pockets", "pattern": "fine_flecked_weave",
             "decoration": "medium", "material_appearance": "boucle_with_velvet_like_piping",
             "main_colors": ["ivory", "burgundy"]},
         "evidence": "微抬肩、公主线收腰、短摆、细滚边和四枚圆扣形成集中精致结构；与HEIR相邻，不以目标BOLT标签证明整套人格。",
         "targets": ["BOLT typical candidate; HEIR boundary requires outfit review"]},
        {"slug": "bolt-folded-shoulder-blouse", "token": "n0101",
         "id": "garment_p0_bolt_folded_shoulder_n0101", "name": "偏肩折片合腰上衣",
         "category": "top", "personas": ["BOLT", "FLOU", "MELT"], "fit": "合体",
         "silhouette": ["fitted_waist", "asymmetric_bodice_fold", "covered_shoulders"],
         "observation": {"subcategory": "asymmetric_folded_shoulder_blouse", "neckline": "shallow_boat",
             "sleeve": "long_tapered", "length": "upper_hip", "volume": "fitted",
             "construction": "one_shoulder_tab_diagonal_bodice_pleats_waist_darts", "pattern": "solid",
             "decoration": "medium", "material_appearance": "matte_crepe_like",
             "main_colors": ["dusty_rose"]},
         "evidence": "偏肩折片与胸腰斜褶构成单一体积焦点，肩部覆盖、长袖收窄；实图绉感偏哑光，需检查BOLT与FLOU/MELT及typical/explore边界。",
         "targets": ["BOLT light exploration target; classification remains pending whole-image review"]},
    ]
    for spec, prompt in zip(specs, prompts):
        spec.update(prompt=prompt["prompt"], source_output=str(AUDIT / "raw" / (spec["slug"] + "-raw-v1.png")),
                    palette="p0_persona_not_color_test", season_tags=["秋"], scene_tags=["日常", "约会社交"])
        stable_write(AUDIT / "qa" / (spec["slug"] + "-v1.json"),
                     (AUDIT / (spec["slug"] + "-qa.v1.json")).read_bytes())
    result = build(specs=specs, audit=AUDIT, static=STATIC, batch_id="p0-bolt-structure-04",
                   prompt_version="selfit-p0-bolt-structure-v1")
    # Avoid the shared helper's optimistic default confidence and appended
    # generic prompt suffix: record the actual prompts and actual judgments.
    for garment in result["garments"]:
        garment["annotation"]["confidence"] = .8
        garment["annotation"]["review_notes"] = [
            "Prepared output viewed individually; only cutout usability is candidate-approved.",
            "User authorized low-alpha cleanup, proportional resizing and transparent padding; no redesign.",
            "Persona and expression targets require whole-outfit judgment; no independent review performed."]
        visual = result["visual"][garment["id"]]
        visual["confidence"] = .8
        visual["record_fingerprint"] = record_fingerprint(garment)
        visual["observations"]["usage_limits"] = "Autumn/date draft; warmth, comfort and persona distinctiveness unverified."
    for row, spec in zip(result["generation"], specs):
        row["final_prompt"] = spec["prompt"]
        row["source_output"] = spec["source_output"]
        row["preprocessing"] = "User-authorized existing prepare_selfit_garment_asset.py; size=1200 padding=.10 alpha_noise=8"
    result["limitations"].append("Failed RGB checkerboard edits were rejected; only original RGBA files were normalized.")
    result.pop("version", None)
    result["version"] = "aw-generated-garments-" + hashlib.sha256(
        json.dumps(result, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]
    stable_write(AUDIT / "manifest.json", (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode())
    print(json.dumps({"version": result["version"], "garments": 2, "published": False}))


if __name__ == "__main__":
    main()
