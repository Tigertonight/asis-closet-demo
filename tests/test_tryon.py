from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest
from fastapi import HTTPException
from PIL import Image
import app.tryon as tryon

from app.tryon import (
    TRYON_OUTPUT_DIR,
    TRYON_MODEL_FIXTURE_DIR,
    FashionItemDetector,
    GarmentAnalyzer,
    MockTryOnProvider,
    RunwayGoogleTryOnProvider,
    StaticGarmentAnalysisProvider,
    get_codex_bridge_job,
    _build_runway_google_tryon_payload,
    _detect_person,
    _extract_image_urls_from_html,
    _extract_runway_google_image,
    _extract_xhs_note_image_urls,
    _extract_xhs_note_payload,
    _extract_top_from_note_image,
    _fit_image_to_reference_canvas,
    _generate_upper_body_mask,
    _review_tryon_quality,
    _build_inspiration_style_context,
    _build_inspiration_tryon_prompt,
    _build_inspiration_reference_sheet,
    _build_outfit_reference_board,
    _build_outfit_tryon_prompt,
    _public_xhs_note,
    _read_upload_image,
    _runway_google_error_summary,
    run_try_on,
    run_try_on_from_inspiration,
    run_try_on_from_outfit_plan,
    tryon_capabilities,
)


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "images"


def _load_upload(path: Path, role: str) -> dict:
    return _read_upload_image(path.read_bytes(), path.name, role)


def _png_bytes(image: Image.Image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, "PNG")
    return buf.getvalue()


def _synthetic_top_image() -> Image.Image:
    image = Image.new("RGB", (720, 900), "#f7f2f4")
    pixels = image.load()
    for y in range(180, 760):
        width = 210 + int((y - 180) * 0.12)
        left = 360 - width // 2
        right = 360 + width // 2
        for x in range(max(0, left), min(720, right)):
            pixels[x, y] = (220, 60, 105)
    return image


def test_tryon_mock_pipeline_generates_result_and_mask() -> None:
    person = _load_upload(FIXTURE_DIR / "season_spring_bright.jpg", "person_test")
    garment = _load_upload(FIXTURE_DIR / "card_missing.jpg", "garment_test")

    result = run_try_on(person, garment, MockTryOnProvider())

    assert result["status"] == "generated"
    assert result["garment"]["category"] == "top"
    assert result["pipeline"]["image_edit"]["evidence"]["provider"] == "local_mock"
    edit_contract = result["pipeline"]["edit_contract"]["evidence"]
    assert edit_contract["strategy"] == "strong_image_editor_with_lightweight_mask"
    assert edit_contract["model_profile"] == "nano_banana_compatible"
    assert edit_contract["preprocessing"]["level"] == "lightweight"
    assert edit_contract["mask"]["editable"] == "transparent_or_black_alpha_lt_128"
    assert "protected_region_difference" in edit_contract["post_quality_checks"]
    assert result["model_plan"]["validation"]
    assert result["model_plan"]["production"]
    assert result["result"]["image_path"].startswith("/user-assets/tryon/")
    assert result["result"]["mask_path"].startswith("/user-assets/tryon/")


def test_tryon_default_medium_male_model_is_not_blocked_as_blurry() -> None:
    person = _load_upload(TRYON_MODEL_FIXTURE_DIR / "male_medium_1.png", "person_test")
    garment = _load_upload(FIXTURE_DIR / "card_missing.jpg", "garment_test")

    result = run_try_on(person, garment, MockTryOnProvider())

    assert result["status"] == "generated"
    assert result["pipeline"]["input_quality"]["status"] in {"pass", "warn"}
    assert not any(issue["code"] == "person.blurry" for issue in result["decision"]["blocking_errors"])


def test_tryon_from_inspiration_skips_local_garment_gate() -> None:
    person = _load_upload(TRYON_MODEL_FIXTURE_DIR / "male_medium_1.png", "person_test")
    inspiration = _load_upload(FIXTURE_DIR / "xhs_low_quality_video_cover.jpg", "inspiration_test")

    result = run_try_on_from_inspiration(person, inspiration, MockTryOnProvider())

    assert result["mode"] == "from_inspiration"
    assert result["pipeline"]["garment_analysis"]["status"] == "pass"
    assert result["pipeline"]["edit_contract"]["evidence"]["mode"] == "upper_body_inspiration"
    assert result["pipeline"]["garment_analysis"]["evidence"]["skipped_local_garment_gate"] is True
    assert not any(issue["code"] == "garment.no_top" for issue in result["decision"]["blocking_errors"])
    assert result["pipeline"]["image_edit"]["evidence"]["provider"] == "local_mock"


