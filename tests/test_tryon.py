from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest
from fastapi import HTTPException
from PIL import Image

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
    _extract_image_urls_from_html,
    _extract_runway_google_image,
    _extract_xhs_note_image_urls,
    _extract_xhs_note_payload,
    _extract_top_from_note_image,
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


def test_runway_google_payload_uses_two_inline_images() -> None:
    person = TRYON_MODEL_FIXTURE_DIR / "male_medium_1.png"
    garment = FIXTURE_DIR / "card_missing.jpg"

    payload = _build_runway_google_tryon_payload(person, garment, "只替换上衣。")
    parts = payload["contents"][0]["parts"]

    assert payload["generationConfig"]["responseModalities"] == ["TEXT", "IMAGE"]
    assert payload["generationConfig"]["maxOutputTokens"] == 32768
    assert payload["safetySettings"]
    assert sum(1 for part in parts if "inlineData" in part) == 2
    assert parts[0]["inlineData"]["mimeType"].startswith("image/")
    assert parts[1]["inlineData"]["data"]
    assert "试穿" in parts[2]["text"]


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
