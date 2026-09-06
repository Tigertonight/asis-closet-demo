"""Normalize and register the final 15 P0 raw garments after explicit authorization."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.selfit_content_quality import record_fingerprint
from scripts.build_selfit_aw_generated_garment_batch import build, stable_write
from scripts.prepare_selfit_garment_asset import prepare

SOURCE_ROOT = ROOT / "docs/audits/20260904-p0-acceptance/generated-garments"
AUDIT = SOURCE_ROOT / "batch11"
STATIC = ROOT / "app/static/selfit/assets/content_v2_drafts/p0-final-supply-11/garments"
PLAN = SOURCE_ROOT / "raw-supply-plan.v1.json"
RAW_AUDIT = SOURCE_ROOT / "raw-supply-audit.v1.json"

META = {
    "oops-rugby-tailored-dress": ("dress", "运动西装斜拼连衣裙", "宽松",
        ["rugby_bodice", "diagonal_waist", "tailored_wrap_skirt"],
        {"subcategory":"sports_tailoring_hybrid_midi_dress","neckline":"small_polo_collar","sleeve":"long_cuffed",
         "length":"midi","volume":"relaxed_straight","construction":"diagonal_waist_pinstripe_wrap_pleats",
         "pattern":"solid_and_pinstripe","decoration":"low","material_appearance":"cotton_jersey_and_suiting_like","main_colors":["charcoal","ivory"]},
        "运动针织上身与细条纹西装褶裙通过斜腰缝并置，冲突来自结构和正式度，而非配件或高彩。"),
    "noir-diagonal-zip-dress": ("dress", "斜拉链覆片针织连衣裙", "宽松",
        ["long_column", "diagonal_zip", "overlap_front"],
        {"subcategory":"diagonal_zip_jersey_midi_dress","neckline":"covered_crew","sleeve":"long_thumbhole_cuff",
         "length":"midi","volume":"relaxed_column","construction":"diagonal_zip_overlap_panel_rib_inset",
         "pattern":"solid","decoration":"low","material_appearance":"heavy_cotton_jersey_like","main_colors":["black"]},
        "斜向长缝、双向拉链、覆片和单侧罗纹形成冷硬方向性；日常针织轮廓避免只靠黑色归类。"),
    "edge-diagonal-knit-top": ("top", "粉领斜拉链罗纹上衣", "合体",
        ["fitted_rib", "diagonal_zip", "small_point_collar"],
        {"subcategory":"sweet_cool_diagonal_zip_knit","neckline":"small_point_collar","sleeve":"long_slim",
         "length":"hip","volume":"fitted","construction":"diagonal_two_way_zip_contrast_piping",
         "pattern":"solid","decoration":"low","material_appearance":"fine_rib_knit_like","main_colors":["black","dusty_rose"]},
        "黑色细罗纹、粉色尖领和单一斜拉链形成低强度甜酷结构。"),
    "edge-organza-panel-jacket": ("outer", "粉纱单侧拼片短外套", "合体",
        ["cropped", "asymmetric_front", "one_side_peplum"],
        {"subcategory":"asymmetric_organza_panel_jacket","neckline":"point_collar","sleeve":"long",
         "length":"waist","volume":"shaped","construction":"pointed_closure_one_side_pleat_inset",
         "pattern":"solid","decoration":"medium","material_appearance":"washed_cotton_and_organza_like","main_colors":["washed_black","dusty_rose"]},
        "洗黑短外套与单侧粉纱褶片构成强甜酷对照；透明度和躯干覆盖仍须整套审核。"),
    "edge-denim-pleat-dress": ("dress", "黑丹宁粉褶拼片连衣裙", "合体",
        ["shirt_dress", "asymmetric_wrap", "pleat_underpanel"],
        {"subcategory":"denim_wrap_pleat_midi_dress","neckline":"small_point_collar","sleeve":"long",
         "length":"midi","volume":"controlled_a_line","construction":"princess_seams_diagonal_wrap_pleat_underpanel",
         "pattern":"solid","decoration":"medium","material_appearance":"washed_denim_and_matte_chiffon_like","main_colors":["washed_black","dusty_rose"]},
        "黑丹宁收束与粉色褶片沿同一斜线组织，甜酷关系完整且不依赖外加配件。"),
    "void-offset-pocket-skirt": ("skirt", "水洗偏缝低口袋针织裙", "宽松",
        ["soft_column", "offset_seam", "uneven_overlap_hem"],
        {"subcategory":"washed_offset_seam_jersey_midi_skirt","neckline":"none","sleeve":"none",
         "length":"midi","volume":"relaxed_straight","construction":"elastic_waist_offset_seam_low_patch_pocket",
         "pattern":"solid","decoration":"low","material_appearance":"washed_cotton_jersey_like","main_colors":["washed_charcoal"]},
        "默认制服般的水洗针织直裙，以偏移缝、低口袋和轻微错层下摆保留游离感。"),
    "neon-curve-panel-top": ("top", "钴蓝荧光弧片针织上衣", "宽松",
        ["relaxed_straight", "single_curve_panel", "regular_shoulder"],
        {"subcategory":"high_color_curve_panel_jersey_top","neckline":"crew","sleeve":"long",
         "length":"hip","volume":"relaxed","construction":"single_lime_curve_panel_coral_zip_pocket",
         "pattern":"color_block","decoration":"low","material_appearance":"cotton_jersey_like","main_colors":["cobalt","lime","coral"]},
        "钴蓝基底仅由一条荧光弧片和小珊瑚拉链袋提亮，形成可日常化的高能主焦点。"),
    "neon-curve-panel-dress": ("dress", "珊瑚钴蓝弧片T恤裙", "宽松",
        ["tshirt_midi", "single_diagonal_panel", "straight"],
        {"subcategory":"high_color_curve_panel_tshirt_dress","neckline":"crew","sleeve":"short",
         "length":"midi","volume":"relaxed_straight","construction":"single_cobalt_curve_panel_lime_piping_pocket",
         "pattern":"color_block","decoration":"low","material_appearance":"cotton_jersey_like","main_colors":["coral","cobalt","lime"]},
        "基础T恤裙用单一钴蓝弧面和荧光细边构成入门吸睛信号。"),
    "neon-typical-graphic-top": ("top", "紫蓝荧光连环图形上衣", "宽松",
        ["mock_neck", "large_scale_graphic", "relaxed"],
        {"subcategory":"high_color_interlocking_graphic_top","neckline":"mock","sleeve":"long",
         "length":"hip","volume":"relaxed","construction":"large_interlocking_rounded_blocks_patch_pocket",
         "pattern":"large_geometric","decoration":"medium","material_appearance":"cotton_jersey_like","main_colors":["violet","cobalt","lime","coral"]},
        "跨衣身和单袖的连续大块图形提高强度，口袋仍从属于同一图形语言。"),
    "neon-explore-arc-dress": ("dress", "洋红多重弧线连衣裙", "合体",
        ["covered_square_neck", "expanding_arcs", "a_line"],
        {"subcategory":"expanding_arc_panel_midi_dress","neckline":"covered_square","sleeve":"sleeveless",
         "length":"midi","volume":"controlled_a_line","construction":"oversized_concentric_arc_panels_patch_pocket",
         "pattern":"large_geometric","decoration":"medium","material_appearance":"matte_twill_like","main_colors":["magenta","cobalt","lime","coral"]},
        "多重扩展弧线贯穿衣身和裙摆，形成探索强度但维持单一图形语法。"),
    "neon-explore-storm-overshirt": ("outer", "橙红荧光斜襟外搭", "宽松",
        ["hip_length", "diagonal_storm_flap", "large_round_pockets"],
        {"subcategory":"high_color_diagonal_flap_overshirt","neckline":"stand_collar","sleeve":"long",
         "length":"hip","volume":"relaxed","construction":"diagonal_storm_flap_two_large_patch_pockets",
         "pattern":"color_block","decoration":"medium","material_appearance":"structured_cotton_like","main_colors":["orange_red","cobalt","lime","violet"]},
        "橙红外搭以荧光斜襟和成对大口袋构成主动吸睛结构，适合作为探索型唯一主角。"),
    "bolt-easy-ivory-blouse": ("top", "象牙丝缎酒红滚边上衣", "合体",
        ["shaped_waist", "soft_sleeve_head", "jewel_neck"],
        {"subcategory":"refined_piped_satin_blouse","neckline":"rounded_jewel","sleeve":"long_soft_gather",
         "length":"hip","volume":"gently_fitted","construction":"waist_darts_three_pearl_buttons_piped_cuffs",
         "pattern":"solid","decoration":"low","material_appearance":"matte_satin_and_velvet_like","main_colors":["ivory","burgundy"]},
        "酒红细滚边、三枚珠扣和轻收腰集中为低强度精致焦点。"),
    "bolt-typical-burgundy-blouse": ("top", "酒红折肩收腰上衣", "合体",
        ["portrait_neck", "sculpted_shoulder_fold", "compact_peplum"],
        {"subcategory":"sculpted_fold_peplum_blouse","neckline":"square_portrait","sleeve":"long_tapered",
         "length":"waist","volume":"fitted_peplum","construction":"princess_seams_compact_shoulder_folds",
         "pattern":"solid","decoration":"medium","material_appearance":"matte_faille_like","main_colors":["burgundy"]},
        "方形肖像领、紧凑折肩、公主线和短荷叶摆形成中强度戏剧轮廓。"),
    "bolt-explore-emerald-dress": ("dress", "祖母绿斜披领裹片裙", "合体",
        ["asymmetric_cape_fold", "defined_waist", "tulip_midi"],
        {"subcategory":"asymmetric_cape_fold_midi_dress","neckline":"covered_boat","sleeve":"long",
         "length":"midi","volume":"fitted_tulip","construction":"one_shoulder_cape_fold_waist_gather_wrap_hem",
         "pattern":"solid","decoration":"medium","material_appearance":"matte_satin_like","main_colors":["deep_emerald"]},
        "单一斜披折片从肩延伸到腰，收束进郁金香裙形成探索级戏剧主线。"),
    "bolt-explore-petal-jacket": ("outer", "酒红花瓣叠领收腰外套", "合体",
        ["petal_lapel", "shaped_waist", "compact_flared_hem"],
        {"subcategory":"petal_lapel_satin_jacket","neckline":"covered_round","sleeve":"long_tapered",
         "length":"waist","volume":"fitted_flared","construction":"overlapping_petal_lapels_princess_seams_three_pearl_closures",
         "pattern":"solid","decoration":"medium","material_appearance":"matte_satin_like","main_colors":["burgundy"]},
        "花瓣式叠领、弧线珠扣和强收腰集中成一个建筑化焦点。"),
}


def specs() -> list[dict]:
    plan = json.loads(PLAN.read_text())
    rows = []
    for item in plan["entries"]:
        category, name, fit, silhouette, observation, evidence = META[item["slug"]]
        batch = SOURCE_ROOT / item["source"]
        prompt_path = batch.parent / (item["slug"].replace("oops-rugby-tailored-dress", "prompt")
            .replace("noir-diagonal-zip-dress", "prompt") + "-prompt.txt")
        # Batch 05/06 use prompt.txt; later batches use <target>-prompt names.
        if item["slug"] in {"oops-rugby-tailored-dress", "noir-diagonal-zip-dress"}:
            prompt_path = batch.parent / "prompt.txt"
        else:
            matches = list(batch.parent.glob("*prompt.txt"))
            prompt_path = next((p for p in matches if item["slug"].split("-", 1)[1].split("-raw", 1)[0] in p.stem), None)
            if prompt_path is None:
                # Bind explicitly by source stem prefix where prompt and asset names differ.
                prompt_path = {
                    "edge-diagonal-knit-top": batch.parent / "edge-easy-top-prompt.txt",
                    "edge-organza-panel-jacket": batch.parent / "edge-explore-jacket-prompt.txt",
                    "edge-denim-pleat-dress": batch.parent / "edge-typical-dress-prompt.txt",
                    "void-offset-pocket-skirt": batch.parent / "void-easy-skirt-prompt.txt",
                    "neon-curve-panel-top": batch.parent / "neon-easy-top-prompt.txt",
                    "neon-curve-panel-dress": batch.parent / "neon-easy-dress-prompt.txt",
                    "neon-typical-graphic-top": batch.parent / "neon-typical-top-prompt.txt",
                    "neon-explore-arc-dress": batch.parent / "neon-explore-dress-prompt.txt",
                    "neon-explore-storm-overshirt": batch.parent / "neon-explore-overshirt-prompt.txt",
                    "bolt-easy-ivory-blouse": batch.parent / "bolt-easy-blouse-prompt.txt",
                    "bolt-typical-burgundy-blouse": batch.parent / "bolt-typical-blouse-prompt.txt",
                    "bolt-explore-emerald-dress": batch.parent / "bolt-explore-dress-prompt.txt",
                    "bolt-explore-petal-jacket": batch.parent / "bolt-explore-jacket-prompt.txt",
                }[item["slug"]]
        rows.append({"slug":item["slug"],"token":item["token"],
            "id":f"garment_p0_final_{item['persona']}_{category}_{item['token']}",
            "name":name,"category":category,"prompt":prompt_path.read_text().strip(),
            "personas":[item["persona"].upper()],"palette":"p0_persona_not_color_test","fit":fit,
            "silhouette":silhouette,"observation":observation,"evidence":evidence,
            "targets":item["targets"],"source_output":str(batch),
            "season_tags":["秋"],"scene_tags":["日常","通勤","约会社交"]})
    if set(META) != {row["slug"] for row in rows}:
        raise ValueError("metadata and supply plan differ")
    return rows


def verify_sources(audit_path: Path = RAW_AUDIT) -> dict:
    audit = json.loads(audit_path.read_text())
    if audit.get("status") != "raw_supply_complete_pending_normalization" or audit.get("errors"):
        raise ValueError("raw supply audit is not clean")
    if audit.get("plan_sha256") != hashlib.sha256(PLAN.read_bytes()).hexdigest():
        raise ValueError("raw supply plan changed after audit")
    expected = {row["source"]: row for row in audit.get("entries", [])}
    if len(expected) != 15:
        raise ValueError("raw supply audit must bind exactly 15 sources")
    for row in json.loads(PLAN.read_text())["entries"]:
        source = SOURCE_ROOT / row["source"]
        evidence = expected.get(row["source"])
        if evidence is None or evidence.get("sha256") != hashlib.sha256(source.read_bytes()).hexdigest():
            raise ValueError(f"raw source changed after audit: {row['source']}")
        if evidence.get("alpha_extrema") != [0, 255] or evidence.get("mode") != "RGBA":
            raise ValueError(f"raw source is not approved RGBA: {row['source']}")
    return audit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="verify immutable inputs without writing files")
    parser.add_argument("--authorized-normalization", action="store_true",
                        help="required: confirms permission to resize/pad raw RGBA without redesign")
    args = parser.parse_args()
    if args.check:
        evidence = verify_sources()
        rows = specs()
        print(json.dumps({"status":"ready","garments":len(rows),
                          "planned_outfits":evidence["summary"]["planned_outfits"]},ensure_ascii=False))
        return
    if not args.authorized_normalization:
        raise SystemExit("explicit --authorized-normalization is required; no files changed")
    verify_sources()
    rows = specs()
    for row in rows:
        source = Path(row["source_output"])
        raw = AUDIT / "raw" / f"{row['slug']}-raw-v1.png"
        prepared = AUDIT / "prepared" / f"{row['slug']}-v1.png"
        qa = AUDIT / "qa" / f"{row['slug']}-v1.json"
        stable_write(raw, source.read_bytes())
        if not prepared.exists():
            report = prepare(raw, prepared, size=1200, padding=.10, alpha_noise=8)
            stable_write(qa, (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode())
    result = build(specs=rows, audit=AUDIT, static=STATIC,
                   batch_id="p0-generated-final-supply-11",
                   prompt_version="selfit-p0-final-supply-v1")
    for garment in result["garments"]:
        garment["annotation"]["confidence"] = .8
        garment["annotation"]["review_notes"] = [
            "Cutout usability reviewed; persona/expression require whole-outfit review.",
            "Normalization only removes alpha noise, resizes proportionally and adds transparent padding."]
        visual = result["visual"][garment["id"]]
        visual["confidence"] = .8
        visual["record_fingerprint"] = record_fingerprint(garment)
    result["limitations"] = [
        "No generated garment is published.",
        "Cutout approval is not outfit, four-gate editorial or independent blind-review approval.",
        "Color-person assessment is outside this P0 scope."]
    result.pop("version", None)
    result["version"] = "aw-generated-garments-" + hashlib.sha256(
        json.dumps(result, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]
    stable_write(AUDIT / "manifest.json", (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode())
    print(json.dumps({"version":result["version"],"garments":len(rows),"published":False},ensure_ascii=False))


if __name__ == "__main__":
    main()