def test_inspiration_prompt_uses_structured_context_without_case_hardcoding() -> None:
    style_context = {
        "note": {"title": "早春条纹针织穿搭", "desc": "宽松长袖条纹套头衫，里面叠穿白衬衫。"},
        "target_attributes": {
            "sleeve": "long_sleeve",
            "fit": "loose",
            "neckline": "collar",
            "colors": ["navy", "green"],
            "patterns": ["striped"],
        },
    }

    prompt = _build_inspiration_tryon_prompt(__import__("json").dumps(style_context, ensure_ascii=False))

    assert "Structured note and multi-image context" in prompt
    assert "multi-image reference board" in prompt
    assert "long_sleeve" in prompt
    assert "If the context says or implies long sleeves" in prompt
    assert "Do not infer a different garment type from generic fashion priors" in prompt


def test_inspiration_reference_sheet_filters_non_photo_cards() -> None:
    work_dir = TRYON_OUTPUT_DIR / "test_inspiration_reference_sheet"
    work_dir.mkdir(parents=True, exist_ok=True)
    red_card = Image.new("RGB", (720, 900), "#ff2442")
    photo = Image.open(FIXTURE_DIR / "season_spring_bright.jpg").convert("RGB")

    sheet_path = _build_inspiration_reference_sheet(
        [
            {"image": red_card},
            {"image": photo},
        ],
        work_dir,
    )

    assert sheet_path is not None
    assert sheet_path.exists()
    sheet = Image.open(sheet_path).convert("RGB")
    assert sheet.width >= 420
    assert sheet.height >= 560


def test_outfit_reference_board_and_prompt_cover_multi_item_context() -> None:
    work_dir = TRYON_OUTPUT_DIR / "test_outfit_reference_board"
    work_dir.mkdir(parents=True, exist_ok=True)
    top = _load_upload(FIXTURE_DIR / "card_missing.jpg", "top_test")
    bottom = _load_upload(FIXTURE_DIR / "season_summer_light.jpg", "bottom_test")
    shoes = _load_upload(FIXTURE_DIR / "season_spring_bright.jpg", "shoes_test")
    plan = {
        "title": "通勤整套",
        "model_photo_mode": "mirror_selfie",
        "scene_label": "通勤",
        "style_reference": {"image_id": "style", "image_path": str(top["saved_path"])},
        "items": [
            {"slot": "top", "category": "top", "image_path": str(top["saved_path"]), "wearing_instruction": "穿在上半身"},
            {"slot": "bottom", "category": "bottom", "image_path": str(bottom["saved_path"]), "wearing_instruction": "穿在下半身"},
            {"slot": "shoes", "category": "shoes", "image_path": str(shoes["saved_path"]), "wearing_instruction": "穿在双脚"},
            {"slot": "bag", "category": "bag", "image_path": str(shoes["saved_path"]), "wearing_instruction": "手提包挂在前臂"},
        ],
    }

    board_path = _build_outfit_reference_board(plan, work_dir / "board.png")
    prompt = _build_outfit_tryon_prompt({
        "photo_mode": "mirror_selfie",
        "scene_label": "通勤",
        "items": plan["items"],
    })

    assert board_path.exists()
    board = Image.open(board_path)
    assert board.size == (1200, 900)
    assert "labeled outfit reference board" in prompt
    assert "mirror selfie perspective" in prompt
    assert "upper items on upper body" in prompt
    assert "shoes only if feet are visible" in prompt
    assert "Do not zoom out or complete missing body parts" in prompt
    assert "handbag should be held by a visible hand or hang from the forearm" in prompt
    assert "Do not render floating, detached, pasted-on, or impossible bags" in prompt


def test_run_tryon_from_outfit_plan_missing_slots_are_non_blocking() -> None:
    person = _load_upload(TRYON_MODEL_FIXTURE_DIR / "male_medium_1.png", "person_test")
    top = _load_upload(FIXTURE_DIR / "card_missing.jpg", "top_test")
    plan = {
        "title": "缺少下装鞋",
        "model_photo_mode": "standard",
        "style_reference": {"image_id": "style", "image_path": str(top["saved_path"])},
        "items": [
            {"slot": "top", "category": "top", "image_path": str(top["saved_path"])},
        ],
    }

    result = run_try_on_from_outfit_plan(person, plan, MockTryOnProvider())

    assert result["mode"] == "from_outfit_plan"
    assert result["status"] == "generated"
    assert result["pipeline"]["edit_contract"]["evidence"]["mode"] == "outfit_body"
    assert result["pipeline"]["edit_contract"]["evidence"]["preprocessing"]["no_heavy_human_parsing_required"] is True
    assert "下装/裙装" in result["missing_slots"]
    assert "鞋子" in result["missing_slots"]
    assert result["pipeline"]["outfit_plan"]["status"] == "warn"
    assert any(issue["code"] == "outfit.missing_reference_slots" for issue in result["decision"]["warnings"])


