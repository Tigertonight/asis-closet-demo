from __future__ import annotations

import io
import itertools
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

import app.closet as closet
import app.auth as auth
import app.ops as ops
import app.storage as storage
import app.tryon as tryon
from app.main import app


_phone_counter = itertools.count(1000)


def _auth_client(phone: str | None = None) -> TestClient:
    phone = phone or f"+8613800{next(_phone_counter):06d}"
    client = TestClient(app)
    start = client.post("/auth/phone/start", json={"phone": phone}).json()
    token = client.post("/auth/phone/verify", json={"phone": phone, "code": start["dev_code"]}).json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def _png_bytes(image: Image.Image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, "PNG")
    return buf.getvalue()


def _synthetic_top_image() -> Image.Image:
    image = Image.new("RGB", (720, 900), "#fffafa")
    pixels = image.load()
    for y in range(170, 770):
        width = 210 + int((y - 170) * 0.14)
        left = 360 - width // 2
        right = 360 + width // 2
        for x in range(max(0, left), min(720, right)):
            pixels[x, y] = (220, 60, 105)
    return image


def _synthetic_top_image_with_color(color: tuple[int, int, int]) -> Image.Image:
    image = Image.new("RGB", (720, 900), "#fffafa")
    pixels = image.load()
    for y in range(170, 770):
        width = 210 + int((y - 170) * 0.14)
        left = 360 - width // 2
        right = 360 + width // 2
        for x in range(max(0, left), min(720, right)):
            pixels[x, y] = color
    return image


def _create_closet_item(client: TestClient, name: str, category: str, color: tuple[int, int, int]) -> dict:
    created = client.post(
        "/closet/import/upload",
        files=[("images", (name, _png_bytes(_synthetic_top_image_with_color(color)), "image/png"))],
    ).json()["items"][0]
    if category != "top":
        patched = client.patch(f"/closet/items/{created['item_id']}", json={"category": category})
        assert patched.status_code == 200
        return patched.json()
    return created


