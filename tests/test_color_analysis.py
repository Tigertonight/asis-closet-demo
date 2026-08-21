from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.analyzer import analyze_contract, analyze_fixture_case, analyze_image_bytes, cached_self_test_results, explain_fixture_case, mvp_algorithm_contract, mvp_algorithm_markdown, mvp_handoff_markdown, mvp_open_source_markdown, mvp_pilot_guide_markdown, mvp_policy_rules, mvp_seasonal_evaluation, mvp_status_summary, render_demo_page, render_mvp_status_page, render_self_test_page, self_test_results
from app.cv_pipeline import ColourScienceColorCardDetector, available_color_card_detectors, run_color_card_cv, run_seasonal_result
from app.main import app
from scripts.generate_qa_artifacts import write_contact_sheet, write_region_overlay_sheet, write_report
from scripts.smoke_mvp import DEFAULT_OUTPUT, SMOKE_CASES, evaluate_case_payload, evaluate_demo_page, evaluate_status_payload


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "images"
EXPECTED_FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "expected.json"
OPEN_SOURCE_SELECTION_PATH = Path(__file__).resolve().parents[1] / "docs" / "OPEN_SOURCE_TECH_SELECTION.md"
EXPECTED_CASE_COUNT = len(json.loads(EXPECTED_FIXTURE_PATH.read_text(encoding="utf-8"))["cases"])
client = TestClient(app)


def test_color_analysis_summary_for_successful_case() -> None:
    result = analyze_fixture_case("season_spring_bright")
    summary = result["result_summary"]

    assert result["status"] == "analyzed"
    assert summary["available"] is True
    assert summary["title"] == "明亮春型"
    assert summary["season"]["season_4_name"] == "春季型"
    assert summary["season"]["season_24"] == "bright_spring_light_bright_high"
    assert summary["season"]["season_24_name"] == "明亮春型 · 明亮 / 鲜明 / 强对比"
    assert len(summary["season"]["top_candidates"]) == 3
    assert summary["season"]["probability_percent"] > 0
    assert summary["season"]["top_candidates"][0]["season_12_name"] == "明亮春型"
    assert summary["season"]["top_candidates"][0]["confidence_percent"] == summary["confidence_percent"]
    assert summary["season"]["top_candidates"][0]["probability_percent"] == summary["season"]["probability_percent"]
    assert summary["season"]["top_candidates"][1]["season_12_name"]
    assert summary["dimensions"]["temperature_name"] == "偏暖"
    assert summary["dimensions"]["contrast_name"] == "强"
    assert summary["confidence_percent"] > 0
    assert summary["confidence_percent"] <= 76
    assert summary["capture"]["quality_level"] == "standard"
    assert summary["capture"]["result_tier"] == "standard"
    assert summary["capture"]["result_tier_label"] == "标准可用"
    assert summary["capture"]["used_color_card"] is True
    assert summary["capture"]["reference_only"] is False
    assert summary["capture"]["risk_labels"] == []
    assert [item["code"] for item in summary["next_actions"]] == ["use_result", "copy_summary"]
    assert summary["why"]
    assert [item["name"] for item in summary["suitable_colors"]] == ["象牙白", "珊瑚色", "蓝绿色"]
    assert [item["hex"] for item in summary["suitable_colors"]] == ["#fff1d6", "#ef6f61", "#228b8d"]
    assert [item["name"] for item in summary["avoid_colors"]] == ["浑浊灰", "黑棕", "冰蓝"]
    assert [item["hex"] for item in summary["avoid_colors"]] == ["#77736c", "#2f211c", "#cde9ff"]


def test_analyze_contract_exposes_frontend_summary_fields() -> None:
    contract = analyze_contract()

    assert contract["endpoint"]["path"] == "/analyze"
    assert contract["endpoint"]["file_field"] == "image"
    assert "result_summary" not in contract["summary_contract"]
    assert "season_24_name" in contract["summary_contract"]["season"]
    assert "top_candidates" in contract["summary_contract"]["season"]
    assert "probability_percent" in contract["summary_contract"]["season"]
    assert "uncertainty_flags" in contract["summary_contract"]["season"]
    assert "suitable_colors" in contract["summary_contract"]
    assert "capture" in contract["summary_contract"]
    assert "used_color_card" in contract["summary_contract"]["capture"]
    assert "next_actions" in contract["summary_contract"]
    assert contract["examples"]["standard"]["summary"]["capture"]["quality_level"] == "standard"
    assert contract["examples"]["reference_only"]["summary"]["capture"]["quality_level"] == "reference_only"
    assert contract["examples"]["light_note"]["summary"]["capture"]["result_tier"] == "light_note"
    assert contract["examples"]["low_confidence"]["summary"]["capture"]["result_tier"] == "low_confidence"
    assert contract["examples"]["retake"]["summary"]["capture"]["quality_level"] == "retake"
    assert contract["examples"]["reference_only"]["summary"]["next_actions"][1]["code"] == "retake_with_card"
    assert contract["examples"]["retake"]["summary"]["next_actions"][0]["code"] == "retake_photo"
    assert "hard_retake" in contract["consumer_rules"]
    assert "soft_continue" in contract["consumer_rules"]
    assert contract["mvp_policy"]["color_card_policy"]["required_for_analysis"] is False
    assert "card.missing" in contract["mvp_policy"]["tiers"]["light_note"]["issue_codes"]
    assert "vl.color_filter" in contract["mvp_policy"]["tiers"]["low_confidence"]["issue_codes"]


def test_analyze_contract_http_endpoint() -> None:
    response = client.get("/analyze/contract")

    assert response.status_code == 200
    contract = response.json()
    assert contract["version"] == "0.5.2"
    assert contract["endpoint"]["path"] == "/analyze"
    assert contract["endpoint"]["file_field"] == "image"


def test_analyze_http_upload_multipart() -> None:
    path = FIXTURE_DIR / "card_missing.jpg"

    with path.open("rb") as image_file:
        response = client.post(
            "/analyze",
            files={"image": ("real_user_card_missing.jpg", image_file, "image/jpeg")},
        )

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "analyzed"
    assert result["result_summary"]["available"] is True
    assert result["pipeline"]["vl_review"]["evidence"]["source"] == "local_cv_visual_risk"
    assert result["pipeline"]["color_card_cv"]["issues"][0]["code"] == "card.missing"