def test_run_tryon_from_outfit_plan_top_and_shoes_only_reports_lower_missing() -> None:
    person = _load_upload(TRYON_MODEL_FIXTURE_DIR / "male_medium_1.png", "person_test")
    top = _load_upload(FIXTURE_DIR / "card_missing.jpg", "top_test")
    shoes = _load_upload(FIXTURE_DIR / "season_spring_bright.jpg", "shoes_test")
    plan = {
        "title": "上衣加鞋子",
        "model_photo_mode": "standard",
        "style_reference": {"image_id": "style", "image_path": str(top["saved_path"])},
        "items": [
            {"slot": "top", "category": "top", "image_path": str(top["saved_path"])},
            {"slot": "shoes", "category": "shoes", "image_path": str(shoes["saved_path"])},
        ],
    }

    result = run_try_on_from_outfit_plan(person, plan, MockTryOnProvider())

    assert result["status"] == "generated"
    assert result["missing_slots"] == ["下装/裙装"]
    assert result["pipeline"]["outfit_plan"]["status"] == "warn"


def test_run_tryon_from_outfit_plan_relaxes_missed_face_for_ai_provider() -> None:
    rng = np.random.default_rng(123)
    scenic = Image.fromarray(rng.integers(80, 220, size=(1100, 800, 3), dtype=np.uint8), "RGB")
    person = _read_upload_image(_png_bytes(scenic), "scenic_no_local_face.png", "person_test")
    top = _load_upload(FIXTURE_DIR / "card_missing.jpg", "top_test")
    plan = {
        "title": "生活照试穿",
        "model_photo_mode": "standard",
        "style_reference": {"image_id": "style", "image_path": str(top["saved_path"])},
        "items": [
            {"slot": "top", "category": "top", "image_path": str(top["saved_path"])},
        ],
    }

    result = run_try_on_from_outfit_plan(person, plan, MockTryOnProvider())

    assert result["status"] == "generated"
    assert result["pipeline"]["person_detection"]["status"] == "warn"
    assert result["pipeline"]["person_detection"]["evidence"]["fallback"] == "ai_tryon_identity_preserve"
    assert not any(issue["code"] == "person.no_face" for issue in result["decision"]["blocking_errors"])


def test_run_tryon_from_outfit_plan_generates_with_mock_provider() -> None:
    person = _load_upload(TRYON_MODEL_FIXTURE_DIR / "male_medium_1.png", "person_test")
    top = _load_upload(FIXTURE_DIR / "card_missing.jpg", "top_test")
    bottom = _load_upload(FIXTURE_DIR / "season_summer_light.jpg", "bottom_test")
    shoes = _load_upload(FIXTURE_DIR / "season_spring_bright.jpg", "shoes_test")
    plan = {
        "title": "整套试穿",
        "model_photo_mode": "face_covered",
        "style_reference": {"image_id": "style", "image_path": str(top["saved_path"])},
        "items": [
            {"slot": "top", "category": "top", "image_path": str(top["saved_path"])},
            {"slot": "bottom", "category": "bottom", "image_path": str(bottom["saved_path"])},
            {"slot": "shoes", "category": "shoes", "image_path": str(shoes["saved_path"])},
        ],
    }

    result = run_try_on_from_outfit_plan(person, plan, MockTryOnProvider())

    assert result["status"] == "generated"
    assert result["mode"] == "from_outfit_plan"
    assert result["generation_strategy"] == "single_step_reference_board"
    assert result["photo_mode"] == "face_covered"
    assert result["reference_board_path"].startswith("/user-assets/tryon/")
    assert result["result"]["mask_path"].startswith("/user-assets/tryon/")


def test_outfit_semantic_review_fails_when_required_slot_is_missing() -> None:
    expected = [
        {"slot": "top", "category": "top"},
        {"slot": "bag", "category": "bag"},
    ]
    stage = tryon._semantic_outfit_stage(
        {
            "items": [
                {"slot": "top", "status": "matched", "confidence": 0.92},
                {"slot": "bag", "status": "missing", "confidence": 0.84},
            ],
            "overall_confidence": 0.86,
        },
        expected,
        "static_test",
    )

    assert stage["status"] == "fail"
    assert stage["evidence"]["verified"] is True
    assert any(issue["code"] == "semantic.bag.missing" for issue in stage["issues"])


