from __future__ import annotations

import json
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
IMG_DIR = ROOT / "tests" / "fixtures" / "images"
EXPECTED = ROOT / "tests" / "fixtures" / "expected.json"


def main() -> None:
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    for path in IMG_DIR.iterdir():
        if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
            path.unlink()
    seed_sources()
    good = Image.open(IMG_DIR / "portrait_card_good.png").convert("RGB")
    table = Image.open(IMG_DIR / "non_portrait_card_table.png").convert("RGB")

    cases = []
    cases += build_input_quality(good)
    cases += build_real_upload_cases(good)
    cases += build_portrait_anomalies(good, table)
    cases += build_card_anomalies(good)
    cases += build_vl_risks(good)
    cases += build_analyzed_cases(good)
    cases = apply_current_policy_overrides(cases)

    EXPECTED.write_text(
        json.dumps({"suite": "AI 色彩测试 MVP 验证集", "cases": cases}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"wrote {len(cases)} cases to {EXPECTED}")


def seed_sources() -> None:
    generated_root = Path.home() / ".codex" / "generated_images" / "019f1ccc-9227-71f0-8cee-2152f2b45555"
    good_source = generated_root / "ig_09fc32194dd55459016a44d73e43b48191a9df1b9dd665d38a.png"
    table_source = generated_root / "ig_09fc32194dd55459016a44d85f1654819182cc223d6d784780.png"
    if not good_source.exists() or not table_source.exists():
        raise FileNotFoundError("缺少 imagegen 生成源图，无法重建 MVP 测试集")
    Image.open(good_source).convert("RGB").save(IMG_DIR / "portrait_card_good.png")
    Image.open(table_source).convert("RGB").save(IMG_DIR / "non_portrait_card_table.png")


def build_input_quality(good: Image.Image) -> list[dict]:
    variants = []
    save("input_low_resolution.jpg", good.resize((360, 360)))
    variants.append(input_case("input_low_resolution", "低分辨率", "input_quality", "image.resolution"))

    canvas = Image.new("RGB", (2400, 900), (235, 235, 235))
    canvas.paste(good.resize((900, 900)), (750, 0))
    save("input_too_wide.jpg", canvas)
    variants.append(input_case("input_too_wide", "超宽比例", "input_quality", "image.aspect_ratio"))

    canvas = Image.new("RGB", (900, 2400), (235, 235, 235))
    canvas.paste(good.resize((900, 900)), (0, 750))
    save("input_too_tall.jpg", canvas)
    variants.append(input_case("input_too_tall", "超长比例", "input_quality", "image.aspect_ratio"))

    save("input_overexposed.png", ImageEnhance.Brightness(good).enhance(1.65))
    variants.append(input_case("input_overexposed", "过曝", "input_quality", "lighting.exposure"))

    save("input_too_dark.jpg", ImageEnhance.Brightness(good).enhance(0.18))
    variants.append(input_case("input_too_dark", "欠曝", "input_quality", "lighting.exposure"))

    save("input_strong_blur.jpg", good.filter(ImageFilter.GaussianBlur(radius=24)))
    variants.append(input_case("input_strong_blur", "强模糊", "input_quality", "image.sharpness"))

    pixelated = good.resize((120, 200)).resize(good.size).filter(ImageFilter.GaussianBlur(radius=16))
    save("input_heavy_compression.jpg", pixelated, quality=18)
    variants.append(input_case("input_heavy_compression", "压缩严重", "input_quality", "image.sharpness"))

    noisy = ImageEnhance.Contrast(good).enhance(0.2).filter(ImageFilter.GaussianBlur(radius=10))
    save("input_low_contrast.jpg", noisy)
    variants.append(input_case("input_low_contrast", "低对比且偏糊", "input_quality", "image.sharpness"))
    return variants


def build_real_upload_cases(good: Image.Image) -> list[dict]:
    cases = []

    wide = Image.new("RGB", (2400, 900), (235, 235, 235))
    wide.paste(good.resize((900, 900)), (750, 0))
    save("real_wide_auto_crop.jpg", wide)
    cases.append(real_upload_auto_crop_case("real_wide_auto_crop", "超宽截图自动裁剪", "image.auto_cropped"))

    tall = Image.new("RGB", (900, 2400), (235, 235, 235))
    tall.paste(good.resize((900, 900)), (0, 750))
    save("real_tall_auto_crop.jpg", tall)
    cases.append(real_upload_auto_crop_case("real_tall_auto_crop", "超长截图自动裁剪", "image.auto_cropped"))

    social = Image.new("RGB", (1170, 2532), (224, 221, 218))
    draw = ImageDraw.Draw(social)
    draw.rounded_rectangle((38, 44, 1132, 170), radius=36, fill=(238, 236, 234), outline=(218, 208, 204), width=3)
    draw.rectangle((0, 2380, 1170, 2532), fill=(238, 236, 234))
    draw.rounded_rectangle((70, 220, 1100, 2260), radius=42, fill=(242, 240, 238))
    social.paste(good.resize((760, 1260)), (205, 520))
    save("real_social_screenshot_auto_crop.jpg", social)
    cases.append(real_upload_face_auto_crop_case("real_social_screenshot_auto_crop", "App截图自动裁脸"))

    colorful_clothes = overlay_rect(good, (210, 890, 800, 1270), (238, 238, 235))
    colorful_clothes = draw_colorful_clothes(colorful_clothes)
    save("real_colorful_clothes_no_card.jpg", colorful_clothes)
    cases.append(soft_case("real_colorful_clothes_no_card", "彩色衣服无色卡", "real_upload", "color_card_cv", "card.missing", {"color_correction": "correction.no_card_fallback"}))

    poster = overlay_rect(good, (210, 900, 800, 1270), (238, 238, 235))
    poster = draw_colorful_background_poster(poster)
    save("real_colorful_poster_no_card.jpg", poster)
    cases.append(soft_case("real_colorful_poster_no_card", "彩色背景无色卡", "real_upload", "color_card_cv", "card.missing", {"color_correction": "correction.no_card_fallback"}))

    poster_wall = overlay_rect(good, (210, 900, 800, 1270), (238, 238, 235))
    poster_wall = draw_busy_poster_wall(poster_wall)
    save("real_busy_poster_wall_no_card.jpg", poster_wall)
    cases.append(soft_case("real_busy_poster_wall_no_card", "海报墙自拍无色卡", "real_upload", "color_card_cv", "card.missing", {"color_correction": "correction.no_card_fallback"}))

    warm_light = overlay_rect(good, (210, 900, 800, 1270), (238, 238, 235))
    warm_light = tint_region(warm_light, (0, 0, warm_light.width, warm_light.height), (255, 190, 92), 0.28)
    save("real_warm_indoor_light_no_card.jpg", warm_light)
    cases.append(soft_case("real_warm_indoor_light_no_card", "室内暖光自拍", "real_upload", "vl_review", "vl.color_filter", {"color_card_cv": "card.missing", "color_correction": "correction.no_card_fallback"}))

    screen_light = overlay_rect(good, (210, 900, 800, 1270), (238, 238, 235))
    screen_light = tint_region(screen_light, (0, 0, screen_light.width, screen_light.height), (100, 150, 255), 0.25)
    save("real_screen_cool_light_no_card.jpg", screen_light)
    cases.append(soft_case("real_screen_cool_light_no_card", "屏幕冷光自拍", "real_upload", "vl_review", "vl.color_filter", {"color_card_cv": "card.missing", "color_correction": "correction.no_card_fallback"}))

    glasses = draw_clear_glasses(good)
    save("real_clear_glasses.jpg", glasses)
    cases.append(analyzed_case("real_clear_glasses", "普通透明眼镜", "spring", "bright_spring", "warm", "light", "bright", "medium", group="real_upload"))

    glare_glasses = draw_glasses_glare(draw_clear_glasses(good))
    save("real_glasses_glare.jpg", glare_glasses)
    cases.append(soft_case("real_glasses_glare", "透明眼镜轻微反光", "real_upload", "vl_review", "vl.glasses_glare"))

    bangs = draw_bangs(good)
    save("real_bangs_forehead.jpg", bangs)
    cases.append(soft_case("real_bangs_forehead", "刘海遮额头", "real_upload", "vl_review", "vl.hat_bangs"))

    hat_shadow = draw_hat_shadow(good)
    save("real_hat_shadow.jpg", hat_shadow)
    cases.append(soft_case("real_hat_shadow", "帽檐轻微阴影", "real_upload", "vl_review", "vl.hat_bangs"))

    hand_near_face = draw_hand_near_face(good)
    save("real_hand_near_face.jpg", hand_near_face)
    cases.append(soft_case("real_hand_near_face", "手托脸自拍", "real_upload", "vl_review", "vl.hand_near_face"))

    return cases


def build_portrait_anomalies(good: Image.Image, table: Image.Image) -> list[dict]:
    cases = []
    save("portrait_non_person.png", table)
    cases.append(block_case("portrait_non_person", "非人像", "portrait", "face_cv", "face.too_small"))

    double = Image.new("RGB", (1500, 1100), (235, 235, 235))
    face = good.resize((650, 1050))
    double.paste(face, (80, 25))
    double.paste(face.transpose(Image.Transpose.FLIP_LEFT_RIGHT), (770, 25))
    save("portrait_multi_face.jpg", double)
    cases.append(block_case("portrait_multi_face", "多人脸", "portrait", "face_cv", "face.multiple_faces"))

    small = Image.new("RGB", (1600, 1600), (175, 178, 175))
    small.paste(good.resize((360, 600)), (620, 500))
    save("portrait_face_too_small.jpg", small)
    cases.append(soft_case("portrait_face_too_small", "脸部过小自动裁剪", "portrait", "face_cv", "face.auto_cropped", {"color_card_cv": "card.missing", "color_correction": "correction.no_card_fallback"}))

    half = good.crop((0, 0, int(good.width * 0.55), good.height)).resize(good.size)
    save("portrait_half_face.jpg", half)
    cases.append(block_case("portrait_half_face", "半张脸裁切", "portrait", "face_cv", "face.no_face"))

    side = good.transpose(Image.Transpose.FLIP_LEFT_RIGHT).crop((int(good.width * 0.18), 0, good.width, good.height)).resize(good.size)
    save("portrait_side_pose.jpg", side)
    cases.append(soft_case("portrait_side_pose", "大角度侧脸", "portrait", "vl_review", "vl.pose_side", {"color_card_cv": "card.occluded"}))

    tilted = good.rotate(18, expand=False, fillcolor=(238, 238, 235))
    save("portrait_head_tilt.jpg", tilted)
    cases.append(soft_case("portrait_head_tilt", "头部姿态异常", "portrait", "vl_review", "vl.pose_tilted", {"color_card_cv": "card.wrong_lighting"}))

    mask = overlay_rect(good, (320, 690, 650, 860), (230, 230, 230))
    save("portrait_mask_occlusion.jpg", mask)
    cases.append(block_case("portrait_mask_occlusion", "口罩遮挡", "portrait", "vl_review", "vl.face_occluded"))

    sunglasses = overlay_rect(good, (280, 480, 700, 575), (25, 25, 25))
    save("portrait_sunglasses.jpg", sunglasses)
    cases.append(block_case("portrait_sunglasses", "墨镜遮挡", "portrait", "vl_review", "vl.eye_occluded"))
    return cases


def build_card_anomalies(good: Image.Image) -> list[dict]:
    cases = []
    no_card = overlay_rect(good, (220, 900, 780, 1260), (238, 238, 235))
    save("card_missing.jpg", no_card)
    cases.append(soft_case("card_missing", "无色卡", "color_card", "color_card_cv", "card.missing", {"color_correction": "correction.no_card_fallback"}))

    cropped = good.crop((0, 0, good.width, int(good.height * 0.77))).resize(good.size)
    save("card_cropped.jpg", cropped)
    cases.append(block_case("card_cropped", "色卡被裁切", "color_card", "color_card_cv", "card.cropped"))

    far = Image.new("RGB", good.size, (238, 238, 235))
    far.paste(good.resize((540, 900)), (210, 120))
    save("card_too_far.jpg", far)
    cases.append(block_case("card_too_far", "色卡太远", "color_card", "color_card_cv", "card.too_far"))

    glare = overlay_rect(good, (350, 940, 600, 1150), (255, 255, 255))
    save("card_glare.jpg", glare)
    cases.append(block_case("card_glare", "色卡反光", "color_card", "color_card_cv", "card.glare"))

    wrong_light = tint_region(good, (210, 900, 800, 1260), (70, 95, 160), 0.45)
    save("card_wrong_light.jpg", wrong_light)
    cases.append(block_case("card_wrong_light", "色卡与脸不同光照", "color_card", "color_card_cv", "card.wrong_lighting"))

    fake = overlay_fake_grid(good)
    save("card_fake_grid.jpg", fake)
    cases.append(block_case("card_fake_grid", "伪色卡", "color_card", "color_card_cv", "card.fake"))

    occluded = overlay_rect(good, (420, 950, 560, 1200), (210, 160, 130))
    save("card_occluded.jpg", occluded)
    cases.append(block_case("card_occluded", "色卡被手指遮挡", "color_card", "color_card_cv", "card.occluded"))

    tilted_card = good.rotate(-10, expand=False, fillcolor=(238, 238, 235))
    save("card_tilted.jpg", tilted_card)
    cases.append(soft_case("card_tilted", "色卡倾斜但完整", "color_card", "color_card_cv", "card.tilted"))
    return cases


def build_vl_risks(good: Image.Image) -> list[dict]:
    cases = []
    save("vl_heavy_makeup.jpg", draw_makeup(good, lipstick=True, blush=True, eye=True))
    cases.append(block_case("vl_heavy_makeup", "浓妆", "vl_risk", "vl_review", "vl.heavy_makeup"))

    save("vl_foundation.jpg", tint_region(good, (230, 350, 760, 860), (250, 220, 190), 0.35))
    cases.append(block_case("vl_foundation", "明显粉底", "vl_risk", "vl_review", "vl.foundation"))

    save("vl_red_lipstick.jpg", draw_makeup(good, lipstick=True))
    cases.append(soft_case("vl_red_lipstick", "口红明显", "vl_risk", "vl_review", "vl.lipstick", {"color_card_cv": "card.wrong_lighting"}))

    save("vl_blush.jpg", draw_makeup(good, blush=True))
    cases.append(block_case("vl_blush", "腮红明显", "vl_risk", "vl_review", "vl.blush"))

    save("vl_colored_contacts.jpg", draw_makeup(good, eye=True))
    cases.append(block_case("vl_colored_contacts", "彩瞳", "vl_risk", "vl_review", "vl.colored_contacts"))

    beauty = ImageEnhance.Brightness(good.filter(ImageFilter.SMOOTH_MORE)).enhance(1.12)
    save("vl_beauty_filter.jpg", beauty)
    cases.append(soft_case("vl_beauty_filter", "美颜磨皮", "vl_risk", "vl_review", "vl.beauty_filter", {"face_cv": "face.blurry", "color_card_cv": "card.wrong_lighting"}))

    color_filter = tint_region(good, (0, 0, good.width, good.height), (245, 170, 210), 0.25)
    save("vl_color_filter.jpg", color_filter)
    cases.append(soft_case("vl_color_filter", "滤镜偏色", "vl_risk", "vl_review", "vl.color_filter", {"color_card_cv": "card.wrong_lighting"}))

    hat = overlay_rect(good, (190, 230, 800, 440), (30, 30, 30))
    save("vl_hat_bangs.jpg", hat)
    cases.append(block_case("vl_hat_bangs", "帽子刘海遮挡", "vl_risk", "vl_review", "vl.hat_bangs"))
    return cases


def build_analyzed_cases(good: Image.Image) -> list[dict]:
    seasons = [
        ("season_spring_bright", "明亮春季型", "spring", "bright_spring", "warm", "light", "bright", "medium"),
        ("season_spring_light", "浅春季型", "spring", "light_spring", "warm", "light", "medium", "low"),
        ("season_summer_light", "浅夏季型", "summer", "light_summer", "cool", "light", "muted", "low"),
        ("season_summer_soft", "柔夏季型", "summer", "soft_summer", "cool", "medium", "muted", "low"),
        ("season_autumn_soft", "柔秋季型", "autumn", "soft_autumn", "warm", "medium", "muted", "low"),
        ("season_autumn_deep", "深秋季型", "autumn", "deep_autumn", "warm", "deep", "medium", "high"),
        ("season_winter_clear", "清冬季型", "winter", "clear_winter", "cool", "medium", "bright", "high"),
        ("season_winter_deep", "深冬季型", "winter", "deep_winter", "cool", "deep", "bright", "high"),
    ]
    cases = []
    for case_id, name, season_4, season_12, temperature, brightness, chroma, contrast in seasons:
        image = seasonal_gold_image(good, temperature, brightness, chroma, contrast)
        save(f"{case_id}.jpg", image)
        cases.append(analyzed_case(case_id, name, season_4, season_12, temperature, brightness, chroma, contrast))
    return cases


def input_case(case_id: str, name: str, stage: str, issue_code: str) -> dict:
    return {
        "id": case_id,
        "name": name,
        "group": "input_quality",
        "image": f"tests/fixtures/images/{case_id}.{'png' if 'overexposed' in case_id else 'jpg'}",
        "expected_status": "needs_retake",
        "expected_stage_status": {"input_quality": "fail"},
        "must_issue": [issue_code],
        "stages": {},
        "notes": "基础质量异常，由本地规则直接阻断。",
    }


def block_case(case_id: str, name: str, group: str, failed_stage: str, issue_code: str) -> dict:
    stages = {
        "face_cv": pass_face(),
        "color_card_cv": pass_card(),
        "vl_review": pass_vl(),
    }
    stage_labels = {
        "face_cv": "人脸检测不满足测试要求",
        "color_card_cv": "色卡检测不满足测试要求",
        "vl_review": "Codex VL 标注为语义风险",
    }
    stages[failed_stage] = fail_stage(issue_code, stage_labels[failed_stage])
    expected = {"input_quality": "pass", failed_stage: "fail"}
    return {
        "id": case_id,
        "name": name,
        "group": group,
        "image": f"tests/fixtures/images/{case_id}.{'png' if case_id == 'portrait_non_person' else 'jpg'}",
        "expected_status": "needs_retake",
        "expected_stage_status": expected,
        "must_issue": [issue_code],
        "stages": stages,
        "notes": "验证期由 Codex 辅助视觉判断沉淀为 fixture mock。",
    }


def soft_case(
    case_id: str,
    name: str,
    group: str,
    warning_stage: str,
    issue_code: str,
    extra_warnings: dict[str, str] | None = None,
) -> dict:
    stages = {
        "face_cv": pass_face(),
        "color_card_cv": pass_card(),
        "vl_review": pass_vl(),
        "color_correction": pass_color_correction(),
        "skin_tone": pass_skin_tone("warm", "light", "bright"),
        "feature_contrast": pass_feature_contrast("medium"),
        "seasonal_result": pass_seasonal("spring", "bright_spring", "warm", "light", "bright", "medium"),
    }
    stage_labels = {
        "face_cv": "人脸姿态有轻微风险但仍可分析",
        "color_card_cv": "色卡有轻微风险但完整可用",
        "color_correction": "缺少色卡校正，使用原图继续推理",
        "vl_review": "Codex VL 标注为轻微语义风险",
    }
    stages[warning_stage] = warn_stage(issue_code, stage_labels[warning_stage])
    for stage_name, extra_issue_code in (extra_warnings or {}).items():
        stages[stage_name] = warn_stage(extra_issue_code, stage_labels.get(stage_name, "轻微风险但仍可分析"))
    expected = {stage: "pass" for stage in [
        "input_quality",
        "face_cv",
        "color_card_cv",
        "vl_review",
        "color_correction",
        "skin_tone",
        "feature_contrast",
        "seasonal_result",
    ]}
    expected[warning_stage] = "warn"
    for stage_name in (extra_warnings or {}):
        expected[stage_name] = "warn"
    return {
        "id": case_id,
        "name": name,
        "group": group,
        "image": f"tests/fixtures/images/{case_id}.jpg",
        "expected_status": "analyzed",
        "expected_stage_status": expected,
        "expected_seasonal": {"season_4": "spring", "season_12": "bright_spring"},
        "must_issue": [issue_code],
        "stages": stages,
        "notes": "轻微风险只做后端标记和建议，不要求用户重新提交。",
    }


def analyzed_case(case_id: str, name: str, season_4: str, season_12: str, temperature: str, brightness: str, chroma: str, contrast: str, group: str = "seasonal_gold") -> dict:
    return {
        "id": case_id,
        "name": name,
        "group": group,
        "image": f"tests/fixtures/images/{case_id}.jpg",
        "expected_status": "analyzed",
        "expected_stage_status": {stage: "pass" for stage in [
            "input_quality",
            "face_cv",
            "color_card_cv",
            "vl_review",
            "color_correction",
            "skin_tone",
            "feature_contrast",
            "seasonal_result",
        ]},
        "expected_seasonal": {"season_4": season_4, "season_12": season_12},
        "stages": {
            "face_cv": pass_face(),
            "color_card_cv": pass_card(),
            "vl_review": pass_vl(),
            "color_correction": pass_color_correction(),
            "skin_tone": pass_skin_tone(temperature, brightness, chroma),
            "feature_contrast": pass_feature_contrast(contrast),
            "seasonal_result": pass_seasonal(season_4, season_12, temperature, brightness, chroma, contrast),
        },
        "notes": "合成色彩金标样本，用于验证完整分析出参和季节型映射。",
    }


def real_upload_auto_crop_case(case_id: str, name: str, input_issue: str) -> dict:
    expected = {stage_name: "pass" for stage_name in [
        "input_quality",
        "face_cv",
        "color_card_cv",
        "vl_review",
        "color_correction",
        "skin_tone",
        "feature_contrast",
        "seasonal_result",
    ]}
    expected["input_quality"] = "warn"
    expected["face_cv"] = "warn"
    expected["color_card_cv"] = "warn"
    expected["color_correction"] = "warn"
    return {
        "id": case_id,
        "name": name,
        "group": "real_upload",
        "image": f"tests/fixtures/images/{case_id}.jpg",
        "expected_status": "analyzed",
        "expected_stage_status": expected,
        "expected_seasonal": {"season_4": "spring", "season_12": "bright_spring"},
        "must_issue": [input_issue, "face.auto_cropped"],
        "stages": {
            "face_cv": pass_face(),
            "color_card_cv": pass_card(),
            "vl_review": pass_vl(),
            "color_correction": pass_color_correction(),
            "skin_tone": pass_skin_tone("warm", "light", "bright"),
            "feature_contrast": pass_feature_contrast("medium"),
            "seasonal_result": pass_seasonal("spring", "bright_spring", "warm", "light", "bright", "medium"),
        },
        "notes": "真实用户上传截图/长图时，优先自动裁脸继续分析，并降低可信度。",
    }


def real_upload_face_auto_crop_case(case_id: str, name: str) -> dict:
    case = real_upload_auto_crop_case(case_id, name, "face.auto_cropped")
    case["must_issue"] = ["face.auto_cropped"]
    case["expected_stage_status"]["input_quality"] = "pass"
    case["expected_stage_status"]["color_card_cv"] = "pass"
    case["expected_stage_status"]["color_correction"] = "pass"
    case["notes"] = "真实 App 截图中人脸偏小但可定位时，优先自动裁脸继续分析，不要求用户重新上传。"
    return case


def apply_current_policy_overrides(cases: list[dict]) -> list[dict]:
    by_id = {case["id"]: case for case in cases}

    set_analyzed_warning(
        by_id["input_heavy_compression"],
        {"input_quality": "warn", "face_cv": "warn", "vl_review": "pass"},
        ["image.sharpness", "face.blurry"],
        "消费级压缩图可继续分析，但需要软标降低可信度。",
    )

    by_id["portrait_non_person"]["must_issue"] = ["face.no_face"]
    by_id["portrait_half_face"]["must_issue"] = ["face.cropped"]

    set_blocking_face_and_vl(
        by_id["portrait_mask_occlusion"],
        "face.lower_occluded",
        "vl.face_occluded",
        "下半脸有明显遮挡",
        "请摘下口罩，并保证脸颊、下巴区域清晰可见。",
    )
    set_blocking_face_and_vl(
        by_id["portrait_sunglasses"],
        "face.eye_occluded",
        "vl.eye_occluded",
        "眼部有明显遮挡",
        "请摘下墨镜或避免眼部大面积遮挡后再拍。",
    )

    card_overrides = {
        "card_cropped": (["card.cropped", "correction.no_card_fallback"], {"color_card_cv": "warn", "color_correction": "warn"}),
        "card_too_far": (["card.missing", "correction.no_card_fallback"], {"color_card_cv": "warn", "color_correction": "warn", "seasonal_result": "warn"}),
        "card_glare": (["card.glare", "correction.no_card_fallback"], {"color_card_cv": "warn", "color_correction": "warn"}),
        "card_wrong_light": (["card.missing", "correction.no_card_fallback"], {"color_card_cv": "warn", "color_correction": "warn"}),
        "card_fake_grid": (["card.fake", "correction.no_card_fallback"], {"color_card_cv": "warn", "color_correction": "warn"}),
        "card_occluded": (["card.occluded", "correction.no_card_fallback"], {"color_card_cv": "warn", "color_correction": "warn"}),
    }
    for case_id, (must_issue, warning_stages) in card_overrides.items():
        set_analyzed_warning(
            by_id[case_id],
            {"input_quality": "pass", "face_cv": "pass", **warning_stages},
            must_issue,
            "色卡异常不阻断用户，改为不用色卡校正并降低可信度。",
        )

    for case_id, code in {
        "vl_heavy_makeup": "vl.heavy_makeup",
        "vl_foundation": "vl.foundation",
        "vl_blush": "vl.blush",
        "vl_colored_contacts": "vl.colored_contacts",
        "vl_hat_bangs": "vl.hat_bangs",
    }.items():
        set_analyzed_warning(
            by_id[case_id],
            {
                "input_quality": "pass",
                "face_cv": "pass",
                "color_card_cv": "pass",
                "vl_review": "warn",
                "color_correction": "pass",
                "feature_contrast": "pass",
                "seasonal_result": "pass",
            },
            [code],
            "妆容/滤镜/轻遮挡只做后端标记和建议，不要求用户重新提交。",
        )

    return cases


def set_analyzed_warning(case: dict, expected_stages: dict[str, str], must_issue: list[str], notes: str) -> None:
    expected = {stage_name: "pass" for stage_name in [
        "input_quality",
        "face_cv",
        "color_card_cv",
        "vl_review",
        "color_correction",
        "skin_tone",
        "feature_contrast",
        "seasonal_result",
    ]}
    expected.update(expected_stages)
    case["expected_status"] = "analyzed"
    case["expected_stage_status"] = expected
    case["expected_seasonal"] = {"season_4": "spring", "season_12": "bright_spring"}
    case["must_issue"] = must_issue
    case["notes"] = notes
    case.setdefault("stages", {})
    case["stages"].setdefault("vl_review", pass_vl())


def set_blocking_face_and_vl(case: dict, face_code: str, vl_code: str, face_message: str, suggestion: str) -> None:
    case["expected_stage_status"] = {"input_quality": "pass", "face_cv": "fail", "vl_review": "fail"}
    case["must_issue"] = [face_code, vl_code]
    case["stages"]["face_cv"] = stage(
        "fail",
        0.78,
        {"face_count": 1, "face_size_ratio": 0.32, "pose": "front", "cropped": False},
        [{"code": face_code, "message": face_message, "suggestion": suggestion}],
        [suggestion],
    )


def pass_face() -> dict:
    return stage("pass", 0.92, {"face_count": 1, "face_size_ratio": 0.32, "pose": "front", "cropped": False})


def pass_card() -> dict:
    return stage("pass", 0.9, {"detected": True, "card_type": "colorchecker_24", "patch_count": 24, "same_lighting_as_face": True})


def pass_vl() -> dict:
    return stage("pass", 0.88, {"is_real_person": True, "makeup_risk": "low", "filter_risk": "low", "occlusion_risk": "low"})


def pass_color_correction() -> dict:
    return stage("pass", 0.86, {"method": "color_checker_24_ccm", "delta_e_before": 12.4, "delta_e_after": 3.1})


def pass_skin_tone(temperature: str, brightness: str, chroma: str) -> dict:
    return stage("pass", 0.84, {
        "color_values": {"rgb": [214, 176, 150], "lab": [72.0, 12.0, 18.0], "hsv": [22, 30, 84]},
        "dimensions": {"temperature": temperature, "brightness": brightness, "chroma": chroma, "undertone": temperature},
    })


def pass_feature_contrast(contrast: str) -> dict:
    return stage("pass", 0.82, {"eye_color": "dark_brown", "hair_color": "dark_brown", "overall_contrast": contrast})


def pass_seasonal(season_4: str, season_12: str, temperature: str, brightness: str, chroma: str, contrast: str) -> dict:
    season_24 = f"{season_12}_{brightness}_{chroma}_{contrast}"
    return stage("pass", 0.81, {
        "season_4": season_4,
        "season_12": season_12,
        "season_24": season_24,
        "confidence": 0.81,
        "ambiguous_between": [],
        "why": [
            f"肤色温度为 {temperature}",
            f"明度为 {brightness}",
            f"彩度为 {chroma}",
            f"整体对比度为 {contrast}",
        ],
        "suitable_colors": ["ivory", "coral", "teal"],
        "avoid_colors": ["muddy_gray", "neon_purple"],
    })


def fail_stage(code: str, message: str) -> dict:
    return stage("fail", 0.9, {}, [{"code": code, "message": message, "suggestion": retake_suggestion(code)}], [retake_suggestion(code)])


def warn_stage(code: str, message: str) -> dict:
    return stage("warn", 0.72, {}, [{"code": code, "message": message, "suggestion": soft_suggestion(code)}], [soft_suggestion(code)])


def stage(status: str, confidence: float, evidence: dict, issues: list | None = None, suggestions: list | None = None) -> dict:
    return {"status": status, "confidence": confidence, "evidence": evidence, "issues": issues or [], "suggestions": suggestions or []}


def retake_suggestion(code: str) -> str:
    if code.startswith("face."):
        return "请重新拍摄正脸单人照，保持脸部完整无遮挡。"
    if code.startswith("card."):
        return "请把标准 24 色卡完整放在下巴附近，并确保和脸处于同一光照。"
    if code.startswith("vl."):
        return "请素颜、无遮挡、关闭滤镜后重新拍摄。"
    return "请重新拍摄。"


def soft_suggestion(code: str) -> str:
    if code == "card.missing":
        return "未检测到色卡，本次可先用原图推理；建议下次加入标准色卡提升准确度。"
    if code == "face.auto_cropped":
        return "检测到脸部偏小，已自动裁剪到更适合分析的范围。"
    if code == "correction.no_card_fallback":
        return "缺少色卡校正，本次结果会降低置信度；后续可引导用户补拍带色卡照片。"
    if code == "card.tilted":
        return "色卡完整可用，本次继续分析；下次可尽量摆正以提高稳定性。"
    if code in {"vl.pose_side", "vl.pose_tilted"}:
        return "姿态有轻微偏差，本次继续分析；下次建议正对镜头。"
    if code == "vl.beauty_filter":
        return "疑似轻微美颜磨皮，本次继续分析；结果会降低一点置信度。"
    if code == "vl.color_filter":
        return "疑似轻微滤镜偏色，本次依赖色卡校正继续分析。"
    if code == "vl.lipstick":
        return "口红主要影响唇色，本次继续分析肤色；后续眼唇建议会标记风险。"
    if code == "vl.hand_near_face":
        return "手部靠近脸颊或下巴，本次会避开受影响区域继续分析。"
    if code == "vl.glasses_glare":
        return "眼镜有轻微反光，本次会降低眼部对比度判断权重。"
    return "存在轻微风险，本次继续分析并在结果中标记。"


def save(name: str, image: Image.Image, quality: int = 92) -> None:
    path = IMG_DIR / name
    image.convert("RGB").save(path, quality=quality)


def overlay_rect(image: Image.Image, box: tuple[int, int, int, int], color: tuple[int, int, int]) -> Image.Image:
    out = image.copy()
    ImageDraw.Draw(out).rectangle(box, fill=color)
    return out


def tint_region(image: Image.Image, box: tuple[int, int, int, int], color: tuple[int, int, int], alpha: float) -> Image.Image:
    out = image.copy()
    overlay = Image.new("RGB", (box[2] - box[0], box[3] - box[1]), color)
    region = out.crop(box)
    out.paste(Image.blend(region, overlay, alpha), box)
    return out


def seasonal_gold_image(image: Image.Image, temperature: str, brightness: str, chroma: str, contrast: str) -> Image.Image:
    out = image.copy()
    skin_palette = {
        ("warm", "light", "bright"): (238, 169, 112),
        ("warm", "light", "medium"): (226, 190, 170),
        ("cool", "light", "muted"): (209, 178, 185),
        ("cool", "medium", "muted"): (176, 146, 158),
        ("warm", "medium", "muted"): (174, 150, 132),
        ("warm", "deep", "medium"): (128, 86, 61),
        ("cool", "medium", "bright"): (190, 126, 160),
        ("cool", "deep", "bright"): (116, 74, 98),
    }
    skin = skin_palette.get((temperature, brightness, chroma), (214, 176, 150))
    if contrast == "high":
        hair, eyes = (34, 25, 23), (26, 22, 21)
    elif contrast == "medium":
        hair, eyes = (92, 67, 55), (72, 54, 47)
    else:
        hair, eyes = (154, 124, 105), (126, 100, 88)

    draw = ImageDraw.Draw(out, "RGBA")
    # Hair and eye regions are intentionally broad; these are synthetic gold samples for algorithm calibration.
    draw.rectangle((220, 250, 790, 485), fill=(*hair, 205))
    draw.ellipse((326, 494, 408, 565), fill=(*eyes, 190))
    draw.ellipse((555, 494, 637, 565), fill=(*eyes, 190))
    for box in [
        (340, 430, 630, 565),
        (250, 555, 430, 735),
        (560, 555, 740, 735),
        (380, 690, 620, 860),
    ]:
        draw.ellipse(box, fill=(*skin, 190))
    if chroma == "bright":
        draw.ellipse((252, 585, 385, 718), fill=(238, 90, 96, 42))
        draw.ellipse((608, 585, 741, 718), fill=(238, 90, 96, 42))
    elif chroma == "muted":
        out = ImageEnhance.Color(out).enhance(0.82)
    if brightness == "deep":
        out = ImageEnhance.Brightness(out).enhance(0.82)
    elif brightness == "light":
        out = ImageEnhance.Brightness(out).enhance(1.05)
    return out.convert("RGB")


def overlay_fake_grid(image: Image.Image) -> Image.Image:
    out = image.copy()
    draw = ImageDraw.Draw(out)
    x0, y0, w, h = 230, 920, 520, 320
    random.seed(7)
    for row in range(4):
        for col in range(6):
            color = tuple(random.randint(20, 240) for _ in range(3))
            draw.rectangle((x0 + col * w // 6, y0 + row * h // 4, x0 + (col + 1) * w // 6 - 4, y0 + (row + 1) * h // 4 - 4), fill=color)
    return out


def draw_makeup(image: Image.Image, lipstick: bool = False, blush: bool = False, eye: bool = False) -> Image.Image:
    out = image.copy()
    draw = ImageDraw.Draw(out, "RGBA")
    if lipstick:
        draw.ellipse((420, 690, 565, 750), fill=(190, 20, 45, 150))
    if blush:
        draw.ellipse((250, 600, 410, 740), fill=(230, 80, 110, 90))
        draw.ellipse((600, 600, 760, 740), fill=(230, 80, 110, 90))
    if eye:
        draw.ellipse((340, 500, 400, 555), fill=(80, 130, 190, 120))
        draw.ellipse((565, 500, 625, 555), fill=(80, 130, 190, 120))
    return out.convert("RGB")


def draw_colorful_clothes(image: Image.Image) -> Image.Image:
    out = image.copy()
    draw = ImageDraw.Draw(out, "RGBA")
    blocks = [
        ((115, 910, 270, 1180), (232, 82, 98, 230)),
        ((270, 910, 430, 1180), (245, 183, 75, 230)),
        ((430, 910, 590, 1180), (71, 156, 168, 230)),
        ((590, 910, 750, 1180), (103, 117, 198, 230)),
        ((750, 910, 890, 1180), (230, 134, 190, 230)),
    ]
    for box, color in blocks:
        draw.rounded_rectangle(box, radius=34, fill=color)
    draw.arc((150, 820, 850, 1320), 200, 340, fill=(255, 255, 255, 160), width=18)
    return out.convert("RGB")


def draw_colorful_background_poster(image: Image.Image) -> Image.Image:
    out = image.copy()
    draw = ImageDraw.Draw(out, "RGBA")
    x0, y0, w, h = 560, 875, 350, 260
    draw.rounded_rectangle((x0 - 18, y0 - 18, x0 + w + 18, y0 + h + 18), radius=28, fill=(245, 242, 238, 235))
    colors = [
        (228, 64, 92, 220), (241, 152, 62, 220), (247, 215, 95, 220), (96, 176, 112, 220), (68, 154, 184, 220), (105, 105, 198, 220),
        (226, 103, 158, 220), (170, 92, 193, 220), (68, 130, 200, 220), (73, 181, 184, 220), (139, 191, 92, 220), (232, 185, 75, 220),
        (186, 78, 70, 220), (203, 134, 80, 220), (206, 186, 112, 220), (118, 155, 116, 220), (92, 132, 158, 220), (125, 117, 168, 220),
        (98, 85, 80, 220), (128, 118, 105, 220), (158, 150, 135, 220), (190, 183, 168, 220), (215, 210, 198, 220), (235, 232, 224, 220),
    ]
    index = 0
    for row in range(4):
        for col in range(6):
            left = x0 + col * w // 6
            top = y0 + row * h // 4
            right = x0 + (col + 1) * w // 6 - 5
            bottom = y0 + (row + 1) * h // 4 - 5
            draw.rounded_rectangle((left, top, right, bottom), radius=8, fill=colors[index])
            index += 1
    draw.rectangle((x0 - 18, y0 - 18, x0 + w + 18, y0 + h + 18), outline=(255, 255, 255, 160), width=5)
    return out.convert("RGB")


def draw_busy_poster_wall(image: Image.Image) -> Image.Image:
    out = image.copy()
    draw = ImageDraw.Draw(out, "RGBA")
    random.seed(19)
    palette = [
        (238, 78, 102, 218),
        (246, 174, 71, 218),
        (86, 170, 185, 218),
        (112, 114, 202, 218),
        (235, 128, 184, 218),
        (102, 178, 122, 218),
        (250, 222, 112, 218),
        (176, 105, 210, 218),
    ]
    for row in range(4):
        for col in range(4):
            x0 = 36 + col * 214 + random.randint(-8, 8)
            y0 = 110 + row * 180 + random.randint(-10, 10)
            w = random.randint(120, 170)
            h = random.randint(110, 150)
            color = palette[(row * 4 + col) % len(palette)]
            draw.rounded_rectangle((x0, y0, x0 + w, y0 + h), radius=14, fill=color)
            draw.rectangle((x0 + 16, y0 + 18, x0 + w - 18, y0 + 26), fill=(255, 255, 255, 105))
            draw.rectangle((x0 + 16, y0 + 42, x0 + w - 38, y0 + 50), fill=(255, 255, 255, 80))
    return out.convert("RGB")


def draw_clear_glasses(image: Image.Image) -> Image.Image:
    out = image.copy()
    draw = ImageDraw.Draw(out, "RGBA")
    draw.rounded_rectangle((306, 478, 430, 570), radius=34, outline=(50, 45, 42, 185), width=7)
    draw.rounded_rectangle((535, 478, 660, 570), radius=34, outline=(50, 45, 42, 185), width=7)
    draw.line((430, 520, 535, 520), fill=(50, 45, 42, 170), width=6)
    draw.line((306, 515, 250, 500), fill=(50, 45, 42, 145), width=5)
    draw.line((660, 515, 720, 500), fill=(50, 45, 42, 145), width=5)
    return out.convert("RGB")


def draw_glasses_glare(image: Image.Image) -> Image.Image:
    out = image.copy()
    draw = ImageDraw.Draw(out, "RGBA")
    draw.line((330, 500, 416, 545), fill=(255, 255, 255, 135), width=9)
    draw.line((556, 500, 640, 545), fill=(255, 255, 255, 125), width=9)
    return out.convert("RGB")


def draw_bangs(image: Image.Image) -> Image.Image:
    out = image.copy()
    draw = ImageDraw.Draw(out, "RGBA")
    hair = (45, 34, 30, 222)
    draw.pieslice((235, 250, 770, 590), 180, 360, fill=hair)
    for x0, y1 in [(275, 505), (350, 555), (432, 530), (520, 560), (610, 525)]:
        draw.polygon([(x0, 345), (x0 + 80, 345), (x0 + 38, y1)], fill=hair)
    return out.convert("RGB")


def draw_hat_shadow(image: Image.Image) -> Image.Image:
    out = image.copy()
    draw = ImageDraw.Draw(out, "RGBA")
    draw.rounded_rectangle((190, 230, 815, 405), radius=48, fill=(54, 50, 46, 230))
    draw.ellipse((145, 365, 860, 500), fill=(42, 39, 36, 170))
    draw.rectangle((275, 405, 735, 520), fill=(34, 32, 30, 70))
    return out.convert("RGB")


def draw_hand_near_face(image: Image.Image) -> Image.Image:
    out = image.copy()
    draw = ImageDraw.Draw(out, "RGBA")
    skin = (218, 166, 132, 220)
    draw.ellipse((612, 684, 838, 940), fill=skin)
    for i, x0 in enumerate([610, 654, 698, 742]):
        draw.rounded_rectangle((x0, 604 - i * 6, x0 + 54, 800), radius=24, fill=skin)
    draw.ellipse((640, 642, 760, 760), fill=(238, 190, 158, 90))
    return out.convert("RGB")


if __name__ == "__main__":
    main()