def test_demo_analyze_http_upload_uses_local_inference_without_spring_fallback() -> None:
    image = Image.open(FIXTURE_DIR / "card_missing.jpg").convert("RGB")
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    buffer.seek(0)

    response = client.post(
        "/demo/analyze",
        files={"image": ("unknown_user_upload.jpg", buffer, "image/jpeg")},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "analyzed"
    assert result["pipeline"]["vl_review"]["evidence"]["source"] == "local_cv_visual_risk"
    assert result["demo"]["fallback_fixture_used"] is False
    assert "不会套用默认季节样本" in result["demo"]["fallback_note"]


def test_seasonal_ranking_uses_depth_not_only_warmth_and_contrast() -> None:
    def stage(lab_l: float, warmth: float, chroma_score: float, saturation: float, dimensions: dict[str, str], contrast: str) -> dict[str, Any]:
        skin = {
            "status": "pass",
            "confidence": 0.72,
            "evidence": {
                "dimensions": dimensions,
                "scores": {"warmth": warmth, "chroma": chroma_score},
                "color_values": {"lab": [lab_l, 12.0, 18.0], "hsv": [18.0, saturation, 72.0]},
            },
        }
        feature = {"status": "pass", "confidence": 0.72, "evidence": {"overall_contrast": contrast}}
        return run_seasonal_result(skin, feature, {"status": "warn"}, {"status": "warn"})

    very_light = stage(
        82.0,
        5.8,
        13.0,
        18.0,
        {"temperature": "neutral", "brightness": "light", "chroma": "muted", "undertone": "neutral"},
        "high",
    )
    medium_tan = stage(
        60.0,
        9.5,
        28.0,
        38.0,
        {"temperature": "warm", "brightness": "medium", "chroma": "bright", "undertone": "warm"},
        "high",
    )

    assert very_light["evidence"]["season_12"] == "light_summer"
    assert medium_tan["evidence"]["season_4"] == "autumn"
    assert medium_tan["evidence"]["season_12"] != "bright_spring"
    assert medium_tan["evidence"]["layered_diagnosis"]["depth_test"]["winner"] == "medium"


def test_real_upload_seasonal_gold_distribution_is_not_all_spring() -> None:
    case_ids = [
        "season_spring_bright",
        "season_summer_light",
        "season_autumn_deep",
        "season_winter_clear",
    ]
    predicted = {}
    for case_id in case_ids:
        path = FIXTURE_DIR / f"{case_id}.jpg"
        result = analyze_image_bytes(path.read_bytes(), f"user_upload_{case_id}.jpg", save_upload=False, fixture_case=None)
        assert result["status"] == "analyzed"
        predicted[case_id] = result["result_summary"]["season"]["season_4"]

    assert predicted == {
        "season_spring_bright": "spring",
        "season_summer_light": "summer",
        "season_autumn_deep": "autumn",
        "season_winter_clear": "winter",
    }


def test_analyze_http_rejects_unsupported_upload() -> None:
    response = client.post(
        "/analyze",
        files={"image": ("note.txt", BytesIO(b"not an image"), "text/plain")},
    )

    assert response.status_code == 400
    body = response.json()
    assert "无法识别" in body["detail"]
    assert body["error"]["code"] == "upload.unrecognized_image"
    assert "JPG" in body["error"]["suggestion"]


def test_analyze_http_missing_image_field_is_friendly() -> None:
    response = client.post(
        "/analyze",
        files={"photo": ("photo.jpg", BytesIO(b"not an image"), "image/jpeg")},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["status"] == "failed"
    assert body["error"]["code"] == "upload.image_missing"
    assert "没有收到照片" in body["detail"]
    assert "JPG" in body["decision"]["user_message"]


def test_color_card_correction_is_applied_to_skin_tone_evidence() -> None:
    result = analyze_fixture_case("season_spring_bright")
    correction = result["pipeline"]["color_correction"]
    skin_values = result["pipeline"]["skin_tone"]["evidence"]["color_values"]

    assert correction["status"] == "pass"
    assert correction["evidence"]["method"] == "linear_rgb_matrix_with_colour_science_delta_e"
    assert correction["evidence"]["delta_e_method"] == "CIE 2000"
    assert correction["evidence"]["delta_e_2000_before"] > correction["evidence"]["delta_e_2000_after"]
    assert correction["evidence"]["delta_e_2000_improvement"] > 0
    assert correction["evidence"]["rgb_distance_before"] == correction["evidence"]["delta_e_before"]
    assert correction["evidence"]["correction_quality"] in {"excellent", "good", "usable", "weak"}
    assert correction["evidence"]["matrix_rgb_3x4"]
    assert skin_values["correction_applied"] is True
    assert skin_values["correction_strength"] > 0
    assert skin_values["raw_rgb"] != skin_values["rgb"]
    assert skin_values["full_corrected_rgb"] != skin_values["raw_rgb"]


def test_skin_tone_uses_stable_adaptive_skin_mask_regions() -> None:
    result = analyze_fixture_case("season_winter_clear")
    evidence = result["pipeline"]["skin_tone"]["evidence"]

    assert evidence["method"] == "adaptive_skin_mask_region_median_rgb_lab_hsv"
    assert evidence["region_source"] == "mediapipe_face_landmarker"
    assert {"forehead", "left_cheek", "right_cheek", "jaw"} <= {region["name"] for region in evidence["regions"]}
    assert evidence["landmark_keypoints"]["nose"]
    assert evidence["sample_quality"]["used_stable_regions"] is True
    assert evidence["sample_quality"]["stable_region_count"] >= 3
    assert all(region["skin_ratio"] > 0.5 for region in evidence["regions"])
    assert all(region["selection_method"] in {"region_skin_mask", "adaptive_window_skin_mask"} for region in evidence["regions"])
    assert all(region["source"] == "mediapipe_face_landmarker" for region in evidence["regions"])


def test_feature_contrast_uses_adaptive_luminance_sampling_without_overcalling_summer() -> None:
    result = analyze_fixture_case("season_summer_light")
    evidence = result["pipeline"]["feature_contrast"]["evidence"]

    assert evidence["method"] == "adaptive_feature_luminance_contrast"
    assert evidence["region_source"] == "mediapipe_face_landmarker"
    assert evidence["overall_contrast"] == "medium"
    assert evidence["sample_quality"]["fallback_region_count"] >= 1
    assert "selection_method" in evidence["regions"]["hair"]
    assert evidence["regions"]["left_eye"]["source"] == "mediapipe_face_landmarker"
    assert evidence["regions"]["hair"]["dark_pixel_ratio"] < 0.35
    assert result["result_summary"]["season"]["season_4"] == "summer"


def test_fixture_explain_compacts_algorithm_evidence_for_debugging() -> None:
    explanation = explain_fixture_case("season_summer_light")

    assert explanation["status"] == "analyzed"
    assert explanation["result_title"] == "浅夏型"
    assert explanation["overlay_url"] == "/qa-artifacts/overlays/season_summer_light.jpg"
    assert explanation["dimensions"]["temperature"] == "cool"
    assert explanation["skin_sampling"]["region_source"] == "mediapipe_face_landmarker"
    assert explanation["feature_contrast"]["region_source"] == "mediapipe_face_landmarker"
    assert explanation["feature_contrast"]["overall_contrast"] == "medium"
    assert explanation["seasonal"]["season_12"] == "light_summer"
    assert explanation["seasonal"]["top_candidates"][0]["season_12"] == "light_summer"
    assert explanation["debug_links"]["algorithm_contract"] == "/mvp/algorithm/contract"


def test_fixture_explain_hides_overlay_for_retake_case() -> None:
    explanation = explain_fixture_case("portrait_sunglasses")

    assert explanation["status"] == "needs_retake"
    assert explanation["overlay_url"] is None
    assert explanation["seasonal"]["season_12"] is None
    assert "face.eye_occluded" in explanation["issues"]


def test_fixture_explain_http_endpoint() -> None:
    response = client.get("/fixtures/season_summer_light/explain")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "analyzed"
    assert body["image_url"].endswith("season_summer_light.jpg")
    assert body["debug_links"]["analyze"] == "/fixtures/season_summer_light/analyze"


def test_self_test_records_sampling_region_source_metrics() -> None:
    results = self_test_results()
    summer = next(case for case in results["cases"] if case["id"] == "season_summer_light")
    metric = results["product_metrics"]["sampling_region_source"]

    assert summer["sampling_debug"]["skin_region_source"] == "mediapipe_face_landmarker"
    assert summer["sampling_debug"]["feature_region_source"] == "mediapipe_face_landmarker"
    assert summer["sampling_debug"]["skin_stable_region_count"] >= 3
    assert metric["label"] == "关键点采样覆盖率"
    assert metric["total"] > 0
    assert metric["rate"] >= 0.9
    assert metric["both_landmark_count"] == metric["total"]


def test_missing_color_card_keeps_raw_skin_tone() -> None:
    result = analyze_fixture_case("card_missing")
    skin_values = result["pipeline"]["skin_tone"]["evidence"]["color_values"]

    assert result["pipeline"]["color_correction"]["status"] == "warn"
    assert skin_values["correction_applied"] is False
    assert skin_values["correction_strength"] == 0
    assert skin_values["raw_rgb"] == skin_values["rgb"]


def test_color_card_detector_adapter_marks_default_detector() -> None:
    image = Image.open(FIXTURE_DIR / "season_spring_bright.jpg").convert("RGB")

    result = run_color_card_cv(image)

    assert result["status"] in {"pass", "warn"}
    assert result["evidence"]["detector_adapter"] == "colour_science_segmentation_with_opencv_fallback"
    assert result["evidence"]["detection_method"] in {"colour_science_segmentation", "colored_patch_grid", "dark_frame_verified_grid"}
    assert result["evidence"]["detected"] is True
    assert result["evidence"]["card_box"]


def test_color_card_detector_can_be_replaced_for_future_model_adapter() -> None:
    class StubNoCardDetector:
        name = "stub_no_card"

        def detect(self, bgr):  # type: ignore[no-untyped-def]
            return None

    image = Image.open(FIXTURE_DIR / "season_spring_bright.jpg").convert("RGB")

    result = run_color_card_cv(image, detector=StubNoCardDetector())

    assert result["status"] == "warn"
    assert result["evidence"]["detector_adapter"] == "stub_no_card"
    assert result["evidence"]["detected"] is False
    assert result["evidence"]["usable_for_correction"] is False
    assert result["issues"][0]["code"] == "card.missing"


def test_color_card_detector_error_falls_back_to_no_card_policy() -> None:
    class BrokenDetector:
        name = "broken_detector"

        def detect(self, bgr):  # type: ignore[no-untyped-def]
            raise RuntimeError("model file missing")

    image = Image.open(FIXTURE_DIR / "season_spring_bright.jpg").convert("RGB")

    result = run_color_card_cv(image, detector=BrokenDetector())

    assert result["status"] == "warn"
    assert result["evidence"]["detector_adapter"] == "broken_detector"
    assert result["evidence"]["detection_method"] == "detector_error"
    assert result["evidence"]["detected"] is False
    assert "model file missing" in result["evidence"]["detector_error"]
    assert result["issues"][0]["code"] == "card.missing"


def test_color_card_detector_registry_documents_replacement_target() -> None:
    detectors = available_color_card_detectors()

    assert detectors[0]["name"] == "colour_science_segmentation_with_opencv_fallback"
    assert detectors[0]["status"] == "active"
    assert any(detector["name"] == "colour_checker_detection" and detector["status"] == "active" for detector in detectors)
    assert any(detector["name"] == "opencv_contour_grid" and detector["role"] == "fallback_adapter" for detector in detectors)


def test_colour_science_detector_does_not_accept_wrong_region_on_fixture() -> None:
    image = Image.open(FIXTURE_DIR / "season_spring_bright.jpg").convert("RGB")

    result = run_color_card_cv(image, detector=ColourScienceColorCardDetector())

    assert result["status"] == "warn"
    assert result["evidence"]["detector_adapter"] == "colour_science_segmentation"
    assert result["evidence"]["detected"] is False
    assert result["issues"][0]["code"] == "card.missing"


def test_color_analysis_retake_does_not_expose_result_summary() -> None:
    result = analyze_fixture_case("portrait_sunglasses")
    summary = result["result_summary"]

    assert result["status"] == "needs_retake"
    assert summary["available"] is False
    assert summary["title"] == ""
    assert summary["season"] is None
    assert summary["dimensions"] is None
    assert summary["suitable_colors"] == []
    assert summary["avoid_colors"] == []
    assert summary["capture"]["quality_level"] == "retake"
    assert summary["capture"]["reference_only"] is True
    assert summary["capture"]["risk_codes"] == ["face.eye_occluded"]
    assert summary["capture"]["risk_labels"] == ["眼部遮挡明显"]
    assert summary["next_actions"][0]["code"] == "retake_photo"
    assert "墨镜" in summary["retake_message"]


def test_self_test_retake_cases_do_not_expose_seasonal_result() -> None:
    results = self_test_results()
    sunglasses = next(case for case in results["cases"] if case["id"] == "portrait_sunglasses")

    assert sunglasses["actual_status"] == "needs_retake"
    assert sunglasses["seasonal_result"] is None


def test_soft_risks_cap_consumer_confidence() -> None:
    no_card = analyze_fixture_case("card_missing")
    beauty = analyze_fixture_case("vl_beauty_filter")
    tilted_card = analyze_fixture_case("card_tilted")

    assert no_card["status"] == "analyzed"
    assert no_card["result_summary"]["confidence"] <= 0.75
    assert no_card["result_summary"]["capture"]["quality_level"] == "reference_only"
    assert no_card["result_summary"]["capture"]["result_tier"] == "light_note"
    assert no_card["result_summary"]["capture"]["result_tier_label"] == "可用但轻提示"
    assert no_card["result_summary"]["capture"]["used_color_card"] is False
    assert no_card["result_summary"]["capture"]["color_card_state"] == "not_used"
    assert no_card["result_summary"]["capture"]["guidance_label"].startswith("这次未使用色卡")
    assert "未检测到色卡" in no_card["result_summary"]["capture"]["risk_labels"]
    assert "未使用色卡校正" in no_card["result_summary"]["capture"]["risk_labels"]
    assert [item["code"] for item in no_card["result_summary"]["next_actions"]] == ["use_result", "retake_with_card"]
    assert "这次未使用色卡" in " ".join(no_card["result_summary"]["why"])
    assert beauty["status"] == "analyzed"
    assert beauty["result_summary"]["confidence"] <= 0.70
    assert beauty["result_summary"]["capture"]["quality_level"] == "reference_only"
    assert beauty["result_summary"]["capture"]["result_tier"] == "light_note"
    assert "vl.beauty_filter" in beauty["result_summary"]["capture"]["risk_codes"]
    assert "可能有轻微美颜" in beauty["result_summary"]["capture"]["risk_labels"]
    assert [item["code"] for item in beauty["result_summary"]["next_actions"]] == ["use_result", "upload_natural_light_photo"]
    assert any(item["code"] == "seasonal.consumer_confidence_cap" for item in beauty["decision"]["warnings"])
    assert tilted_card["status"] == "analyzed"
    assert tilted_card["result_summary"]["capture"]["used_color_card"] is True
    assert tilted_card["result_summary"]["capture"]["color_card_state"] == "used"
    assert "色卡轻微倾斜" in tilted_card["result_summary"]["capture"]["risk_labels"]
    assert "检测到可用色卡" in " ".join(tilted_card["result_summary"]["why"])
    assert "retake_with_card" not in [item["code"] for item in tilted_card["result_summary"]["next_actions"]]


def test_user_facing_guidance_prioritizes_real_photo_risk_over_color_card() -> None:
    warm_light = analyze_fixture_case("real_warm_indoor_light_no_card")
    auto_crop = analyze_fixture_case("portrait_face_too_small")
    fake_card = analyze_fixture_case("card_fake_grid")

    warm_capture = warm_light["result_summary"]["capture"]
    assert warm_capture["result_tier"] == "low_confidence"
    assert warm_capture["risk_codes"][:1] == ["vl.color_filter"]
    assert warm_capture["risk_labels"][:1] == ["照片有滤镜偏色"]
    assert warm_capture["guidance_label"].startswith("这张照片的光线或色调会影响肤色判断")
    assert [item["code"] for item in warm_light["result_summary"]["next_actions"]][:2] == ["use_result", "upload_natural_light_photo"]
    assert warm_light["result_summary"]["confidence"] <= 0.62

    crop_capture = auto_crop["result_summary"]["capture"]
    assert crop_capture["auto_cropped"] is True
    assert crop_capture["risk_codes"][:1] == ["face.auto_cropped"]
    assert crop_capture["guidance_label"].startswith("已帮你放大脸部区域继续分析")
    assert [item["code"] for item in auto_crop["result_summary"]["next_actions"]][:2] == ["use_result", "upload_clearer_photo"]

    fake_capture = fake_card["result_summary"]["capture"]
    assert fake_capture["result_tier"] == "low_confidence"
    assert fake_capture["risk_codes"][:1] == ["card.fake"]
    assert fake_capture["guidance_label"].startswith("照片里有类似色卡的彩色块")
    assert "暂时不能用于校准" in fake_capture["guidance_label"]


def test_real_upload_wide_image_auto_crops_and_continues() -> None:
    path = FIXTURE_DIR / "real_wide_auto_crop.jpg"
    result = analyze_image_bytes(path.read_bytes(), "real_user_wide.jpg", save_upload=False, fixture_case=None)
    summary = result["result_summary"]
    warning_codes = {item["code"] for item in result["decision"]["warnings"]}

    assert result["status"] == "analyzed"
    assert summary["available"] is True
    assert "image.auto_cropped" in warning_codes
    assert "face.auto_cropped" in warning_codes
    assert summary["capture"]["auto_cropped"] is True
    assert summary["capture"]["quality_level"] == "reference_only"
    assert summary["capture"]["result_tier"] in {"light_note", "low_confidence"}
    assert any(item["code"] in {"retake_with_card", "upload_clearer_photo"} for item in summary["next_actions"])
    assert summary["why"]


def test_real_upload_user_intuition_cases_continue_without_retake() -> None:
    social_path = FIXTURE_DIR / "real_social_screenshot_auto_crop.jpg"
    clothes_path = FIXTURE_DIR / "real_colorful_clothes_no_card.jpg"
    poster_path = FIXTURE_DIR / "real_colorful_poster_no_card.jpg"
    busy_wall_path = FIXTURE_DIR / "real_busy_poster_wall_no_card.jpg"
    warm_light_path = FIXTURE_DIR / "real_warm_indoor_light_no_card.jpg"
    screen_light_path = FIXTURE_DIR / "real_screen_cool_light_no_card.jpg"
    glasses_path = FIXTURE_DIR / "real_clear_glasses.jpg"
    bangs_path = FIXTURE_DIR / "real_bangs_forehead.jpg"
    hat_path = FIXTURE_DIR / "real_hat_shadow.jpg"

    social = analyze_image_bytes(social_path.read_bytes(), "user_social_screenshot.jpg", save_upload=False, fixture_case=None)
    clothes = analyze_image_bytes(clothes_path.read_bytes(), "user_colorful_top.jpg", save_upload=False, fixture_case=None)
    poster = analyze_image_bytes(poster_path.read_bytes(), "user_colorful_poster.jpg", save_upload=False, fixture_case=None)
    busy_wall = analyze_image_bytes(busy_wall_path.read_bytes(), "user_busy_poster_wall.jpg", save_upload=False, fixture_case=None)
    warm_light = analyze_image_bytes(warm_light_path.read_bytes(), "user_warm_indoor_light.jpg", save_upload=False, fixture_case=None)
    screen_light = analyze_image_bytes(screen_light_path.read_bytes(), "user_screen_cool_light.jpg", save_upload=False, fixture_case=None)
    glasses = analyze_image_bytes(glasses_path.read_bytes(), "user_clear_glasses.jpg", save_upload=False, fixture_case=None)
    bangs = analyze_image_bytes(bangs_path.read_bytes(), "user_bangs_forehead.jpg", save_upload=False, fixture_case=None)
    hat = analyze_image_bytes(hat_path.read_bytes(), "user_hat_shadow.jpg", save_upload=False, fixture_case=None)

    assert social["status"] == "analyzed"
    assert social["result_summary"]["capture"]["auto_cropped"] is True
    assert social["result_summary"]["capture"]["result_tier"] == "light_note"
    assert "face.auto_cropped" in {item["code"] for item in social["decision"]["warnings"]}
    assert [item["code"] for item in social["result_summary"]["next_actions"]] == ["use_result", "upload_clearer_photo"]

    assert clothes["status"] == "analyzed"
    assert clothes["result_summary"]["capture"]["used_color_card"] is False
    assert clothes["result_summary"]["capture"]["color_card_state"] == "not_used"
    assert clothes["result_summary"]["capture"]["result_tier"] == "light_note"
    assert {"card.missing", "correction.no_card_fallback"}.issubset({item["code"] for item in clothes["decision"]["warnings"]})
    assert "retake_photo" not in [item["code"] for item in clothes["result_summary"]["next_actions"]]

    assert poster["status"] == "analyzed"
    assert poster["result_summary"]["capture"]["used_color_card"] is False
    assert poster["result_summary"]["capture"]["result_tier"] == "light_note"
    assert "card.fake" not in {item["code"] for item in poster["decision"]["warnings"]}
    assert {"card.missing", "correction.no_card_fallback"}.issubset({item["code"] for item in poster["decision"]["warnings"]})

    assert busy_wall["status"] == "analyzed"
    assert busy_wall["result_summary"]["capture"]["result_tier"] in {"light_note", "low_confidence"}
    assert "card.fake" not in {item["code"] for item in busy_wall["decision"]["warnings"]}
    assert "retake_photo" not in [item["code"] for item in busy_wall["result_summary"]["next_actions"]]

    assert warm_light["status"] == "analyzed"
    assert warm_light["result_summary"]["capture"]["result_tier"] == "low_confidence"
    assert "vl.color_filter" in {item["code"] for item in warm_light["decision"]["warnings"]}
    assert "retake_photo" not in [item["code"] for item in warm_light["result_summary"]["next_actions"]]
    assert [item["code"] for item in warm_light["result_summary"]["next_actions"]][:2] == ["use_result", "upload_natural_light_photo"]

    assert screen_light["status"] == "analyzed"
    assert screen_light["result_summary"]["capture"]["result_tier"] == "low_confidence"
    assert "vl.color_filter" in {item["code"] for item in screen_light["decision"]["warnings"]}
    assert "retake_photo" not in [item["code"] for item in screen_light["result_summary"]["next_actions"]]
    assert [item["code"] for item in screen_light["result_summary"]["next_actions"]][:2] == ["use_result", "upload_natural_light_photo"]

    assert glasses["status"] == "analyzed"
    assert glasses["result_summary"]["capture"]["result_tier"] == "standard"
    assert glasses["result_summary"]["capture"]["risk_codes"] == []
    assert "face.eye_occluded" not in {item["code"] for item in glasses["decision"]["warnings"]}
    assert "vl.eye_occluded" not in {item["code"] for item in glasses["decision"]["warnings"]}

    assert bangs["status"] == "analyzed"
    assert bangs["result_summary"]["capture"]["result_tier"] == "light_note"
    assert "vl.hat_bangs" in {item["code"] for item in bangs["decision"]["warnings"]}

    assert hat["status"] == "analyzed"
    assert hat["result_summary"]["capture"]["result_tier"] == "light_note"
    assert "vl.hat_bangs" in {item["code"] for item in hat["decision"]["warnings"]}


def test_fixture_review_covers_hand_and_glasses_edge_cases() -> None:
    hand = analyze_fixture_case("real_hand_near_face")
    glare = analyze_fixture_case("real_glasses_glare")

    assert hand["status"] == "analyzed"
    assert hand["result_summary"]["capture"]["result_tier"] == "light_note"
    assert "vl.hand_near_face" in {item["code"] for item in hand["decision"]["warnings"]}
    assert "retake_photo" not in [item["code"] for item in hand["result_summary"]["next_actions"]]

    assert glare["status"] == "analyzed"
    assert glare["result_summary"]["capture"]["result_tier"] == "light_note"
    assert "vl.glasses_glare" in {item["code"] for item in glare["decision"]["warnings"]}
    assert "face.eye_occluded" not in {item["code"] for item in glare["decision"]["warnings"]}


def test_dark_eyes_without_sunglasses_are_not_blocked_as_eye_occlusion() -> None:
    path = FIXTURE_DIR / "real_dark_eyes_no_sunglasses.jpg"
    result = analyze_image_bytes(path.read_bytes(), "real_dark_eyes_no_sunglasses.jpg", save_upload=False, fixture_case=None)
    face_codes = {item["code"] for item in result["pipeline"]["face_cv"].get("issues", [])}
    warning_codes = {item["code"] for item in result["decision"].get("warnings", [])}
    blocking_codes = {item["code"] for item in result["decision"].get("blocking_errors", [])}

    assert result["status"] == "analyzed"
    assert result["result_summary"]["available"] is True
    assert "face.eye_occluded" not in face_codes
    assert "face.eye_occluded" not in warning_codes
    assert "face.eye_occluded" not in blocking_codes


def test_real_upload_uses_local_visual_risk_review_without_fixture() -> None:
    path = FIXTURE_DIR / "vl_red_lipstick.jpg"
    result = analyze_image_bytes(path.read_bytes(), "real_user_lip_color.jpg", save_upload=False, fixture_case=None)
    vl_stage = result["pipeline"]["vl_review"]

    assert result["status"] == "analyzed"
    assert vl_stage["status"] in {"pass", "warn"}
    assert vl_stage["evidence"]["source"] == "local_cv_visual_risk"
    assert "vl.not_checked" not in {item["code"] for item in vl_stage["issues"]}
    assert "mouth_redness" in vl_stage["evidence"]["scores"]


def test_local_visual_risk_review_flags_obvious_lip_color_as_soft_warning() -> None:
    image = Image.open(FIXTURE_DIR / "season_spring_bright.jpg").convert("RGB")
    draw = ImageDraw.Draw(image, "RGBA")
    draw.ellipse((370, 790, 595, 895), fill=(190, 20, 55, 210))
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=95)

    result = analyze_image_bytes(buffer.getvalue(), "real_user_lip_overlay.jpg", save_upload=False, fixture_case=None)
    warning_codes = {item["code"] for item in result["decision"]["warnings"]}

    assert result["status"] == "analyzed"
    assert "vl.lipstick" in warning_codes
    assert result["pipeline"]["vl_review"]["status"] == "warn"


def test_color_self_test_suite_passes() -> None:
    results = self_test_results()

    assert results["total"] == EXPECTED_CASE_COUNT
    assert results["failed"] == 0
    assert results["passed"] == EXPECTED_CASE_COUNT


def test_cached_self_test_results_are_qa_ready() -> None:
    results = cached_self_test_results()

    assert results["total"] == EXPECTED_CASE_COUNT
    assert results["passed"] == EXPECTED_CASE_COUNT
    assert results["failed"] == 0
    assert results["_meta"]["source"] in {"cache", "live"}
    assert results["cases"][0]["image"]
    assert results["capture_summary"]["reference_only"]["count"] >= 1
    assert results["result_tier_summary"]["standard"]["count"] >= 8
    assert results["result_tier_summary"]["light_note"]["count"] >= 1
    assert results["result_tier_summary"]["low_confidence"]["count"] >= 1
    assert results["result_tier_summary"]["retake"]["count"] == 12
    assert results["action_summary"]["retake_with_card"]["count"] >= 1
    assert results["group_summary"]["color_card"]["reference_only"] >= 1
    assert results["group_summary"]["color_card"]["light_note"] >= 1
    assert results["group_summary"]["color_card"]["low_confidence"] == 1
    assert results["group_summary"]["seasonal_gold"]["standard"] == results["group_summary"]["seasonal_gold"]["total"]
    assert results["group_summary"]["vl_risk"]["light_note"] >= 1
    assert results["group_summary"]["portrait"]["retake"] >= 1
    for group in results["group_summary"].values():
        assert group["standard"] + group["reference_only"] + group["retake"] == group["total"]
    assert results["product_metrics"]["no_card_pass_rate"]["analyzed"] >= 1
    assert results["product_metrics"]["auto_crop_success_rate"]["rate"] == 1
    assert results["product_metrics"]["soft_risk_retake_rate"]["retake"] == 0
    assert results["product_metrics"]["hard_block_rate"]["retake"] >= 1
    assert results["product_metrics"]["seasonal_accuracy"]["total"] == 8
    assert "top1_rate" in results["product_metrics"]["seasonal_accuracy"]
    assert "top2_rate" in results["product_metrics"]["seasonal_accuracy"]
    assert results["acceptance_gates"]
    assert all(gate["status"] == "pass" for gate in results["acceptance_gates"])
    assert {gate["code"] for gate in results["acceptance_gates"]} >= {"regression_pass", "no_card_pass_rate", "auto_crop_success_rate", "soft_risk_retake_rate", "hard_block_rate", "seasonal_top1_accuracy", "seasonal_top2_accuracy"}
    assert results["product_metrics"]["reference_reason_summary"]
    assert results["product_metrics"]["tier_reason_summary"]["light_note"]
    assert results["product_metrics"]["tier_reason_summary"]["low_confidence"]
    assert results["product_metrics"]["reference_reason_summary"][0]["label"]
    assert any(item["label"] == "未使用色卡校正" for item in results["product_metrics"]["reference_reason_summary"])
    assert results["acceptance_notes"]
    assert any(note["title"] == "重拍比例可接受" for note in results["acceptance_notes"])
    assert any(note["title"] == "低可信样本需重点复核" for note in results["acceptance_notes"])
    assert any(note["title"] == "轻提示样本已放行" for note in results["acceptance_notes"])
    assert "capture" in results["cases"][0]["result_summary"]
    assert "next_actions" in results["cases"][0]["result_summary"]


def test_mvp_status_summary_is_ready_for_validation_demo() -> None:
    status = mvp_status_summary()

    assert status["status"] == "ready"
    assert status["label"] == "MVP 验证通过，可继续演示"
    assert status["summary"]["total"] == EXPECTED_CASE_COUNT
    assert status["summary"]["passed"] == EXPECTED_CASE_COUNT
    assert status["summary"]["failed"] == 0
    assert status["summary"]["seasonal_top1_rate"] == 1
    assert status["summary"]["seasonal_top2_rate"] == 1
    assert status["summary"]["sampling_landmark_rate"] >= 0.9
    assert status["summary"]["sampling_landmark_count"] > 0
    assert status["summary"]["standard_count"] >= 8
    assert status["summary"]["color_card_low_confidence_count"] == 1
    assert status["failed_gates"] == []
    assert all(gate["status"] == "pass" for gate in status["gates"])
    assert status["artifact_urls"]["qa"] == "/qa"
    assert status["artifact_urls"]["rules"] == "/mvp/rules"
    assert status["artifact_urls"]["handoff"] == "/mvp/handoff"
    assert status["artifact_urls"]["pilot_guide"] == "/mvp/pilot-guide"
    assert status["artifact_urls"]["smoke_results"] == "/qa-artifacts/smoke_mvp_results.json"
    assert status["artifact_urls"]["contact_sheet"] == "/qa-artifacts/contact_sheet.jpg"
    assert status["artifact_urls"]["region_overlay_sheet"] == "/qa-artifacts/region_overlay_sheet.jpg"
    assert status["smoke"]["status"] in {"ok", "missing", "invalid"}
    assert status["smoke"]["url"] == "/qa-artifacts/smoke_mvp_results.json"
    assert len(status["demo_cases"]) >= 12
    assert [case["id"] for case in status["demo_cases"]] == [
        "season_spring_bright",
        "season_summer_light",
        "season_autumn_deep",
        "season_winter_clear",
        "card_missing",
        "card_fake_grid",
        "real_social_screenshot_auto_crop",
        "real_colorful_poster_no_card",
        "real_busy_poster_wall_no_card",
        "real_warm_indoor_light_no_card",
        "real_screen_cool_light_no_card",
        "real_clear_glasses",
        "real_bangs_forehead",
        "real_hand_near_face",
        "portrait_sunglasses",
    ]


def test_mvp_policy_rules_expose_user_intuitive_gate_matrix() -> None:
    rules = mvp_policy_rules()

    assert rules["tiers"]["hard_retake"]["status"] == "needs_retake"
    assert rules["tiers"]["light_note"]["status"] == "analyzed"
    assert rules["tiers"]["low_confidence"]["status"] == "analyzed"
    assert rules["color_card_policy"]["required_for_analysis"] is False
    assert rules["auto_crop_policy"]["enabled"] is True
    assert "face.no_face" in rules["tiers"]["hard_retake"]["issue_codes"]
    assert "card.missing" in rules["tiers"]["light_note"]["issue_codes"]
    assert "face.auto_cropped" in rules["tiers"]["light_note"]["issue_codes"]
    assert "vl.heavy_makeup" in rules["tiers"]["low_confidence"]["issue_codes"]
    assert "card.fake" in rules["tiers"]["low_confidence"]["issue_codes"]
    assert "vl.pose_side" in rules["tiers"]["low_confidence"]["issue_codes"]


def test_mvp_policy_rules_http_endpoint() -> None:
    response = client.get("/mvp/rules")

    assert response.status_code == 200
    body = response.json()
    assert body["tiers"]["light_note"]["result_tier"] == "light_note"
    assert body["color_card_policy"]["retake_rule"].startswith("单纯色卡问题不要求重拍")


def test_mvp_status_page_renders_human_readable_summary() -> None:
    html = render_mvp_status_page()

    assert "AI 色彩测试" in html
    assert "MVP 验证状态" in html
    assert "MVP 验证通过，可继续演示" in html
    assert "标准可用" in html
    assert "交接文档" in html
    assert "算法说明" in html
    assert "算法 Contract" in html
    assert "季节评估" in html
    assert "开源选型" in html
    assert "Smoke 结果" in html
    assert "最近 Smoke" in html
    assert "快速体验样本" in html
    assert "无色卡轻提示" in html
    assert "伪色卡低可信" in html
    assert "遮挡需重拍" in html
    assert "用户侧门禁" in html
    assert "必须重拍" in html
    assert "可测，轻提示" in html
    assert "可测，低可信" in html
    assert "/qa" in html
    assert "/demo" in html
    assert "/mvp/handoff" in html
    assert "/mvp/pilot-guide" in html
    assert "/mvp/algorithm" in html
    assert "/mvp/algorithm/contract" in html
    assert "/mvp/seasonal-evaluation" in html
    assert "/mvp/open-source-tech" in html
    assert "试用指南" in html
    assert "/qa-artifacts/smoke_mvp_results.json" in html
    assert "/demo?case=season_spring_bright" in html
    assert "/demo?case=season_summer_light" in html
    assert "/demo?case=season_autumn_deep" in html
    assert "/demo?case=season_winter_clear" in html
    assert "点击后会打开产品 Demo，并自动跑对应样本。" in html


def test_mvp_status_page_http_endpoint() -> None:
    response = client.get("/mvp")

    assert response.status_code == 200
    assert "AI 色彩测试" in response.text
    assert "查看 QA 面板" in response.text


def test_mvp_handoff_markdown_contains_operational_checklist() -> None:
    markdown = mvp_handoff_markdown()

    assert "AI 色彩测试 MVP 验证交接" in markdown
    assert "如何启动" in markdown
    assert "演示路径" in markdown
    assert "验收底线" in markdown
    assert "pytest -q" in markdown
    assert "OPEN_SOURCE_TECH_SELECTION.md" in markdown


def test_open_source_tech_selection_documents_replacement_strategy() -> None:
    markdown = OPEN_SOURCE_SELECTION_PATH.read_text(encoding="utf-8")

    assert "AI 色彩测试开源技术选型" in markdown
    assert "colour-checker-detection" in markdown
    assert "colour-science" in markdown
    assert "SkinToneClassifier" in markdown
    assert "不建议直接使用开源 seasonal color classifier" in markdown
    assert "`color_card_cv`" in markdown
    assert "`color_correction`" in markdown
    assert "`seasonal_result`" in markdown


def test_mvp_open_source_markdown_explains_no_mature_end_to_end_engine() -> None:
    markdown = mvp_open_source_markdown()

    assert "AI 色彩测试开源技术选型" in markdown
    assert "不建议直接引入某个开源 personal color 项目作为最终诊断引擎" in markdown
    assert "MediaPipe Face Landmarker" in markdown
    assert "`colour-checker-detection`" in markdown
    assert "`colour-science`" in markdown
    assert "`seasonal_result` 暂时保留可解释规则" in markdown


def test_mvp_open_source_http_endpoint() -> None:
    response = client.get("/mvp/open-source-tech")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert "AI 色彩测试开源技术选型" in response.text
    assert "不建议直接使用开源 seasonal color classifier" in response.text


def test_mvp_open_source_head_endpoint() -> None:
    response = client.head("/mvp/open-source-tech")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")


def test_mvp_handoff_http_endpoint() -> None:
    response = client.get("/mvp/handoff")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert "AI 色彩测试 MVP 验证交接" in response.text


def test_mvp_handoff_head_endpoint() -> None:
    response = client.head("/mvp/handoff")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")


def test_mvp_algorithm_markdown_explains_current_real_logic() -> None:
    markdown = mvp_algorithm_markdown()

    assert "AI 色彩测试算法说明" in markdown
    assert "MediaPipe Face Landmarker" in markdown
    assert "当前没有让 VL 模型直接输出春夏秋冬" in markdown
    assert "三段诊断" in markdown
    assert "24 季是派生命名" in markdown
    assert "/qa-artifacts/region_overlay_sheet.jpg" in markdown


def test_mvp_algorithm_http_endpoint() -> None:
    response = client.get("/mvp/algorithm")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert "AI 色彩测试算法说明" in response.text


def test_mvp_algorithm_contract_exposes_thresholds_and_mapping() -> None:
    contract = mvp_algorithm_contract()

    assert contract["models"]["face_landmarks"]["model"] == "MediaPipe Face Landmarker"
    assert contract["models"]["seasonal_result"]["method"] == "layered_lab_hsv_virtual_drape_ranking"
    assert contract["dimension_thresholds"]["temperature"]["warm"] == ">= 8"
    assert contract["dimension_thresholds"]["contrast"]["high"] == ">= 78"
    assert contract["season_mapping"]["season_12"]["autumn"][0]["season"] == "deep_autumn"
    assert contract["season_mapping"]["diagnosis_layers"][0]["layer"] == "temperature_test"
    assert contract["season_mapping"]["season_24"] == "{season_12}_{brightness}_{chroma}_{contrast}"
    assert contract["color_card_policy"]["required_for_analysis"] is False
    assert contract["qa_gates"]["seasonal_top2_accuracy"] == ">=85%"
    assert contract["artifacts"]["single_overlay_pattern"] == "/qa-artifacts/overlays/{case_id}.jpg"


def test_mvp_algorithm_contract_http_endpoint() -> None:
    response = client.get("/mvp/algorithm/contract")

    assert response.status_code == 200
    body = response.json()
    assert body["version"] == "2026-07-03"
    assert body["models"]["color_card_cv"]["primary"] == "colour-checker-detection segmentation"
    assert body["runtime_principles"][0] == "VL 不直接输出春夏秋冬。"


def test_mvp_seasonal_evaluation_exposes_gold_case_evidence() -> None:
    evaluation = mvp_seasonal_evaluation()
    autumn = next(case for case in evaluation["cases"] if case["id"] == "season_autumn_deep")

    assert evaluation["label"] == "季节型金标评估"
    assert evaluation["total"] == 8
    assert evaluation["top1_rate"] == 1
    assert evaluation["miss_count"] == 0
    assert autumn["expected"]["season_12"] == "deep_autumn"
    assert autumn["predicted"]["season_12"] == "deep_autumn"
    assert autumn["dimensions"]["brightness"] == "deep"
    assert autumn["feature_contrast"]["overall_contrast"] == "medium"
    assert autumn["overlay_url"] == "/qa-artifacts/overlays/season_autumn_deep.jpg"
    assert autumn["explain_url"] == "/fixtures/season_autumn_deep/explain"


def test_mvp_seasonal_evaluation_http_endpoint() -> None:
    response = client.get("/mvp/seasonal-evaluation")

    assert response.status_code == 200
    body = response.json()
    assert body["top1_rate"] == 1
    assert body["debug_links"]["algorithm_contract"] == "/mvp/algorithm/contract"
    assert body["cases"][0]["overlay_url"].startswith("/qa-artifacts/overlays/")


def test_mvp_algorithm_head_endpoint() -> None:
    response = client.head("/mvp/algorithm")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")


def test_mvp_pilot_guide_markdown_contains_trial_flow() -> None:
    markdown = mvp_pilot_guide_markdown()

    assert "AI 色彩测试 MVP 试用指南" in markdown
    assert "推荐试用顺序" in markdown
    assert "反馈格式" in markdown
    assert "real_screen_cool_light_no_card" in markdown


def test_mvp_pilot_guide_http_endpoint() -> None:
    response = client.get("/mvp/pilot-guide")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert "AI 色彩测试 MVP 试用指南" in response.text


def test_mvp_pilot_guide_head_endpoint() -> None:
    response = client.head("/mvp/pilot-guide")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")


def test_readme_summary_example_matches_standard_tier() -> None:
    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
    example_section = readme.split('"result_summary": {', 1)[1].split('"pipeline": {', 1)[0]

    assert '"title": "明亮春型"' in example_section
    assert '"quality_level": "standard"' in example_section
    assert '"result_tier": "standard"' in example_section
    assert '"result_tier_label": "标准可用"' in example_section
    assert '"risk_codes": []' in example_section
    assert '"copy_summary"' in example_section


def test_smoke_mvp_evaluators_cover_status_and_demo_cases() -> None:
    status_checks = evaluate_status_payload(mvp_status_summary())
    assert status_checks
    assert all(item["passed"] for item in status_checks)

    for case_id, tier in dict(SMOKE_CASES).items():
        checks = evaluate_case_payload(case_id, tier, analyze_fixture_case(case_id))
        assert all(item["passed"] for item in checks)
    assert all(item["passed"] for item in evaluate_demo_page(render_demo_page()))


def test_smoke_mvp_default_output_is_qa_artifact() -> None:
    assert DEFAULT_OUTPUT.name == "smoke_mvp_results.json"
    assert DEFAULT_OUTPUT.parent.name == "results"


def test_mvp_status_http_endpoint() -> None:
    response = client.get("/mvp/status")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["summary"]["total"] == EXPECTED_CASE_COUNT
    assert body["artifact_urls"]["self_test_report"] == "/qa-artifacts/self_test_report.html"
    assert body["artifact_urls"]["handoff"] == "/mvp/handoff"
    assert body["artifact_urls"]["algorithm"] == "/mvp/algorithm"
    assert body["artifact_urls"]["algorithm_contract"] == "/mvp/algorithm/contract"
    assert body["artifact_urls"]["seasonal_evaluation"] == "/mvp/seasonal-evaluation"
    assert body["artifact_urls"]["smoke_results"] == "/qa-artifacts/smoke_mvp_results.json"
    assert body["demo_cases"][0]["url"] == "/demo?case=season_spring_bright"
    assert body["demo_cases"][0]["api_url"] == "/fixtures/season_spring_bright/analyze"


def test_qa_page_has_product_acceptance_view() -> None:
    html = render_self_test_page()

    assert "产品验收视图" in html
    assert "用户侧结论" in html
    assert "下一步动作" in html
    assert "影响准确度的原因" in html
    assert "研发阶段明细" in html
    assert "标准可用" in html
    assert "可用但轻提示" in html
    assert "低可信初步" in html
    assert "只看轻提示" in html
    assert "只看低可信" in html
    assert "只看全部初步" in html
    assert "只看建议重拍" in html
    assert "只看标准可测" in html
    assert "data-filter=\"light_note\"" in html
    assert "data-filter=\"low_confidence\"" in html
    assert "productFilterCount" in html
    assert "metricStandard" in html
    assert "metricLightNote" in html
    assert "metricLowConfidence" in html
    assert "capture.risk_labels || []" in html
    assert "actionSummary" in html
    assert "关键体验指标" in html
    assert "productMetrics" in html
    assert "sampling_region_source" in html
    assert "同时使用关键点肤色" in html
    assert "验收门槛" in html
    assert "季节型金标命中率" in html
    assert "refreshArtifacts" in html
    assert "/qa/regenerate-artifacts" in html
    assert "/mvp/status" in html
    assert "/mvp" in html
    assert "查看 MVP 状态页" in html
    assert "查看 MVP 状态 JSON" in html
    assert "/mvp/rules" in html
    assert "查看门禁规则 JSON" in html
    assert "/qa-artifacts/contact_sheet.jpg" in html
    assert "/qa-artifacts/region_overlay_sheet.jpg" in html
    assert "/qa-artifacts/self_test_report.html" in html
    assert "acceptanceGates" in html
    assert "gate-card" in html
    assert "场景分布" in html
    assert "groupSummary" in html
    assert "group-meter" in html
    assert "low_confidence" in html
    assert "light_note" in html
    assert "初步结果原因" in html
    assert "reasonSummary" in html
    assert "轻提示原因" in html
    assert "低可信原因" in html
    assert "lightNoteReasonSummary" in html
    assert "lowConfidenceReasonSummary" in html
    assert "item.label || item.code" in html
    assert "acceptanceNotes" in html
    assert "productCapture" in html
    assert "result_tier_label" in html
    assert "可测，低可信" in html
    assert "可测，轻提示" in html
    assert "productActions" in html
    assert "result_summary?.next_actions" in html
    assert "singleExplain" in html
    assert "/explain" in html
    assert "renderSingleExplain" in html
    assert "查看采样图" in html


def test_qa_artifact_generators_write_expected_outputs(tmp_path, monkeypatch) -> None:
    import scripts.generate_qa_artifacts as artifacts

    monkeypatch.setattr(artifacts, "RESULTS_DIR", tmp_path)
    monkeypatch.setattr(artifacts, "SELF_TEST_REPORT", tmp_path / "self_test_report.html")
    monkeypatch.setattr(artifacts, "CONTACT_SHEET", tmp_path / "contact_sheet.jpg")
    monkeypatch.setattr(artifacts, "REGION_OVERLAY_SHEET", tmp_path / "region_overlay_sheet.jpg")
    monkeypatch.setattr(artifacts, "REGION_OVERLAY_DIR", tmp_path / "overlays")
    results = self_test_results()

    write_contact_sheet(results)
    write_region_overlay_sheet(results)
    write_report(results)

    assert (tmp_path / "contact_sheet.jpg").stat().st_size > 1000
    assert (tmp_path / "region_overlay_sheet.jpg").stat().st_size > 1000
    assert (tmp_path / "overlays" / "season_summer_light.jpg").stat().st_size > 1000
    report_html = (tmp_path / "self_test_report.html").read_text(encoding="utf-8")
    assert "季节型 Top-1" in report_html
    assert "region_overlay_sheet.jpg" in report_html
    assert "/qa-artifacts/overlays/season_summer_light.jpg" in report_html


def test_qa_artifacts_are_served_over_http() -> None:
    contact = client.get("/qa-artifacts/contact_sheet.jpg")
    overlay = client.get("/qa-artifacts/region_overlay_sheet.jpg")
    case_overlay = client.get("/qa-artifacts/overlays/season_summer_light.jpg")
    report = client.get("/qa-artifacts/self_test_report.html")

    assert contact.status_code == 200
    assert contact.headers["content-type"].startswith("image/jpeg")
    assert len(contact.content) > 1000
    assert overlay.status_code == 200
    assert overlay.headers["content-type"].startswith("image/jpeg")
    assert len(overlay.content) > 1000
    assert case_overlay.status_code == 200
    assert case_overlay.headers["content-type"].startswith("image/jpeg")
    assert len(case_overlay.content) > 1000
    assert report.status_code == 200
    assert "AI 色彩测试 MVP 自测报告" in report.text


def test_qa_artifacts_regenerate_endpoint() -> None:
    response = client.post("/qa/regenerate-artifacts")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["passed"] == EXPECTED_CASE_COUNT
    assert body["urls"]["contact_sheet"] == "/qa-artifacts/contact_sheet.jpg"
    assert body["urls"]["region_overlay_sheet"] == "/qa-artifacts/region_overlay_sheet.jpg"
    assert body["urls"]["region_overlay_dir"] == "/qa-artifacts/overlays"
    assert body["seasonal_accuracy"]["top1_rate"] == 1


def test_demo_page_uses_backend_friendly_error_suggestion() -> None:
    html = render_demo_page()

    assert "payload.decision?.user_message || payload.error?.suggestion" in html
    assert "throw payload" in html
    assert "拍摄要求参考" in html
    assert "自然光合格" in html
    assert "避免暖光" in html
    assert "避免浓妆" in html
    assert "避免冷光" not in html
    assert html.count("/demo-assets/photo-guide-") == 3
    assert ".webp" in html
    assert html.count("const esc =") == 1
    assert "function esc(value)" not in html
    assert "网络连接不稳定，照片没有传完" in html


def test_demo_page_compresses_mobile_uploads_before_cloudflare_request() -> None:
    html = render_demo_page()

    assert "const REQUEST_TIMEOUT_MS = 90000" in html
    assert "const CLIENT_MAX_UPLOAD_BYTES = 3.2 * 1024 * 1024" in html
    assert "const CLIENT_MAX_IMAGE_SIDE = 1600" in html
    assert "async function prepareUploadFile(file)" in html
    assert 'canvas.toBlob(blob =>' in html
    assert 'body.append("image", prepared.file)' in html
    assert "已自动压缩为" not in html
    assert "如果是手机实况或 HEIC 照片，可以先另存为 JPG" in html


def test_demo_page_uses_capture_summary_for_result_copy() -> None:
    html = render_demo_page()

    assert "我的selfit色彩结果" in html
    assert "结果口径：" not in html
    assert "主倾向概率：" not in html
    assert "照片可信度：" not in html
    assert "可信度说明" not in html
    assert "applyResultActions(summary.next_actions || [])" in html
    assert "retake_with_card" in html
    assert "actionPanel" in html
    assert "renderNextActions([])" in html
    assert "function toast(text)" in html
    assert 'new URLSearchParams(window.location.search).get("source") === "selfit"' in html
    assert 'id="homeBackBtn"' in html
    assert 'window.location.href = "/selfit/demo"' in html


def test_demo_page_starts_on_upload_without_sample_gallery() -> None:
    html = render_demo_page()

    assert 'showPanel("uploadPanel")' in html
    assert 'showPanel("home")' not in html
    assert "用带色卡样例体验" not in html
    assert "常见上传场景" not in html
    assert "data-case=" not in html
    assert "快速体验样本" not in html
    assert "analyzeFixture" not in html
    assert "function sampleButtonFor(caseId)" not in html
    assert 'new URLSearchParams(window.location.search).get("case")' in html
    assert "当前页面已切换为真实上传流程" in html


def test_demo_page_has_consumer_analysis_flow_without_paywall() -> None:
    html = render_demo_page()

    assert "正在定位面部特征" in html
    assert "照片可用性测试" in html
    assert "人脸定位测试" in html
    assert "季节型匹配测试" in html
    assert "analysis-checkmark" in html
    assert "scan-line" in html
    assert "startAnalysisPaletteLoop" in html
    assert "analysis-progress-list" in html
    assert "保存免费结果摘要" in html
    assert "Premium" not in html
    assert "订阅" not in html
    assert "付费" not in html