def test_outfit_tryon_reuses_completed_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    person = _load_upload(TRYON_MODEL_FIXTURE_DIR / "male_medium_1.png", "person_cache")
    top = _load_upload(FIXTURE_DIR / "card_missing.jpg", "top_cache")
    plan = {
        "title": "cache outfit",
        "model_photo_mode": "standard",
        "style_reference": {"image_id": "style-cache", "image_path": str(top["saved_path"])},
        "items": [{"slot": "top", "category": "top", "image_path": str(top["saved_path"])}],
    }

    class CountingProvider(MockTryOnProvider):
        def __init__(self):
            self.calls = 0

        def edit(self, *args, **kwargs):
            self.calls += 1
            return super().edit(*args, **kwargs)

    provider = CountingProvider()
    monkeypatch.setattr(tryon, "_tryon_output_dir", lambda: tmp_path)
    monkeypatch.setattr(tryon, "_default_provider", lambda: provider)
    monkeypatch.setattr(tryon, "_review_outfit_semantics", lambda *_: tryon._stage("pass", 0.9, {"verified": True, "slot_results": []}, []))

    first = run_try_on_from_outfit_plan(person, plan)
    second = run_try_on_from_outfit_plan(person, plan)

    assert first["status"] == "generated"
    assert first.get("cached") is not True
    assert second["cached"] is True
    assert second["tryon_id"] == first["tryon_id"]
    assert provider.calls == 1