def _use_tmp_closet(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SELFIT_GARMENT_AI_ENABLED", "0")
    monkeypatch.setattr(closet.AIGarmentCutoutProvider, "_availability_cache", {})
    monkeypatch.setattr(storage, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(auth, "AUTH_DIR", tmp_path / "outputs" / "auth")
    monkeypatch.setattr(auth, "AUTH_STORE_PATH", tmp_path / "outputs" / "auth" / "auth_store.json")
    monkeypatch.setattr(closet, "CLOSET_OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(closet, "CLOSET_SOURCE_DIR", tmp_path / "sources")
    monkeypatch.setattr(closet, "CLOSET_ITEM_DIR", tmp_path / "items")
    monkeypatch.setattr(closet, "CLOSET_MANIFEST_PATH", tmp_path / "closet_manifest.json")
    monkeypatch.setattr(closet, "OUTFIT_DIR", tmp_path / "outfits")
    monkeypatch.setattr(closet, "OUTFIT_MANIFEST_PATH", tmp_path / "outfits_manifest.json")
    monkeypatch.setattr(closet, "TRYON_RECORD_DIR", tmp_path / "tryon_records")
    monkeypatch.setattr(closet, "TRYON_RECORDS_MANIFEST_PATH", tmp_path / "tryon_records_manifest.json")


def test_closet_upload_import_creates_manifest_item(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    client = _auth_client()

    response = client.post(
        "/closet/import/upload",
        files=[("images", ("top.png", _png_bytes(_synthetic_top_image()), "image/png"))],
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "partial"
    assert data["summary"]["created"] == 1
    item = data["items"][0]
    assert item["category"] == "top"
    assert item["assets"]["cutout_path"].startswith("/user-assets/closet/")
    assert item["assets"]["preview_path"].startswith("/user-assets/closet/")
    preview_path = closet._closet_disk_path(item["assets"]["preview_path"])
    assert preview_path is not None
    assert Image.open(preview_path).size == (900, 900)
    assert (tmp_path / "closet_manifest.json").exists()


def test_closet_prefers_ai_garment_cutout_before_local_fallback(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    client = _auth_client()
    calls: list[str] = []

    def fake_extract(self, source, work_dir):
        calls.append("ai")
        return [{
            "item_id": "ai-cutout-item",
            "category": "top",
            "category_label": "上衣",
            "source": source["source"],
            "assets": {"cutout_path": "/user-assets/closet/items/ai/cutout.png", "preview_path": "/user-assets/closet/items/ai/preview.png"},
            "attributes": {"slot": "top"},
            "quality": {"status": "usable", "score": 0.88, "reasons": ["ai_garment_extraction"]},
            "pipeline": {"ai_cutout": {"provider": "runway_google_generate_content", "status": "ok"}},
        }]

    monkeypatch.setattr(closet.AIGarmentCutoutProvider, "extract_inventory", lambda *_: [])
    monkeypatch.setattr(closet.AIGarmentCutoutProvider, "extract", fake_extract)
    monkeypatch.setattr(closet.SegFormerClothesAdapter, "extract", lambda *_: [])
    monkeypatch.setattr(closet, "_extract_with_top_fallback", lambda *_: (_ for _ in ()).throw(AssertionError("should not reach legacy fallback")))

    response = client.post(
        "/closet/import/upload",
        files=[("images", ("top.png", _png_bytes(_synthetic_top_image()), "image/png"))],
    )

    assert response.status_code == 200
    data = response.json()
    assert calls == ["ai"]
    assert data["status"] == "imported"
    assert data["summary"]["fallback_used"] is False
    assert data["items"][0]["pipeline"]["ai_cutout"]["provider"] == "runway_google_generate_content"


def test_outfit_upload_splits_every_inventory_item_into_unique_transparent_pngs(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    client = _auth_client()
    candidates = [
        {"category": "top", "bbox": {"x": 0.15, "y": 0.08, "width": 0.45, "height": 0.3}, "confidence": 0.91},
        {"category": "bottom", "bbox": {"x": 0.22, "y": 0.4, "width": 0.35, "height": 0.35}, "confidence": 0.89},
        {"category": "shoes", "bbox": {"x": 0.25, "y": 0.78, "width": 0.42, "height": 0.15}, "confidence": 0.86},
    ]

    def fake_cutout(self, source_path, category=None):
        image = Image.new("RGBA", (320, 320), (255, 255, 255, 0))
        color = {"top": (120, 160, 220, 255), "bottom": (40, 60, 90, 255), "shoes": (25, 25, 25, 255)}[category]
        for y in range(55, 265):
            for x in range(75, 245):
                image.putpixel((x, y), color)
        return image

    monkeypatch.setattr(closet.AIGarmentCutoutProvider, "_provider_kind", lambda *_: "runway_google_generate_content")
    monkeypatch.setattr(closet.AIGarmentCutoutProvider, "_analyze_inventory", lambda *_: candidates)
    monkeypatch.setattr(closet.AIGarmentCutoutProvider, "_generate_cutout", fake_cutout)
    monkeypatch.setattr(closet.SegFormerClothesAdapter, "extract", lambda *_: (_ for _ in ()).throw(AssertionError("complete AI inventory should not need fallback")))

    response = client.post(
        "/closet/import/upload",
        files=[("images", ("full-outfit.png", _png_bytes(_synthetic_top_image()), "image/png"))],
    )

    assert response.status_code == 200
    data = response.json()
    assert data["summary"]["created"] == 3
    assert data["summary"]["extraction_modes"] == ["ai_inventory"]
    assert {item["category"] for item in data["items"]} == {"top", "bottom", "shoes"}
    assert len({item["item_id"] for item in data["items"]}) == 3
    for item in data["items"]:
        cutout_path = closet._closet_disk_path(item["assets"]["cutout_path"])
        assert cutout_path is not None and cutout_path.exists()
        assert Image.open(cutout_path).mode == "RGBA"
        assert closet._has_meaningful_transparency(Image.open(cutout_path)) is True
    assert client.get("/closet/items").json()["total"] == 3
    assert data["draft_outfit"]["origin"] == "auto_split"
    assert data["draft_outfit"]["draft"] is True
    assert set(data["draft_outfit"]["item_ids"]) == {item["item_id"] for item in data["items"]}
    assert client.get("/closet/outfits").json()["total"] == 1


def test_single_inventory_item_keeps_non_top_category(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    client = _auth_client()
    candidate = {"category": "dress", "bbox": {"x": 0.18, "y": 0.08, "width": 0.64, "height": 0.82}, "confidence": 0.94}

    def fake_cutout(self, source_path, category=None):
        image = Image.new("RGBA", (320, 420), (255, 255, 255, 0))
        for y in range(30, 390):
            for x in range(80, 240):
                image.putpixel((x, y), (38, 38, 42, 255))
        return image

    monkeypatch.setattr(closet.AIGarmentCutoutProvider, "_provider_kind", lambda *_: "runway_google_generate_content")
    monkeypatch.setattr(closet.AIGarmentCutoutProvider, "_analyze_inventory", lambda *_: [candidate])
    monkeypatch.setattr(closet.AIGarmentCutoutProvider, "_generate_cutout", fake_cutout)
    monkeypatch.setattr(closet.AIGarmentCutoutProvider, "extract", lambda *_: (_ for _ in ()).throw(AssertionError("single inventory must not fall back to the top analyzer")))

    response = client.post(
        "/closet/import/upload",
        files=[("images", ("qipao.png", _png_bytes(_synthetic_top_image()), "image/png"))],
    )

    assert response.status_code == 200
    data = response.json()
    assert data["items"][0]["category"] == "dress"
    assert data["items"][0]["source"]["source_group_id"]
    assert data["summary"]["extraction_modes"] == ["ai_inventory"]


def test_duplicate_source_uses_cutout_cache(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    client = _auth_client()
    calls = {"cutout": 0}
    candidate = {"category": "bag", "bbox": {"x": 0.2, "y": 0.2, "width": 0.6, "height": 0.6}, "confidence": 0.9}

    def fake_cutout(self, source_path, category=None):
        calls["cutout"] += 1
        image = Image.new("RGBA", (240, 240), (255, 255, 255, 0))
        for y in range(45, 195):
            for x in range(40, 200):
                image.putpixel((x, y), (120, 88, 60, 255))
        return image

    monkeypatch.setattr(closet.AIGarmentCutoutProvider, "_provider_kind", lambda *_: "runway_google_generate_content")
    monkeypatch.setattr(closet.AIGarmentCutoutProvider, "_analyze_inventory", lambda *_: [candidate])
    monkeypatch.setattr(closet.AIGarmentCutoutProvider, "_generate_cutout", fake_cutout)
    payload = [("images", ("bag.png", _png_bytes(_synthetic_top_image()), "image/png"))]

    first = client.post("/closet/import/upload", files=payload).json()
    second = client.post("/closet/import/upload", files=payload).json()

    assert first["summary"]["created"] == 1
    assert second["status"] == "cached"
    assert second["summary"]["created"] == 0
    assert second["summary"]["cached"] == 1
    assert second["items"][0]["item_id"] == first["items"][0]["item_id"]
    assert calls["cutout"] == 1


def test_persona_recommendation_ranks_normalized_english_tags_and_colors() -> None:
    persona = {
        "keywords": ["低装饰", "秩序感"],
        "colors": {"items": [{"name": "黑"}, {"name": "烟白"}]},
        "recommendations": {"outfits": {"summary": "简洁轮廓和清晰线条"}},
    }
    aligned = {
        "title": "quiet office",
        "items": [
            {"category": "top", "attributes": {"style_tags": ["minimal", "tailored"], "colors": ["white"]}, "quality": {"score": 0.8}},
            {"category": "bottom", "attributes": {"style_tags": ["clean lines"], "colors": ["black"]}, "quality": {"score": 0.8}},
        ],
    }
    loud = {
        "title": "party",
        "items": [
            {"category": "dress", "attributes": {"style_tags": ["bold", "romantic"], "colors": ["hot pink"]}, "quality": {"score": 0.9}},
        ],
    }

    aligned_score = closet._score_outfit_for_persona(aligned, persona)
    loud_score = closet._score_outfit_for_persona(loud, persona)

    assert aligned_score["score"] > loud_score["score"]
    assert set(aligned_score["matched_style_tokens"]) >= {"minimal", "structured"}
    assert set(aligned_score["matched_color_tokens"]) == {"black", "white"}


def test_import_job_reports_progress_and_can_retry(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    client = _auth_client()

    class ImmediateExecutor:
        def submit(self, fn, *args):
            fn(*args)

    attempts = {"count": 0}

    def flaky_import(sources, import_type, progress_callback=None, **kwargs):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("temporary provider failure")
        if progress_callback:
            progress_callback(1, 1, "extracted")
        return {"status": "imported", "items": [], "outfits": [], "summary": {"created": 0}, "message": "done"}

    monkeypatch.setattr(closet, "IMPORT_JOB_EXECUTOR", ImmediateExecutor())
    monkeypatch.setattr(closet, "_import_sources", flaky_import)
    created = client.post(
        "/closet/import/jobs",
        files=[("images", ("top.png", _png_bytes(_synthetic_top_image()), "image/png"))],
    ).json()
    failed = client.get(f"/closet/import/jobs/{created['job_id']}").json()

    assert failed["status"] == "failed"
    assert failed["error"]["retryable"] is True
    client.post(f"/closet/import/jobs/{created['job_id']}/retry")
    completed = client.get(f"/closet/import/jobs/{created['job_id']}").json()
    assert completed["status"] == "completed"
    assert completed["progress"] == 100
    assert completed["attempt"] == 2


def test_tryon_job_reports_progress_and_force_retries(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    client = _auth_client()

    class ImmediateExecutor:
        def submit(self, fn, *args):
            fn(*args)

    monkeypatch.setattr(tryon, "TRYON_JOB_EXECUTOR", ImmediateExecutor())
    monkeypatch.setattr(tryon, "_default_provider", lambda: tryon.MockTryOnProvider())
    item = client.post(
        "/closet/import/upload",
        files=[("images", ("top.png", _png_bytes(_synthetic_top_image()), "image/png"))],
    ).json()["items"][0]
    outfit = client.post("/closet/outfits", json={"item_ids": [item["item_id"]], "title": "任务试穿"}).json()
    person = (Path(__file__).resolve().parent / "fixtures" / "tryon_models" / "male_medium_1.png").read_bytes()
    created = client.post(
        "/selfit/try-on/jobs",
        files={"person_image": ("person.png", person, "image/png")},
        data={"outfit_id": outfit["outfit_id"]},
    ).json()
    completed = client.get(f"/selfit/try-on/jobs/{created['job_id']}").json()

    assert completed["status"] == "completed"
    assert completed["progress"] == 100
    assert completed["result"]["status"] == "generated"
    assert completed["result"]["record"]["outfit_id"] == outfit["outfit_id"]

    client.post(f"/selfit/try-on/jobs/{created['job_id']}/retry")
    retried = client.get(f"/selfit/try-on/jobs/{created['job_id']}").json()
    assert retried["status"] == "completed"
    assert retried["attempt"] == 2
    assert client.get("/closet/tryon-records").json()["total"] == 1


def test_tryon_job_status_polling_has_a_separate_rate_limit(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    monkeypatch.setenv("SELFIT_DISABLE_RATE_LIMIT", "0")
    monkeypatch.setenv("SELFIT_UPLOAD_RATE_LIMIT", "1")
    monkeypatch.setenv("SELFIT_TRYON_STATUS_RATE_LIMIT", "3")
    monkeypatch.setattr(ops, "_limiter", ops.InMemoryRateLimiter())
    client = _auth_client()
    missing_job = "a" * 18

    # 状态读取使用独立额度，不会消耗下方 POST 生成额度。
    for _ in range(3):
        assert client.get(f"/selfit/try-on/jobs/{missing_job}").status_code == 404
    limited_status = client.get(f"/selfit/try-on/jobs/{missing_job}")
    assert limited_status.status_code == 429
    assert limited_status.json()["error"]["code"] == "request.rate_limited"

    # 重试仍是真实生成动作，继续受上传/生成限额保护。
    assert client.post(f"/selfit/try-on/jobs/{missing_job}/retry").status_code == 404
    assert client.post(f"/selfit/try-on/jobs/{missing_job}/retry").status_code == 429


def test_selfit_app_uses_ranked_refresh_and_category_aware_item_action() -> None:
    response = TestClient(app).get("/wearwow/demo")

    assert response.status_code == 200
    assert "function loadRankedOutfits(offset = 0)" in response.text
    assert 'fetchJSON("/closet/recommendations/outfits"' in response.text
    assert "sort(() => Math.random() - 0.5)" not in response.text
    assert '["top", "bottom", "skirt", "dress"].includes(item.category) ? "试穿这件" : "搭配这件"' in response.text
    assert 'fetchJSON("/closet/import/jobs"' in response.text
    assert 'fetchJSON("/selfit/try-on/jobs"' in response.text
    assert 'id="retryImportBtn"' in response.text
    assert "function renderTryonFailure(message)" in response.text
    assert 'id="changeTryonPhotoBtn"' in response.text
    assert 'renderTryonFailure(message);' in response.text
    assert '/static/selfit/assets/splash-textile@2x.png' in response.text
    assert '/static/selfit/assets/loading-stage-25@2x.png' in response.text
    assert '/static/selfit/assets/loading-stage-${stage}@2x.png' in response.text
    assert '/static/selfit/assets/splash-signature@2x.png' in response.text
    assert 'id="tryonProgressBar"' in response.text
    assert 'function updateTryonGeneratingState(job = {})' in response.text
    assert '正在让这套穿搭更像你' in response.text
    assert '/static/animations/tryon-generating.json' not in response.text
    assert 'error.retryAfterSeconds = Math.max(0' in response.text
    assert 'if (error.status !== 429) throw error;' in response.text
    assert '试穿任务还在继续' in response.text
    assert 'const pollDelay = attempt < 5 ? 1000 : attempt < 20 ? 1500 : 2500;' in response.text


def test_inventory_candidate_normalization_deduplicates_overlapping_items() -> None:
    candidates = closet._normalize_inventory_candidates([
        {"category": "bag", "bbox": {"x": 0.6, "y": 0.2, "width": 0.25, "height": 0.3}, "confidence": 0.9},
        {"category": "bag", "bbox": {"x": 0.61, "y": 0.21, "width": 0.25, "height": 0.3}, "confidence": 0.88},
        {"category": "phone", "bbox": {"x": 0.1, "y": 0.1, "width": 0.1, "height": 0.1}, "confidence": 0.99},
    ])

    assert len(candidates) == 1
    assert candidates[0]["category"] == "bag"


def test_inventory_candidate_normalization_accepts_gemini_1000_space_and_percentages() -> None:
    candidates = closet._normalize_inventory_candidates([
        {"category": "top", "bbox": {"x": 33, "y": 164, "width": 933, "height": 688}, "confidence": 0.9},
        {"category": "bag", "bbox": {"x": 60, "y": 20, "width": 25, "height": 30}, "confidence": 0.86},
    ])

    assert candidates[0]["bbox"] == {"x": 0.033, "y": 0.164, "width": 0.933, "height": 0.688}
    assert candidates[1]["bbox"] == {"x": 0.6, "y": 0.2, "width": 0.25, "height": 0.3}


def test_inventory_candidate_normalization_rejects_household_textiles_and_clipped_garments() -> None:
    candidates = closet._normalize_inventory_candidates([
        {"category": "accessory", "bbox": {"x": 0.1, "y": 0.2, "width": 0.7, "height": 0.5}, "confidence": 0.9, "style_tags": ["bath towel", "folded"]},
        {"category": "bottom", "bbox": {"x": 0.2, "y": 0.68, "width": 0.5, "height": 0.32}, "confidence": 0.98, "fully_visible": False},
        {"category": "top", "bbox": {"x": 0.15, "y": 0.1, "width": 0.7, "height": 0.5}, "confidence": 0.96, "fully_visible": True},
    ])

    assert [candidate["category"] for candidate in candidates] == ["top"]


def test_confirmed_empty_inventory_does_not_reach_shape_fallback(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    client = _auth_client()
    monkeypatch.setattr(closet.AIGarmentCutoutProvider, "extract_inventory", lambda self, *_: (setattr(self, "last_attempt", {"status": "skipped", "reason": "no_inventory"}) or []))
    monkeypatch.setattr(closet.AIGarmentCutoutProvider, "extract", lambda *_: [])
    monkeypatch.setattr(closet.SegFormerClothesAdapter, "extract", lambda *_: (_ for _ in ()).throw(AssertionError("confirmed negative should not use segmentation")))
    monkeypatch.setattr(closet, "_extract_with_top_fallback", lambda *_: (_ for _ in ()).throw(AssertionError("confirmed negative should not use legacy fallback")))

    response = client.post(
        "/closet/import/upload",
        files=[("images", ("towel.png", _png_bytes(_synthetic_top_image()), "image/png"))],
    )

    assert response.status_code == 200
    assert response.json()["status"] == "no_items_found"
    assert response.json()["summary"]["created"] == 0


def test_ai_cutout_requires_a_transparent_result() -> None:
    opaque = Image.new("RGBA", (120, 120), (255, 255, 255, 255))
    transparent = Image.new("RGBA", (120, 120), (255, 255, 255, 0))
    for y in range(20, 100):
        for x in range(35, 85):
            transparent.putpixel((x, y), (200, 65, 108, 255))

    assert closet._has_meaningful_transparency(opaque) is False
    assert closet._has_meaningful_transparency(transparent) is True


def test_opaque_ai_cutout_is_matted_before_rejection(monkeypatch) -> None:
    opaque = Image.new("RGBA", (120, 120), (240, 240, 240, 255))
    matted = Image.new("RGBA", (120, 120), (255, 255, 255, 0))
    for y in range(20, 100):
        for x in range(35, 85):
            matted.putpixel((x, y), (70, 70, 70, 255))
    monkeypatch.setattr(closet.RembgMattingProvider, "remove_background", lambda *_: matted)

    result, status = closet._ensure_transparent_ai_cutout(opaque)

    assert status == "rembg_after_ai"
    assert closet._has_meaningful_transparency(result) is True


def test_uniform_magenta_ai_background_is_converted_to_alpha(monkeypatch) -> None:
    image = Image.new("RGBA", (160, 160), (255, 0, 255, 255))
    for y in range(25, 140):
        for x in range(45, 115):
            image.putpixel((x, y), (28, 34, 45, 255))
    monkeypatch.setattr(closet.RembgMattingProvider, "remove_background", lambda *_: (_ for _ in ()).throw(AssertionError("chroma key should run first")))

    result, status = closet._ensure_transparent_ai_cutout(image)

    assert status == "chroma_key_after_ai"
    assert result.getpixel((0, 0))[3] == 0
    assert result.getpixel((80, 80))[3] == 255
    assert result.getpixel((44, 80))[3] <= 32


def test_garment_cutout_and_tryon_share_nano_banana_model_config(monkeypatch) -> None:
    monkeypatch.delenv("TRYON_IMAGE_MODEL", raising=False)
    assert closet.AIGarmentCutoutProvider().model == "nano-banana"
    assert tryon.OpenAIImageEditTryOnProvider().model == "nano-banana"

    monkeypatch.setenv("TRYON_IMAGE_MODEL", "nano-banana-2")
    assert closet.AIGarmentCutoutProvider().model == "nano-banana-2"
    assert tryon.OpenAIImageEditTryOnProvider().model == "nano-banana-2"


def test_garment_cutout_prefers_the_existing_runway_tryon_service(monkeypatch) -> None:
    monkeypatch.setattr(closet.AIGarmentCutoutProvider, "_availability_cache", {})
    monkeypatch.setattr(closet, "_has_runway_google_provider", lambda: True)
    monkeypatch.setattr(closet, "_has_openai_compatible_provider", lambda: False)
    monkeypatch.setattr(closet, "_has_openai_image_edit_provider", lambda: False)

    provider = closet.AIGarmentCutoutProvider()

    assert provider.available() is True
    assert provider._provider_kind() == "runway_google_generate_content"
    assert provider.status() == "available_via_runway"


def test_runway_inventory_text_request_omits_rejected_text_only_modality(monkeypatch) -> None:
    captured: dict = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": '{"items": []}'}]}}]}

    def fake_post(url, *, headers, json, timeout):
        captured.update({"url": url, "headers": headers, "payload": json, "timeout": timeout})
        return FakeResponse()

    monkeypatch.setattr(closet, "_runway_google_api_key", lambda: "test-key")
    monkeypatch.setattr(closet, "_runway_google_url", lambda: "https://runway.example/v1:generateContent")
    monkeypatch.setattr(closet.httpx, "post", fake_post)

    text = closet.AIGarmentCutoutProvider()._analyze_inventory_with_runway(Image.new("RGB", (80, 100), "white"), "inventory")

    assert text == '{"items": []}'
    assert "responseModalities" not in captured["payload"]["generationConfig"]
    assert captured["headers"]["api-key"] == "test-key"


def test_closet_cutout_quality_flags_sparse_reference(tmp_path: Path) -> None:
    cutout = Image.new("RGBA", (320, 320), (255, 255, 255, 0))
    for y in range(150, 170):
        for x in range(150, 170):
            cutout.putpixel((x, y), (220, 60, 105, 255))
    cutout_path = tmp_path / "sparse_cutout.png"
    cutout.save(cutout_path)

    quality = closet._closet_cutout_quality("top", cutout_path, 0.78, ["semantic_segmentation_mask"])

    assert quality["status"] in {"review", "rejected"}
    assert "foreground_too_sparse" in quality["reasons"]


def test_closet_upload_rejects_empty_image(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    client = _auth_client()

    response = client.post(
        "/closet/import/upload",
        files=[("images", ("empty.png", b"", "image/png"))],
    )

    assert response.status_code == 400
    assert "没有收到照片" in response.json()["detail"]


def test_closet_list_patch_and_delete(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    client = _auth_client()
    created = client.post(
        "/closet/import/upload",
        files=[("images", ("top.png", _png_bytes(_synthetic_top_image()), "image/png"))],
    ).json()["items"][0]

    patched = client.patch(
        f"/closet/items/{created['item_id']}",
        json={"category": "dress", "style_tags": ["通勤"], "note": "显白", "favorite": True},
    )
    assert patched.status_code == 200
    assert patched.json()["category"] == "dress"
    assert patched.json()["favorite"] is True

    listed = client.get("/closet/items?category=dress")
    assert listed.json()["total"] == 1

    deleted = client.delete(f"/closet/items/{created['item_id']}")
    assert deleted.status_code == 200
    assert client.get("/closet/items").json()["total"] == 0


def test_closet_preferences_persist_current_model(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    client = _auth_client()

    updated = client.patch("/closet/preferences", json={"current_model_id": "male_slim_1", "current_stylist_session_id": "session_123"})

    assert updated.status_code == 200
    assert updated.json()["current_model_id"] == "male_slim_1"
    assert updated.json()["current_stylist_session_id"] == "session_123"
    preferences = client.get("/closet/preferences").json()
    assert preferences["current_model_id"] == "male_slim_1"
    assert preferences["current_stylist_session_id"] == "session_123"


def test_webpage_image_url_extraction() -> None:
    html = """
    <html>
      <head>
        <meta property="og:image" content="/cover.jpg" />
        <meta name="twitter:image" content="https://img.example.com/tw.jpg" />
      </head>
      <body><img data-src="//img.example.com/detail.webp"></body>
    </html>
    """

    urls = closet._extract_webpage_image_urls(html, "https://shop.example.com/item/1")

    assert "https://shop.example.com/cover.jpg" in urls
    assert "https://img.example.com/tw.jpg" in urls
    assert "https://img.example.com/detail.webp" in urls


def test_closet_top_item_can_enter_tryon(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    client = _auth_client()
    created = client.post(
        "/closet/import/upload",
        files=[("images", ("top.png", _png_bytes(_synthetic_top_image()), "image/png"))],
    ).json()["items"][0]
    person = (Path(__file__).resolve().parent / "fixtures" / "tryon_models" / "male_medium_1.png").read_bytes()

    response = client.post(
        "/try-on",
        data={"closet_item_id": created["item_id"]},
        files={"person_image": ("person.png", person, "image/png")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["input"]["garment_image_id"]
    assert data["status"] in {"failed", "pending", "generated", "review", "needs_retake"}
    if data["status"] == "failed":
        assert data["decision"]["user_message"]


def test_outfit_crud_uses_existing_closet_items(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    client = _auth_client()
    created = client.post(
        "/closet/import/upload",
        files=[("images", ("top.png", _png_bytes(_synthetic_top_image()), "image/png"))],
    ).json()["items"][0]

    outfit = client.post("/closet/outfits", json={"item_ids": [created["item_id"]], "title": "通勤套装"}).json()

    assert outfit["title"] == "通勤套装"
    assert outfit["items"][0]["item_id"] == created["item_id"]
    assert outfit["cover_path"].startswith("/user-assets/closet/")
    assert outfit["cover_path"].endswith("/flatlay.png")
    assert outfit["layout_snapshot_path"] == outfit["cover_path"]
    assert outfit["layout_version"] == closet.OUTFIT_LAYOUT_VERSION
    assert outfit["layout_slots"][0]["item_id"] == created["item_id"]
    assert client.get("/closet/outfits").json()["total"] == 1

    patched = client.patch(f"/closet/outfits/{outfit['outfit_id']}", json={"title": "周一通勤", "scene_tags": ["上班"], "favorite": True, "favorite_count": 99})
    assert patched.status_code == 200
    assert patched.json()["title"] == "周一通勤"
    assert patched.json()["favorite"] is True
    assert patched.json()["favorite_count"] == 99

    deleted = client.delete(f"/closet/outfits/{outfit['outfit_id']}")
    assert deleted.status_code == 200
    assert client.get("/closet/outfits").json()["total"] == 0


def test_outfit_list_reads_closet_manifest_once(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    client = _auth_client()
    top = _create_closet_item(client, "top.png", "top", (210, 80, 110))
    bottom = _create_closet_item(client, "bottom.png", "bottom", (70, 75, 85))
    created = client.post(
        "/closet/outfits",
        json={"item_ids": [top["item_id"], bottom["item_id"]], "title": "一次读取"},
    )
    assert created.status_code == 200

    original_ensure_manifest = closet._ensure_manifest
    calls = 0

    def counted_ensure_manifest() -> dict:
        nonlocal calls
        calls += 1
        return original_ensure_manifest()

    monkeypatch.setattr(closet, "_ensure_manifest", counted_ensure_manifest)
    response = client.get("/closet/outfits")

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert calls == 1


def test_outfit_from_invalid_item_is_rejected(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    client = _auth_client()

    response = client.post("/closet/outfits", json={"item_ids": ["missing"]})

    assert response.status_code == 404
    assert "没有找到这件衣物" in response.json()["detail"]


def test_outfit_layout_keeps_only_one_pair_of_shoes(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    client = _auth_client()
    first = _create_closet_item(client, "shoe-one.png", "shoes", (20, 20, 20))
    second = _create_closet_item(client, "shoe-two.png", "shoes", (80, 80, 80))

    outfit = client.post("/closet/outfits", json={"item_ids": [first["item_id"], second["item_id"]], "title": "鞋子去重"}).json()

    shoe_slots = [slot for slot in outfit["layout_slots"] if slot["slot"] == "shoes"]
    assert len(shoe_slots) == 1
    assert shoe_slots[0]["item_id"] == first["item_id"]
    assert outfit["overflow_items"][0]["item_id"] == second["item_id"]
    assert "一套搭配里先保留一件鞋子" in outfit["warnings"][0]


def test_outfit_layout_keeps_only_one_lower_body_item(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    client = _auth_client()
    pants = _create_closet_item(client, "pants.png", "bottom", (80, 120, 220))
    skirt = _create_closet_item(client, "skirt.png", "skirt", (20, 40, 80))

    outfit = client.post("/closet/outfits", json={"item_ids": [pants["item_id"], skirt["item_id"]], "title": "下装去重"}).json()

    slots = [slot["slot"] for slot in outfit["layout_slots"]]
    assert slots.count("bottom") == 1
    assert "skirt" not in slots
    assert outfit["overflow_items"][0]["item_id"] == skirt["item_id"]
    assert "裤子和裙子先保留一个" in outfit["warnings"][0]


def test_outfit_layout_dress_conflicts_with_separate_main_items(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    client = _auth_client()
    dress = _create_closet_item(client, "dress.png", "dress", (230, 220, 200))
    top = _create_closet_item(client, "top.png", "top", (220, 60, 105))
    bottom = _create_closet_item(client, "bottom.png", "bottom", (80, 120, 220))

    outfit = client.post("/closet/outfits", json={"item_ids": [dress["item_id"], top["item_id"], bottom["item_id"]], "title": "连衣装主搭"}).json()

    slots = [slot["slot"] for slot in outfit["layout_slots"]]
    assert slots == ["dress"]
    assert [item["item_id"] for item in outfit["overflow_items"]] == [top["item_id"], bottom["item_id"]]
    assert len(outfit["warnings"]) == 2


def test_outfit_list_dedupes_highly_similar_main_axis(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    client = _auth_client()
    top = _create_closet_item(client, "top.png", "top", (220, 60, 105))
    pants = _create_closet_item(client, "pants.png", "bottom", (40, 60, 90))
    shoes = _create_closet_item(client, "shoes.png", "shoes", (20, 20, 20))

    with_shoes = client.post(
        "/closet/outfits",
        json={"item_ids": [top["item_id"], pants["item_id"], shoes["item_id"]], "title": "完整套装"},
    ).json()
    without_shoes = client.post(
        "/closet/outfits",
        json={"item_ids": [top["item_id"], pants["item_id"]], "title": "重复主轴"},
    ).json()

    listed = client.get("/closet/outfits").json()

    assert listed["total"] == 1
    assert listed["outfits"][0]["outfit_id"] == with_shoes["outfit_id"]
    assert shoes["item_id"] in listed["outfits"][0]["item_ids"]
    assert listed["outfits"][0]["outfit_id"] != without_shoes["outfit_id"]


def test_tryon_from_outfit_uses_outfit_plan_pipeline(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    client = _auth_client()
    top = _create_closet_item(client, "top.png", "top", (220, 60, 105))
    bottom = _create_closet_item(client, "bottom.png", "bottom", (40, 60, 90))
    shoes = _create_closet_item(client, "shoes.png", "shoes", (20, 20, 20))
    outfit = client.post("/closet/outfits", json={"item_ids": [top["item_id"], bottom["item_id"], shoes["item_id"]], "title": "试穿套装"}).json()
    person = (Path(__file__).resolve().parent / "fixtures" / "tryon_models" / "male_medium_1.png").read_bytes()

    response = client.post(
        "/try-on/from-outfit",
        data={"outfit_id": outfit["outfit_id"], "photo_mode": "mirror_selfie"},
        files={"person_image": ("person.png", person, "image/png")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "from_outfit_plan"
    assert data["source_mode"] == "from_outfit"
    assert data["photo_mode"] == "mirror_selfie"
    assert data["outfit"]["outfit_id"] == outfit["outfit_id"]
    assert data["reference_board_path"].startswith("/user-assets/tryon/")
    assert data["missing_slots"] == []


def test_tryon_from_outfit_without_top_returns_reference_message(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    monkeypatch.setattr(tryon, "_default_provider", lambda: tryon.MockTryOnProvider())
    client = _auth_client()
    created = client.post(
        "/closet/import/upload",
        files=[("images", ("top.png", _png_bytes(_synthetic_top_image()), "image/png"))],
    ).json()["items"][0]
    client.patch(f"/closet/items/{created['item_id']}", json={"category": "shoes"})
    outfit = client.post("/closet/outfits", json={"item_ids": [created["item_id"]], "title": "鞋子参考"}).json()
    person = (Path(__file__).resolve().parent / "fixtures" / "tryon_models" / "male_medium_1.png").read_bytes()

    response = client.post(
        "/try-on/from-outfit",
        data={"outfit_id": outfit["outfit_id"]},
        files={"person_image": ("person.png", person, "image/png")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "generated"
    assert data["mode"] == "from_outfit_plan"
    assert "上装" in data["missing_slots"]
    assert "下装/裙装" in data["missing_slots"]
    assert data["pipeline"]["outfit_plan"]["status"] == "warn"


def test_tryon_from_outfit_plan_upload_endpoint(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    monkeypatch.setattr(tryon, "_default_provider", lambda: tryon.MockTryOnProvider())
    client = _auth_client()
    person = (Path(__file__).resolve().parent / "fixtures" / "tryon_models" / "male_medium_1.png").read_bytes()
    top = _png_bytes(_synthetic_top_image_with_color((220, 60, 105)))
    bottom = _png_bytes(_synthetic_top_image_with_color((40, 60, 90)))
    shoes = _png_bytes(_synthetic_top_image_with_color((20, 20, 20)))
    plan = {
        "title": "直接上传整套",
        "items": [
            {"slot": "top", "category": "top"},
            {"slot": "bottom", "category": "bottom"},
            {"slot": "shoes", "category": "shoes"},
        ],
    }

    response = client.post(
        "/try-on/from-outfit-plan",
        data={"outfit_plan": __import__("json").dumps(plan), "photo_mode": "scene_photo", "scene_label": "咖啡店"},
        files=[
            ("person_image", ("person.png", person, "image/png")),
            ("style_reference_image", ("style.png", top, "image/png")),
            ("item_images", ("top.png", top, "image/png")),
            ("item_images", ("bottom.png", bottom, "image/png")),
            ("item_images", ("shoes.png", shoes, "image/png")),
        ],
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "generated"
    assert data["mode"] == "from_outfit_plan"
    assert data["photo_mode"] == "scene_photo"
    assert data["missing_slots"] == []
    assert data["reference_board_path"].startswith("/user-assets/tryon/")


def test_selfit_tryon_from_outfit_uses_real_outfit_plan_and_records(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    monkeypatch.setattr(tryon, "_default_provider", lambda: tryon.MockTryOnProvider())
    client = _auth_client()
    top = _create_closet_item(client, "top.png", "top", (220, 60, 105))
    bottom = _create_closet_item(client, "bottom.png", "bottom", (40, 60, 90))
    shoes = _create_closet_item(client, "shoes.png", "shoes", (20, 20, 20))
    outfit = client.post(
        "/closet/outfits",
        json={"item_ids": [top["item_id"], bottom["item_id"], shoes["item_id"]], "title": "SELFIT 试穿"},
    ).json()
    person = (Path(__file__).resolve().parent / "fixtures" / "tryon_models" / "male_medium_1.png").read_bytes()

    response = client.post(
        "/selfit/try-on/from-outfit",
        data={"outfit_id": outfit["outfit_id"], "photo_mode": "standard"},
        files={"person_image": ("person.png", person, "image/png")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "generated"
    assert data["selfit_mode"] == "product_tryon"
    assert data["mode"] == "from_outfit_plan"
    assert data["record"]["mode"] == "selfit_from_outfit_plan"
    assert data["record"]["image_path"] == data["result"]["image_path"]
    listed = client.get("/closet/tryon-records").json()
    assert listed["total"] == 1
    assert listed["records"][0]["outfit_id"] == outfit["outfit_id"]


def test_selfit_tryon_allows_soft_preset_female_model(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    monkeypatch.setattr(tryon, "_default_provider", lambda: tryon.MockTryOnProvider())
    client = _auth_client()
    top = _create_closet_item(client, "top.png", "top", (220, 60, 105))
    bottom = _create_closet_item(client, "bottom.png", "bottom", (40, 60, 90))
    shoes = _create_closet_item(client, "shoes.png", "shoes", (20, 20, 20))
    outfit = client.post(
        "/closet/outfits",
        json={"item_ids": [top["item_id"], bottom["item_id"], shoes["item_id"]], "title": "柔焦预设模特"},
    ).json()
    person = (Path(__file__).resolve().parent / "fixtures" / "tryon_models" / "female_medium_1.png").read_bytes()

    response = client.post(
        "/selfit/try-on/from-outfit",
        data={"outfit_id": outfit["outfit_id"]},
        files={"person_image": ("female_medium_1.png", person, "image/png")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "generated"
    assert data["pipeline"]["input_quality"]["status"] == "warn"
    assert not data["decision"]["blocking_errors"]


def test_selfit_tryon_review_result_is_saved_to_records(monkeypatch, tmp_path: Path) -> None:
    class BackgroundChangedProvider(tryon.TryOnProvider):
        mode = "background_changed_test"

        def edit(self, person_image: Path, garment_image: Path, mask_image: Path, prompt: str, output_dir: Path) -> dict:
            person = Image.open(person_image).convert("RGB")
            output_path = output_dir / "result_background_changed.png"
            Image.new("RGB", person.size, "#050505").save(output_path, "PNG")
            return {
                "stage": tryon._stage("pass", 0.5, {"provider": self.mode, "result_path": str(output_path)}, []),
                "image_path": output_path,
            }

    _use_tmp_closet(monkeypatch, tmp_path)
    monkeypatch.setattr(tryon, "_default_provider", lambda: BackgroundChangedProvider())
    client = _auth_client()
    top = _create_closet_item(client, "top.png", "top", (220, 60, 105))
    bottom = _create_closet_item(client, "bottom.png", "bottom", (40, 60, 90))
    shoes = _create_closet_item(client, "shoes.png", "shoes", (20, 20, 20))
    outfit = client.post(
        "/closet/outfits",
        json={"item_ids": [top["item_id"], bottom["item_id"], shoes["item_id"]], "title": "需复核试穿"},
    ).json()
    person = (Path(__file__).resolve().parent / "fixtures" / "tryon_models" / "female_medium_1.png").read_bytes()

    response = client.post(
        "/selfit/try-on/from-outfit",
        data={"outfit_id": outfit["outfit_id"]},
        files={"person_image": ("female_medium_1.png", person, "image/png")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "review"
    assert data["record"]["status"] == "review"
    assert data["record"]["image_path"] == data["result"]["image_path"]
    assert data["record"]["quality_review"]["status"] == "fail"
    listed = client.get("/closet/tryon-records").json()
    assert listed["total"] == 1
    assert listed["records"][0]["record_id"] == data["record"]["record_id"]


def test_mock_tryon_from_outfit_creates_local_record(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    client = _auth_client()
    created = client.post(
        "/closet/import/upload",
        files=[("images", ("top.png", _png_bytes(_synthetic_top_image()), "image/png"))],
    ).json()["items"][0]
    outfit = client.post("/closet/outfits", json={"item_ids": [created["item_id"]], "title": "模拟试穿"}).json()

    response = client.post("/try-on/mock-from-outfit", data={"outfit_id": outfit["outfit_id"]})

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "generated"
    assert data["record"]["image_path"].startswith("/user-assets/closet/")
    assert (tmp_path / "tryon_records_manifest.json").exists()
    listed = client.get("/closet/tryon-records").json()
    assert listed["total"] == 1
    assert listed["records"][0]["outfit_id"] == outfit["outfit_id"]


def test_delete_tryon_record_hides_it_from_records(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    client = _auth_client()
    created = client.post(
        "/closet/import/upload",
        files=[("images", ("top.png", _png_bytes(_synthetic_top_image()), "image/png"))],
    ).json()["items"][0]
    outfit = client.post("/closet/outfits", json={"item_ids": [created["item_id"]], "title": "删除试穿记录"}).json()
    generated = client.post("/try-on/mock-from-outfit", data={"outfit_id": outfit["outfit_id"]}).json()

    deleted = client.delete(f"/closet/tryon-records/{generated['record']['record_id']}")

    assert deleted.status_code == 200
    assert deleted.json()["status"] == "deleted"
    listed = client.get("/closet/tryon-records").json()
    assert listed["total"] == 0


def test_selfit_demo_page_is_available(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    client = _auth_client()

    response = client.get("/selfit/demo")

    assert response.status_code == 200
    assert "selfit" in response.text
    assert "先认识自己，再决定怎么穿" in response.text
    assert "个人风格DNA" in response.text
    assert "suit 你适合的" in response.text
    assert "like 你喜欢的" in response.text
    assert "vibe 你表达的" in response.text
    assert 'data-screen="splash"' in response.text
    assert 'id="splashEnter"' in response.text
    assert "/static/selfit/assets/selfit-wordmark.svg" in response.text
    assert "/static/selfit/assets/selfit-wordmark@2x.png" not in response.text
    assert "/static/selfit/assets/suit-word@2x.png" in response.text
    assert "/static/selfit/assets/like-word@2x.png" in response.text
    assert "/static/selfit/assets/vibe-word@2x.png" in response.text
    assert "/static/selfit/assets/face-upload-guide@4x.png" in response.text
    assert "/static/selfit/assets/body-upload-guide@4x.png" in response.text
    assert 'data-screen="intro"' in response.text
    assert 'data-screen="suit-manual"' in response.text
    assert 'data-screen="loading"' in response.text
    assert "先看见真实的你" in response.text
    assert "/static/selfit/assets/loading-stage-25@2x.png" in response.text
    assert "/static/selfit/assets/splash-signature@2x.png" in response.text
    assert "Know yourself first." not in response.text
    assert 'data-screen="report"' in response.text
    assert 'data-report-summary' in response.text
    assert "/static/selfit/assets/figma-report/report-hero-reference.png" in response.text
    assert 'data-report-outfit-summary' in response.text
    assert 'data-report-advice-intro' in response.text
    assert 'class="report-signoff"' in response.text
    assert 'class="report-image-grid"' in response.text
    assert 'data-share-summary' in response.text
    assert "选择你更喜欢的风格和颜色" not in response.text
    assert "再告诉我一些你的喜好吧" in response.text
    assert "几个问题，了解你想表达的" in response.text
    assert "生成风格报告" in response.text
    assert "保存并分享" in response.text
    assert 'data-next="suit"' in response.text
    assert "去认识自己" in response.text
    assert "手机号登录" in response.text
    assert "邀请码登录" in response.text


def test_selfit_route_uses_the_same_onboarding(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    client = _auth_client()

    response = client.get("/selfit")

    assert response.status_code == 200
    assert "selfit" in response.text
    assert 'data-screen="splash"' in response.text
    assert "适我" in response.text
    assert "先认识自己，再决定怎么穿" in response.text


def test_selfit_mirror_route_exposes_the_complete_kiosk_flow(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    client = _auth_client()

    response = client.get("/selfit/mirror")

    assert response.status_code == 200
    assert 'data-state="home"' in response.text
    assert 'data-screen="gate"' not in response.text
    assert "工作人员登录" not in response.text
    assert 'data-screen="home"' in response.text
    assert 'data-screen="countdown"' in response.text
    assert 'data-screen="confirm"' in response.text
    assert 'data-screen="processing"' in response.text
    assert 'data-screen="result"' in response.text
    assert "适我，不适众" in response.text
    assert "一分钟，看见你的 16 型风格人格" in response.text
    assert "拿出手机扫码，完成型格测试" in response.text
    assert "/static/selfit/assets/icon-camera.svg" in response.text
    assert "扫码查看" in response.text
    assert "mirror-report-qr.png" in response.text
    assert "/static/selfit/mirror.js" in response.text


def test_wearwow_demo_route_keeps_selfit_compatibility(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    client = _auth_client()

    response = client.get("/wearwow/demo")

    assert response.status_code == 200
    assert "selfit" in response.text
    assert "灵感" in response.text
    assert "AI穿搭师" not in response.text
    assert 'id="loginScreen"' not in response.text
    assert 'id="loginPhone"' not in response.text
    assert 'id="loginCode"' not in response.text
    assert 'return "/selfit?entry=login"' in response.text
    assert 'id="personaCard"' not in response.text
    assert 'window.location.replace("/selfit")' in response.text
    assert 'class="app auth-pending"' in response.text
    assert 'class="closet-skeleton"' in response.text
    assert "state.dataReady = true" in response.text
    assert "loadDeferredData();" in response.text
    assert 'loading="lazy" decoding="async"><span>${item.category_label}</span>' in response.text
    assert 'class="home-intro"' not in response.text
    assert 'id="homeGreeting"' not in response.text
    assert 'id="homePersona"' not in response.text
    assert "今天，也穿得更像自己" not in response.text
    assert "从这里开始" not in response.text
    assert 'outfit-canvas" data-preview-image' not in response.text
    assert "today-art image-preview-button" not in response.text
    assert 'class="model-chip" data-preview-image' not in response.text
    assert 'data-profile-outfit="${item.id}"' in response.text
    assert 'closet-img" data-preview-image' not in response.text
    assert 'data-open-item="${item.item_id}"' in response.text
    assert 'data-detail-item="${item.item_id}" data-preview-image' not in response.text
    assert '`${reportUrl}&from=app-profile`' in response.text
    assert '["home", "ai", "closet", "me"].includes(requestedTab)' in response.text
    assert 'function syncTabURL(tab, historyMode = "replace")' in response.text
    assert 'setTab(btn.dataset.tab, { historyMode: "push" })' in response.text
    assert 'id="filterBtn"' not in response.text
    assert 'id="settingsBtn"' not in response.text
    assert 'id="floatingMatch" class="closet-compose" type="button">开始搭配' in response.text
    assert 'id="importReviewSheet"' in response.text
    assert 'id="importReviewGrid"' in response.text
    assert 'data-import-category="${item.item_id}"' in response.text
    assert 'data-import-remove="${item.item_id}"' in response.text
    assert 'class="closet-card-label"' in response.text
    assert 'loading="lazy" decoding="async"' in response.text
    assert 'data-match="${item.item_id}"' not in response.text
    assert response.text.count('id="detailItemsSection"') == 1
    assert "function smartItemRecommendations(anchor, limit = 6)" in response.text
    assert 'id="detailItemsTitle">穿搭单品' in response.text

    styles = client.get("/static/selfit-app/app.css")
    assert styles.status_code == 200
    assert ".closet-top {\n  position: sticky;" in styles.text
    assert ".category-row {\n  position: sticky;" in styles.text
    assert "transform: scale(1.16);" not in styles.text
    assert ".recommendation-tile small" in styles.text