def test_tryon_default_provider_fails_without_real_image_edit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("TRYON_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("TRYON_ENABLE_PI_AGENT_CODE_WORKER", raising=False)
    monkeypatch.setattr("app.tryon._has_runway_google_provider", lambda: False)
    monkeypatch.setattr("app.tryon._has_openai_image_edit_provider", lambda: False)
    person = _load_upload(TRYON_MODEL_FIXTURE_DIR / "male_medium_1.png", "person_test")
    garment = _load_upload(FIXTURE_DIR / "card_missing.jpg", "garment_test")

    result = run_try_on(person, garment)

    assert result["status"] == "failed"
    assert result["result"]["image_path"] is None
    assert result["pipeline"]["image_edit"]["evidence"]["provider"] == "ai_image_edit_unavailable"
    assert result["decision"]["user_message"] == "当前还没有接入真实 AI 试穿模型，暂时不能生成可信试穿图。"


def test_tryon_pi_agent_code_worker_is_explicitly_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("TRYON_OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("TRYON_ENABLE_PI_AGENT_CODE_WORKER", "1")
    monkeypatch.setattr("app.tryon._has_runway_google_provider", lambda: False)
    monkeypatch.setattr("app.tryon._has_openai_image_edit_provider", lambda: False)
    monkeypatch.setattr("app.tryon._start_pi_agent_tryon_worker", lambda job_id: True)
    person = _load_upload(TRYON_MODEL_FIXTURE_DIR / "male_medium_1.png", "person_test")
    garment = _load_upload(FIXTURE_DIR / "card_missing.jpg", "garment_test")

    result = run_try_on(person, garment)

    assert result["status"] == "pending"
    assert result["pipeline"]["image_edit"]["evidence"]["provider"] == "pi_agent_worker"
    assert result["result"]["bridge_job_id"]
    bridge_job = get_codex_bridge_job(result["result"]["bridge_job_id"])
    assert bridge_job["status"] in {"pending", "running", "completed", "failed"}
    assert "Pi/Diga Agent worker" in " ".join(bridge_job["instructions"])


def test_garment_analyzer_accepts_structured_vlm_result() -> None:
    analyzer = GarmentAnalyzer(StaticGarmentAnalysisProvider({
        "has_top": True,
        "category": "top",
        "colors": ["red", "white"],
        "material": ["cotton"],
        "fit": "regular",
        "sleeve": "short_sleeve",
        "neckline": "crew",
        "pattern": "printed",
        "details": ["front graphic"],
        "style_tags": ["casual"],
        "source_type": "single_garment",
        "bbox": {"x": 0.2, "y": 0.1, "width": 0.6, "height": 0.7},
        "confidence": 0.91,
        "reason": "clear top",
    }))

    stage = analyzer.analyze(_synthetic_top_image())

    assert stage["status"] == "pass"
    assert stage["evidence"]["provider"] == "static_test"
    assert stage["evidence"]["has_top"] is True
    assert stage["evidence"]["garment"]["neckline"] == "crew"
    assert stage["evidence"]["garment"]["bbox"]["width"] == 0.6


def test_tryon_mask_uses_transparent_area_for_upper_body_editing() -> None:
    person = _load_upload(FIXTURE_DIR / "season_spring_bright.jpg", "person_test")
    garment = _load_upload(FIXTURE_DIR / "card_missing.jpg", "garment_test")

    result = run_try_on(person, garment, MockTryOnProvider())
    mask_path = result["pipeline"]["upper_body_mask"]["evidence"]["mask_path"]
    mask = Image.open(mask_path).convert("RGBA")
    alpha = np.array(mask.getchannel("A"))

    assert mask.size == person["image"].size
    assert np.any(alpha == 0)
    assert np.any(alpha == 255)
    assert result["pipeline"]["upper_body_mask"]["evidence"]["editable_pixels"] > 0
    assert result["pipeline"]["upper_body_mask"]["evidence"]["protected_pixels"] > 0
    assert result["pipeline"]["upper_body_mask"]["evidence"]["mask_semantics"]["protected"] == "opaque_or_white_alpha_gte_220"


def test_tryon_quality_fails_when_mask_protected_region_changes() -> None:
    person = _load_upload(FIXTURE_DIR / "season_spring_bright.jpg", "person_test")
    person_stage = _detect_person(person["image"])
    work_dir = TRYON_OUTPUT_DIR / "test_mask_protected_region"
    work_dir.mkdir(parents=True, exist_ok=True)
    mask_stage = _generate_upper_body_mask(
        person["image"],
        person_stage,
        work_dir / "mask.png",
    )
    mask_alpha = np.array(Image.open(mask_stage["evidence"]["mask_path"]).convert("RGBA").getchannel("A"))
    result_pixels = np.array(person["image"].convert("RGB"))
    result_pixels[mask_alpha > 220] = (0, 0, 0)
    result = Image.fromarray(result_pixels, "RGB")
    result_path = work_dir / "bad_result.png"
    result.save(result_path)

    review = _review_tryon_quality(person["image"], result_path, person_stage, Path(mask_stage["evidence"]["mask_path"]))

    assert review["status"] == "fail"
    assert review["evidence"]["mask_contract"] == "fail_if_protected_face_or_background_changes"
    assert any(issue["code"] == "quality.background_changed" for issue in review["issues"])


def test_tryon_blocks_when_person_image_has_no_face() -> None:
    rng = np.random.default_rng(42)
    noisy = rng.integers(60, 220, size=(900, 900, 3), dtype=np.uint8)
    blank = Image.fromarray(noisy)
    garment_img = Image.new("RGB", (500, 500), "red")
    person = _read_upload_image(_png_bytes(blank), "blank.png", "person_test")
    garment = _read_upload_image(_png_bytes(garment_img), "garment_test.png", "garment_test")

    result = run_try_on(person, garment, MockTryOnProvider())

    assert result["status"] == "needs_retake"
    assert result["pipeline"]["person_detection"]["status"] == "fail"
    assert any(issue["code"] == "person.no_face" for issue in result["decision"]["blocking_errors"])
    assert result["result"]["image_path"] is None


def test_lower_face_like_prop_does_not_block_primary_subject() -> None:
    faces = [
        {"box": {"x": 293, "y": 372, "width": 214, "height": 214}, "area_ratio": 0.0291},
        {"box": {"x": 162, "y": 1183, "width": 242, "height": 242}, "area_ratio": 0.0372},
    ]

    ignored = tryon._lower_face_like_props(faces, 1846)

    assert ignored == [faces[1]]


def test_second_face_at_primary_height_still_fails_closed() -> None:
    faces = [
        {"box": {"x": 120, "y": 170, "width": 150, "height": 150}, "area_ratio": 0.03},
        {"box": {"x": 520, "y": 190, "width": 148, "height": 148}, "area_ratio": 0.029},
    ]

    assert tryon._lower_face_like_props(faces, 1000) == []


def test_outfit_body_coverage_skips_hidden_shoes_without_blocking_visible_top() -> None:
    image = Image.new("RGB", (852, 1846), "white")
    person_stage = {
        "status": "warn",
        "evidence": {"primary_face": {"box": {"x": 293, "y": 372, "width": 214, "height": 214}}},
    }

    shoes = tryon._outfit_body_coverage_stage(image, person_stage, {"items": [{"slot": "top"}, {"slot": "shoes"}]})
    top_only = tryon._outfit_body_coverage_stage(image, person_stage, {"items": [{"slot": "top"}]})

    effective = tryon._visible_outfit_plan({"items": [{"item_id": "top", "slot": "top"}, {"item_id": "shoes", "slot": "shoes"}]}, shoes)

    assert shoes["status"] == "warn"
    assert shoes["issues"][0]["code"] == "person.hidden_slots_skipped"
    assert shoes["evidence"]["skipped_slots"] == ["shoes"]
    assert [item["item_id"] for item in effective["items"]] == ["top"]
    assert top_only["status"] == "pass"


def test_outfit_generation_runs_clothing_before_accessories(tmp_path: Path) -> None:
    person = _load_upload(TRYON_MODEL_FIXTURE_DIR / "male_medium_1.png", "person_test")
    detection = _detect_person(person["image"])
    item_path = str(FIXTURE_DIR / "season_spring_bright.jpg")
    plan = {
        "title": "分阶段试穿",
        "model_photo_mode": "standard",
        "style_reference": {"image_path": item_path},
        "items": [
            {"item_id": "top", "slot": "top", "category": "top", "image_path": item_path},
            {"item_id": "skirt", "slot": "skirt", "category": "skirt", "image_path": item_path},
            {"item_id": "bag", "slot": "bag", "category": "bag", "image_path": item_path},
            {"item_id": "hat", "slot": "accessory", "category": "accessory", "category_label": "奶油贝雷帽", "image_path": item_path},
        ],
    }

    class RecordingProvider:
        mode = "recording"

        def __init__(self):
            self.calls = []

        def edit(self, person_image, garment_image, mask_image, prompt, output_dir):
            self.calls.append({"person": person_image, "mask": mask_image, "prompt": prompt})
            result_path = output_dir / "result.png"
            Image.open(person_image).convert("RGB").save(result_path)
            return {"stage": tryon._stage("pass", 0.9, {"provider": self.mode}, []), "image_path": result_path}

    provider = RecordingProvider()
    result = tryon._run_staged_outfit_edit(provider, person["saved_path"], plan, detection, tmp_path)

    assert result["stage"]["status"] == "pass"
    assert [stage["name"] for stage in result["stage"]["evidence"]["stages"]] == ["visible_clothing", "visible_accessories"]
    assert result["stage"]["evidence"]["stages"][0]["item_ids"] == ["top", "skirt"]
    assert result["stage"]["evidence"]["stages"][1]["item_ids"] == ["bag", "hat"]
    assert len(provider.calls) == 2


def test_head_accessory_mask_opens_hat_region_but_protects_face(tmp_path: Path) -> None:
    image = Image.new("RGB", (852, 1846), "white")
    person_stage = {
        "status": "pass",
        "evidence": {"primary_face": {"box": {"x": 293, "y": 372, "width": 214, "height": 214}}},
    }
    mask = tryon._generate_outfit_group_mask(
        image,
        person_stage,
        [{"slot": "accessory", "category_label": "奶油贝雷帽"}],
        tmp_path / "hat_mask.png",
    )
    alpha = np.array(Image.open(mask["evidence"]["mask_path"]).convert("RGBA").getchannel("A"))

    assert mask["status"] == "pass"
    assert mask["evidence"]["head_accessory_count"] == 1
    assert alpha[230, 400] < 220
    assert alpha[470, 400] > 220


def test_garment_upload_rejects_empty_image() -> None:
    with pytest.raises(HTTPException) as exc:
        _read_upload_image(b"", "empty.png", "garment")

    assert exc.value.status_code == 400


def test_extract_image_urls_from_xhs_html_metadata() -> None:
    html = """
    <html>
      <head><meta property="og:image" content="https://sns-webpic-qc.xhscdn.com/abc.jpg?imageView2/2/w/1080" /></head>
      <script>{"url":"https:\\/\\/sns-webpic-qc.xhscdn.com\\/def.webp?foo=1"}</script>
    </html>
    """

    urls = _extract_image_urls_from_html(html, "https://www.xiaohongshu.com/explore/demo")

    assert urls[0].startswith("https://sns-webpic-qc.xhscdn.com/abc.jpg")
    assert any("def.webp" in url for url in urls)


def test_extract_xhs_note_payload_from_note_data_image_list() -> None:
    html = """
    <script>
      window.__page = {"noteData":{"type":"normal","noteId":"abc123","title":"黑色冲锋衣",
      "desc":"试穿参考","user":{"nickname":"穿搭博主","userId":"u1"},
      "imageList":[
        {"url":"https:\\/\\/sns-webpic-qc.xhscdn.com\\/first.jpg!h5_1080jpg"},
        {"infoList":[{"url":"//sns-webpic-qc.xhscdn.com/second.webp?imageView2/2/w/1080"}]}
      ]}};
    </script>
    """

    note = _extract_xhs_note_payload(html)
    urls = _extract_xhs_note_image_urls(note)
    public_note = _public_xhs_note(note)

    assert note["noteId"] == "abc123"
    assert urls[0].startswith("https://sns-webpic-qc.xhscdn.com/first.jpg")
    assert urls[1].startswith("https://sns-webpic-qc.xhscdn.com/second.webp")
    assert public_note["title"] == "黑色冲锋衣"
    assert public_note["user"]["nickname"] == "穿搭博主"
    assert public_note["image_count"] == 2


def test_extract_xhs_note_payload_from_initial_state_note_map() -> None:
    html = """
    <script>
      window.__INITIAL_STATE__ = {"note":{"note_detail_map":{"xyz":{"note":{
        "note_id":"xyz","title":"蓝色衬衫","image_list":[
          {"url":"https://sns-webpic-qc.xhscdn.com/blue.png"}
        ]}}}}};
    </script>
    """

    note = _extract_xhs_note_payload(html)
    urls = _extract_xhs_note_image_urls(note)

    assert note["note_id"] == "xyz"
    assert note["title"] == "蓝色衬衫"
    assert urls == ["https://sns-webpic-qc.xhscdn.com/blue.png"]


def test_extract_top_from_note_image_creates_cutout() -> None:
    image = Image.open(FIXTURE_DIR / "season_spring_bright.jpg").convert("RGB")
    work_dir = TRYON_OUTPUT_DIR / "test_xhs_extract"
    source_path = work_dir / "source.jpg"
    work_dir.mkdir(parents=True, exist_ok=True)
    image.save(source_path)

    item = _extract_top_from_note_image(
        {"url": "https://sns-webpic-qc.xhscdn.com/source.jpg", "image": image, "source_path": source_path},
        0,
        work_dir,
    )

    assert item["has_top"] is True
    assert item["cutout_path"].startswith("/tryon-outputs/")
    cutout_disk_path = TRYON_OUTPUT_DIR / str(item["cutout_path"]).replace("/tryon-outputs/", "")
    cutout = Image.open(cutout_disk_path).convert("RGBA")
    assert cutout.width > 0
    assert cutout.height > 0
    assert np.any(np.array(cutout.getchannel("A")) == 0)
    assert item["fashion_items"]
    fashion_item = item["fashion_items"][0]
    assert fashion_item["category"] == "top"
    assert fashion_item["category_label"] == "上衣"
    assert fashion_item["clean_reference_path"] == item["cutout_path"]
    assert fashion_item["quality"]["status"] in {"usable", "review"}
    assert fashion_item["pipeline"]["clean_reference"]["provider"] == "local_crop_reference"


def test_fashion_item_detector_uses_top_mvp_contract() -> None:
    image = _synthetic_top_image()
    work_dir = TRYON_OUTPUT_DIR / "test_fashion_item_detector"
    source_path = work_dir / "source.png"
    work_dir.mkdir(parents=True, exist_ok=True)
    image.save(source_path)

    item = FashionItemDetector().detect(
        {"url": "https://sns-webpic-qc.xhscdn.com/garment.png", "image": image, "source_path": source_path},
        0,
        work_dir,
    )

    assert item["has_top"] is True
    assert item["fashion_items"][0]["category"] == "top"
    assert item["fashion_items"][0]["source"]["source_path"].startswith("/tryon-outputs/")


def test_worn_top_full_frame_reference_is_rejected_before_generation() -> None:
    image = Image.open(FIXTURE_DIR / "xhs_low_quality_video_cover.jpg").convert("RGB")
    work_dir = TRYON_OUTPUT_DIR / "test_reject_low_quality_xhs_reference"
    source_path = work_dir / "source.jpg"
    work_dir.mkdir(parents=True, exist_ok=True)
    image.save(source_path)

    item = FashionItemDetector().detect(
        {"url": "https://sns-webpic-qc.xhscdn.com/video-cover.jpg", "image": image, "source_path": source_path},
        0,
        work_dir,
    )

    assert item["fashion_items"]
    quality = item["fashion_items"][0]["quality"]
    assert quality["status"] == "rejected"
    assert "contains_person_face" in quality["reasons"] or "person_or_background_contamination" in quality["reasons"]


def test_extract_top_from_single_garment_image_without_face() -> None:
    image = _synthetic_top_image()
    work_dir = TRYON_OUTPUT_DIR / "test_single_garment_extract"
    source_path = work_dir / "source.png"
    work_dir.mkdir(parents=True, exist_ok=True)
    image.save(source_path)

    item = _extract_top_from_note_image(
        {"url": "https://sns-webpic-qc.xhscdn.com/garment.png", "image": image, "source_path": source_path},
        0,
        work_dir,
    )

    assert item["has_top"] is True
    assert item["reason"] == "single_garment_top"
    assert item["cutout_path"].startswith("/tryon-outputs/")
    assert item["crop_box"]["width"] < image.width


def test_extract_top_rejects_image_without_top() -> None:
    image = Image.new("RGB", (720, 900), "#f7f2f4")
    work_dir = TRYON_OUTPUT_DIR / "test_no_top_extract"
    source_path = work_dir / "source.png"
    work_dir.mkdir(parents=True, exist_ok=True)
    image.save(source_path)

    item = _extract_top_from_note_image(
        {"url": "https://sns-webpic-qc.xhscdn.com/blank.png", "image": image, "source_path": source_path},
        0,
        work_dir,
    )

    assert item["has_top"] is False
    assert item["reason"] == "no_top_found"
    assert item["cutout_path"] is None


def test_tryon_capabilities_reports_image_edit_pending(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("TRYON_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("TRYON_ENABLE_PI_AGENT_CODE_WORKER", raising=False)
    monkeypatch.setattr("app.tryon._openai_base_url", lambda: "http://127.0.0.1:8787/v1")
    monkeypatch.setattr("app.tryon._configured_openai_base_url", lambda: None)
    monkeypatch.setattr("app.tryon._openai_chat_or_responses_supported", lambda base_url: False)
    monkeypatch.setattr("app.tryon._openai_images_api_supported", lambda base_url: False)
    monkeypatch.setattr("app.tryon._has_runway_google_provider", lambda: False)

    capabilities = tryon_capabilities()

    assert capabilities["status"] == "ready_for_validation"
    assert capabilities["validation"]["status"] == "ready"
    assert capabilities["production"]["status"] == "image_edit_pending"
    assert capabilities["features"]["image_edit"] == "unavailable"
    assert capabilities["features"]["fashion_item_detection"] == "top_only_local_mvp"
    assert capabilities["fashion_architecture"]["mvp_categories"] == ["top", "outer", "bottom", "skirt", "dress", "shoes"]
    assert capabilities["features"]["outfit_plan_tryon"] == "single_step_reference_board"
    assert "shoes" in capabilities["fashion_architecture"]["terminal_categories"]
    assert capabilities["checks"]["openai_compatible_images_edit"] is False


def test_runway_google_payload_uses_person_garment_and_mask_images() -> None:
    person = TRYON_MODEL_FIXTURE_DIR / "male_medium_1.png"
    garment = FIXTURE_DIR / "card_missing.jpg"

    mask = TRYON_OUTPUT_DIR / "test_runway_payload_mask.png"
    Image.new("RGBA", (100, 100), (255, 255, 255, 255)).save(mask)

    payload = _build_runway_google_tryon_payload(person, garment, mask, "只替换上衣。")
    parts = payload["contents"][0]["parts"]

    assert payload["generationConfig"]["responseModalities"] == ["TEXT", "IMAGE"]
    assert payload["generationConfig"]["maxOutputTokens"] == 32768
    assert payload["safetySettings"]
    assert sum(1 for part in parts if "inlineData" in part) == 3
    assert parts[0]["inlineData"]["mimeType"].startswith("image/")
    assert parts[1]["inlineData"]["data"]
    assert parts[2]["inlineData"]["data"]
    assert "试穿" in parts[3]["text"]
    assert "Image C is the edit mask" in parts[3]["text"]
    assert "protected areas and must remain unchanged" in parts[3]["text"]
    with Image.open(person) as image:
        width, height = image.size
    assert f"Image A is {width}x{height}px" in parts[3]["text"]
    assert "same canvas aspect ratio" in parts[3]["text"]
    assert "Image A is the framing authority" in parts[3]["text"]
    assert "do not invent them" in parts[3]["text"]


def test_fit_image_to_reference_canvas_preserves_model_size() -> None:
    reference = TRYON_MODEL_FIXTURE_DIR / "female_medium_1.png"
    generated = Image.new("RGB", (1195, 896), "white")

    normalized, evidence = _fit_image_to_reference_canvas(generated, reference)

    with Image.open(reference) as image:
        assert normalized.size == image.size
    assert evidence["normalized"] is True
    assert evidence["rule"] == "center_crop_to_image_a_canvas"


def test_runway_google_extracts_inline_image() -> None:
    tiny = Image.new("RGB", (8, 8), "red")
    b64 = _png_bytes(tiny)
    response = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": "ok"},
                        {"inlineData": {"mimeType": "image/png", "data": __import__("base64").b64encode(b64).decode("ascii")}},
                    ]
                }
            }
        ]
    }

    extracted = _extract_runway_google_image(response)

    assert extracted is not None
    assert extracted[0] == "image/png"


def test_runway_google_error_summary_extracts_proxy_error() -> None:
    summary = _runway_google_error_summary({"Code": 10001, "Error": "INVALID_ARGUMENT"})

    assert summary == {"code": 10001, "error": "INVALID_ARGUMENT"}


def test_runway_google_provider_handles_missing_key() -> None:
    provider = RunwayGoogleTryOnProvider(api_key="")

    result = provider.edit(Path("person.png"), Path("garment.png"), Path("mask.png"), "prompt", TRYON_OUTPUT_DIR)

    assert result["image_path"] is None
    assert result["stage"]["status"] == "fail"
    assert result["stage"]["evidence"]["provider"] == "runway_google_generate_content"
