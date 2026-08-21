from __future__ import annotations

import base64
import html
import hashlib
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import cv2
import httpx
import numpy as np
from fastapi import HTTPException, UploadFile
from PIL import Image, ImageDraw, ImageFilter, UnidentifiedImageError

from app.storage import storage_context, user_asset_public_path


ROOT_DIR = Path(__file__).resolve().parents[1]
UPLOAD_DIR = ROOT_DIR / "uploads"
TRYON_OUTPUT_DIR = ROOT_DIR / "outputs" / "tryon"
CODEX_BRIDGE_DIR = TRYON_OUTPUT_DIR / "codex_bridge"
TRYON_MODEL_FIXTURE_DIR = ROOT_DIR / "tests" / "fixtures" / "tryon_models"
MAX_IMAGE_BYTES = 12 * 1024 * 1024
SUPPORTED_FORMATS = {"JPEG", "PNG", "WEBP"}
MIN_PERSON_EDGE = 640
MIN_GARMENT_EDGE = 360
HARD_SHARPNESS_THRESHOLD = 55
SOFT_SHARPNESS_THRESHOLD = 90
TRYON_PIPELINE_STAGES = [
    "input_quality",
    "person_detection",
    "garment_analysis",
    "upper_body_mask",
    "edit_contract",
    "image_edit",
    "quality_review",
]
XHS_ALLOWED_HOST_PARTS = ("xiaohongshu.com", "xhslink.com", "xhscdn.com")
MAX_XHS_IMAGES = 12
FASHION_ITEM_CATEGORIES = {"top", "outer", "bottom", "skirt", "dress", "shoes", "bag", "accessory"}
OUTFIT_PHOTO_MODES = {"standard", "mirror_selfie", "face_covered", "scene_photo"}
OUTFIT_REQUIRED_GROUPS = {
    "upper": {"top", "outer"},
    "lower": {"bottom", "skirt", "dress"},
    "feet": {"shoes"},
}
LOCAL_AGENT_SETTINGS_PATH = Path.home() / ".pi" / "agent" / "settings.json"
LOCAL_AGENT_MODELS_PATH = Path.home() / ".pi" / "agent" / "models.json"
TRYON_VISION_MODEL = os.getenv("TRYON_VISION_MODEL", "gpt-5.4-mini")
RUNWAY_GOOGLE_GENERATE_CONTENT_URL = "https://runway.devops.rednote.life/openai/google/v1:generateContent"
LOCAL_OPENAI_PROXY_CANDIDATES = ("http://127.0.0.1:8787/v1", "http://localhost:8787/v1")
HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def _upload_dir() -> Path:
    return storage_context().upload_dir


def _tryon_output_dir() -> Path:
    return storage_context().tryon_output_dir


def _codex_bridge_dir() -> Path:
    return storage_context().codex_bridge_dir


def _openai_base_url() -> str | None:
    configured = _configured_openai_base_url()
    if configured:
        return configured

    for candidate in LOCAL_OPENAI_PROXY_CANDIDATES:
        try:
            response = httpx.get(f"{candidate.rstrip('/')}/models", timeout=0.6)
            if response.status_code < 500:
                return candidate.rstrip("/")
        except Exception:
            continue
    return None


def _configured_openai_base_url() -> str | None:
    configured = (
        os.getenv("TRYON_OPENAI_BASE_URL")
        or os.getenv("OPENAI_BASE_URL")
        or os.getenv("OPENAI_API_BASE")
        or os.getenv("LOCAL_OPENAI_BASE_URL")
    )
    if configured:
        return configured.rstrip("/")
    return None


def _openai_images_api_supported(base_url: str) -> bool:
    try:
        response = httpx.post(f"{base_url.rstrip('/')}/images/edits", json={}, timeout=0.8)
        return response.status_code != 404
    except Exception:
        return False


def _openai_chat_or_responses_supported(base_url: str) -> bool:
    model = _default_tryon_vision_model()
    probes = [
        ("/responses", {"model": model, "input": "Return ok."}),
        ("/chat/completions", {"model": model, "messages": [{"role": "user", "content": "Return ok."}]}),
    ]
    for path, payload in probes:
        try:
            response = httpx.post(f"{base_url.rstrip('/')}{path}", json=payload, timeout=0.8)
            if response.status_code not in {404, 500}:
                return True
        except Exception:
            continue
    return False


def _openai_api_key(base_url: str | None = None) -> str | None:
    key = os.getenv("TRYON_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("LOCAL_OPENAI_API_KEY")
    if key:
        return key
    if base_url:
        return "local-codex-proxy"
    return None


def _has_openai_compatible_provider() -> bool:
    if os.getenv("TRYON_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY"):
        return True
    if _configured_openai_base_url():
        return True
    base_url = _openai_base_url()
    return bool(base_url and _openai_chat_or_responses_supported(base_url))


def _has_openai_image_edit_provider() -> bool:
    if os.getenv("TRYON_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY"):
        return True
    if _configured_openai_base_url():
        return True
    base_url = _openai_base_url()
    return bool(base_url and _openai_images_api_supported(base_url))


def _openai_compatible_client(openai_cls: Any) -> Any:
    base_url = _openai_base_url()
    api_key = _openai_api_key(base_url)
    kwargs: dict[str, Any] = {}
    if api_key:
        kwargs["api_key"] = api_key
    if base_url:
        kwargs["base_url"] = base_url
    return openai_cls(**kwargs)


def _runway_google_url() -> str:
    return (os.getenv("TRYON_RUNWAY_GOOGLE_URL") or os.getenv("RUNWAY_GOOGLE_URL") or RUNWAY_GOOGLE_GENERATE_CONTENT_URL).strip()


def _runway_google_api_key() -> str | None:
    key = os.getenv("TRYON_RUNWAY_GOOGLE_API_KEY") or os.getenv("RUNWAY_GOOGLE_API_KEY") or os.getenv("REDNOTE_RUNWAY_API_KEY")
    if key:
        return key
    try:
        models = json.loads(LOCAL_AGENT_MODELS_PATH.read_text(encoding="utf-8"))
        provider = (models.get("providers") or {}).get("rednote-runway-local") or {}
        configured = provider.get("apiKey")
        if isinstance(configured, str) and configured.strip() and not configured.strip().startswith("$"):
            return configured.strip()
    except Exception:
        pass
    try:
        key = subprocess.check_output(
            ["security", "find-generic-password", "-a", "rednote-runway", "-s", "REDNOTE_RUNWAY_API_KEY", "-w"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return key or None
    except Exception:
        return None


def _has_runway_google_provider() -> bool:
    return bool(_runway_google_url() and _runway_google_api_key())


def _default_tryon_vision_model() -> str:
    configured = os.getenv("TRYON_VISION_MODEL")
    if configured:
        return configured
    try:
        settings = json.loads(LOCAL_AGENT_SETTINGS_PATH.read_text(encoding="utf-8"))
        model = settings.get("defaultModel")
        if isinstance(model, str) and model.strip():
            return model.strip()
    except Exception:
        pass
    return TRYON_VISION_MODEL


def image_edit_model() -> str:
    """The single model selection point for try-on and garment cutout."""
    return os.getenv("TRYON_IMAGE_MODEL") or "nano-banana"


async def analyze_garment_upload(image: UploadFile) -> dict[str, Any]:
    garment = _read_upload_image(await image.read(), image.filename, "garment")
    analysis = GarmentAnalyzer().analyze(garment["image"])
    return {
        "status": "analyzed" if analysis["status"] in {"pass", "warn"} else "failed",
        "garment_image_id": garment["image_id"],
        "input": garment["meta"],
        "garment": analysis["evidence"]["garment"],
        "pipeline": {"garment_analysis": analysis},
    }


async def run_try_on_upload(person_image: UploadFile, garment_image: UploadFile | None = None, closet_item_id: str | None = None) -> dict[str, Any]:
    person = _read_upload_image(await person_image.read(), person_image.filename, "person")
    if closet_item_id:
        from app.closet import closet_item_as_upload

        garment = closet_item_as_upload(closet_item_id)
    elif garment_image is not None:
        garment = _read_upload_image(await garment_image.read(), garment_image.filename, "garment")
    else:
        raise HTTPException(status_code=422, detail="请上传衣服图片，或选择一件衣橱里的上衣。")
    return run_try_on(person, garment)


async def run_try_on_from_inspiration_upload(person_image: UploadFile, inspiration_image: UploadFile, style_brief: str | None = None) -> dict[str, Any]:
    person = _read_upload_image(await person_image.read(), person_image.filename, "person")
    inspiration = _read_upload_image(await inspiration_image.read(), inspiration_image.filename, "inspiration")
    return run_try_on_from_inspiration(person, inspiration, style_brief=style_brief)


async def run_try_on_from_outfit_upload(
    person_image: UploadFile,
    outfit_id: str,
    photo_mode: str | None = None,
    scene_label: str | None = None,
) -> dict[str, Any]:
    from app.closet import outfit_as_tryon_plan

    outfit_plan, outfit = outfit_as_tryon_plan(outfit_id, photo_mode=photo_mode, scene_label=scene_label)
    person = _read_upload_image(await person_image.read(), person_image.filename, "person")
    result = run_try_on_from_outfit_plan(person, outfit_plan)
    result["source_mode"] = "from_outfit"
    result["outfit"] = outfit
    return result


async def run_try_on_from_outfit_plan_upload(
    person_image: UploadFile,
    style_reference_image: UploadFile,
    item_images: list[UploadFile],
    outfit_plan: str | None = None,
    photo_mode: str | None = None,
    scene_label: str | None = None,
) -> dict[str, Any]:
    person = _read_upload_image(await person_image.read(), person_image.filename, "person")
    style_reference = _read_upload_image(await style_reference_image.read(), style_reference_image.filename, "style_reference")
    uploaded_items = [
        _read_upload_image(await image.read(), image.filename, f"outfit_item_{index:02d}")
        for index, image in enumerate(item_images or [])
    ]
    plan = _build_uploaded_outfit_tryon_plan(
        style_reference=style_reference,
        uploaded_items=uploaded_items,
        outfit_plan_json=outfit_plan,
        photo_mode=photo_mode,
        scene_label=scene_label,
    )
    return run_try_on_from_outfit_plan(person, plan)


async def complete_codex_bridge_job_upload(job_id: str, result_image: UploadFile | None = None, result_path: str | None = None) -> dict[str, Any]:
    result_disk_path: Path | None = None
    if result_image is not None:
        raw = await result_image.read()
        if not raw:
            raise HTTPException(status_code=400, detail="生成结果图片为空")
        try:
            image = Image.open(io.BytesIO(raw)).convert("RGB")
            image.load()
        except UnidentifiedImageError as exc:
            raise HTTPException(status_code=400, detail="无法识别生成结果图片") from exc
        job = _read_codex_bridge_job(job_id)
        result_disk_path = Path(job["result"]["target_path"])
        result_disk_path.parent.mkdir(parents=True, exist_ok=True)
        _save_png_atomically(image, result_disk_path)
    elif result_path:
        result_disk_path = Path(result_path).expanduser()
    return complete_codex_bridge_job(job_id, result_disk_path)


async def extract_xhs_link(url: str) -> dict[str, Any]:
    normalized_url = _normalize_xhs_url(url)
    extract_id = hashlib.sha256(normalized_url.encode("utf-8")).hexdigest()[:16]
    work_dir = _tryon_output_dir() / "xhs" / extract_id
    work_dir.mkdir(parents=True, exist_ok=True)

    html_text, final_url = await _fetch_xhs_html(normalized_url)
    note = _extract_xhs_note_payload(html_text)
    structured_urls = _extract_xhs_note_image_urls(note)
    fallback_urls = _extract_image_urls_from_html(html_text, final_url)
    image_urls = _merge_unique_urls([*structured_urls, *fallback_urls])
    downloaded = await _download_candidate_images(image_urls, final_url, work_dir)
    items = []
    detector = FashionItemDetector()
    for index, image_item in enumerate(downloaded):
        items.append(detector.detect(image_item, index, work_dir))

    extracted = [item for item in items if item["has_top"] and item["cutout_path"]]
    fashion_items = [fashion_item for item in items for fashion_item in item.get("fashion_items", [])]
    usable_fashion_items = [item for item in fashion_items if item.get("quality", {}).get("status") == "usable"]
    reference_sheet_path = _build_inspiration_reference_sheet(downloaded, work_dir)
    style_context = _build_inspiration_style_context(note, items, fashion_items, reference_sheet_path)
    status = "extracted" if extracted else "no_top_found"
    message = "已从链接图片中提取可用上衣。" if extracted else "已解析链接，但没有找到可稳定提取的上衣图。"
    return {
        "status": status,
        "extract_id": extract_id,
        "source_url": normalized_url,
        "final_url": final_url,
        "note": _public_xhs_note(note),
        "image_count": len(image_urls),
        "downloaded_count": len(downloaded),
        "extracted_count": len(extracted),
        "style_context": style_context,
        "fashion_item_count": len(fashion_items),
        "usable_fashion_item_count": len(usable_fashion_items),
        "fashion_items": fashion_items,
        "items": items,
        "result": {
            "cutouts": [item["cutout_path"] for item in extracted],
            "clean_references": [item["clean_reference_path"] for item in usable_fashion_items if item.get("clean_reference_path")],
            "message": message,
        },
    }


def tryon_capabilities() -> dict[str, Any]:
    base_url = _openai_base_url()
    chat_supported = bool(base_url and _openai_chat_or_responses_supported(base_url))
    image_edit_supported = bool(base_url and _openai_images_api_supported(base_url))
    has_key = bool(os.getenv("TRYON_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY"))
    runway_google_supported = _has_runway_google_provider()
    pi_code_worker_enabled = _pi_agent_code_worker_enabled()
    return {
        "status": "ready_for_validation",
        "provider": {
            "base_url": base_url,
            "configured_base_url": _configured_openai_base_url(),
            "api_key_present": has_key,
            "vision_model": _default_tryon_vision_model(),
            "runway_google_url": _runway_google_url(),
            "runway_google_configured": runway_google_supported,
            "runway_google_note": "configured_only_image_output_must_be_verified_by_generation",
        },
        "features": {
            "garment_analysis": "vlm" if chat_supported or has_key else "local_cv_fallback",
            "fashion_item_detection": "top_only_local_mvp",
            "clean_item_reference": "local_crop_placeholder",
            "image_edit": (
                "runway_google_generate_content"
                if runway_google_supported
                else "openai_compatible"
                if image_edit_supported or has_key
                else "pi_agent_code_worker_experimental" if pi_code_worker_enabled
                else "unavailable"
            ),
            "xhs_extraction": "enabled",
            "model_fixtures": "enabled",
            "outfit_plan_tryon": "single_step_reference_board",
            "photo_modes": sorted(OUTFIT_PHOTO_MODES),
        },
        "fashion_architecture": {
            "terminal_categories": sorted(FASHION_ITEM_CATEGORIES),
            "mvp_categories": ["top", "outer", "bottom", "skirt", "dress", "shoes"],
            "layers": [
                "xhs_note_image_extraction",
                "fashion_item_detection",
                "clean_item_reference_generation",
                "outfit_reference_board_generation",
                "category_aware_tryon_generation",
                "quality_review",
            ],
            "current_mode": "top_mvp_plus_multi_item_outfit_plan_mvp",
        },
        "checks": {
            "openai_compatible_text_or_vision": chat_supported,
            "openai_compatible_images_edit": image_edit_supported,
            "runway_google_generate_content": runway_google_supported,
        },
        "validation": {
            "status": "ready",
            "garment_analysis": "local_cv_or_fixture",
            "image_edit": "mock_tryon_provider_for_tests_only",
            "source": "same_pattern_as_color_mvp_fixture_validation",
        },
        "production": {
            "status": "ready" if image_edit_supported or has_key else "runway_google_configured" if runway_google_supported else "image_edit_pending",
            "required_capability": "Runway Google generateContent image output or OpenAI-compatible images.edit",
        },
        "message": (
            "Runway Google 代理已配置，生成时会验证是否支持图片输出。"
            if runway_google_supported
            else
            "真实图片编辑能力可用。"
            if image_edit_supported or has_key
            else "本地 Pi CLI 当前不会直接调用 GPT 图片生成；真实试穿生成需接入 images.edit 或 Diga 的真实生图接口。"
            if not pi_code_worker_enabled
            else "已显式启用实验性 Pi coding worker；该模式可能用脚本合成，不应视为真实 GPT 试穿结果。"
        ),
    }


def run_try_on(person: dict[str, Any], garment: dict[str, Any], provider: "TryOnProvider | None" = None) -> dict[str, Any]:
    tryon_id = hashlib.sha256(f"{person['image_id']}:{garment['image_id']}".encode("utf-8")).hexdigest()[:16]
    work_dir = _tryon_output_dir() / tryon_id
    work_dir.mkdir(parents=True, exist_ok=True)

    input_quality = _input_quality_stage(person["image"], garment["image"])
    person_detection = _detect_person(person["image"]) if input_quality["status"] != "fail" else _stage("unknown", 0.0, {"skipped": True}, [])
    garment_analysis = GarmentAnalyzer().analyze(garment["image"]) if input_quality["status"] != "fail" else _stage("unknown", 0.0, {"skipped": True}, [])
    mask_stage = (
        _generate_upper_body_mask(person["image"], person_detection, work_dir / "upper_body_mask.png")
        if person_detection["status"] in {"pass", "warn"}
        else _stage("unknown", 0.0, {"skipped": True, "reason": "person_detection_not_pass"}, [])
    )

    pipeline: dict[str, Any] = {
        "input_quality": input_quality,
        "person_detection": person_detection,
        "garment_analysis": garment_analysis,
        "upper_body_mask": mask_stage,
        "edit_contract": _lightweight_tryon_edit_contract(mask_stage, mode="upper_body"),
        "image_edit": _stage("unknown", 0.0, {"skipped": True}, []),
        "quality_review": _stage("unknown", 0.0, {"skipped": True}, []),
    }

    blocking = _blocking_issues(pipeline)
    result_image_path: Path | None = None
    if blocking:
        status = "needs_retake"
        user_message = "照片暂不适合试穿，请按提示重新上传。"
    else:
        provider = provider or _default_provider()
        prompt = _build_tryon_prompt(garment_analysis["evidence"]["garment"])
        edit_result = provider.edit(
            person_image=person["saved_path"],
            garment_image=garment["saved_path"],
            mask_image=Path(mask_stage["evidence"]["mask_path"]),
            prompt=prompt,
            output_dir=work_dir,
        )
        pipeline["image_edit"] = edit_result["stage"]
        result_image_path = edit_result.get("image_path")
        if pipeline["image_edit"]["status"] == "pending":
            pipeline["quality_review"] = _stage("pending", 0.0, {"skipped": True, "reason": "pi_agent_worker_pending"}, [])
            status = "pending"
            user_message = "已提交到本地 Diga/Pi Agent 生图后台，生成完成后会自动显示。"
        else:
            pipeline["quality_review"] = _review_tryon_quality(
                person["image"],
                result_image_path,
                person_detection,
                Path(mask_stage["evidence"]["mask_path"]),
            )
        if pipeline["image_edit"]["status"] == "pass" and pipeline["quality_review"]["status"] in {"pass", "warn"}:
            status = "generated"
            user_message = "已生成上衣试穿效果，建议重点观察衣服版型和整体风格。"
        elif pipeline["image_edit"]["status"] != "pending":
            status = "failed"
            if any(issue.get("code") == "image_edit.provider_unavailable" for issue in pipeline["image_edit"].get("issues", [])):
                user_message = "当前还没有接入真实 AI 试穿模型，暂时不能生成可信试穿图。"
            else:
                user_message = "这次试穿图质量没有达标，暂不建议展示给用户。"

    return {
        "status": status,
        "tryon_id": tryon_id,
        "user_id": storage_context().user_id,
        "input": {
            "person_image_id": person["image_id"],
            "garment_image_id": garment["image_id"],
            "person": person["meta"],
            "garment": garment["meta"],
        },
        "garment": garment_analysis.get("evidence", {}).get("garment", _fallback_garment()),
        "decision": {
            "blocking_errors": blocking,
            "warnings": _warnings(pipeline),
            "user_message": user_message,
        },
        "pipeline": pipeline,
        "model_plan": {
            "validation": [
                "对齐色彩测试 MVP：验证期使用本地 CV、测试 fixture 和 MockTryOnProvider 稳定回归",
                "服务运行时不依赖 Codex 内部授权实时出图",
                "验收脚本默认验证接口、上衣提取、mask、质量校验和可展示结果结构",
            ],
            "production": [
                "OpenAIImageEditTryOnProvider 为生产化预留 adapter",
                "本地或远程 OpenAI 兼容代理支持 images.edit 后，可通过严格验收验证真实 AI 试穿图",
            ],
        },
        "result": {
            "image_path": _public_output_path(result_image_path) if result_image_path else None,
            "mask_path": _public_output_path(Path(mask_stage["evidence"]["mask_path"])) if mask_stage["status"] in {"pass", "warn"} else None,
            "bridge_job_id": pipeline["image_edit"].get("evidence", {}).get("bridge_job_id"),
            "bridge_status_url": pipeline["image_edit"].get("evidence", {}).get("status_url"),
            "user_message": user_message,
        },
    }


def run_try_on_from_inspiration(
    person: dict[str, Any],
    inspiration: dict[str, Any],
    provider: "TryOnProvider | None" = None,
    style_brief: str | None = None,
) -> dict[str, Any]:
    tryon_id = hashlib.sha256(f"inspiration:{person['image_id']}:{inspiration['image_id']}:{style_brief or ''}".encode("utf-8")).hexdigest()[:16]
    work_dir = _tryon_output_dir() / tryon_id
    work_dir.mkdir(parents=True, exist_ok=True)

    input_quality = _input_quality_stage(person["image"], inspiration["image"])
    person_detection = _detect_person(person["image"]) if input_quality["status"] != "fail" else _stage("unknown", 0.0, {"skipped": True}, [])
    inspiration_analysis = _stage("pass", 0.62, {
        "provider": "inspiration_direct",
        "mode": "one_step_ai_extract_and_tryon",
        "category": "top",
        "skipped_local_garment_gate": True,
        "style_brief": _safe_style_brief(style_brief),
        "note": "Inspiration image is intentionally passed directly to the image model; local garment analysis is not a blocker.",
    }, [])
    mask_stage = (
        _generate_upper_body_mask(person["image"], person_detection, work_dir / "upper_body_mask.png")
        if person_detection["status"] in {"pass", "warn"}
        else _stage("unknown", 0.0, {"skipped": True, "reason": "person_detection_not_pass"}, [])
    )

    pipeline: dict[str, Any] = {
        "input_quality": input_quality,
        "person_detection": person_detection,
        "garment_analysis": inspiration_analysis,
        "upper_body_mask": mask_stage,
        "edit_contract": _lightweight_tryon_edit_contract(mask_stage, mode="upper_body_inspiration"),
        "image_edit": _stage("unknown", 0.0, {"skipped": True}, []),
        "quality_review": _stage("unknown", 0.0, {"skipped": True}, []),
    }

    blocking = _blocking_issues(pipeline, include_garment=False)
    result_image_path: Path | None = None
    if blocking:
        status = "needs_retake"
        user_message = "照片暂不适合试穿，请按提示重新上传。"
    else:
        provider = provider or _default_provider()
        prompt = _build_inspiration_tryon_prompt(style_brief)
        edit_result = provider.edit(
            person_image=person["saved_path"],
            garment_image=inspiration["saved_path"],
            mask_image=Path(mask_stage["evidence"]["mask_path"]),
            prompt=prompt,
            output_dir=work_dir,
        )
        pipeline["image_edit"] = edit_result["stage"]
        result_image_path = edit_result.get("image_path")
        if pipeline["image_edit"]["status"] == "pending":
            pipeline["quality_review"] = _stage("pending", 0.0, {"skipped": True, "reason": "worker_pending"}, [])
            status = "pending"
            user_message = "已提交生成，正在从灵感图中提取上衣并试穿。"
        else:
            pipeline["quality_review"] = _review_tryon_quality(
                person["image"],
                result_image_path,
                person_detection,
                Path(mask_stage["evidence"]["mask_path"]),
            )
        if pipeline["image_edit"]["status"] == "pass" and pipeline["quality_review"]["status"] in {"pass", "warn"}:
            status = "generated"
            user_message = "已根据灵感图生成上衣试穿效果，建议重点观察条纹、领口和整体版型。"
        elif pipeline["image_edit"]["status"] != "pending":
            status = "failed"
            user_message = "这次灵感试穿没有达标，暂不建议展示给用户。"

    return {
        "status": status,
        "tryon_id": tryon_id,
        "mode": "from_inspiration",
        "input": {
            "person_image_id": person["image_id"],
            "inspiration_image_id": inspiration["image_id"],
            "person": person["meta"],
            "inspiration": inspiration["meta"],
        },
        "garment": {
            **_fallback_garment(),
            "category": "top",
            "source_type": "inspiration_image",
            "extraction_mode": "one_step_ai",
        },
        "decision": {
            "blocking_errors": blocking,
            "warnings": _warnings(pipeline),
            "user_message": user_message,
        },
        "pipeline": pipeline,
        "result": {
            "image_path": _public_output_path(result_image_path) if result_image_path else None,
            "mask_path": _public_output_path(Path(mask_stage["evidence"]["mask_path"])) if mask_stage["status"] in {"pass", "warn"} else None,
            "bridge_job_id": pipeline["image_edit"].get("evidence", {}).get("bridge_job_id"),
            "bridge_status_url": pipeline["image_edit"].get("evidence", {}).get("status_url"),
            "user_message": user_message,
        },
    }


def run_try_on_from_outfit_plan(
    person: dict[str, Any],
    outfit_plan: dict[str, Any],
    provider: "TryOnProvider | None" = None,
) -> dict[str, Any]:
    normalized_plan = _normalize_outfit_tryon_plan(outfit_plan)
    plan_signature = json.dumps(_public_outfit_tryon_plan(normalized_plan), ensure_ascii=False, sort_keys=True)
    tryon_id = hashlib.sha256(f"outfit-plan:{person['image_id']}:{plan_signature}".encode("utf-8")).hexdigest()[:16]
    work_dir = _tryon_output_dir() / tryon_id
    work_dir.mkdir(parents=True, exist_ok=True)

    reference_board_path = _build_outfit_reference_board(normalized_plan, work_dir / "outfit_reference_board.png")
    reference_board = Image.open(reference_board_path).convert("RGB")
    raw_input_quality = _input_quality_stage(person["image"], reference_board)
    person_detection = _detect_person(person["image"])
    person_detection = _relax_outfit_person_detection_for_ai_tryon(person["image"], person_detection, raw_input_quality)
    input_quality = _relax_preset_model_blur_for_outfit_tryon(person, raw_input_quality, person_detection)
    plan_stage = _outfit_plan_stage(normalized_plan)
    mask_stage = (
        _generate_outfit_body_mask(person["image"], person_detection, work_dir / "outfit_body_mask.png")
        if person_detection["status"] in {"pass", "warn"}
        else _stage("unknown", 0.0, {"skipped": True, "reason": "person_detection_not_pass"}, [])
    )

    pipeline: dict[str, Any] = {
        "input_quality": input_quality,
        "person_detection": person_detection,
        "outfit_plan": plan_stage,
        "outfit_body_mask": mask_stage,
        "edit_contract": _lightweight_tryon_edit_contract(mask_stage, mode="outfit_body"),
        "image_edit": _stage("unknown", 0.0, {"skipped": True}, []),
        "quality_review": _stage("unknown", 0.0, {"skipped": True}, []),
    }

    blocking = _outfit_blocking_issues(pipeline)
    result_image_path: Path | None = None
    prompt_context = _build_outfit_prompt_context(normalized_plan)
    if blocking:
        status = "needs_retake" if any(issue.get("code", "").startswith("person.") for issue in blocking) else "failed"
        user_message = "这套搭配暂时没有可用单品，请先加入至少一件衣物或鞋包。" if status == "failed" else "照片暂不适合试穿，请按提示重新上传。"
    else:
        provider = provider or _default_provider()
        prompt = _build_outfit_tryon_prompt(prompt_context)
        edit_result = provider.edit(
            person_image=person["saved_path"],
            garment_image=reference_board_path,
            mask_image=Path(mask_stage["evidence"]["mask_path"]),
            prompt=prompt,
            output_dir=work_dir,
        )
        pipeline["image_edit"] = edit_result["stage"]
        result_image_path = edit_result.get("image_path")
        if pipeline["image_edit"]["status"] == "pending":
            pipeline["quality_review"] = _stage("pending", 0.0, {"skipped": True, "reason": "worker_pending"}, [])
            status = "pending"
            user_message = "已提交生成，正在把整套穿搭穿到模特身上。"
        else:
            pipeline["quality_review"] = _review_outfit_tryon_quality(
                person["image"],
                result_image_path,
                person_detection,
                Path(mask_stage["evidence"]["mask_path"]),
                normalized_plan,
            )
            if pipeline["image_edit"]["status"] == "pass" and pipeline["quality_review"]["status"] in {"pass", "warn"}:
                status = "generated"
                user_message = "已生成整套穿搭试穿图，建议重点观察单品是否完整、比例和整体氛围。"
            elif pipeline["image_edit"]["status"] == "pass" and result_image_path:
                status = "review"
                user_message = "试穿图已生成，但有些细节建议复核；你可以先查看，也可以重新生成一版。"
            else:
                status = "failed"
                user_message = "这次整套试穿图质量没有达标，暂不建议展示给用户。"

    return {
        "status": status,
        "tryon_id": tryon_id,
        "mode": "from_outfit_plan",
        "source_mode": normalized_plan.get("source_mode", "direct_upload"),
        "generation_strategy": "single_step_reference_board",
        "photo_mode": normalized_plan["model_photo_mode"],
        "missing_slots": plan_stage["evidence"].get("missing_slots", []),
        "input": {
            "person_image_id": person["image_id"],
            "person": person["meta"],
            "style_reference_image_id": normalized_plan.get("style_reference", {}).get("image_id"),
            "item_image_ids": [item.get("image_id") for item in normalized_plan.get("items", []) if item.get("image_id")],
        },
        "outfit_plan": _public_outfit_tryon_plan(normalized_plan),
        "reference_board_path": _public_output_path(reference_board_path),
        "prompt_context": prompt_context,
        "decision": {
            "blocking_errors": blocking,
            "warnings": _warnings(pipeline),
            "user_message": user_message,
        },
        "pipeline": pipeline,
        "result": {
            "image_path": _public_output_path(result_image_path) if result_image_path else None,
            "mask_path": _public_output_path(Path(mask_stage["evidence"]["mask_path"])) if mask_stage["status"] in {"pass", "warn"} else None,
            "bridge_job_id": pipeline["image_edit"].get("evidence", {}).get("bridge_job_id"),
            "bridge_status_url": pipeline["image_edit"].get("evidence", {}).get("status_url"),
            "user_message": user_message,
        },
    }


class GarmentAnalyzer:
    def __init__(self, provider: "GarmentAnalysisProvider | None" = None) -> None:
        self.provider = provider or _default_garment_analysis_provider()

    def analyze(self, image: Image.Image) -> dict[str, Any]:
        return self.provider.analyze(image)


class FashionItemDetector:
    """Terminal architecture adapter: detect reusable fashion items from inspiration images."""

    def __init__(self, provider: "FashionItemDetectionProvider | None" = None) -> None:
        self.provider = provider or LocalTopFashionItemDetectionProvider()

    def detect(self, image_item: dict[str, Any], index: int, work_dir: Path) -> dict[str, Any]:
        return self.provider.detect(image_item, index, work_dir)


class FashionItemDetectionProvider:
    mode = "abstract"

    def detect(self, image_item: dict[str, Any], index: int, work_dir: Path) -> dict[str, Any]:
        raise NotImplementedError


class LocalTopFashionItemDetectionProvider(FashionItemDetectionProvider):
    mode = "local_top_only"

    def detect(self, image_item: dict[str, Any], index: int, work_dir: Path) -> dict[str, Any]:
        return _extract_top_from_note_image(image_item, index, work_dir)


class CleanFashionItemProvider:
    mode = "abstract"

    def clean_reference(
        self,
        source_image: Path,
        category: str,
        crop_box: dict[str, Any] | None,
        prompt: str,
        output_dir: Path,
    ) -> dict[str, Any]:
        raise NotImplementedError


class LocalCropCleanFashionItemProvider(CleanFashionItemProvider):
    mode = "local_crop_reference"

    def clean_reference(
        self,
        source_image: Path,
        category: str,
        crop_box: dict[str, Any] | None,
        prompt: str,
        output_dir: Path,
    ) -> dict[str, Any]:
        image = Image.open(source_image).convert("RGBA")
        cutout = _save_garment_bbox_cutout(image.convert("RGB"), crop_box, output_dir / f"clean_{category}.png")
        return {
            "stage": _stage("warn", 0.48, {
                "provider": self.mode,
                "category": category,
                "result_path": str(cutout["path"]),
                "note": "Local crop is a placeholder for AI clean product-reference extraction.",
            }, [
                _issue("fashion_item.clean_reference_local", "当前为本地裁剪参考图", "后续可接入 AI 单品清洁提取模型。")
            ]),
            "image_path": cutout["path"],
        }


class GarmentAnalysisProvider:
    mode = "abstract"

    def analyze(self, image: Image.Image) -> dict[str, Any]:
        raise NotImplementedError


class LocalGarmentAnalysisProvider(GarmentAnalysisProvider):
    mode = "local_cv"

    def analyze(self, image: Image.Image) -> dict[str, Any]:
        width, height = image.size
        if width < MIN_GARMENT_EDGE or height < MIN_GARMENT_EDGE:
            return _stage("fail", 0.78, {"provider": self.mode, "garment": _fallback_garment(), "width": width, "height": height}, [
                _issue("garment.too_small", "衣服图片分辨率过低", "请上传更清晰的上衣图片。")
            ])

        edge_density = _edge_density(image)
        saturation = _median_saturation(image)
        face_stage = _detect_person(image)
        source_type = "person_wearing_top" if face_stage["status"] in {"pass", "warn"} else "single_garment"
        bbox = _estimate_worn_top_bbox(image, face_stage) if source_type == "person_wearing_top" else _estimate_garment_bbox(image)
        if bbox is None:
            bbox = _estimate_garment_bbox(image)
        colors = _dominant_colors(_crop_image_by_bbox(image, bbox)) if bbox else _dominant_colors(image)
        has_top = _local_has_top_candidate(image, bbox, edge_density, saturation, face_stage)
        garment = _fallback_garment()
        if has_top:
            garment.update({
                "category": "top",
                "colors": colors,
                "material": _guess_material(edge_density, saturation),
                "fit": "regular",
                "sleeve": _guess_sleeve(source_type, bbox),
                "neckline": "unknown",
                "pattern": _guess_pattern(edge_density, saturation),
                "details": _guess_details(edge_density),
                "style_tags": _guess_style_tags(colors, saturation),
                "source_type": source_type,
                "bbox": bbox,
            })

        if not has_top:
            return _stage("fail", 0.58, {
                "provider": self.mode,
                "garment": garment,
                "has_top": False,
                "source_type": "not_garment",
                "bbox": bbox,
                "edge_density": edge_density,
                "median_saturation": saturation,
                "face_status": face_stage["status"],
            }, [_issue("garment.no_top", "没有识别到清晰上衣", "请上传单件上衣图，或包含清晰上半身穿搭的图片。")])

        confidence = 0.78 if source_type == "single_garment" else 0.72
        issues = []
        if not colors or bbox is None:
            confidence = 0.52
            issues.append(_issue("garment.low_confidence", "衣服要素识别置信度较低", "建议上传单件上衣的清晰正面图。"))
        status = "warn" if issues else "pass"
        return _stage(status, confidence, {
            "provider": self.mode,
            "garment": garment,
            "has_top": True,
            "source_type": source_type,
            "bbox": bbox,
            "edge_density": edge_density,
            "median_saturation": saturation,
            "face_status": face_stage["status"],
        }, issues)


class OpenAIGarmentAnalysisProvider(GarmentAnalysisProvider):
    mode = "openai_vision"

    def __init__(self, model: str | None = None) -> None:
        self.model = model or _default_tryon_vision_model()

    def analyze(self, image: Image.Image) -> dict[str, Any]:
        try:
            from openai import OpenAI
        except ImportError:
            return LocalGarmentAnalysisProvider().analyze(image)

        try:
            base_url = _openai_base_url()
            client = _openai_compatible_client(OpenAI)
            prompt = (
                "Analyze this image for an AI upper-body virtual try-on MVP. "
                "Return strict JSON only. Schema: "
                "{has_top:boolean, category:string, colors:string[], material:string[], "
                "fit:string, sleeve:string, neckline:string, pattern:string, details:string[], "
                "style_tags:string[], source_type:string, bbox:{x:number,y:number,width:number,height:number}|null, "
                "confidence:number, reason:string}. "
                "bbox must be normalized 0-1 around the visible upper garment if possible. "
                "source_type must be one of single_garment, person_wearing_top, no_top, unknown."
            )
            image_url = _image_to_data_url(image)
            try:
                response = client.responses.create(
                    model=self.model,
                    input=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "input_text", "text": prompt},
                                {"type": "input_image", "image_url": image_url, "detail": "high"},
                            ],
                        }
                    ],
                )
                text = getattr(response, "output_text", "") or ""
            except Exception as responses_exc:
                response = client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {"type": "image_url", "image_url": {"url": image_url}},
                            ],
                        }
                    ],
                    max_tokens=1200,
                )
                text = response.choices[0].message.content or ""
                if not text:
                    raise responses_exc
            data = _extract_json_object(text)
            stage = _stage_from_vlm_garment(data, self.mode, self.model)
            stage["evidence"]["base_url"] = base_url
            return stage
        except Exception as exc:  # pragma: no cover - depends on external API availability
            fallback = LocalGarmentAnalysisProvider().analyze(image)
            fallback["issues"].append(_issue("garment.vlm_unavailable", "衣服识别暂未走大模型", "已使用本地识别继续处理。"))
            fallback["suggestions"] = [issue["suggestion"] for issue in fallback["issues"] if issue.get("suggestion")]
            fallback["evidence"]["provider"] = "local_cv_fallback"
            fallback["evidence"]["vlm_error"] = str(exc)
            return fallback


class StaticGarmentAnalysisProvider(GarmentAnalysisProvider):
    mode = "static_test"

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def analyze(self, image: Image.Image) -> dict[str, Any]:
        return _stage_from_vlm_garment(self.payload, self.mode, "test")


def _default_garment_analysis_provider() -> GarmentAnalysisProvider:
    if _has_openai_compatible_provider():
        return OpenAIGarmentAnalysisProvider()
    return LocalGarmentAnalysisProvider()


def _stage_from_vlm_garment(data: dict[str, Any], provider: str, model: str) -> dict[str, Any]:
    has_top = bool(data.get("has_top"))
    garment = _fallback_garment()
    if has_top:
        garment.update({
            "category": str(data.get("category") or "top"),
            "colors": _string_list(data.get("colors")),
            "material": _string_list(data.get("material")),
            "fit": str(data.get("fit") or "regular"),
            "sleeve": str(data.get("sleeve") or "unknown"),
            "neckline": str(data.get("neckline") or "unknown"),
            "pattern": str(data.get("pattern") or "unknown"),
            "details": _string_list(data.get("details")),
            "style_tags": _string_list(data.get("style_tags")),
            "source_type": str(data.get("source_type") or "unknown"),
            "bbox": _normalized_bbox(data.get("bbox")),
        })
    confidence = float(data.get("confidence") or (0.82 if has_top else 0.62))
    evidence = {
        "provider": provider,
        "model": model,
        "garment": garment,
        "has_top": has_top,
        "source_type": str(data.get("source_type") or ("unknown" if has_top else "no_top")),
        "bbox": garment.get("bbox"),
        "reason": str(data.get("reason") or ""),
    }
    if not has_top:
        return _stage("fail", min(confidence, 0.68), evidence, [
            _issue("garment.no_top", "没有识别到清晰上衣", "请上传单件上衣图，或包含清晰上半身穿搭的图片。")
        ])
    status = "pass" if confidence >= 0.68 else "warn"
    issues = [] if status == "pass" else [_issue("garment.low_confidence", "衣服要素识别置信度较低", "建议上传单件上衣的清晰正面图。")]
    return _stage(status, confidence, evidence, issues)


def _extract_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if match:
        cleaned = match.group(0)
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise ValueError("garment analyzer response is not a JSON object")
    return data


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _normalized_bbox(value: Any) -> dict[str, float] | None:
    if not isinstance(value, dict):
        return None
    try:
        x = max(0.0, min(1.0, float(value.get("x", 0))))
        y = max(0.0, min(1.0, float(value.get("y", 0))))
        width = max(0.0, min(1.0 - x, float(value.get("width", 0))))
        height = max(0.0, min(1.0 - y, float(value.get("height", 0))))
    except (TypeError, ValueError):
        return None
    if width <= 0 or height <= 0:
        return None
    return {"x": round(x, 4), "y": round(y, 4), "width": round(width, 4), "height": round(height, 4)}


def _image_to_data_url(image: Image.Image) -> str:
    buf = io.BytesIO()
    image.convert("RGB").save(buf, "JPEG", quality=92)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _path_to_runway_inline_data(path: Path) -> dict[str, Any]:
    image = Image.open(path)
    image.load()
    fmt = (image.format or path.suffix.lstrip(".") or "png").upper()
    mime_type = {
        "JPEG": "image/jpeg",
        "JPG": "image/jpeg",
        "PNG": "image/png",
        "WEBP": "image/webp",
    }.get(fmt, "image/png")
    return {
        "inlineData": {
            "mimeType": mime_type,
            "data": base64.b64encode(path.read_bytes()).decode("ascii"),
        }
    }


def _runway_output_size_instruction(person_image: Path) -> str:
    try:
        with Image.open(person_image) as image:
            width, height = image.size
    except Exception:
        return "Output size/framing: keep the same portrait orientation, aspect ratio, and full-body framing as Image A."
    aspect = width / max(1, height)
    orientation = "portrait" if height >= width else "landscape"
    return (
        f"Output size/framing: Image A is {width}x{height}px, aspect ratio {aspect:.4f}, {orientation}. "
        "Return the final image with exactly the same canvas aspect ratio, crop, camera distance, and visual framing as Image A. "
        "Image A is the framing authority, not Image B. Do not zoom out, widen the canvas, rotate to landscape, add margins, or create a collage layout. "
        "Only change garments/accessories that are already visible in Image A. If shoes, feet, a bag, or lower-body details are not visible or are cropped in Image A, do not invent them, do not complete them, and do not change the camera framing to show them."
    )


def _image_size_evidence(path: Path) -> dict[str, Any]:
    try:
        with Image.open(path) as image:
            width, height = image.size
    except Exception:
        return {}
    return {
        "width": width,
        "height": height,
        "aspect_ratio": round(width / max(1, height), 4),
    }


def _fit_image_to_reference_canvas(image: Image.Image, reference_path: Path) -> tuple[Image.Image, dict[str, Any]]:
    try:
        with Image.open(reference_path) as reference:
            target_size = reference.size
    except Exception:
        return image, {"normalized": False, "reason": "reference_unavailable"}
    source_size = image.size
    if source_size == target_size:
        return image, {"normalized": False, "source_size": {"width": source_size[0], "height": source_size[1]}, "target_size": {"width": target_size[0], "height": target_size[1]}}
    src_aspect = source_size[0] / max(1, source_size[1])
    target_aspect = target_size[0] / max(1, target_size[1])
    if src_aspect > target_aspect:
        crop_width = int(source_size[1] * target_aspect)
        left = max(0, (source_size[0] - crop_width) // 2)
        crop_box = (left, 0, left + crop_width, source_size[1])
    else:
        crop_height = int(source_size[0] / target_aspect)
        top = max(0, (source_size[1] - crop_height) // 2)
        crop_box = (0, top, source_size[0], top + crop_height)
    normalized = image.crop(crop_box).resize(target_size, Image.Resampling.LANCZOS)
    return normalized, {
        "normalized": True,
        "source_size": {"width": source_size[0], "height": source_size[1]},
        "target_size": {"width": target_size[0], "height": target_size[1]},
        "crop_box": crop_box,
        "rule": "center_crop_to_image_a_canvas",
    }


def _mask_editing_contract() -> str:
    return (
        "Mask contract: Image C is the edit mask for Image A. Transparent/black/dark mask pixels mark the clothing area that may be edited. "
        "White/opaque/light mask pixels are protected areas and must remain unchanged. "
        "Do not alter protected face, hair, hands, skin, body shape, pose, background, lighting, camera angle, or canvas framing outside the editable mask."
    )


def _build_provider_prompt_with_mask_contract(prompt: str) -> str:
    return f"{_mask_editing_contract()}\n\n{prompt}"


def _lightweight_tryon_edit_contract(mask_stage: dict[str, Any], mode: str) -> dict[str, Any]:
    evidence = mask_stage.get("evidence", {}) if isinstance(mask_stage, dict) else {}
    return _stage("pass", 0.86, {
        "strategy": "strong_image_editor_with_lightweight_mask",
        "model_profile": "nano_banana_compatible",
        "mode": mode,
        "preprocessing": {
            "level": "lightweight",
            "reason": "backend image editor is expected to understand person, garment, and mask inputs without heavy VTON preprocessing",
            "no_heavy_human_parsing_required": True,
        },
        "inputs": [
            {"id": "image_a", "role": "identity_pose_background_anchor", "meaning": "user/person photo; preserve identity, pose, background, camera, and canvas"},
            {"id": "image_b", "role": "garment_or_outfit_reference", "meaning": "clothing visual reference; use for color, material, fit, pattern, and details"},
            {"id": "image_c_or_mask", "role": "editable_region_mask", "meaning": "same-size mask for Image A; guides where edits are allowed"},
        ],
        "mask": {
            "path": evidence.get("mask_path"),
            "rule": evidence.get("rule"),
            "editable_ratio": evidence.get("editable_ratio"),
            "editable": "transparent_or_black_alpha_lt_128",
            "protected": "opaque_or_white_alpha_gte_220",
            "soft_boundary": True,
        },
        "preserve": [
            "face",
            "hair",
            "skin_tone",
            "hands",
            "body_shape",
            "pose",
            "background",
            "lighting",
            "camera_angle",
            "canvas_framing",
        ],
        "post_quality_checks": [
            "same_canvas_size_or_normalized_to_image_a",
            "face_region_difference",
            "protected_region_difference",
            "mask_editable_ratio",
        ],
    }, [])


def _build_runway_google_tryon_payload(person_image: Path, garment_image: Path, mask_image: Path, prompt: str) -> dict[str, Any]:
    output_instruction = _runway_output_size_instruction(person_image)
    tryon_prompt = (
        "请生成一张真实自然的虚拟试穿结果图。"
        "图A是要保留身份和姿态的模特/用户照片，图B是目标服饰或穿搭参考，图C是图A的可编辑衣服区域 mask。"
        "请根据补充约束让图A中的人物穿上图B中的目标服饰。"
        "必须保留图A的人脸、发型、肤色、体型、姿势、手臂、背景、光线、相机角度和整体照片风格。"
        "如果补充约束要求上衣，只替换上衣；如果要求整套穿搭，则替换对应服饰区域。"
        "不要改变脸、身体轮廓、背景，不要添加文字、水印或 UI。"
        "目标服饰要尽量还原图B的颜色、材质、版型、穿法、图案和细节。"
        f"{_mask_editing_contract()}"
        f"{output_instruction}"
        f"\n\n补充约束：{prompt}"
    )
    return {
        "contents": [
            {
                "role": "user",
                "parts": [
                    _path_to_runway_inline_data(person_image),
                    _path_to_runway_inline_data(garment_image),
                    _path_to_runway_inline_data(mask_image),
                    {"text": tryon_prompt},
                ],
            }
        ],
        "generationConfig": {
            "temperature": float(os.getenv("TRYON_RUNWAY_TEMPERATURE", "1")),
            "maxOutputTokens": int(os.getenv("TRYON_RUNWAY_MAX_OUTPUT_TOKENS", "32768")),
            "responseModalities": ["TEXT", "IMAGE"],
            "topP": float(os.getenv("TRYON_RUNWAY_TOP_P", "0.95")),
        },
        "safetySettings": [
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "OFF"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "OFF"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "OFF"},
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "OFF"},
        ],
    }


def _extract_runway_google_image(data: dict[str, Any]) -> tuple[str, str] | None:
    candidates = data.get("candidates") if isinstance(data, dict) else None
    if isinstance(candidates, list):
        for candidate in candidates:
            content = candidate.get("content") if isinstance(candidate, dict) else None
            parts = content.get("parts") if isinstance(content, dict) else None
            found = _extract_image_from_parts(parts)
            if found:
                return found
    parts = data.get("parts") if isinstance(data, dict) else None
    return _extract_image_from_parts(parts)


def _runway_google_error_summary(data: Any) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None
    if "Code" not in data and "Error" not in data:
        return None
    error_text = str(data.get("Error") or data.get("error") or data.get("message") or "")
    return {
        "code": data.get("Code"),
        "error": error_text[:800],
    }


def _extract_image_from_parts(parts: Any) -> tuple[str, str] | None:
    if not isinstance(parts, list):
        return None
    for part in parts:
        if not isinstance(part, dict):
            continue
        inline = part.get("inlineData") or part.get("inline_data")
        if isinstance(inline, dict):
            b64_data = inline.get("data")
            if isinstance(b64_data, str) and b64_data.strip():
                return str(inline.get("mimeType") or inline.get("mime_type") or "image/png"), _strip_data_url_prefix(b64_data.strip())
        text = part.get("text")
        if isinstance(text, str):
            data_url = re.search(r"data:(image/[^;]+);base64,([A-Za-z0-9+/=\s]+)", text)
            if data_url:
                return data_url.group(1), re.sub(r"\s+", "", data_url.group(2))
    return None


def _strip_data_url_prefix(value: str) -> str:
    if value.startswith("data:") and ";base64," in value:
        return value.split(",", 1)[1]
    return value


def _response_shape(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {"type": type(data).__name__}
    shape: dict[str, Any] = {"keys": sorted(str(key) for key in data.keys())[:12]}
    candidates = data.get("candidates")
    if isinstance(candidates, list):
        shape["candidate_count"] = len(candidates)
        if candidates:
            content = candidates[0].get("content") if isinstance(candidates[0], dict) else None
            parts = content.get("parts") if isinstance(content, dict) else None
            if isinstance(parts, list):
                shape["first_candidate_part_keys"] = [
                    sorted(str(key) for key in part.keys()) if isinstance(part, dict) else type(part).__name__
                    for part in parts[:4]
                ]
    return shape


class TryOnProvider:
    mode = "abstract"

    def edit(
        self,
        person_image: Path,
        garment_image: Path,
        mask_image: Path,
        prompt: str,
        output_dir: Path,
    ) -> dict[str, Any]:
        raise NotImplementedError


class OpenAIImageEditTryOnProvider(TryOnProvider):
    mode = "openai_image_edit"

    def __init__(self, model: str | None = None) -> None:
        self.model = model or image_edit_model()

    def edit(self, person_image: Path, garment_image: Path, mask_image: Path, prompt: str, output_dir: Path) -> dict[str, Any]:
        try:
            from openai import OpenAI
        except ImportError:
            return {
                "stage": _stage("fail", 0.0, {"provider": self.mode, "model": self.model}, [
                    _issue("image_edit.openai_sdk_missing", "缺少 OpenAI SDK", "请安装 requirements.txt 后重试。")
                ]),
                "image_path": None,
            }

        base_url = _openai_base_url()
        try:
            client = _openai_compatible_client(OpenAI)
            with person_image.open("rb") as person_file, garment_image.open("rb") as garment_file, mask_image.open("rb") as mask_file:
                response = client.images.edit(
                    model=self.model,
                    image=[person_file, garment_file],
                    mask=mask_file,
                    prompt=_build_provider_prompt_with_mask_contract(prompt),
                    size="auto",
                    quality="auto",
                    input_fidelity="high",
                )
            b64_json = response.data[0].b64_json
            if not b64_json:
                return {
                    "stage": _stage("fail", 0.0, {"provider": self.mode, "model": self.model}, [
                        _issue("image_edit.empty_result", "图像编辑没有返回图片", "请稍后重试。")
                    ]),
                    "image_path": None,
                }
            output_path = output_dir / "result.png"
            output_path.write_bytes(base64.b64decode(b64_json))
            return {
                "stage": _stage("pass", 0.82, {"provider": self.mode, "model": self.model, "base_url": base_url, "result_path": str(output_path)}, []),
                "image_path": output_path,
            }
        except Exception as exc:  # pragma: no cover - depends on external API availability
            return {
                "stage": _stage("fail", 0.0, {"provider": self.mode, "model": self.model, "base_url": base_url, "error": str(exc)}, [
                    _issue("image_edit.provider_error", "图像编辑服务调用失败", "请稍后重试，或检查本地授权代理。")
                ]),
                "image_path": None,
            }


class RunwayGoogleTryOnProvider(TryOnProvider):
    mode = "runway_google_generate_content"

    def __init__(self, url: str | None = None, api_key: str | None = None) -> None:
        self.url = url or _runway_google_url()
        self.api_key = api_key or _runway_google_api_key()

    def edit(self, person_image: Path, garment_image: Path, mask_image: Path, prompt: str, output_dir: Path) -> dict[str, Any]:
        if not self.api_key:
            return {
                "stage": _stage("fail", 0.0, {"provider": self.mode, "url": self.url}, [
                    _issue("image_edit.provider_unavailable", "未配置 Runway 图片代理授权", "请配置 Runway Google 代理 key 后再生成。")
                ]),
                "image_path": None,
            }
        try:
            payload = _build_runway_google_tryon_payload(person_image, garment_image, mask_image, prompt)
            response = httpx.post(
                self.url,
                headers={"api-key": self.api_key, "Content-Type": "application/json"},
                json=payload,
                timeout=180,
            )
            response.raise_for_status()
            data = response.json()
            provider_error = _runway_google_error_summary(data)
            if provider_error:
                return {
                    "stage": _stage("fail", 0.0, {
                        "provider": self.mode,
                        "url": self.url,
                        "provider_error": provider_error,
                        "response_shape": _response_shape(data),
                    }, [
                        _issue("image_edit.provider_error", "Runway 图片代理返回错误", "请确认该代理 endpoint 绑定的是支持图片输出的模型。")
                    ]),
                    "image_path": None,
                }
            image_payload = _extract_runway_google_image(data)
            if not image_payload:
                return {
                    "stage": _stage("fail", 0.0, {"provider": self.mode, "url": self.url, "response_shape": _response_shape(data)}, [
                        _issue("image_edit.empty_result", "图片代理没有返回试穿图", "请确认该代理模型已开启图片输出能力。")
                    ]),
                    "image_path": None,
                }
            mime_type, b64_data = image_payload
            raw = base64.b64decode(b64_data)
            image = Image.open(io.BytesIO(raw)).convert("RGB")
            image.load()
            image, canvas_normalization = _fit_image_to_reference_canvas(image, person_image)
            output_path = output_dir / "result_runway_google.png"
            _save_png_atomically(image, output_path)
            return {
                "stage": _stage("pass", 0.82, {
                    "provider": self.mode,
                    "url": self.url,
                    "result_path": str(output_path),
                    "mime_type": mime_type,
                    "target_size": _image_size_evidence(person_image),
                    "result_size": _image_size_evidence(output_path),
                    "canvas_normalization": canvas_normalization,
                    "response_shape": _response_shape(data),
                }, []),
                "image_path": output_path,
            }
        except Exception as exc:  # pragma: no cover - depends on external proxy availability
            return {
                "stage": _stage("fail", 0.0, {"provider": self.mode, "url": self.url, "error": str(exc)}, [
                    _issue("image_edit.provider_error", "Runway 图片代理调用失败", "请检查代理地址、key 或稍后重试。")
                ]),
                "image_path": None,
            }


class UnavailableTryOnProvider(TryOnProvider):
    mode = "ai_image_edit_unavailable"

    def edit(self, person_image: Path, garment_image: Path, mask_image: Path, prompt: str, output_dir: Path) -> dict[str, Any]:
        return {
            "stage": _stage("fail", 0.0, {"provider": self.mode, "required_capability": "OpenAI-compatible images.edit"}, [
                _issue(
                    "image_edit.provider_unavailable",
                    "未接入真实 AI 试穿模型",
                    "请接入支持图片编辑的 AI provider 后再生成试穿图。",
                )
            ]),
            "image_path": None,
        }


class CodexImageGenBridgeTryOnProvider(TryOnProvider):
    mode = "pi_agent_worker"

    def edit(self, person_image: Path, garment_image: Path, mask_image: Path, prompt: str, output_dir: Path) -> dict[str, Any]:
        job = create_codex_bridge_job(
            person_image=person_image,
            garment_image=garment_image,
            mask_image=mask_image,
            prompt=prompt,
            output_dir=output_dir,
        )
        return {
            "stage": _stage("pending", 0.2, {
                "provider": self.mode,
                "bridge_job_id": job["job_id"],
                "job_path": job["job_path"],
                "status_url": f"/try-on/codex-bridge/jobs/{job['job_id']}",
                "worker_started": _start_pi_agent_tryon_worker(job["job_id"]),
                "note": "网页请求已进入本地 Diga/Pi Agent GPT 生图队列，后台 worker 会生成并回填结果。",
            }, []),
            "image_path": None,
        }


class MockTryOnProvider(TryOnProvider):
    mode = "local_mock"

    def edit(self, person_image: Path, garment_image: Path, mask_image: Path, prompt: str, output_dir: Path) -> dict[str, Any]:
        person = Image.open(person_image).convert("RGB")
        garment = Image.open(garment_image).convert("RGB")
        mask = Image.open(mask_image).convert("RGBA")
        edit_region = np.array(mask.getchannel("A")) == 0
        ys, xs = np.where(edit_region)
        if len(xs) == 0:
            return {
                "stage": _stage("fail", 0.0, {"provider": self.mode}, [
                    _issue("image_edit.empty_mask", "上衣区域为空", "请上传上半身更完整的人像照片。")
                ]),
                "image_path": None,
            }
        box = (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))
        garment_alpha = _mock_existing_shirt_alpha(person, edit_region, box) or _mock_garment_alpha(person.size, box)
        edit_alpha = Image.fromarray(edit_region.astype(np.uint8) * 255)
        garment_alpha = Image.fromarray(np.minimum(np.array(garment_alpha), np.array(edit_alpha)).astype(np.uint8))
        garment_alpha = garment_alpha.filter(ImageFilter.GaussianBlur(radius=max(2, int(person.width * 0.003))))
        shirt = _mock_shirt_layer(person, garment, garment_alpha)
        result = Image.alpha_composite(person.convert("RGBA"), shirt).convert("RGB")
        output_path = output_dir / "result_mock.png"
        result.save(output_path, "PNG")
        return {
            "stage": _stage("pass", 0.55, {"provider": self.mode, "result_path": str(output_path), "note": "验证期本地模拟试穿图，仅用于产品链路验收。"}, [
                _issue("image_edit.mock_provider", "当前为验证期模拟试穿图", "接入真实图片编辑代理后可生成更自然的试穿效果。")
            ]),
            "image_path": output_path,
        }


def _mock_garment_alpha(size: tuple[int, int], box: tuple[int, int, int, int]) -> Image.Image:
    width, height = size
    left, top, right, bottom = box
    box_width = max(1, right - left)
    box_height = max(1, bottom - top)
    center_x = (left + right) / 2
    neck_y = top + box_height * 0.08
    shoulder_y = top + box_height * 0.18
    chest_y = top + box_height * 0.38
    hem_y = min(height - 1, top + box_height * 0.88)
    shoulder_half = box_width * 0.34
    chest_half = box_width * 0.27
    hem_half = box_width * 0.24
    sleeve_half = box_width * 0.13
    alpha = Image.new("L", size, 0)
    draw = ImageDraw.Draw(alpha)

    draw.polygon(
        [
            (center_x - shoulder_half, shoulder_y),
            (center_x - chest_half, chest_y),
            (center_x - hem_half, hem_y),
            (center_x + hem_half, hem_y),
            (center_x + chest_half, chest_y),
            (center_x + shoulder_half, shoulder_y),
        ],
        fill=238,
    )
    draw.polygon(
        [
            (center_x - shoulder_half, shoulder_y),
            (center_x - shoulder_half - sleeve_half, shoulder_y + box_height * 0.09),
            (center_x - chest_half - sleeve_half * 0.78, chest_y + box_height * 0.12),
            (center_x - chest_half, chest_y),
        ],
        fill=225,
    )
    draw.polygon(
        [
            (center_x + shoulder_half, shoulder_y),
            (center_x + shoulder_half + sleeve_half, shoulder_y + box_height * 0.09),
            (center_x + chest_half + sleeve_half * 0.78, chest_y + box_height * 0.12),
            (center_x + chest_half, chest_y),
        ],
        fill=225,
    )
    neck_width = box_width * 0.18
    neck_height = box_height * 0.13
    draw.ellipse([center_x - neck_width, neck_y, center_x + neck_width, neck_y + neck_height], fill=0)
    return alpha


def _mock_existing_shirt_alpha(person: Image.Image, edit_region: np.ndarray, box: tuple[int, int, int, int]) -> Image.Image | None:
    left, top, right, bottom = box
    person_rgb = np.array(person.convert("RGB"))
    hsv = cv2.cvtColor(person_rgb, cv2.COLOR_RGB2HSV)
    saturation = hsv[:, :, 1]
    value = hsv[:, :, 2]
    white_like = (saturation < 46) & (value > 188)
    torso_band = np.zeros(edit_region.shape, dtype=bool)
    torso_band[int(top + (bottom - top) * 0.16): int(top + (bottom - top) * 0.92), left:right + 1] = True
    candidate_bool = edit_region & torso_band & white_like
    seed = np.zeros(edit_region.shape, dtype=bool)
    seed_left = int(left + (right - left) * 0.32)
    seed_right = int(left + (right - left) * 0.68)
    seed_top = int(top + (bottom - top) * 0.50)
    seed_bottom = int(top + (bottom - top) * 0.82)
    seed[seed_top:seed_bottom, seed_left:seed_right] = True
    component_input = candidate_bool.astype(np.uint8)
    component_count, labels = cv2.connectedComponents(component_input, connectivity=8)
    seed_labels = labels[seed & candidate_bool]
    if component_count > 1 and seed_labels.size:
        values, counts = np.unique(seed_labels[seed_labels > 0], return_counts=True)
        if values.size:
            selected = int(values[np.argmax(counts)])
            candidate_bool = labels == selected
    candidate = candidate_bool.astype(np.uint8) * 255
    if np.count_nonzero(candidate) < max(1600, int(edit_region.size * 0.012)):
        return None
    kernel = np.ones((17, 17), np.uint8)
    candidate = cv2.morphologyEx(candidate, cv2.MORPH_CLOSE, kernel)
    candidate = cv2.morphologyEx(candidate, cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))
    contours, _ = cv2.findContours(candidate, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    largest = max(contours, key=cv2.contourArea)
    if cv2.contourArea(largest) < max(1600, int(edit_region.size * 0.012)):
        return None
    alpha = np.zeros(candidate.shape, dtype=np.uint8)
    cv2.drawContours(alpha, [largest], -1, 235, thickness=-1)
    alpha = cv2.GaussianBlur(alpha, (0, 0), 2.0)
    return Image.fromarray(alpha)


def _mock_shirt_layer(person: Image.Image, garment: Image.Image, alpha: Image.Image) -> Image.Image:
    base_color = np.array(_dominant_rgb(garment), dtype=np.float32)
    person_rgb = np.array(person.convert("RGB"), dtype=np.float32)
    luminance = np.dot(person_rgb, np.array([0.299, 0.587, 0.114], dtype=np.float32))
    shade = np.clip((luminance - 70) / 180, 0.38, 1.18)
    shirt_rgb = np.clip(base_color[None, None, :] * (0.74 + shade[:, :, None] * 0.34), 0, 255)
    alpha_np = np.array(alpha, dtype=np.float32) / 255.0
    if np.any(alpha_np > 0):
        rng = np.random.default_rng(7)
        noise = rng.normal(0, 2.5, alpha_np.shape).astype(np.float32)
        noise = cv2.GaussianBlur(noise, (0, 0), 1.4)
        shirt_rgb = np.clip(shirt_rgb + noise[:, :, None], 0, 255)
    layer = Image.fromarray(shirt_rgb.astype(np.uint8), "RGB").convert("RGBA")
    layer.putalpha(alpha)
    return layer


def render_tryon_demo_page() -> str:
    model_manifest = _load_tryon_model_manifest()
    page = """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>AI 上衣试穿 Demo</title>
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='10' fill='%23ff4f86'/%3E%3Cpath d='M10 11c2-3 10-3 12 0v10H10V11z' fill='white'/%3E%3C/svg%3E" />
  <style>
    :root {
      --accent: #ff4f86;
      --accent-deep: #e83d73;
      --canvas: #fffafa;
      --page: #f8f2f5;
      --card: #ffffff;
      --soft: #fff1f6;
      --mist: #eefbff;
      --ink: #1c1b20;
      --muted: #8b8388;
      --line: #eee4e8;
      --success: #23835a;
      --warning: #a46a00;
      --negative: #d92c4e;
      --screen-w: 430px;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--ink);
      background:
        radial-gradient(circle at 16% 10%, rgba(255, 185, 218, .22), transparent 32%),
        radial-gradient(circle at 86% 4%, rgba(221, 239, 255, .42), transparent 34%),
        var(--page);
      font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Segoe UI", sans-serif;
      letter-spacing: 0;
    }
    button, input { font: inherit; }
    button { cursor: pointer; }
    .shell {
      width: min(100%, var(--screen-w));
      min-height: 100vh;
      margin: 0 auto;
      background:
        radial-gradient(circle at 82% 10%, rgba(220, 238, 255, .62), transparent 29%),
        radial-gradient(circle at 14% 8%, rgba(255, 190, 220, .45), transparent 30%),
        linear-gradient(180deg, #fff9fc 0%, #faf5f8 100%);
      box-shadow: 0 0 0 1px rgba(0,0,0,.04), 0 20px 80px rgba(48, 20, 28, .08);
      overflow: hidden;
      position: relative;
    }
    .topbar {
      position: sticky;
      top: 0;
      z-index: 20;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 14px 18px 10px;
      background: rgba(255, 250, 253, .84);
      border-bottom: 1px solid rgba(238,228,232,.8);
      backdrop-filter: blur(16px);
    }
    .brand { display: flex; align-items: center; gap: 9px; font-weight: 850; }
    .brand-mark {
      width: 30px;
      height: 30px;
      border-radius: 11px;
      background: linear-gradient(135deg, var(--accent), #a56cff);
      box-shadow: 0 10px 22px rgba(255, 79, 134, .22);
    }
    .top-step { color: var(--muted); font-size: 12px; font-weight: 750; }
    .top-link { color: var(--accent-deep); font-size: 12px; font-weight: 800; text-decoration: none; }
    .page {
      min-height: calc(100vh - 64px);
      padding: 0 18px 132px;
      display: none;
      animation: pageIn .28s ease both;
    }
    .page.active { display: block; }
    @keyframes pageIn {
      from { opacity: 0; transform: translateY(12px); }
      to { opacity: 1; transform: translateY(0); }
    }
    .hero { padding: 0 0 22px; }
    .hero-art {
      min-height: 268px;
      border-radius: 8px;
      position: relative;
      overflow: hidden;
      background:
        radial-gradient(circle at 18% 88%, rgba(255, 79, 134, .34) 0 13%, transparent 31%),
        radial-gradient(circle at 82% 16%, rgba(150, 221, 255, .36), transparent 28%),
        linear-gradient(135deg, #fff7fb, #f2fbff);
      box-shadow: 0 18px 48px rgba(82, 42, 61, .09);
    }
    .hero-art::before {
      content: "";
      position: absolute;
      inset: 0;
      background:
        linear-gradient(112deg, rgba(255,255,255,.86) 0 27%, rgba(255,255,255,.28) 53%, rgba(255,255,255,.88) 100%);
    }
    .hero-orbit { display: none; }
    .hero-device {
      position: absolute;
      left: 26px;
      top: 24px;
      width: 138px;
      height: 184px;
      border-radius: 8px;
      background: rgba(255,255,255,.72);
      box-shadow: 0 22px 50px rgba(56, 27, 36, .16);
      overflow: hidden;
      backdrop-filter: blur(12px);
    }
    .hero-device::after {
      content: "今日试穿";
      position: absolute;
      left: 12px;
      right: 12px;
      bottom: 12px;
      padding: 8px 10px;
      border-radius: 999px;
      background: rgba(255,255,255,.82);
      color: var(--accent-deep);
      font-size: 12px;
      font-weight: 800;
      text-align: center;
      box-shadow: 0 10px 24px rgba(69, 28, 44, .12);
      backdrop-filter: blur(10px);
    }
    .hero-device img {
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
    }
    .hero-card {
      position: absolute;
      right: 18px;
      top: 26px;
      width: 176px;
      padding: 16px;
      border-radius: 8px;
      background: rgba(255,255,255,.82);
      border: 1px solid rgba(255,255,255,.84);
      box-shadow: 0 18px 42px rgba(44, 25, 31, .13);
      color: #7a2738;
      backdrop-filter: blur(14px);
    }
    .hero-card small { display: block; color: var(--muted); margin-bottom: 6px; }
    .hero-card b { display: block; font-size: 16px; line-height: 1.25; }
    .hero-swatches { display: flex; gap: 7px; margin-top: 14px; }
    .hero-swatches span {
      width: 28px;
      height: 28px;
      border-radius: 50%;
      background: var(--swatch);
      border: 2px solid rgba(255,255,255,.88);
      box-shadow: 0 6px 14px rgba(32, 24, 28, .14);
    }
    .title { text-align: center; padding-top: 22px; }
    h1 { margin: 0; font-size: 30px; line-height: 1.12; font-weight: 800; }
    h1 span { color: var(--accent); display: block; }
    .subtitle { margin: 14px auto 0; max-width: 520px; color: var(--muted); font-size: 15px; line-height: 1.65; }
    .trust-row { display: flex; flex-wrap: wrap; justify-content: center; gap: 9px; margin-top: 16px; }
    .trust-pill {
      border: 1px solid rgba(232, 207, 212, .8);
      border-radius: 999px;
      padding: 8px 10px;
      background: rgba(255,255,255,.72);
      color: var(--muted);
      font-size: 12px;
      font-weight: 650;
    }
    .panel, .result, .feature-card {
      border-radius: 24px;
      background: linear-gradient(180deg, rgba(255,255,255,.96), rgba(255,250,253,.9));
      border: 1px solid rgba(255,255,255,.9);
      box-shadow: 0 18px 48px rgba(82, 42, 61, .09);
    }
    .panel { padding: 16px; display: grid; gap: 14px; }
    .feature-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin-top: 14px; }
    .feature-card { min-height: 86px; padding: 14px; display: grid; align-content: space-between; }
    .feature-card b { font-size: 14px; }
    .feature-card span { color: var(--muted); font-size: 12px; line-height: 1.45; }
    .section-title { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
    .section-title b { font-size: 16px; }
    .section-title small { color: var(--muted); font-size: 12px; }
    .current-model {
      display: grid;
      grid-template-columns: 84px 1fr;
      gap: 12px;
      align-items: center;
      border: 1px solid var(--line);
      border-radius: 20px;
      background:
        radial-gradient(circle at 90% 8%, rgba(238, 251, 255, .9), transparent 40%),
        linear-gradient(180deg, #fff 0%, #fff5fa 100%);
      padding: 10px;
    }
    .current-model img { width: 84px; height: 110px; object-fit: cover; border-radius: 16px; background: #f4eeee; }
    .current-model b { display: block; font-size: 18px; line-height: 1.2; margin-bottom: 6px; }
    .current-model span { display: block; color: var(--muted); font-size: 12px; line-height: 1.45; }
    .model-toggle, .ghost-button {
      width: 100%;
      border: 1px solid #f2c6cc;
      color: var(--accent-deep);
      background: #fff;
      padding: 13px 16px;
      border-radius: 999px;
      font-weight: 750;
      box-shadow: none;
    }
    .model-toggle { display: none; }
    .model-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; max-height: 360px; overflow: auto; padding: 2px; }
    #pageModel .model-grid { max-height: 230px; }
    .model-card {
      border: 1px solid var(--line);
      border-radius: 16px;
      background: #fff;
      color: var(--ink);
      padding: 7px;
      font-size: 12px;
      font-weight: 700;
      display: grid;
      gap: 6px;
      text-align: center;
    }
    .model-card.active { outline: 2px solid var(--accent); background: linear-gradient(180deg, #fff, var(--soft)); }
    .model-card img { width: 100%; aspect-ratio: 3 / 4; object-fit: cover; border-radius: 12px; background: #f4eeee; }
    .upload-box { display: grid; gap: 10px; }
    .file-input { display: none; }
    .upload-tile {
      border: 1.5px dashed #f0b7c0;
      border-radius: 22px;
      min-height: 138px;
      background:
        radial-gradient(circle at 92% 10%, rgba(238, 251, 255, .88), transparent 36%),
        linear-gradient(180deg, #fff 0%, #fff5fa 100%);
      display: grid;
      place-items: center;
      text-align: center;
      padding: 16px;
      color: var(--muted);
      cursor: pointer;
      overflow: hidden;
      transition: border-color .18s ease, background .18s ease, box-shadow .18s ease, transform .18s ease;
    }
    .upload-tile.drag-over {
      border-color: var(--accent);
      background:
        radial-gradient(circle at 92% 10%, rgba(238, 251, 255, .94), transparent 36%),
        linear-gradient(180deg, #fff 0%, #fff0f6 100%);
      box-shadow: 0 14px 34px rgba(255, 79, 134, .16);
      transform: translateY(-1px);
    }
    .upload-tile strong { display: block; color: var(--ink); font-size: 16px; margin-bottom: 4px; }
    .upload-tile img { width: 100%; max-height: 188px; object-fit: contain; display: none; border-radius: 14px; background: #f4eeee; }
    #pageModel .upload-tile { min-height: 112px; }
    #pageModel .upload-tile img { max-height: 132px; }
    .sample-garments { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
    .sample-garment {
      border: 1px solid var(--line);
      border-radius: 16px;
      background: #fff;
      padding: 7px;
      display: grid;
      gap: 6px;
      color: var(--ink);
      font-size: 11px;
      font-weight: 750;
      text-align: center;
    }
    .sample-garment.active { outline: 2px solid var(--accent); background: linear-gradient(180deg, #fff, var(--soft)); }
    .sample-garment img { width: 100%; aspect-ratio: 1; object-fit: contain; border-radius: 12px; background: #fffafa; }
    .cta {
      width: 100%;
      border: 0;
      color: #fff;
      padding: 18px 22px;
      border-radius: 999px;
      font-weight: 800;
      font-size: 16px;
      letter-spacing: 0;
      text-transform: none;
      background: linear-gradient(135deg, var(--accent), #ff78a6);
      box-shadow: 0 16px 30px rgba(255, 79, 134, .24);
    }
    .cta:disabled { opacity: .52; cursor: not-allowed; box-shadow: none; }
    .sticky-cta {
      margin-top: 20px;
    }
    .secondary-row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .status-line { min-height: 22px; color: var(--muted); font-size: 13px; line-height: 1.55; }
    .divider { height: 1px; background: var(--line); border: 0; margin: 2px 0; }
    .url-row { display: grid; gap: 10px; }
    input[type=url] {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 13px 16px;
      background: #fff;
      color: var(--ink);
      outline: none;
    }
    input[type=url]:focus { border-color: #f0a3b0; box-shadow: 0 0 0 4px rgba(255, 79, 134, .1); }
    .stage-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-top: 12px; }
    .stage {
      min-height: 86px;
      border-radius: 18px;
      background: linear-gradient(180deg, rgba(255,255,255,.96), rgba(255,250,253,.9));
      box-shadow: 0 12px 30px rgba(78, 47, 57, .07);
      padding: 13px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }
    .stage b { font-size: 13px; }
    .badge { align-self: flex-start; border-radius: 999px; padding: 4px 9px; font-size: 12px; font-weight: 750; background: #edf8f3; color: var(--success); }
    .badge.warn, .badge.unknown { background: #fff5dd; color: var(--warning); }
    .badge.fail { background: #ffe9ed; color: var(--negative); }
    .result { margin-top: 14px; padding: 18px; }
    .result.primary { margin-top: 0; }
    .result-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 14px; }
    .result-head b { font-size: 17px; }
    .result-head span { color: var(--muted); font-size: 12px; }
    .result-grid { display: grid; gap: 12px; }
    .output-frame {
      min-height: 360px;
      border-radius: 20px;
      background:
        radial-gradient(circle at 88% 10%, rgba(238, 251, 255, .78), transparent 42%),
        #fff7fa;
      border: 1px solid var(--line);
      overflow: hidden;
      display: grid;
      place-items: center;
      color: var(--muted);
      font-size: 13px;
    }
    .output-frame img { width: 100%; height: 100%; max-height: 520px; object-fit: contain; display: none; }
    .debug-details {
      margin-top: 14px;
      border: 1px solid var(--line);
      border-radius: 18px;
      background: rgba(255,255,255,.72);
      overflow: hidden;
    }
    .debug-details summary {
      list-style: none;
      cursor: pointer;
      padding: 14px 16px;
      color: var(--accent-deep);
      font-size: 14px;
      font-weight: 800;
    }
    .debug-details summary::-webkit-details-marker { display: none; }
    .debug-body { display: grid; gap: 12px; padding: 0 12px 12px; }
    pre {
      max-height: 300px;
      overflow: auto;
      background: #fffafa;
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 12px;
      white-space: pre-wrap;
      color: #5f555a;
      font-size: 12px;
      line-height: 1.45;
    }
    .xhs-results { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }
    .xhs-card {
      appearance: none;
      border: 1px solid var(--line);
      border-radius: 14px;
      background: #fffafa;
      padding: 10px;
      text-align: left;
      cursor: pointer;
      color: inherit;
      transition: border-color .16s ease, box-shadow .16s ease, transform .16s ease;
    }
    .xhs-card:disabled { cursor: default; opacity: .62; filter: grayscale(.12); }
    .xhs-card:not(:disabled):hover { border-color: #f2b5c6; box-shadow: 0 12px 28px rgba(82, 42, 61, .08); transform: translateY(-1px); }
    .xhs-card.active { border-color: var(--accent); background: var(--soft-rose); box-shadow: 0 14px 30px rgba(255, 79, 134, .14); }
    .xhs-results img { width: 100%; max-height: 280px; object-fit: contain; border-radius: 12px; background: #f4eeee; }
    .xhs-results p { margin: 8px 0 0; color: var(--muted); font-size: 12px; }
    .mode-grid, .photo-mode-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; }
    .mode-chip, .photo-chip {
      border: 1px solid var(--line);
      border-radius: 999px;
      background: #fff;
      color: var(--muted);
      padding: 11px 10px;
      font-size: 12px;
      font-weight: 800;
    }
    .mode-chip.active, .photo-chip.active { border-color: #f2b5c6; background: var(--soft); color: var(--accent-deep); }
    .outfit-picker { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }
    .outfit-card {
      border: 1px solid var(--line);
      border-radius: 16px;
      background: #fffafa;
      padding: 8px;
      text-align: left;
      color: inherit;
    }
    .outfit-card.active { outline: 2px solid var(--accent); background: var(--soft); }
    .outfit-card img { width: 100%; aspect-ratio: 1; object-fit: contain; border-radius: 12px; background: #fff; }
    .outfit-card span { display: block; margin-top: 6px; color: var(--muted); font-size: 12px; font-weight: 750; }
    .outfit-upload-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }
    .outfit-upload-grid .upload-tile { min-height: 118px; border-radius: 18px; }
    .outfit-upload-grid .upload-tile img { max-height: 118px; }
    .bottom-nav {
      position: fixed;
      left: 50%;
      bottom: 0;
      z-index: 24;
      width: min(100%, var(--screen-w));
      transform: translateX(-50%);
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 6px;
      padding: 8px 12px 10px;
      background: rgba(255,250,253,.9);
      border-top: 1px solid rgba(238,228,232,.9);
      backdrop-filter: blur(18px);
    }
    .nav-btn {
      border: 0;
      border-radius: 16px;
      background: transparent;
      color: var(--muted);
      padding: 8px 4px;
      font-size: 12px;
      font-weight: 800;
    }
    .nav-btn.active { background: var(--soft); color: var(--accent-deep); }
    @media (min-width: 861px) {
      body { padding: 24px 0; }
      .shell { min-height: calc(100vh - 48px); border-radius: 34px; }
      .bottom-nav { bottom: 24px; border-radius: 0 0 34px 34px; }
    }
    @media (max-width: 430px) {
      .page { padding-left: 16px; padding-right: 16px; }
      .hero-device { width: 128px; height: 170px; }
      .hero-card { width: 178px; right: 12px; }
      h1 { font-size: 29px; }
    }
  </style>
</head>
<body>
  <main class="shell">
    <div class="topbar">
      <div class="brand"><span class="brand-mark"></span><span>AI 试穿</span></div>
      <div style="display:flex;align-items:center;gap:10px;"><a class="top-link" href="/closet/demo">我的衣橱</a><div class="top-step" id="topStep">首页</div></div>
    </div>

    <section class="page active" id="pageHome">
      <section class="hero">
        <div class="hero-art">
          <div class="hero-orbit"></div>
          <div class="hero-device"><img id="heroModelPreview" alt="默认模特预览" /></div>
          <div class="hero-card">
            <small>像修图一样试衣</small>
            <b>一键换上衣，保留人像氛围感</b>
            <div class="hero-swatches">
              <span style="--swatch:#ffffff"></span>
              <span style="--swatch:#ff4f86"></span>
              <span style="--swatch:#ffe7a9"></span>
              <span style="--swatch:#7be8ef"></span>
            </div>
          </div>
        </div>
        <div class="title">
          <h1>AI 上衣<span>试穿</span></h1>
          <p class="subtitle">先选人像，再放入上衣，快速看一眼颜色、版型和整体氛围是否适合自己。</p>
        </div>
        <div class="trust-row">
          <span class="trust-pill">0 门槛试穿</span>
          <span class="trust-pill">背景保护</span>
          <span class="trust-pill">小红书取图</span>
        </div>
        <div class="feature-grid">
          <div class="feature-card"><b>默认模特</b><span>中等男模已准备好，也可以切换其它体型。</span></div>
          <div class="feature-card"><b>上衣素材</b><span>上传本地图片，或从小红书链接提取。</span></div>
        </div>
      </section>
      <button class="cta sticky-cta" data-page="pageUpload">开始试穿</button>
    </section>

    <section class="page" id="pageModel">
      <section class="panel">
        <div class="section-title"><b>选择试穿对象</b><small>01 / 04</small></div>
        <div class="model-picker">
          <div class="current-model">
            <img id="currentModelThumb" alt="当前模特" />
            <div>
              <b id="currentModelName">中等男模 1</b>
              <span id="currentModelDesc">默认试穿人像</span>
            </div>
          </div>
          <button id="modelToggleBtn" class="model-toggle" type="button">切换模特</button>
          <div class="model-grid" id="modelGrid"></div>
        </div>
        <div class="upload-box">
          <label class="upload-tile" for="personInput">
            <span id="personUploadHint"><strong>上传本人照片</strong>可选；上传后覆盖当前模特</span>
            <img id="personPreview" alt="本人照片预览" />
          </label>
          <input id="personInput" class="file-input" type="file" accept="image/*" />
        </div>
        <button class="cta" data-page="pageUpload">下一步：选择上衣</button>
      </section>
    </section>

    <section class="page" id="pageUpload">
      <section class="panel">
        <div class="upload-box">
          <div class="section-title"><b>上传目标上衣</b><small>02 / 04</small></div>
          <label class="upload-tile" for="garmentInput">
            <span id="garmentEmpty"><strong>选择上衣图</strong>单件上衣或穿搭图都可以，也可以拖拽图片到这里</span>
            <img id="garmentPreview" alt="上衣预览" />
          </label>
          <input id="garmentInput" class="file-input" type="file" accept="image/*" />
        </div>
        <div class="upload-box">
          <div class="section-title"><b>测试上衣素材</b><small>本地样例</small></div>
          <div class="sample-garments" id="sampleGarments"></div>
        </div>
        <hr class="divider" />
        <div class="upload-box">
          <div class="section-title"><b>整套试穿</b><small>上衣 / 下装 / 鞋</small></div>
          <div class="mode-grid">
            <button type="button" class="mode-chip active" data-tryon-mode="top">上衣试穿</button>
            <button type="button" class="mode-chip" data-tryon-mode="outfit">整套试穿</button>
          </div>
          <div class="photo-mode-grid" id="photoModeGrid">
            <button type="button" class="photo-chip active" data-photo-mode="standard">普通全身</button>
            <button type="button" class="photo-chip" data-photo-mode="mirror_selfie">对镜拍</button>
            <button type="button" class="photo-chip" data-photo-mode="face_covered">挡脸拍</button>
            <button type="button" class="photo-chip" data-photo-mode="scene_photo">场景拍</button>
          </div>
          <button id="loadOutfitsBtn" class="ghost-button" type="button">加载已保存搭配</button>
          <div class="outfit-picker" id="outfitPicker"><p class="status-line" style="grid-column:1/-1;">可以加载衣橱搭配，或直接上传下面四张图。</p></div>
          <div class="outfit-upload-grid">
            <label class="upload-tile" for="styleReferenceInput"><span><strong>整体灵感图</strong>穿法和比例参考</span><img id="styleReferencePreview" alt="整体灵感图预览" /></label>
            <label class="upload-tile" for="outfitTopInput"><span><strong>上装</strong>上衣或外套</span><img id="outfitTopPreview" alt="上装预览" /></label>
            <label class="upload-tile" for="outfitBottomInput"><span><strong>下装</strong>裤子或裙子</span><img id="outfitBottomPreview" alt="下装预览" /></label>
            <label class="upload-tile" for="outfitShoesInput"><span><strong>鞋子</strong>双脚穿着参考</span><img id="outfitShoesPreview" alt="鞋子预览" /></label>
          </div>
          <input id="styleReferenceInput" class="file-input" type="file" accept="image/*" />
          <input id="outfitTopInput" class="file-input" type="file" accept="image/*" />
          <input id="outfitBottomInput" class="file-input" type="file" accept="image/*" />
          <input id="outfitShoesInput" class="file-input" type="file" accept="image/*" />
        </div>
        <button id="runBtn" class="cta" disabled>生成试穿图</button>
        <p id="message" class="status-line">请先选择目标上衣。</p>
        <hr class="divider" />
        <div class="url-row">
          <div class="section-title"><b>小红书取图</b><small>素材入口</small></div>
          <input id="xhsInput" type="url" placeholder="粘贴小红书链接" />
          <button id="xhsBtn" class="ghost-button">解析链接并提取上衣</button>
          <p id="xhsMessage" class="status-line">支持笔记链接和图片 CDN 链接；私密或登录内容可能只能抓到封面。</p>
          <div class="xhs-results" id="xhsResults"></div>
        </div>
      </section>
    </section>

    <section class="page" id="pageResult">
      <section>
        <div class="result primary">
          <div class="result-head"><b>试穿结果</b><span>生成后优先看这里</span></div>
          <div class="result-grid">
            <div class="output-frame"><span id="resultPlaceholder">生成后在这里预览试穿效果</span><img id="resultImage" alt="试穿结果" /></div>
          </div>
          <details class="debug-details">
            <summary>检查详情</summary>
            <div class="debug-body">
              <div class="stage-grid" id="stages"></div>
              <div class="output-frame"><span id="maskPlaceholder">等待生成区域预览</span><img id="maskImage" alt="上衣区域预览" /></div>
              <pre id="jsonOut">{}</pre>
            </div>
          </details>
        </div>
      </section>
    </section>

    <nav class="bottom-nav">
      <button class="nav-btn active" data-page="pageHome">首页</button>
      <button class="nav-btn" data-page="pageModel">模特</button>
      <button class="nav-btn" data-page="pageUpload">上衣</button>
      <button class="nav-btn" data-page="pageResult">结果</button>
    </nav>
  </main>
  <script>
    const modelFixtures = __MODEL_FIXTURES__;
    const testGarments = [
      { file: "spring_mint_cardigan.png", name: "春季开衫" },
      { file: "summer_coral_tshirt.png", name: "珊瑚T恤" },
      { file: "summer_sky_linen_shirt.png", name: "蓝色衬衫" },
      { file: "autumn_camel_ribbed_sweater.png", name: "驼色毛衣" },
      { file: "autumn_burgundy_hoodie.png", name: "酒红卫衣" },
      { file: "winter_navy_quilted_jacket.png", name: "深蓝夹克" }
    ];
    const defaultModelFile = "male_medium_1.png";
    const stages = {
      input_quality: "输入质量",
      person_detection: "人像状态",
      garment_analysis: "衣服要素",
      upper_body_mask: "上衣区域",
      image_edit: "试穿生成",
      quality_review: "结果检查"
    };
    const personInput = document.getElementById("personInput");
    const garmentInput = document.getElementById("garmentInput");
    const styleReferenceInput = document.getElementById("styleReferenceInput");
    const outfitTopInput = document.getElementById("outfitTopInput");
    const outfitBottomInput = document.getElementById("outfitBottomInput");
    const outfitShoesInput = document.getElementById("outfitShoesInput");
    const runBtn = document.getElementById("runBtn");
    const modelToggleBtn = document.getElementById("modelToggleBtn");
    const xhsBtn = document.getElementById("xhsBtn");
    const loadOutfitsBtn = document.getElementById("loadOutfitsBtn");
    const xhsInput = document.getElementById("xhsInput");
    const xhsMessage = document.getElementById("xhsMessage");
    const message = document.getElementById("message");
    const jsonOut = document.getElementById("jsonOut");
    let selectedModel = modelFixtures.items.find(item => item.file === defaultModelFile) || modelFixtures.items[0];
    let uploadedPersonFile = null;
    let selectedSampleGarment = null;
    let selectedInspirationSourcePath = null;
    let selectedInspirationStyleBrief = "";
    let tryonMode = "top";
    let selectedPhotoMode = "standard";
    let selectedOutfitId = null;
    let availableOutfits = [];
    const pageNames = {
      pageHome: "首页",
      pageModel: "选择模特",
      pageUpload: "选择服饰",
      pageResult: "生成结果"
    };
    function showPage(pageId) {
      document.querySelectorAll(".page").forEach(page => {
        const active = page.id === pageId;
        page.classList.toggle("active", active);
        page.toggleAttribute("inert", !active);
        page.setAttribute("aria-hidden", String(!active));
      });
      document.querySelectorAll("[data-page]").forEach(btn => btn.classList.toggle("active", btn.dataset.page === pageId && btn.classList.contains("nav-btn")));
      document.getElementById("topStep").textContent = pageNames[pageId] || "";
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
    function bindPreview(input, imageId) {
      input.addEventListener("change", () => {
        const img = document.getElementById(imageId);
        const span = img.parentElement.querySelector("span");
        if (input.files && input.files[0]) {
          if (input === personInput) uploadedPersonFile = input.files[0];
          if (input === garmentInput) {
            tryonMode = "top";
            document.querySelectorAll("[data-tryon-mode]").forEach(item => item.classList.toggle("active", item.dataset.tryonMode === tryonMode));
            selectedSampleGarment = null;
            selectedInspirationSourcePath = null;
            selectedInspirationStyleBrief = "";
          }
          if ([styleReferenceInput, outfitTopInput, outfitBottomInput, outfitShoesInput].includes(input)) {
            selectedOutfitId = null;
            tryonMode = "outfit";
            document.querySelectorAll("[data-tryon-mode]").forEach(item => item.classList.toggle("active", item.dataset.tryonMode === tryonMode));
          }
          img.src = URL.createObjectURL(input.files[0]);
          img.style.display = "block";
          span.style.display = "none";
        }
        updateRunButton();
      });
    }
    function setInputFile(input, file) {
      const transfer = new DataTransfer();
      transfer.items.add(file);
      input.files = transfer.files;
      input.dispatchEvent(new Event("change", { bubbles: true }));
    }
    function bindDropUpload(tile, input, options = {}) {
      const stop = event => {
        event.preventDefault();
        event.stopPropagation();
      };
      ["dragenter", "dragover"].forEach(type => {
        tile.addEventListener(type, event => {
          stop(event);
          tile.classList.add("drag-over");
        });
      });
      ["dragleave", "dragend"].forEach(type => {
        tile.addEventListener(type, event => {
          stop(event);
          tile.classList.remove("drag-over");
        });
      });
      tile.addEventListener("drop", event => {
        stop(event);
        tile.classList.remove("drag-over");
        const file = event.dataTransfer?.files?.[0];
        if (!file) return;
        if (!file.type.startsWith("image/")) {
          message.textContent = options.invalidMessage || "请拖入图片文件。";
          return;
        }
        if (file.size > 12 * 1024 * 1024) {
          message.textContent = "图片太大了，请换一张 12MB 以内的图片。";
          return;
        }
        setInputFile(input, file);
        message.textContent = options.successMessage || "已添加图片。";
      });
    }
    function testGarmentUrl(file) {
      return `/tryon-outputs/test_garments/${encodeURIComponent(file)}`;
    }
    function updateRunButton() {
      const hasTopInput = Boolean(garmentInput.files?.[0] || selectedSampleGarment);
      const hasDirectOutfit = Boolean(styleReferenceInput.files?.[0] && outfitTopInput.files?.[0] && outfitBottomInput.files?.[0] && outfitShoesInput.files?.[0]);
      const hasSavedOutfit = Boolean(selectedOutfitId);
      runBtn.disabled = tryonMode === "outfit" ? !(hasSavedOutfit || hasDirectOutfit) : !hasTopInput;
    }
    function modelUrl(file) {
      return `/tryon-models/${encodeURIComponent(file)}?v=fullbody-20260704`;
    }
    function setPersonPreview(src) {
      const img = document.getElementById("personPreview");
      const span = img.parentElement.querySelector("span");
      img.src = src;
      img.style.display = "block";
      span.style.display = "none";
      document.getElementById("heroModelPreview").src = src;
    }
    function updateSelectedModelUI() {
      if (!selectedModel) return;
      document.getElementById("currentModelThumb").src = modelUrl(selectedModel.file);
      document.getElementById("currentModelName").textContent = `${selectedModel.gender_label}${selectedModel.body_type_label}模特 ${selectedModel.variant}`;
      document.getElementById("currentModelDesc").textContent = selectedModel.description || "默认试穿人像";
    }
    function renderModels() {
      document.getElementById("modelGrid").innerHTML = modelFixtures.items.map(item => {
        const active = item.file === selectedModel.file ? " active" : "";
        return `<button type="button" class="model-card${active}" data-model="${item.file}"><img src="${modelUrl(item.file)}" alt="${item.description}"><span>${item.gender_label}${item.body_type_label} ${item.variant}</span></button>`;
      }).join("");
      document.querySelectorAll("[data-model]").forEach(btn => {
        btn.addEventListener("click", () => {
          selectedModel = modelFixtures.items.find(item => item.file === btn.dataset.model);
          uploadedPersonFile = null;
          personInput.value = "";
          setPersonPreview(modelUrl(selectedModel.file));
          updateSelectedModelUI();
          renderModels();
          message.textContent = `当前模特：${selectedModel.description}`;
        });
      });
      updateSelectedModelUI();
    }
    function renderTestGarments() {
      document.getElementById("sampleGarments").innerHTML = testGarments.map(item => {
        const active = selectedSampleGarment?.file === item.file ? " active" : "";
        return `<button type="button" class="sample-garment${active}" data-garment="${item.file}"><img src="${testGarmentUrl(item.file)}" alt="${item.name}"><span>${item.name}</span></button>`;
      }).join("");
      document.querySelectorAll("[data-garment]").forEach(btn => {
        btn.addEventListener("click", () => {
          selectedSampleGarment = testGarments.find(item => item.file === btn.dataset.garment);
          tryonMode = "top";
          document.querySelectorAll("[data-tryon-mode]").forEach(item => item.classList.toggle("active", item.dataset.tryonMode === tryonMode));
          selectedInspirationSourcePath = null;
          selectedInspirationStyleBrief = "";
          garmentInput.value = "";
          const img = document.getElementById("garmentPreview");
          const span = document.getElementById("garmentEmpty");
          img.src = testGarmentUrl(selectedSampleGarment.file);
          img.style.display = "block";
          span.style.display = "none";
          renderTestGarments();
          updateRunButton();
          message.textContent = `已选择测试上衣：${selectedSampleGarment.name}`;
        });
      });
    }
    async function renderOutfits() {
      try {
        const res = await fetch("/closet/outfits");
        if (!res.ok) return;
        const data = await res.json();
        availableOutfits = data.outfits || [];
        const picker = document.getElementById("outfitPicker");
        if (!availableOutfits.length) {
          picker.innerHTML = `<p class="status-line" style="grid-column:1/-1;">暂无已保存搭配，也可以直接上传下面四张图。</p>`;
          return;
        }
        picker.innerHTML = availableOutfits.slice(0, 4).map(outfit => {
          const active = selectedOutfitId === outfit.outfit_id ? " active" : "";
          const cover = outfit.cover_path || outfit.layout_snapshot_path || "";
          return `<button type="button" class="outfit-card${active}" data-outfit-id="${outfit.outfit_id}">${cover ? `<img src="${cover}" alt="${escapeAttr(outfit.title || "搭配")}">` : ""}<span>${outfit.title || "我的搭配"}</span></button>`;
        }).join("");
        document.querySelectorAll("[data-outfit-id]").forEach(btn => {
          btn.addEventListener("click", () => {
            selectedOutfitId = btn.dataset.outfitId;
            tryonMode = "outfit";
            document.querySelectorAll("[data-tryon-mode]").forEach(item => item.classList.toggle("active", item.dataset.tryonMode === tryonMode));
            renderOutfits();
            updateRunButton();
            message.textContent = "已选择整套搭配，可以生成完整试穿图。";
          });
        });
      } catch (error) {
        document.getElementById("outfitPicker").innerHTML = "";
      }
    }
    function renderStages(pipeline = {}) {
      document.getElementById("stages").innerHTML = Object.entries(stages).map(([key, label]) => {
        const status = pipeline[key]?.status || "unknown";
        const text = status === "pass" ? "通过" : status === "warn" ? "提示" : status === "fail" ? "失败" : status === "pending" ? "等待" : "等待";
        return `<div class="stage"><b>${label}</b><span class="badge ${status}">${text}</span></div>`;
      }).join("");
    }
    function setResultImage(src) {
      document.getElementById("resultImage").src = src || "";
      document.getElementById("resultImage").style.display = src ? "block" : "none";
      document.getElementById("resultPlaceholder").style.display = src ? "none" : "block";
    }
    function setMaskImage(src) {
      document.getElementById("maskImage").src = src || "";
      document.getElementById("maskImage").style.display = src ? "block" : "none";
      document.getElementById("maskPlaceholder").style.display = src ? "none" : "block";
    }
    async function pollBridgeJob(jobId) {
      let attempts = 0;
      const maxAttempts = 180;
      const tick = async () => {
        attempts += 1;
        try {
          const res = await fetch(`/try-on/codex-bridge/jobs/${encodeURIComponent(jobId)}`);
          const job = await res.json();
          jsonOut.textContent = JSON.stringify(job, null, 2);
          if (job.status === "completed" && job.result?.public_image_path) {
            setResultImage(job.result.public_image_path);
            message.textContent = "试穿结果已生成。";
            return;
          }
          if (job.status === "failed") {
            message.textContent = job.result?.message || "生成失败，请重试。";
            return;
          }
          if (job.status === "running") {
            message.textContent = `本地 Diga/Pi Agent 正在生成试穿图... ${attempts}`;
          } else {
            message.textContent = `已提交到本地 Diga/Pi Agent，等待处理中... ${attempts}`;
          }
        } catch (error) {
          message.textContent = error.message || "等待生成结果时出错";
        }
        if (attempts < maxAttempts) window.setTimeout(tick, 2000);
      };
      tick();
    }
    bindPreview(personInput, "personPreview");
    bindPreview(garmentInput, "garmentPreview");
    bindPreview(styleReferenceInput, "styleReferencePreview");
    bindPreview(outfitTopInput, "outfitTopPreview");
    bindPreview(outfitBottomInput, "outfitBottomPreview");
    bindPreview(outfitShoesInput, "outfitShoesPreview");
    bindDropUpload(document.querySelector('label[for="garmentInput"]'), garmentInput, {
      successMessage: "已拖入上衣图片。",
      invalidMessage: "请拖入 JPG、PNG 或 WebP 图片。"
    });
    bindDropUpload(document.querySelector('label[for="personInput"]'), personInput, {
      successMessage: "已拖入本人照片。",
      invalidMessage: "请拖入 JPG、PNG 或 WebP 图片。"
    });
    [
      ["styleReferenceInput", styleReferenceInput, "已拖入整体灵感图。"],
      ["outfitTopInput", outfitTopInput, "已拖入上装图片。"],
      ["outfitBottomInput", outfitBottomInput, "已拖入下装图片。"],
      ["outfitShoesInput", outfitShoesInput, "已拖入鞋子图片。"]
    ].forEach(([id, input, successMessage]) => {
      bindDropUpload(document.querySelector(`label[for="${id}"]`), input, {
        successMessage,
        invalidMessage: "请拖入 JPG、PNG 或 WebP 图片。"
      });
    });
    document.querySelectorAll("[data-page]").forEach(btn => btn.addEventListener("click", () => showPage(btn.dataset.page)));
    document.querySelectorAll("[data-tryon-mode]").forEach(btn => {
      btn.addEventListener("click", () => {
        tryonMode = btn.dataset.tryonMode;
        document.querySelectorAll("[data-tryon-mode]").forEach(item => item.classList.toggle("active", item === btn));
        updateRunButton();
        message.textContent = tryonMode === "outfit" ? "整套试穿需要选择套装，或上传整体图、上装、下装和鞋。" : "上衣试穿需要选择一张目标上衣图。";
      });
    });
    document.querySelectorAll("[data-photo-mode]").forEach(btn => {
      btn.addEventListener("click", () => {
        selectedPhotoMode = btn.dataset.photoMode;
        document.querySelectorAll("[data-photo-mode]").forEach(item => item.classList.toggle("active", item === btn));
      });
    });
    loadOutfitsBtn.addEventListener("click", renderOutfits);
    modelToggleBtn.addEventListener("click", () => {
      showPage("pageModel");
    });
    renderModels();
    renderTestGarments();
    setPersonPreview(modelUrl(selectedModel.file));
    message.textContent = `当前默认模特：${selectedModel.description}`;
    renderStages();
    showPage("pageHome");
    runBtn.addEventListener("click", async () => {
      runBtn.disabled = true;
      message.textContent = "正在生成试穿结果...";
      renderStages();
      const body = new FormData();
      let personFile = uploadedPersonFile;
      if (!personFile) {
        const personResponse = await fetch(modelUrl(selectedModel.file));
        const personBlob = await personResponse.blob();
        personFile = new File([personBlob], selectedModel.file, { type: personBlob.type || "image/png" });
      }
      body.append("person_image", personFile);
      let garmentFile = garmentInput.files[0];
      if (!garmentFile && selectedSampleGarment) {
        const garmentResponse = await fetch(testGarmentUrl(selectedSampleGarment.file));
        const garmentBlob = await garmentResponse.blob();
        garmentFile = new File([garmentBlob], selectedSampleGarment.file, { type: garmentBlob.type || "image/png" });
      }
      let endpoint = "/try-on";
      if (tryonMode === "outfit" && selectedOutfitId) {
        body.append("outfit_id", selectedOutfitId);
        body.append("photo_mode", selectedPhotoMode);
        endpoint = "/try-on/from-outfit";
      } else if (tryonMode === "outfit") {
        body.append("style_reference_image", styleReferenceInput.files[0]);
        body.append("item_images", outfitTopInput.files[0]);
        body.append("item_images", outfitBottomInput.files[0]);
        body.append("item_images", outfitShoesInput.files[0]);
        body.append("photo_mode", selectedPhotoMode);
        body.append("outfit_plan", JSON.stringify({
          title: "直接上传穿搭",
          model_photo_mode: selectedPhotoMode,
          items: [
            { slot: "top", category: "top", wearing_instruction: "穿在模特上半身，保留领口、袖长、衣长、图案和材质。" },
            { slot: "bottom", category: "bottom", wearing_instruction: "穿在模特下半身，保留腰线、裤型或裙型、长度和面料垂坠。" },
            { slot: "shoes", category: "shoes", wearing_instruction: "穿在模特双脚，保留鞋型、颜色和鞋底比例。" }
          ]
        }));
        endpoint = "/try-on/from-outfit-plan";
      } else if (selectedInspirationSourcePath) {
        const inspirationResponse = await fetch(selectedInspirationSourcePath);
        const inspirationBlob = await inspirationResponse.blob();
        const inspirationFile = new File([inspirationBlob], "inspiration_xhs.jpg", { type: inspirationBlob.type || "image/jpeg" });
        body.append("inspiration_image", inspirationFile);
        if (selectedInspirationStyleBrief) body.append("style_brief", selectedInspirationStyleBrief);
        endpoint = "/try-on/from-inspiration";
      } else {
        body.append("garment_image", garmentFile);
      }
      try {
        const res = await fetch(endpoint, { method: "POST", body });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "试穿接口失败");
        showPage("pageResult");
        renderStages(data.pipeline);
        jsonOut.textContent = JSON.stringify(data, null, 2);
        setResultImage(data.result.image_path || "");
        setMaskImage(data.result.mask_path || "");
        message.textContent = data.result.user_message || data.status;
        if (data.status === "pending" && data.result.bridge_job_id) {
          pollBridgeJob(data.result.bridge_job_id);
        }
      } catch (error) {
        message.textContent = error.message || "调用失败";
      } finally {
        updateRunButton();
      }
    });
    xhsBtn.addEventListener("click", async () => {
      const url = xhsInput.value.trim();
      if (!url) {
        xhsMessage.textContent = "请先粘贴小红书链接。";
        return;
      }
      xhsBtn.disabled = true;
      xhsMessage.textContent = "正在解析链接和下载图片...";
      const body = new FormData();
      body.append("url", url);
      try {
        const res = await fetch("/try-on/extract-inspiration", { method: "POST", body });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "链接解析失败");
        jsonOut.textContent = JSON.stringify(data, null, 2);
        const fashionItems = data.fashion_items?.length ? data.fashion_items : data.items.map((item, index) => ({
          item_id: `legacy_${index}`,
          category_label: "上衣",
          clean_reference_path: item.cutout_path,
          cutout_path: item.cutout_path,
          quality: { status: item.has_top ? "review" : "rejected" },
          source: { source_path: item.source_path },
          reason: item.reason
        }));
        const styleBrief = JSON.stringify(data.style_context || {});
        const referenceSheetPath = data.style_context?.reference_sheet_path || "";
        document.getElementById("xhsResults").innerHTML = fashionItems.map((item, index) => {
          const qualityStatus = item.quality?.status || "rejected";
          const reference = item.clean_reference_path || item.cutout_path || "";
          const disabled = reference && qualityStatus !== "rejected" ? "" : " disabled";
          const qualityText = readableQuality(item.quality?.status);
          const sourcePath = referenceSheetPath || item.source?.source_path || "";
          const cutout = reference ? `<img src="${reference}" alt="${item.category_label || "单品"}">` : `<p>未找到稳定上衣</p>`;
          return `<button type="button" class="xhs-card" data-xhs-cutout="${reference}" data-xhs-source="${sourcePath}" data-xhs-style="${escapeAttr(styleBrief)}" data-xhs-index="${index}" data-xhs-category="${item.category || "top"}" data-quality="${qualityStatus}"${disabled}>${cutout}<p>${item.category_label || "单品"} · ${qualityText}</p></button>`;
        }).join("");
        bindXhsCards();
        const extractMessage = String(data.result.message || data.status || "").replace(/[。.]$/, "");
        if (data.note?.title) {
          xhsMessage.textContent = `${extractMessage}，请选择一件上衣：${data.note.title}`;
        } else {
          xhsMessage.textContent = `${extractMessage}，请选择一件上衣。`;
        }
        document.getElementById("xhsResults").scrollIntoView({ block: "nearest", behavior: "smooth" });
      } catch (error) {
        xhsMessage.textContent = error.message || "链接解析失败";
      } finally {
        xhsBtn.disabled = false;
      }
    });
    function bindXhsCards() {
      document.querySelectorAll("[data-xhs-cutout]").forEach(card => {
        card.addEventListener("click", async () => {
          const cutoutPath = card.dataset.xhsCutout;
          const sourcePath = card.dataset.xhsSource;
          const styleBrief = card.dataset.xhsStyle || "";
          if (card.dataset.quality === "rejected") {
            xhsMessage.textContent = "这张图暂不适合试穿，建议换图文笔记里的清晰上衣图。";
            return;
          }
          if (!cutoutPath) return;
          try {
            xhsMessage.textContent = "正在把这件上衣放入试穿区...";
            const response = await fetch(cutoutPath);
            const blob = await response.blob();
            const file = new File([blob], `xhs_top_${card.dataset.xhsIndex || "0"}.png`, { type: blob.type || "image/png" });
            selectedSampleGarment = null;
            tryonMode = "top";
            document.querySelectorAll("[data-tryon-mode]").forEach(item => item.classList.toggle("active", item.dataset.tryonMode === tryonMode));
            setInputFile(garmentInput, file);
            selectedInspirationSourcePath = sourcePath || null;
            selectedInspirationStyleBrief = styleBrief;
            document.querySelectorAll("[data-xhs-cutout]").forEach(item => item.classList.toggle("active", item === card));
            showPage("pageUpload");
            xhsMessage.textContent = "已选择灵感图上衣，可以生成试穿图。";
            message.textContent = selectedInspirationSourcePath ? "已选择灵感图，将由 AI 一步提取上衣并试穿。" : "已选择小红书提取上衣，可以生成试穿图。";
          } catch (error) {
            xhsMessage.textContent = error.message || "选择上衣失败";
          }
        });
      });
    }
    function readableReason(reason) {
      const reasonMap = {
        no_top_found: "未找到清晰上衣",
        no_clear_top: "未找到清晰上衣",
        upper_body_region_unstable: "上半身区域不稳定",
        single_garment_top: "已找到单件上衣",
        person_wearing_top: "已找到上身上衣",
        person_wearing_top_bbox: "已找到上身上衣"
      };
      return reasonMap[reason] || "暂不可用";
    }
    function readableQuality(status) {
      const map = {
        usable: "可试穿",
        review: "需确认",
        rejected: "暂不可用"
      };
      return map[status] || "待确认";
    }
    function escapeAttr(value) {
      return String(value || "").replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
    }
  </script>
</body>
</html>
"""
    return page.replace("__MODEL_FIXTURES__", json.dumps(model_manifest, ensure_ascii=False))


def _read_upload_image(raw: bytes, filename: str | None, role: str) -> dict[str, Any]:
    if not raw:
        raise HTTPException(status_code=400, detail=f"{role} 图片为空")
    if len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail=f"{role} 图片超过 12MB")
    try:
        pil_image = Image.open(io.BytesIO(raw))
        pil_image.load()
    except UnidentifiedImageError as exc:
        raise HTTPException(status_code=400, detail=f"无法识别 {role} 图片格式") from exc
    if pil_image.format not in SUPPORTED_FORMATS:
        raise HTTPException(status_code=400, detail="仅支持 JPG、PNG、WebP")
    image_id = hashlib.sha256(raw).hexdigest()[:16]
    suffix = _suffix_for_format(pil_image.format)
    saved_path = _upload_dir() / f"{role}_{image_id}{suffix}"
    _upload_dir().mkdir(parents=True, exist_ok=True)
    saved_path.write_bytes(raw)
    rgb_image = pil_image.convert("RGB")
    return {
        "image": rgb_image,
        "image_id": image_id,
        "saved_path": saved_path,
        "meta": {
            "filename": filename,
            "saved_path": str(saved_path),
            "format": pil_image.format,
            "width": rgb_image.width,
            "height": rgb_image.height,
            "aspect_ratio": round(rgb_image.width / rgb_image.height, 4),
            "size_bytes": len(raw),
        },
    }


def _input_quality_stage(person: Image.Image, garment: Image.Image) -> dict[str, Any]:
    blocking_issues = []
    warnings = []
    if min(person.size) < MIN_PERSON_EDGE:
        blocking_issues.append(_issue("person.too_small", "本人照片分辨率过低", "请上传边长至少 640px 的清晰半身照。"))
    if min(garment.size) < MIN_GARMENT_EDGE:
        blocking_issues.append(_issue("garment.too_small", "衣服图片分辨率过低", "请上传边长至少 360px 的清晰上衣图。"))
    sharpness = _sharpness(person)
    if sharpness < HARD_SHARPNESS_THRESHOLD:
        blocking_issues.append(_issue("person.blurry", "本人照片偏糊", "请保持手机稳定后重新拍摄。"))
    elif sharpness < SOFT_SHARPNESS_THRESHOLD:
        warnings.append(_issue("person.soft_detail", "照片细节略软", "已继续生成；换一张更清晰的照片会更准。"))
    evidence = {
        "person_size": {"width": person.width, "height": person.height},
        "garment_size": {"width": garment.width, "height": garment.height},
        "person_sharpness": sharpness,
        "hard_sharpness_threshold": HARD_SHARPNESS_THRESHOLD,
        "soft_sharpness_threshold": SOFT_SHARPNESS_THRESHOLD,
    }
    issues = blocking_issues + warnings
    status = "fail" if blocking_issues else "warn" if warnings else "pass"
    confidence = 0.86 if status == "pass" else 0.78 if status == "warn" else 0.72
    return _stage(status, confidence, evidence, issues)


def _detect_person(image: Image.Image) -> dict[str, Any]:
    bgr = _pil_to_bgr(image)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    detections = cascade.detectMultiScale(gray, scaleFactor=1.08, minNeighbors=4, minSize=(72, 72))
    h, w = gray.shape[:2]
    faces = []
    for x, y, fw, fh in detections:
        area_ratio = (fw * fh) / (w * h)
        if area_ratio >= 0.012:
            faces.append({"box": {"x": int(x), "y": int(y), "width": int(fw), "height": int(fh)}, "area_ratio": round(area_ratio, 4)})
    if not faces:
        fallback_face = _clean_center_portrait_fallback(image)
        if fallback_face is not None:
            return _stage("warn", 0.58, {"face_count": 1, "primary_face": fallback_face, "fallback": "clean_center_portrait"}, [
                _issue("person.face_detector_fallback", "已按清晰单人模特继续", "这张图像接近干净模特照，已继续生成试穿。")
            ])
        return _stage("fail", 0.82, {"face_count": 0}, [_issue("person.no_face", "未检测到单人正脸", "请上传本人单人半身或全身照片。")])
    if len(faces) > 1:
        return _stage("fail", 0.86, {"face_count": len(faces), "faces": faces}, [_issue("person.multiple_faces", "检测到多人脸", "请上传只有本人出镜的照片。")])
    face = faces[0]
    box = face["box"]
    torso_top = box["y"] + box["height"]
    if torso_top > h * 0.58:
        return _stage("fail", 0.76, {"face_count": 1, "primary_face": face}, [_issue("person.upper_body_missing", "上半身区域不足", "请上传包含肩膀和胸口区域的照片。")])
    return _stage("pass", 0.84, {"face_count": 1, "primary_face": face}, [])


def _clean_center_portrait_fallback(image: Image.Image) -> dict[str, Any] | None:
    rgb = image.convert("RGB")
    arr = np.asarray(rgb)
    h, w = arr.shape[:2]
    if min(h, w) < 640:
        return None
    corner = np.concatenate(
        [
            arr[:80, :80].reshape(-1, 3),
            arr[:80, -80:].reshape(-1, 3),
            arr[-80:, :80].reshape(-1, 3),
            arr[-80:, -80:].reshape(-1, 3),
        ]
    )
    if float(corner.std()) > 8:
        return None
    background = np.median(corner, axis=0)
    diff = np.linalg.norm(arr.astype(float) - background, axis=2)
    foreground = diff > 35
    center_ratio = float(foreground[:, w // 3 : (w * 2) // 3].mean())
    full_ratio = float(foreground.mean())
    head_band_ratio = float(foreground[int(h * 0.07) : int(h * 0.17), w // 3 : (w * 2) // 3].mean())
    if center_ratio < 0.42 or full_ratio < 0.18 or head_band_ratio < 0.08:
        return None
    fw = max(96, int(w * 0.16))
    fh = max(96, int(h * 0.13))
    x = (w - fw) // 2
    y = int(h * 0.08)
    return {"box": {"x": x, "y": y, "width": fw, "height": fh}, "area_ratio": round((fw * fh) / (w * h), 4)}


def _relax_outfit_person_detection_for_ai_tryon(
    image: Image.Image,
    person_detection: dict[str, Any],
    input_quality: dict[str, Any],
) -> dict[str, Any]:
    if person_detection.get("status") != "fail":
        return person_detection
    issue_codes = {issue.get("code") for issue in person_detection.get("issues", [])}
    if "person.multiple_faces" in issue_codes:
        return person_detection
    if input_quality.get("status") == "fail":
        return person_detection
    width, height = image.size
    if min(width, height) < MIN_PERSON_EDGE:
        return person_detection
    face_width = max(96, int(width * 0.14))
    face_height = max(96, int(height * 0.10))
    fallback_face = {
        "box": {
            "x": int((width - face_width) / 2),
            "y": int(height * 0.34),
            "width": face_width,
            "height": face_height,
        },
        "area_ratio": round((face_width * face_height) / (width * height), 4),
    }
    return _stage("warn", 0.52, {
        **person_detection.get("evidence", {}),
        "face_count": person_detection.get("evidence", {}).get("face_count", 0),
        "primary_face": fallback_face,
        "fallback": "ai_tryon_identity_preserve",
        "reason": "local_face_detector_missed_real_world_photo",
    }, [
        _issue(
            "person.face_detector_relaxed_for_ai_tryon",
            "本地人脸检测未命中，已交给 AI 继续判断",
            "真实生活照可能无法被本地检测器稳定识别，已继续生成试穿。",
        )
    ])


def _generate_upper_body_mask(image: Image.Image, person_stage: dict[str, Any], output_path: Path) -> dict[str, Any]:
    box = person_stage["evidence"]["primary_face"]["box"]
    width, height = image.size
    face_center_x = box["x"] + box["width"] / 2
    top = int(box["y"] + box["height"] * 0.82)
    bottom = min(height - 1, int(box["y"] + box["height"] * 3.75))
    half_width_top = box["width"] * 0.92
    half_width_bottom = box["width"] * 1.72
    left_top = int(max(0, face_center_x - half_width_top))
    right_top = int(min(width - 1, face_center_x + half_width_top))
    left_bottom = int(max(0, face_center_x - half_width_bottom))
    right_bottom = int(min(width - 1, face_center_x + half_width_bottom))
    if bottom - top < box["height"]:
        return _stage("fail", 0.72, {"mask_path": None}, [_issue("mask.upper_body_too_small", "可编辑上衣区域过小", "请上传上半身更完整的照片。")])

    alpha = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(alpha)
    draw.polygon([(left_top, top), (right_top, top), (right_bottom, bottom), (left_bottom, bottom)], fill=0)
    alpha = alpha.filter(ImageFilter.GaussianBlur(radius=max(3, int(width * 0.006))))
    mask = Image.new("RGBA", (width, height), (255, 255, 255, 255))
    mask.putalpha(alpha)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _save_png_atomically(mask, output_path)
    alpha_array = np.array(alpha)
    editable_pixels = int(np.sum(alpha_array < 128))
    protected_pixels = int(alpha_array.size - editable_pixels)
    editable_ratio = editable_pixels / max(1, alpha_array.size)
    status = "pass" if 0.06 <= editable_ratio <= 0.46 else "warn"
    issues = [] if status == "pass" else [_issue("mask.ratio_unusual", "上衣 mask 面积不稳定", "建议使用肩膀和胸口完整入镜的照片。")]
    return _stage(status, 0.78 if status == "pass" else 0.55, {
        "mask_path": str(output_path),
        "width": width,
        "height": height,
        "editable_pixels": editable_pixels,
        "protected_pixels": protected_pixels,
        "editable_ratio": round(editable_ratio, 4),
        "rule": "face_box_torso_trapezoid",
        "mask_semantics": {
            "editable": "transparent_or_black_alpha_lt_128",
            "protected": "opaque_or_white_alpha_gte_220",
        },
    }, issues)


def _save_png_atomically(image: Image.Image, output_path: Path) -> None:
    temp_path = output_path.with_name(f".{output_path.name}.{os.getpid()}.tmp")
    image.save(temp_path, "PNG")
    with Image.open(temp_path) as saved:
        saved.verify()
    temp_path.replace(output_path)


def _review_tryon_quality(original: Image.Image, result_path: Path | None, person_stage: dict[str, Any], mask_path: Path) -> dict[str, Any]:
    if result_path is None or not result_path.exists():
        return _stage("fail", 0.0, {"result_exists": False}, [_issue("quality.missing_result", "没有生成试穿结果", "请稍后重试。")])
    try:
        result = Image.open(result_path).convert("RGB")
        result.load()
    except UnidentifiedImageError:
        return _stage("fail", 0.0, {"result_exists": True}, [_issue("quality.invalid_result", "试穿结果不是有效图片", "请稍后重试。")])
    issues = []
    evidence: dict[str, Any] = {"result_exists": True, "result_size": {"width": result.width, "height": result.height}}
    if min(result.size) < 512:
        issues.append(_issue("quality.result_too_small", "试穿图分辨率过低", "请重新生成。"))
    if result.size == original.size:
        face_diff = _face_region_difference(original, result, person_stage)
        background_diff = _protected_region_difference(original, result, mask_path)
        editable_ratio = _mask_editable_ratio(mask_path)
        evidence["face_diff"] = face_diff
        evidence["protected_region_diff"] = background_diff
        evidence["mask_editable_ratio"] = editable_ratio
        evidence["mask_contract"] = "fail_if_protected_face_or_background_changes"
        if face_diff > 28:
            issues.append(_issue("quality.face_changed", "人脸区域变化过大", "请重新生成，避免改变用户本人特征。"))
        if background_diff > 18:
            issues.append(_issue("quality.background_changed", "背景或非衣服区域变化较大", "请重新生成。"))
    else:
        evidence["dimension_note"] = "result_size_differs_from_input"
    status = "fail" if issues else "pass"
    return _stage(status, 0.82 if status == "pass" else 0.62, evidence, issues)


def _default_provider() -> TryOnProvider:
    if _has_runway_google_provider():
        return RunwayGoogleTryOnProvider()
    if _has_openai_image_edit_provider():
        return OpenAIImageEditTryOnProvider()
    if _pi_agent_code_worker_enabled():
        return CodexImageGenBridgeTryOnProvider()
    return UnavailableTryOnProvider()


def _pi_agent_code_worker_enabled() -> bool:
    return os.getenv("TRYON_ENABLE_PI_AGENT_CODE_WORKER", "").strip().lower() in {"1", "true", "yes", "on"}


def create_codex_bridge_job(person_image: Path, garment_image: Path, mask_image: Path, prompt: str, output_dir: Path) -> dict[str, Any]:
    _codex_bridge_dir().mkdir(parents=True, exist_ok=True)
    provider_version = "pi_agent_worker:v4_mask_guided_identity_preserve"
    job_id = hashlib.sha256(f"{provider_version}:{person_image}:{garment_image}:{mask_image}:{prompt}".encode("utf-8")).hexdigest()[:16]
    result_path = output_dir / "result_codex_imagegen.png"
    job_path = _codex_bridge_dir() / f"{job_id}.json"
    now_payload = {
        "status": "pending",
        "job_id": job_id,
        "created_by": "try-on-web",
        "provider": "pi_agent_worker",
        "provider_version": provider_version,
        "input": {
            "person_image_path": str(person_image),
            "garment_image_path": str(garment_image),
            "mask_image_path": str(mask_image),
        },
        "prompt": _build_codex_imagegen_prompt(prompt, person_image, garment_image, mask_image),
        "result": {
            "target_path": str(result_path),
            "image_path": None,
            "public_image_path": None,
            "message": "等待本地 Diga/Pi Agent 生成试穿图。",
        },
        "instructions": [
            "The local Pi/Diga Agent worker consumes this job.",
            "Pass person_image_path, garment_image_path, and mask_image_path as separate image inputs.",
            "Use mask_image_path as the editable clothing area guide for image A.",
            "Make the person in image A wear the upper-body garment from image B while preserving protected regions.",
            "Save the final image to result.target_path and mark this JSON completed.",
        ],
    }
    if job_path.exists():
        try:
            existing = json.loads(job_path.read_text(encoding="utf-8"))
            if existing.get("status") == "completed":
                return {**existing, "job_path": str(job_path)}
        except Exception:
            pass
    _write_json_atomically(job_path, now_payload)
    return {**now_payload, "job_path": str(job_path)}


def _start_pi_agent_tryon_worker(job_id: str) -> bool:
    worker_path = ROOT_DIR / "scripts" / "pi_agent_tryon_worker.py"
    if not worker_path.exists():
        return False
    try:
        subprocess.Popen(
            [sys.executable, str(worker_path), "--job-id", job_id, "--once"],
            cwd=ROOT_DIR,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return True
    except Exception:
        return False


def _build_codex_imagegen_prompt(prompt: str, person_image: Path, garment_image: Path, mask_image: Path) -> str:
    return (
        "Use case: identity-preserve\n"
        "Asset type: AI virtual try-on result for a local web demo\n"
        "Primary request: Put the target upper garment onto the model/person image.\n"
        f"Input images: person target={person_image}; garment reference={garment_image}; upper-body mask guide={mask_image}\n"
        f"{_mask_editing_contract()}\n"
        "Style/medium: realistic consumer fashion app photo result\n"
        "Composition/framing: preserve the original portrait framing and camera angle\n"
        "Constraints: preserve the person's face, hair, skin tone, body shape, pose, arms, hands, background, lighting, camera angle, and image style. "
        "Change only the upper-body clothing. Use the garment reference for color, fabric, neckline, sleeves, chest graphics/details, and overall fit. "
        "No UI, no watermark, no extra text outside the garment details.\n"
        f"Original provider prompt: {prompt}"
    )


def _write_json_atomically(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(path)


def list_codex_bridge_jobs(status: str | None = None) -> dict[str, Any]:
    _codex_bridge_dir().mkdir(parents=True, exist_ok=True)
    jobs = []
    for path in sorted(_codex_bridge_dir().glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            job = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if status and job.get("status") != status:
            continue
        job["job_path"] = str(path)
        jobs.append(job)
    return {"status": "ok", "total": len(jobs), "jobs": jobs}


def next_codex_bridge_job() -> dict[str, Any]:
    jobs = list_codex_bridge_jobs("pending")["jobs"]
    if not jobs:
        return {"status": "empty", "job": None}
    return {"status": "pending", "job": jobs[-1]}


def _read_codex_bridge_job(job_id: str) -> dict[str, Any]:
    if not re.fullmatch(r"[a-f0-9]{16}", job_id):
        raise HTTPException(status_code=400, detail="无效的 bridge job id")
    job_path = _codex_bridge_dir() / f"{job_id}.json"
    if not job_path.exists():
        raise HTTPException(status_code=404, detail="没有找到这个生成任务")
    try:
        job = json.loads(job_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail="生成任务文件损坏") from exc
    job["job_path"] = str(job_path)
    return job


def get_codex_bridge_job(job_id: str) -> dict[str, Any]:
    job = _read_codex_bridge_job(job_id)
    result_path = Path(job.get("result", {}).get("target_path", ""))
    if job.get("status") in {"pending", "running", "failed"} and result_path.exists():
        job = complete_codex_bridge_job(job_id, result_path)
    return job


def complete_codex_bridge_job(job_id: str, result_path: Path | None) -> dict[str, Any]:
    job = _read_codex_bridge_job(job_id)
    if result_path is None or not result_path.exists():
        raise HTTPException(status_code=400, detail="生成结果图片不存在")
    try:
        image = Image.open(result_path).convert("RGB")
        image.load()
    except UnidentifiedImageError as exc:
        raise HTTPException(status_code=400, detail="生成结果不是有效图片") from exc

    target_path = Path(job["result"]["target_path"])
    if result_path.resolve() != target_path.resolve():
        target_path.parent.mkdir(parents=True, exist_ok=True)
        _save_png_atomically(image, target_path)
    job["status"] = "completed"
    job["result"]["image_path"] = str(target_path)
    job["result"]["public_image_path"] = _public_output_path(target_path)
    job["result"]["message"] = "本地 Diga/Pi Agent 已回填试穿结果。"
    if isinstance(job.get("worker"), dict):
        job["worker"].pop("error", None)
        job["worker"].pop("failed_at", None)
        job["worker"]["completed_from_existing_result"] = True
    _write_json_atomically(Path(job["job_path"]), {key: value for key, value in job.items() if key != "job_path"})
    return job


def _build_tryon_prompt(garment: dict[str, Any]) -> str:
    return (
        "Edit the person image for a virtual try-on. Replace only the clothing inside the transparent mask with the reference top. "
        "Preserve the person's face, hair, skin tone, body shape, pose, hands, background, lighting, camera angle, and image style. "
        "Use realistic fabric folds and natural occlusion around hair, neck, shoulders, arms, and accessories. "
        f"The target garment is a {garment.get('fit', 'regular')} {garment.get('category', 'top')} with colors {', '.join(garment.get('colors', []))}, "
        f"materials {', '.join(garment.get('material', []))}, pattern {garment.get('pattern', 'unknown')}, "
        f"neckline {garment.get('neckline', 'unknown')}, sleeve {garment.get('sleeve', 'unknown')}, and details {', '.join(garment.get('details', []))}. "
        "Do not alter anything outside the garment area."
    )


def _build_uploaded_outfit_tryon_plan(
    style_reference: dict[str, Any],
    uploaded_items: list[dict[str, Any]],
    outfit_plan_json: str | None,
    photo_mode: str | None,
    scene_label: str | None,
) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    if outfit_plan_json and outfit_plan_json.strip():
        try:
            loaded = json.loads(outfit_plan_json)
            if isinstance(loaded, dict):
                parsed = loaded
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="outfit_plan 必须是 JSON 对象") from exc
    raw_items = parsed.get("items") if isinstance(parsed.get("items"), list) else []
    fallback_slots = ["top", "bottom", "shoes", "bag", "accessory"]
    items = []
    for index, upload in enumerate(uploaded_items):
        raw = raw_items[index] if index < len(raw_items) and isinstance(raw_items[index], dict) else {}
        category = str(raw.get("category") or raw.get("slot") or fallback_slots[min(index, len(fallback_slots) - 1)])
        slot = str(raw.get("slot") or category)
        items.append(
            {
                **raw,
                "slot": slot,
                "category": category,
                "image_id": upload["image_id"],
                "image_path": str(upload["saved_path"]),
                "meta": upload["meta"],
            }
        )
    return {
        "source_mode": "direct_upload",
        "title": str(parsed.get("title") or "直接上传穿搭")[:48],
        "model_photo_mode": photo_mode or parsed.get("model_photo_mode") or "standard",
        "scene_label": scene_label or parsed.get("scene_label") or "",
        "style_reference": {
            "image_id": style_reference["image_id"],
            "image_path": str(style_reference["saved_path"]),
            "meta": style_reference["meta"],
            "role": "overall_outfit_reference",
        },
        "items": items,
        "style_brief": str(parsed.get("style_brief") or parsed.get("note") or "")[:1200],
    }


def _normalize_outfit_tryon_plan(plan: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(plan, dict):
        raise HTTPException(status_code=400, detail="穿搭方案格式不正确")
    photo_mode = _normalize_photo_mode(plan.get("model_photo_mode") or plan.get("photo_mode"))
    style_reference = dict(plan.get("style_reference") or {})
    items = []
    for index, raw_item in enumerate(plan.get("items") or []):
        if not isinstance(raw_item, dict):
            continue
        category = _normalize_outfit_category(raw_item.get("category") or raw_item.get("slot"))
        slot = _normalize_outfit_slot(raw_item.get("slot") or category)
        image_path = str(raw_item.get("image_path") or raw_item.get("path") or "").strip()
        if not image_path:
            continue
        items.append(
            {
                **raw_item,
                "slot": slot,
                "category": category,
                "category_label": raw_item.get("category_label") or _fashion_category_label(category),
                "wear_region": raw_item.get("wear_region") or _wear_region_for_slot(slot),
                "wearing_instruction": str(raw_item.get("wearing_instruction") or _default_wearing_instruction(slot))[:240],
                "image_path": image_path,
                "display_order": int(raw_item.get("display_order") or index),
            }
        )
    items.sort(key=lambda item: (int(item.get("display_order") or 0), _slot_sort_key(str(item.get("slot") or ""))))
    return {
        **plan,
        "model_photo_mode": photo_mode,
        "scene_label": str(plan.get("scene_label") or "")[:80],
        "style_reference": style_reference,
        "items": items[:8],
        "style_brief": str(plan.get("style_brief") or "")[:1600],
    }


def _normalize_photo_mode(value: Any) -> str:
    mode = str(value or "standard").strip().lower()
    return mode if mode in OUTFIT_PHOTO_MODES else "standard"


def _normalize_outfit_category(value: Any) -> str:
    raw = str(value or "accessory").strip().lower()
    aliases = {
        "jacket": "outer",
        "coat": "outer",
        "outerwear": "outer",
        "pants": "bottom",
        "trousers": "bottom",
        "jeans": "bottom",
        "shoe": "shoes",
        "sneakers": "shoes",
    }
    category = aliases.get(raw, raw)
    return category if category in FASHION_ITEM_CATEGORIES else "accessory"


def _normalize_outfit_slot(value: Any) -> str:
    slot = _normalize_outfit_category(value)
    return slot


def _wear_region_for_slot(slot: str) -> str:
    return {
        "top": "upper_body",
        "outer": "outer_layer_over_upper_body",
        "bottom": "lower_body",
        "skirt": "lower_body",
        "dress": "full_body_main_garment",
        "shoes": "feet",
        "bag": "hand_or_shoulder",
        "accessory": "matching_accessory",
    }.get(slot, "matching_accessory")


def _placement_rule_for_slot(slot: str) -> str:
    return {
        "top": "align with shoulders, neck, chest, waist, and arm openings; preserve natural folds and occlusion by hair or arms.",
        "outer": "place as the outermost upper-body layer; align shoulders, sleeves, opening, and hem over the inner garment.",
        "bottom": "align with visible waist, hips, legs, and original crop; do not invent feet or extend the body.",
        "skirt": "align with visible waist and legs; keep the original body crop and do not extend the frame.",
        "dress": "align with visible shoulders, waist, hips, and legs; keep the original body crop and camera distance.",
        "shoes": "apply only when feet are visible in Image A; if feet are cropped or hidden, omit shoes instead of zooming out or inventing feet.",
        "bag": "must have a believable contact point: handbag held by a visible hand or hanging from the forearm, shoulder bag resting on the shoulder, crossbody strap crossing the torso. Never let the bag float, hover, or sit detached from the arm/body.",
        "accessory": "place only where it naturally attaches to the visible body or clothing; do not float or cover the face unless Image A already does.",
    }.get(slot, "place naturally on the visible body or clothing without floating.")


def _default_wearing_instruction(slot: str) -> str:
    return {
        "top": "穿在模特上半身，保留领口、袖长、衣长和主要图案。",
        "outer": "作为外层穿在上半身，保持外套轮廓、开合方式和材质厚度。",
        "bottom": "穿在模特下半身，保留裤型、腰线、裤长和面料垂坠。",
        "skirt": "穿在模特下半身，保留裙长、廓形和腰线。",
        "dress": "作为连衣装覆盖上半身和下半身，保留裙长、腰线和整体廓形。",
        "shoes": "穿在模特双脚，保留鞋型、颜色和鞋底比例。",
        "bag": "作为包袋搭配在可见手臂、手部或肩侧；手提包需要手握或挂在前臂，肩背包需要贴合肩线，不能悬空。",
        "accessory": "作为配饰自然搭配，不改变模特身份和脸部。",
    }.get(slot, "作为配饰自然搭配。")


def _slot_sort_key(slot: str) -> int:
    order = {"outer": 0, "top": 1, "dress": 2, "bottom": 3, "skirt": 4, "shoes": 5, "bag": 6, "accessory": 7}
    return order.get(slot, 99)


def _outfit_plan_stage(plan: dict[str, Any]) -> dict[str, Any]:
    missing = _missing_outfit_slots(plan)
    evidence = {
        "item_count": len(plan.get("items", [])),
        "missing_slots": missing,
        "required_groups": {key: sorted(value) for key, value in OUTFIT_REQUIRED_GROUPS.items()},
        "photo_mode": plan.get("model_photo_mode"),
    }
    if not plan.get("items"):
        return _stage("fail", 0.72, evidence, [
            _issue("outfit.no_available_items", "这套搭配暂时没有可用单品", "请先加入至少一件可识别的衣物或鞋包。")
        ])
    if missing:
        return _stage("warn", 0.68, evidence, [
            _issue("outfit.missing_reference_slots", "穿搭参考不完整", f"已继续生成；缺少{'、'.join(missing)}时会让模型按现有单品自然补足。")
        ])
    return _stage("pass", 0.84, evidence, [])


def _missing_outfit_slots(plan: dict[str, Any]) -> list[str]:
    categories = {str(item.get("category") or item.get("slot") or "") for item in plan.get("items", [])}
    labels = {"upper": "上装", "lower": "下装/裙装", "feet": "鞋子"}
    missing = []
    for group, accepted in OUTFIT_REQUIRED_GROUPS.items():
        if not categories.intersection(accepted):
            missing.append(labels[group])
    return missing


def _outfit_blocking_issues(pipeline: dict[str, Any]) -> list[dict[str, Any]]:
    issues = []
    for stage_name in ["input_quality", "person_detection", "outfit_plan", "outfit_body_mask"]:
        stage = pipeline.get(stage_name, {})
        if stage.get("status") == "fail":
            issues.extend(stage.get("issues", []))
    return issues


def _relax_preset_model_blur_for_outfit_tryon(
    person: dict[str, Any],
    input_quality: dict[str, Any],
    person_detection: dict[str, Any],
) -> dict[str, Any]:
    if input_quality.get("status") != "fail":
        return input_quality
    issues = input_quality.get("issues", [])
    issue_codes = {issue.get("code") for issue in issues}
    if issue_codes != {"person.blurry"}:
        return input_quality
    if person_detection.get("status") not in {"pass", "warn"}:
        return input_quality
    filename = str(person.get("meta", {}).get("filename") or "")
    if filename not in _preset_tryon_model_filenames():
        return input_quality
    relaxed_issue = _issue("person.preset_model_soft_detail", "预设模特照片细节偏柔", "已按预设模特继续生成。")
    evidence = {
        **input_quality.get("evidence", {}),
        "relaxed_for_preset_model": True,
        "preset_model_filename": filename,
    }
    return _stage("warn", 0.70, evidence, [relaxed_issue])


def _preset_tryon_model_filenames() -> set[str]:
    manifest = _load_tryon_model_manifest()
    return {str(item.get("file") or "") for item in manifest.get("items", []) if item.get("file")}


def _build_outfit_reference_board(plan: dict[str, Any], output_path: Path) -> Path:
    canvas = Image.new("RGB", (1200, 900), "#fffafa")
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((24, 24, 1176, 876), radius=34, fill="#ffffff", outline="#eee4e8", width=2)
    _draw_board_label(draw, (54, 44), "整体穿搭参考", "#1c1b20")
    style_path = _path_from_plan_image(plan.get("style_reference", {}).get("image_path"))
    if style_path and style_path.exists():
        _paste_board_image(canvas, style_path, (54, 86, 520, 786))
    else:
        draw.rounded_rectangle((54, 86, 520, 786), radius=22, fill="#fff1f6", outline="#f0b7c0", width=2)
        _draw_board_label(draw, (178, 420), "暂无整体图", "#8b8388")

    slot_boxes = [
        ("top", (560, 86, 820, 310)),
        ("outer", (850, 86, 1110, 310)),
        ("dress", (560, 330, 820, 590)),
        ("bottom", (850, 330, 1110, 590)),
        ("skirt", (850, 330, 1110, 590)),
        ("shoes", (560, 610, 820, 808)),
        ("bag", (850, 610, 980, 808)),
        ("accessory", (998, 610, 1110, 808)),
    ]
    used = set()
    for item in plan.get("items", []):
        slot = str(item.get("slot") or item.get("category") or "accessory")
        box = next((candidate_box for candidate_slot, candidate_box in slot_boxes if candidate_slot == slot and candidate_slot not in used), None)
        if box is None:
            box = next((candidate_box for candidate_slot, candidate_box in slot_boxes if candidate_slot == "accessory"), (998, 610, 1110, 808))
        used.add(slot)
        path = _path_from_plan_image(item.get("image_path"))
        left, top, right, bottom = box
        draw.rounded_rectangle((left, top, right, bottom), radius=20, fill="#fffafa", outline="#eee4e8", width=2)
        if path and path.exists():
            _paste_board_image(canvas, path, (left + 12, top + 12, right - 12, bottom - 54))
        label = f"{item.get('category_label') or _fashion_category_label(slot)} / {item.get('wear_region') or _wear_region_for_slot(slot)}"
        _draw_board_label(draw, (left + 14, bottom - 38), label[:24], "#1c1b20")
    note = f"photo_mode={plan.get('model_photo_mode')} scene={plan.get('scene_label') or 'none'}"
    _draw_board_label(draw, (54, 824), note[:80], "#8b8388")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _save_png_atomically(canvas, output_path)
    return output_path


def _path_from_plan_image(value: Any) -> Path | None:
    if not value:
        return None
    return Path(str(value)).expanduser()


def _paste_board_image(canvas: Image.Image, image_path: Path, box: tuple[int, int, int, int]) -> None:
    try:
        image = Image.open(image_path).convert("RGB")
    except Exception:
        return
    left, top, right, bottom = box
    max_w = right - left
    max_h = bottom - top
    image.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
    x = left + (max_w - image.width) // 2
    y = top + (max_h - image.height) // 2
    canvas.paste(image, (x, y))


def _draw_board_label(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, fill: str) -> None:
    try:
        draw.text(xy, text, fill=fill)
    except UnicodeEncodeError:
        draw.text(xy, text.encode("ascii", "ignore").decode("ascii"), fill=fill)


def _build_outfit_prompt_context(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": plan.get("title") or "穿搭试穿",
        "photo_mode": plan.get("model_photo_mode"),
        "scene_label": plan.get("scene_label") or "",
        "style_brief": plan.get("style_brief") or "",
        "items": [
            {
                "slot": item.get("slot"),
                "category": item.get("category"),
                "category_label": item.get("category_label"),
                "wear_region": item.get("wear_region"),
                "wearing_instruction": item.get("wearing_instruction"),
                "placement_rule": _placement_rule_for_slot(str(item.get("slot") or item.get("category") or "accessory")),
                "attributes": item.get("attributes") or {},
                "note": item.get("note") or "",
            }
            for item in plan.get("items", [])
        ],
        "priority": [
            "preserve_model_identity_body_pose_background",
            "preserve_individual_item_details",
            "follow_wearing_instructions",
            "use_overall_style_reference_for_layering_and_proportion",
            "avoid_copying_reference_person_or_background",
        ],
    }


def _build_outfit_tryon_prompt(prompt_context: dict[str, Any]) -> str:
    return (
        "Full outfit virtual try-on. Image A is the target model/person. Image B is a labeled outfit reference board with an overall styling image and separate item references. "
        "Make the person in Image A wear the complete outfit described by Image B and the structured context below. "
        "Do not copy any person, face, pose, background, watermark, text, or collage layout from Image B. "
        "Keep Image A as the absolute authority for canvas, crop, camera distance, pose, background, and visible body range. Do not zoom out or complete missing body parts just to show shoes, a bag, or other references from Image B. "
        f"Structured outfit context: {json.dumps(prompt_context, ensure_ascii=False)}\n"
        "For each item, put it on the specified body region only when that region is visible in Image A: upper items on upper body, lower items on visible lower body, dress on visible body, shoes only if feet are visible, bag/accessories only if naturally compatible with the original crop. "
        "Accessory logic: bags must physically attach to the person. A handbag should be held by a visible hand or hang from the forearm; a shoulder bag should rest on the shoulder; a crossbody bag should have a strap crossing the torso. Do not render floating, detached, pasted-on, or impossible bags. If Image A has no visible hand/arm/shoulder contact point, omit or minimize the bag rather than placing it illogically. "
        "Use the overall outfit reference only for styling relationship, layering, proportions, color harmony, and wearing method. "
        "Priority order: preserve Image A identity, body shape, pose, skin tone, hair, face visibility, camera angle, lighting, and background first; then preserve individual item details; then follow wearing instructions; then harmonize overall style. "
        f"Photo mode constraints: {_photo_mode_prompt_clause(str(prompt_context.get('photo_mode') or 'standard'), str(prompt_context.get('scene_label') or ''))} "
        "Return only one realistic final try-on photo, with no UI, no labels, no watermark, and no extra people."
    )


def _photo_mode_prompt_clause(photo_mode: str, scene_label: str = "") -> str:
    if photo_mode == "mirror_selfie":
        return "preserve mirror selfie perspective, phone position, mirror relation, and room/background geometry from Image A."
    if photo_mode == "face_covered":
        return "preserve the original face-covering object/pose; do not invent or reveal a new face."
    if photo_mode == "scene_photo":
        if scene_label:
            return f"lightly respect the requested scene mood '{scene_label}', but do not replace the original background unless it is naturally compatible."
        return "preserve the original scene and only adjust outfit integration."
    return "preserve the original full-body portrait framing, face, pose, background, and lighting."


def _generate_outfit_body_mask(image: Image.Image, person_stage: dict[str, Any], output_path: Path) -> dict[str, Any]:
    box = person_stage["evidence"]["primary_face"]["box"]
    width, height = image.size
    face_center_x = box["x"] + box["width"] / 2
    top = int(box["y"] + box["height"] * 0.76)
    bottom = height - 1
    shoulder_half = box["width"] * 1.25
    hip_half = box["width"] * 1.85
    foot_half = box["width"] * 1.55
    if bottom - top < box["height"] * 2.0:
        return _stage("fail", 0.70, {"mask_path": None}, [_issue("mask.full_body_too_small", "全身服饰区域不足", "请上传包含上身、下身和鞋子的全身照片。")])

    alpha = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(alpha)
    waist_y = int(top + (bottom - top) * 0.40)
    draw.polygon(
        [
            (int(max(0, face_center_x - shoulder_half)), top),
            (int(min(width - 1, face_center_x + shoulder_half)), top),
            (int(min(width - 1, face_center_x + hip_half)), waist_y),
            (int(min(width - 1, face_center_x + foot_half)), bottom),
            (int(max(0, face_center_x - foot_half)), bottom),
            (int(max(0, face_center_x - hip_half)), waist_y),
        ],
        fill=0,
    )
    alpha = alpha.filter(ImageFilter.GaussianBlur(radius=max(4, int(width * 0.007))))
    mask = Image.new("RGBA", (width, height), (255, 255, 255, 255))
    mask.putalpha(alpha)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _save_png_atomically(mask, output_path)
    alpha_array = np.array(alpha)
    editable_pixels = int(np.sum(alpha_array < 128))
    protected_pixels = int(alpha_array.size - editable_pixels)
    editable_ratio = editable_pixels / max(1, alpha_array.size)
    status = "pass" if 0.14 <= editable_ratio <= 0.72 else "warn"
    issues = [] if status == "pass" else [_issue("mask.full_body_ratio_unusual", "全身服饰区域面积不稳定", "建议使用站姿完整、衣服鞋子入镜的照片。")]
    return _stage(status, 0.78 if status == "pass" else 0.56, {
        "mask_path": str(output_path),
        "width": width,
        "height": height,
        "editable_pixels": editable_pixels,
        "protected_pixels": protected_pixels,
        "editable_ratio": round(editable_ratio, 4),
        "rule": "face_box_full_body_clothing_polygon",
        "mask_semantics": {
            "editable": "transparent_or_black_alpha_lt_128",
            "protected": "opaque_or_white_alpha_gte_220",
        },
    }, issues)


def _review_outfit_tryon_quality(
    original: Image.Image,
    result_path: Path | None,
    person_stage: dict[str, Any],
    mask_path: Path,
    plan: dict[str, Any],
) -> dict[str, Any]:
    base = _review_tryon_quality(original, result_path, person_stage, mask_path)
    evidence = {**base.get("evidence", {}), "required_slots": sorted({item.get("slot") for item in plan.get("items", []) if item.get("slot")})}
    issues = list(base.get("issues", []))
    if result_path is None or not result_path.exists():
        return base
    evidence["outfit_review_note"] = "MVP checks structural output only; semantic slot verification is reserved for a VLM reviewer."
    status = "fail" if any(issue.get("code", "").startswith("quality.") for issue in issues) else "pass"
    return _stage(status, 0.78 if status == "pass" else 0.60, evidence, issues)


def _public_outfit_tryon_plan(plan: dict[str, Any]) -> dict[str, Any]:
    public_items = []
    for item in plan.get("items", []):
        public_items.append(
            {
                key: value
                for key, value in item.items()
                if key not in {"image_path"} and not isinstance(value, Image.Image)
            }
        )
        public_items[-1]["image_path"] = _public_output_path(Path(item["image_path"])) if _is_tryon_output_path(item.get("image_path")) else item.get("image_path")
    style_reference = dict(plan.get("style_reference") or {})
    if style_reference.get("image_path") and _is_tryon_output_path(style_reference.get("image_path")):
        style_reference["image_path"] = _public_output_path(Path(style_reference["image_path"]))
    return {
        "title": plan.get("title") or "穿搭试穿",
        "model_photo_mode": plan.get("model_photo_mode"),
        "scene_label": plan.get("scene_label") or "",
        "style_reference": style_reference,
        "items": public_items,
        "style_brief": plan.get("style_brief") or "",
    }


def _is_tryon_output_path(value: Any) -> bool:
    if not value:
        return False
    try:
        Path(str(value)).resolve().relative_to(_tryon_output_dir().resolve())
        return True
    except ValueError:
        return False


def _build_inspiration_tryon_prompt(style_brief: str | None = None) -> str:
    brief = _safe_style_brief(style_brief)
    return (
        "Experimental one-step inspiration try-on. Image A is the target person/model. Image B is a fashion inspiration reference image or multi-image reference board, "
        "not a clean product image. Use the structured context below together with all visible references in Image B to identify the target upper garment. "
        "Extract the garment facts from the note context and all visible reference images: category, sleeve length, collar/neckline, fit, length, colors, pattern, material feel, layering, and key details. "
        f"Structured note and multi-image context: {brief or '{}'}\n"
        "If any local structured label is incomplete or conflicts with the visual reference board, trust the repeated visual evidence across the reference images. "
        "Put only that upper garment onto the person in Image A. Do not infer a different garment type from generic fashion priors. "
        "If the context says or implies long sleeves, keep long sleeves and cover the arms naturally; do not shorten it into a T-shirt or short-sleeve polo. "
        "If the context says or implies loose/oversized/cropped/knit/sweater/sweatshirt/collar/layering, preserve those attributes. "
        "Do not copy Image B's person, face, hair, pose, trousers, skirt, shoes, bag, accessories, headphones, background, camera angle, or lighting. "
        "Do not copy any text, watermark, collage layout, or extra objects from Image B. "
        "Preserve Image A's face, hair, skin tone, body shape, pose, arms, hands, background, lighting, camera angle, and photo style. "
        "Change only the upper-body clothing region. Keep the garment realistic with natural fabric folds, correct sleeve length, neckline/collar, hem length, pattern scale, color, and fit. "
        "Return only the final realistic try-on photo."
    )


def _blocking_issues(pipeline: dict[str, Any], include_garment: bool = True) -> list[dict[str, Any]]:
    issues = []
    stage_names = ["input_quality", "person_detection", "upper_body_mask"]
    if include_garment:
        stage_names.insert(2, "garment_analysis")
    for stage_name in stage_names:
        stage = pipeline[stage_name]
        if stage["status"] == "fail":
            issues.extend(stage.get("issues", []))
    return issues


def _warnings(pipeline: dict[str, Any]) -> list[dict[str, Any]]:
    warnings = []
    for stage in pipeline.values():
        if stage["status"] == "warn":
            warnings.extend(stage.get("issues", []))
    image_edit_issues = pipeline.get("image_edit", {}).get("issues", [])
    warnings.extend(issue for issue in image_edit_issues if issue.get("code") == "image_edit.mock_provider")
    return warnings


def _public_output_path(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return user_asset_public_path("tryon", path, _tryon_output_dir())
    except ValueError:
        try:
            relative = path.relative_to(TRYON_OUTPUT_DIR)
            return f"/tryon-outputs/{relative.as_posix()}"
        except ValueError:
            return str(path)


def _load_tryon_model_manifest() -> dict[str, Any]:
    manifest_path = TRYON_MODEL_FIXTURE_DIR / "manifest.json"
    if not manifest_path.exists():
        return {"total": 0, "items": []}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    items = []
    for item in manifest.get("items", []):
        image_path = TRYON_MODEL_FIXTURE_DIR / item.get("file", "")
        if image_path.exists():
            items.append(item)
    return {"total": len(items), "items": items}


def _normalize_xhs_url(url: str) -> str:
    cleaned = (url or "").strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="小红书链接不能为空")
    if not cleaned.startswith(("http://", "https://")):
        cleaned = "https://" + cleaned
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="链接格式不正确")
    host = parsed.netloc.lower()
    if not any(part in host for part in XHS_ALLOWED_HOST_PARTS):
        raise HTTPException(status_code=400, detail="当前仅支持小红书或小红书图片链接")
    return cleaned


async def _fetch_xhs_html(url: str) -> tuple[str, str]:
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=20, headers=HTTP_HEADERS) as client:
            response = await client.get(url)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"小红书链接抓取失败: {exc}") from exc
    content_type = response.headers.get("content-type", "")
    if content_type.startswith("image/"):
        return f'<meta property="og:image" content="{response.url}">', str(response.url)
    return response.text, str(response.url)


def _extract_image_urls_from_html(html_text: str, base_url: str) -> list[str]:
    decoded = html.unescape(html_text).replace("\\u002F", "/").replace("\\/", "/")
    candidates: list[str] = []
    meta_patterns = [
        r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image|image)["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](?:og:image|twitter:image|image)["\']',
    ]
    for pattern in meta_patterns:
        candidates.extend(re.findall(pattern, decoded, flags=re.IGNORECASE))

    candidates.extend(re.findall(r'https?://[^\s"\'<>]+', decoded))
    candidates.extend(re.findall(r'//[A-Za-z0-9._~:/?#\[\]@!$&()*+,;=%-]+', decoded))

    image_urls = []
    for raw_url in candidates:
        url = _clean_image_url(urljoin(base_url, raw_url))
        if not _looks_like_xhs_image_url(url):
            continue
        if url not in image_urls:
            image_urls.append(url)
        if len(image_urls) >= MAX_XHS_IMAGES:
            break
    return image_urls


def _extract_xhs_note_payload(html_text: str) -> dict[str, Any]:
    decoded = html.unescape(html_text).replace("\\u002F", "/").replace("\\/", "/")
    for key in ('"noteData"', "'noteData'", '"noteDetail"', "'noteDetail'"):
        key_index = decoded.find(key)
        if key_index < 0:
            continue
        colon_index = decoded.find(":", key_index + len(key))
        object_start = decoded.find("{", colon_index)
        if colon_index < 0 or object_start < 0:
            continue
        raw_object = _balanced_json_object(decoded, object_start)
        if not raw_object:
            continue
        try:
            payload = json.loads(raw_object)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload

    state = _extract_xhs_initial_state(decoded)
    if state:
        note = _find_first_note_payload(state)
        if note:
            return note
    return {}


def _extract_xhs_initial_state(decoded_html: str) -> dict[str, Any]:
    markers = ("window.__INITIAL_STATE__", "__INITIAL_STATE__", "window.__INITIAL_SSR_STATE__")
    for marker in markers:
        marker_index = decoded_html.find(marker)
        if marker_index < 0:
            continue
        object_start = decoded_html.find("{", marker_index)
        if object_start < 0:
            continue
        raw_object = _balanced_json_object(decoded_html, object_start)
        if not raw_object:
            continue
        try:
            payload = json.loads(raw_object)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def _balanced_json_object(text: str, start: int) -> str | None:
    depth = 0
    in_string = False
    quote = ""
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                in_string = False
            continue
        if char in {'"', "'"}:
            in_string = True
            quote = char
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def _find_first_note_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        if isinstance(value.get("imageList"), list) or isinstance(value.get("image_list"), list):
            return value
        note = value.get("note")
        if isinstance(note, dict):
            note_detail_map = note.get("note_detail_map")
            if isinstance(note_detail_map, dict):
                for detail in note_detail_map.values():
                    note_payload = detail.get("note") if isinstance(detail, dict) else None
                    if isinstance(note_payload, dict):
                        return note_payload
            if isinstance(note.get("imageList"), list) or isinstance(note.get("image_list"), list):
                return note
        for child in value.values():
            found = _find_first_note_payload(child)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_first_note_payload(item)
            if found:
                return found
    return {}


def _extract_xhs_note_image_urls(note: dict[str, Any]) -> list[str]:
    if not note:
        return []
    candidates: list[str] = []
    for key in ("imageList", "image_list", "images", "cover"):
        _collect_xhs_image_urls(note.get(key), candidates)
    if not candidates:
        _collect_xhs_image_urls(note, candidates)
    return _merge_unique_urls([_clean_image_url(url) for url in candidates if _looks_like_xhs_image_url(_clean_image_url(url))])


def _collect_xhs_image_urls(value: Any, candidates: list[str]) -> None:
    if isinstance(value, str):
        if value.startswith(("http://", "https://", "//")):
            candidates.append(value)
        return
    if isinstance(value, list):
        for item in value:
            _collect_xhs_image_urls(item, candidates)
        return
    if not isinstance(value, dict):
        return

    for key in ("url", "original", "originalUrl", "traceId", "fileId"):
        raw = value.get(key)
        if isinstance(raw, str) and raw.startswith(("http://", "https://", "//")):
            candidates.append(raw)
    for key in ("infoList", "info_list", "imageScene", "image_scene", "images", "imageList", "image_list"):
        _collect_xhs_image_urls(value.get(key), candidates)


def _merge_unique_urls(urls: list[str]) -> list[str]:
    unique: list[str] = []
    for raw_url in urls:
        url = _clean_image_url(raw_url)
        if not url or url in unique:
            continue
        unique.append(url)
        if len(unique) >= MAX_XHS_IMAGES:
            break
    return unique


def _public_xhs_note(note: dict[str, Any]) -> dict[str, Any]:
    if not note:
        return {}
    user = note.get("user") or note.get("userInfo") or note.get("user_info") or {}
    return {
        "note_id": note.get("noteId") or note.get("note_id") or note.get("id") or "",
        "type": note.get("type") or note.get("noteType") or "",
        "title": note.get("title") or "",
        "desc": note.get("desc") or note.get("description") or "",
        "user": {
            "nickname": user.get("nickname") or user.get("nickName") or "",
            "user_id": user.get("userId") or user.get("user_id") or "",
        }
        if isinstance(user, dict)
        else {},
        "image_count": len(_extract_xhs_note_image_urls(note)),
    }


def _build_inspiration_reference_sheet(downloaded: list[dict[str, Any]], work_dir: Path) -> Path | None:
    candidates = []
    for item in downloaded:
        image = item.get("image")
        if not isinstance(image, Image.Image):
            continue
        if not _looks_like_reference_photo(image):
            continue
        candidates.append(image.convert("RGB"))
        if len(candidates) >= 6:
            break
    if not candidates:
        return None
    cell_w, cell_h = 420, 560
    cols = 2 if len(candidates) <= 4 else 3
    rows = int(np.ceil(len(candidates) / cols))
    sheet = Image.new("RGB", (cols * cell_w, rows * cell_h), "#f8f2f5")
    for index, image in enumerate(candidates):
        thumb = image.copy()
        thumb.thumbnail((cell_w - 24, cell_h - 24), Image.LANCZOS)
        x = (index % cols) * cell_w + (cell_w - thumb.width) // 2
        y = (index // cols) * cell_h + (cell_h - thumb.height) // 2
        sheet.paste(thumb, (x, y))
    output_path = work_dir / "inspiration_reference_sheet.jpg"
    sheet.save(output_path, quality=92)
    return output_path


def _looks_like_reference_photo(image: Image.Image) -> bool:
    width, height = image.size
    if width < 360 or height < 360:
        return False
    arr = np.array(image.resize((96, 96)).convert("RGB"))
    mean = arr.reshape(-1, 3).mean(axis=0)
    red_logo_like = mean[0] > 185 and mean[1] < 95 and mean[2] < 110
    if red_logo_like:
        return False
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    edge_ratio = float(np.mean(cv2.Canny(gray, 70, 150) > 0))
    if edge_ratio < 0.01:
        return False
    return True


def _build_inspiration_style_context(
    note: dict[str, Any],
    items: list[dict[str, Any]],
    fashion_items: list[dict[str, Any]],
    reference_sheet_path: Path | None = None,
) -> dict[str, Any]:
    public_note = _public_xhs_note(note)
    note_text = " ".join(str(value or "") for value in (public_note.get("title"), public_note.get("desc")))
    usable_items = [item for item in fashion_items if item.get("quality", {}).get("status") in {"usable", "review"}]
    attributes = [item.get("attributes", {}) for item in usable_items]
    all_colors = _most_common_strings(color for attr in attributes for color in attr.get("colors", []))
    all_materials = _most_common_strings(material for attr in attributes for material in attr.get("material", []))
    all_patterns = [
        pattern
        for pattern in _most_common_strings(attr.get("pattern") for attr in attributes if attr.get("pattern"))
        if pattern not in {"solid", "solid_bright"}
    ]
    source_types = _most_common_strings(item.get("reason") for item in items if item.get("reason"))
    text_features = _infer_style_features_from_text(note_text)
    visual_features = _infer_style_features_from_items(usable_items)
    merged = {**visual_features, **{key: value for key, value in text_features.items() if value}}
    brief_parts = [
        f"target_category={merged.get('category', 'top')}",
        f"sleeve={merged.get('sleeve', 'unknown')}",
        f"fit={merged.get('fit', 'unknown')}",
        f"neckline={merged.get('neckline', 'unknown')}",
        f"length={merged.get('length', 'unknown')}",
        f"colors={', '.join(all_colors) or 'unknown'}",
        f"materials={', '.join(all_materials) or 'unknown'}",
        f"patterns={', '.join(all_patterns) or 'unknown'}",
    ]
    if public_note.get("title"):
        brief_parts.append(f"note_title={public_note['title']}")
    if public_note.get("desc"):
        brief_parts.append(f"note_desc={public_note['desc'][:240]}")
    return {
        "note": public_note,
        "reference_sheet_path": _public_output_path(reference_sheet_path) if reference_sheet_path else None,
        "target_category": merged.get("category", "top"),
        "target_attributes": {
            "sleeve": merged.get("sleeve", "unknown"),
            "fit": merged.get("fit", "unknown"),
            "neckline": merged.get("neckline", "unknown"),
            "length": merged.get("length", "unknown"),
            "colors": all_colors,
            "materials": all_materials,
            "patterns": all_patterns,
            "style_tags": _most_common_strings(tag for attr in attributes for tag in attr.get("style_tags", [])),
        },
        "evidence": {
            "usable_item_count": len(usable_items),
            "source_reasons": source_types,
            "text_features": text_features,
            "visual_features": visual_features,
        },
        "brief": "; ".join(part for part in brief_parts if part),
    }


def _infer_style_features_from_text(text: str) -> dict[str, str]:
    lowered = text.lower()
    features: dict[str, str] = {"category": "top"}
    if any(token in text for token in ("长袖", "卫衣", "毛衣", "针织", "开衫", "外套", "冲锋衣")) or "long sleeve" in lowered:
        features["sleeve"] = "long_sleeve"
    if any(token in text for token in ("短袖", "T恤", "polo", "Polo")) or "short sleeve" in lowered:
        features["sleeve"] = "short_sleeve"
    if any(token in text for token in ("宽松", "oversize", "Oversize", "廓形")) or "oversized" in lowered:
        features["fit"] = "loose"
    if any(token in text for token in ("修身", "紧身")) or "slim" in lowered:
        features["fit"] = "slim"
    if any(token in text for token in ("条纹", "横条", "stripe")) or "striped" in lowered:
        features["pattern"] = "striped"
    if any(token in text for token in ("翻领", "polo", "Polo", "领")):
        features["neckline"] = "collar"
    if any(token in text for token in ("短款", "crop", "cropped")):
        features["length"] = "cropped"
    return features


def _infer_style_features_from_items(items: list[dict[str, Any]]) -> dict[str, str]:
    features: dict[str, str] = {"category": "top"}
    attrs = [item.get("attributes", {}) for item in items]
    sleeves = _most_common_strings(attr.get("sleeve") for attr in attrs if attr.get("sleeve") and attr.get("sleeve") != "unknown")
    fits = _most_common_strings(attr.get("fit") for attr in attrs if attr.get("fit"))
    necklines = _most_common_strings(attr.get("neckline") for attr in attrs if attr.get("neckline") and attr.get("neckline") != "unknown")
    patterns = _most_common_strings(attr.get("pattern") for attr in attrs if attr.get("pattern") and attr.get("pattern") != "unknown")
    if sleeves:
        features["sleeve"] = sleeves[0]
    if fits:
        features["fit"] = fits[0]
    if necklines:
        features["neckline"] = necklines[0]
    if patterns:
        features["pattern"] = patterns[0]
    boxes = [item.get("source", {}).get("crop_box") for item in items if isinstance(item.get("source", {}).get("crop_box"), dict)]
    if boxes:
        avg_aspect = float(np.mean([box.get("width", 1) / max(1, box.get("height", 1)) for box in boxes]))
        avg_height = float(np.mean([box.get("height", 0) for box in boxes]))
        if "sleeve" not in features and avg_height >= 520 and avg_aspect <= 0.9:
            features["sleeve"] = "long_sleeve_or_oversized"
        if "fit" not in features and avg_aspect >= 0.72:
            features["fit"] = "loose_or_regular"
    return features


def _most_common_strings(values: Any) -> list[str]:
    counts: dict[str, int] = {}
    for value in values:
        if not value:
            continue
        text = str(value).strip()
        if not text or text == "unknown":
            continue
        counts[text] = counts.get(text, 0) + 1
    return [key for key, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:5]]


def _safe_style_brief(style_brief: str | None) -> str:
    if not style_brief:
        return ""
    text = str(style_brief).strip()
    if len(text) > 2400:
        text = text[:2400]
    return text


async def _download_candidate_images(image_urls: list[str], referer: str, work_dir: Path) -> list[dict[str, Any]]:
    downloaded = []
    headers = {**HTTP_HEADERS, "Referer": referer, "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"}
    async with httpx.AsyncClient(follow_redirects=True, timeout=20, headers=headers) as client:
        for index, url in enumerate(image_urls):
            try:
                response = await client.get(url)
                response.raise_for_status()
                raw = response.content
                if not raw or len(raw) > MAX_IMAGE_BYTES:
                    continue
                image = Image.open(io.BytesIO(raw)).convert("RGB")
                image.load()
            except (httpx.HTTPError, UnidentifiedImageError, OSError):
                continue
            suffix = ".jpg"
            if image.format == "PNG":
                suffix = ".png"
            elif image.format == "WEBP":
                suffix = ".webp"
            source_path = work_dir / f"source_{index:02d}{suffix}"
            image.save(source_path)
            downloaded.append({"url": url, "image": image, "source_path": source_path})
    return downloaded


def _extract_top_from_note_image(image_item: dict[str, Any], index: int, work_dir: Path) -> dict[str, Any]:
    image = image_item["image"]
    source_path = image_item["source_path"]
    garment_stage = GarmentAnalyzer().analyze(image)
    person_stage = _detect_person(image)
    has_top = bool(garment_stage.get("evidence", {}).get("has_top")) and garment_stage["status"] in {"pass", "warn"}
    item: dict[str, Any] = {
        "index": index,
        "source_url": image_item["url"],
        "source_path": _public_output_path(source_path),
        "has_top": False,
        "reason": "no_clear_top",
        "cutout_path": None,
        "mask_path": None,
        "crop_box": None,
        "fashion_items": [],
        "person_detection": person_stage,
        "garment_analysis": garment_stage,
    }
    if not has_top:
        item["reason"] = "no_top_found"
        return item

    if person_stage["status"] in {"pass", "warn"}:
        mask_stage = _generate_upper_body_mask(image, person_stage, work_dir / f"mask_{index:02d}.png")
        item["mask_path"] = _public_output_path(Path(mask_stage["evidence"]["mask_path"])) if mask_stage["status"] in {"pass", "warn"} else None
        item["upper_body_mask"] = mask_stage
        bbox = garment_stage.get("evidence", {}).get("bbox") or garment_stage.get("evidence", {}).get("garment", {}).get("bbox")
        cutout = _save_garment_bbox_cutout(image, bbox, work_dir / f"top_cutout_{index:02d}.png", alpha_mode="worn_top")
        item.update(
            {
                "has_top": True,
                "reason": "person_wearing_top_bbox",
                "cutout_path": _public_output_path(cutout["path"]),
                "crop_box": cutout["box"],
            }
        )
        item["fashion_items"] = [
            _build_fashion_item(
                index=index,
                category="top",
                source_url=image_item["url"],
                source_path=source_path,
                crop_box=cutout["box"],
                cutout_path=cutout["path"],
                clean_reference_path=cutout["path"],
                garment_stage=garment_stage,
                extraction_mode="local_worn_top_crop",
            )
        ]
        return item

    bbox = garment_stage.get("evidence", {}).get("bbox") or garment_stage.get("evidence", {}).get("garment", {}).get("bbox")
    cutout = _save_garment_bbox_cutout(image, bbox, work_dir / f"top_cutout_{index:02d}.png")
    item.update(
        {
            "has_top": True,
            "reason": "single_garment_top",
            "cutout_path": _public_output_path(cutout["path"]),
            "crop_box": cutout["box"],
        }
    )
    item["fashion_items"] = [
        _build_fashion_item(
            index=index,
            category="top",
            source_url=image_item["url"],
            source_path=source_path,
            crop_box=cutout["box"],
            cutout_path=cutout["path"],
            clean_reference_path=cutout["path"],
            garment_stage=garment_stage,
            extraction_mode="local_single_garment_crop",
        )
    ]
    return item


def _build_fashion_item(
    index: int,
    category: str,
    source_url: str,
    source_path: Path,
    crop_box: dict[str, Any],
    cutout_path: Path,
    clean_reference_path: Path,
    garment_stage: dict[str, Any],
    extraction_mode: str,
) -> dict[str, Any]:
    garment = garment_stage.get("evidence", {}).get("garment", _fallback_garment())
    category = category if category in FASHION_ITEM_CATEGORIES else "accessory"
    item_id = hashlib.sha256(f"{source_url}:{index}:{category}:{crop_box}".encode("utf-8")).hexdigest()[:16]
    quality = _fashion_item_quality(category, cutout_path, garment_stage, extraction_mode)
    return {
        "item_id": item_id,
        "category": category,
        "category_label": _fashion_category_label(category),
        "source": {
            "image_index": index,
            "source_url": source_url,
            "source_path": _public_output_path(source_path),
            "crop_box": crop_box,
        },
        "cutout_path": _public_output_path(cutout_path),
        "clean_reference_path": _public_output_path(clean_reference_path),
        "mask_path": None,
        "attributes": {
            "colors": garment.get("colors") or [],
            "material": garment.get("material") or [],
            "fit": garment.get("fit") or "",
            "sleeve": garment.get("sleeve") or "",
            "neckline": garment.get("neckline") or "",
            "pattern": garment.get("pattern") or "",
            "details": garment.get("details") or [],
            "style_tags": garment.get("style_tags") or [],
        },
        "quality": quality,
        "pipeline": {
            "detector": {
                "status": garment_stage.get("status"),
                "confidence": garment_stage.get("confidence"),
                "provider": garment_stage.get("evidence", {}).get("provider"),
            },
            "clean_reference": {
                "status": "pass" if quality["status"] in {"usable", "review"} else "fail",
                "provider": "local_crop_reference",
                "mode": extraction_mode,
                "note": "MVP uses local crop as reference. AI clean extraction can replace this provider later.",
            },
        },
    }


def _fashion_item_quality(category: str, cutout_path: Path, garment_stage: dict[str, Any], extraction_mode: str) -> dict[str, Any]:
    reasons: list[str] = []
    try:
        image = Image.open(cutout_path).convert("RGBA")
        width, height = image.size
        alpha = np.array(image.getchannel("A"))
        visible_ratio = float(np.mean(alpha > 18))
        aspect_ratio = width / max(1, height)
        face_stage = _detect_person(image.convert("RGB"))
    except Exception:
        return {"status": "rejected", "score": 0.0, "reasons": ["reference_unreadable"]}

    score = float(garment_stage.get("confidence") or 0.45)
    if width < 160 or height < 160:
        score -= 0.22
        reasons.append("reference_too_small")
    if visible_ratio < 0.08:
        score -= 0.25
        reasons.append("foreground_too_sparse")
    if category == "top" and not (0.35 <= aspect_ratio <= 2.4):
        score -= 0.12
        reasons.append("top_aspect_unusual")
    if extraction_mode == "local_worn_top_crop":
        score -= 0.28
        reasons.append("needs_ai_clean_reference")
        if visible_ratio > 0.82:
            score -= 0.28
            reasons.append("person_or_background_contamination")
        if face_stage["status"] in {"pass", "warn"}:
            score -= 0.32
            reasons.append("contains_person_face")
        if width >= 900 and height >= 850:
            score -= 0.16
            reasons.append("likely_video_cover_or_full_frame")
    status = "usable" if score >= 0.62 else "review" if score >= 0.42 else "rejected"
    return {"status": status, "score": round(max(0.0, min(1.0, score)), 3), "reasons": reasons}


def _fashion_category_label(category: str) -> str:
    return {
        "top": "上衣",
        "outer": "外套",
        "bottom": "裤子",
        "skirt": "裙子",
        "dress": "连衣裙",
        "shoes": "鞋子",
        "bag": "包",
        "accessory": "配饰",
    }.get(category, "单品")


def _save_upper_body_cutout(image: Image.Image, mask_path: Path, output_path: Path) -> dict[str, Any]:
    mask = Image.open(mask_path).convert("RGBA")
    alpha = np.array(mask.getchannel("A"))
    editable = alpha < 160
    ys, xs = np.where(editable)
    if len(xs) == 0:
        raise HTTPException(status_code=500, detail="上衣区域为空，无法提取")
    pad_x = max(8, int(image.width * 0.02))
    pad_y = max(8, int(image.height * 0.02))
    left = max(0, int(xs.min()) - pad_x)
    top = max(0, int(ys.min()) - pad_y)
    right = min(image.width, int(xs.max()) + pad_x)
    bottom = min(image.height, int(ys.max()) + pad_y)
    rgba = image.convert("RGBA")
    cutout_alpha = Image.fromarray((editable.astype(np.uint8) * 255)).filter(ImageFilter.GaussianBlur(2))
    rgba.putalpha(cutout_alpha)
    cropped = rgba.crop((left, top, right, bottom))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cropped.save(output_path, "PNG")
    return {"path": output_path, "box": {"x": left, "y": top, "width": right - left, "height": bottom - top}}


def _save_garment_bbox_cutout(
    image: Image.Image,
    bbox: dict[str, Any] | None,
    output_path: Path,
    alpha_mode: str = "auto",
) -> dict[str, Any]:
    left, top, right, bottom = _bbox_to_pixel_box(bbox, image.size)
    cropped = image.convert("RGBA").crop((left, top, right, bottom))
    alpha = _worn_top_alpha(cropped) if alpha_mode == "worn_top" else _foreground_alpha(cropped)
    if alpha is not None:
        cropped.putalpha(alpha)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cropped.save(output_path, "PNG")
    return {"path": output_path, "box": {"x": left, "y": top, "width": right - left, "height": bottom - top}}


def _crop_image_by_bbox(image: Image.Image, bbox: dict[str, Any] | None) -> Image.Image:
    left, top, right, bottom = _bbox_to_pixel_box(bbox, image.size)
    return image.crop((left, top, right, bottom))


def _bbox_to_pixel_box(bbox: dict[str, Any] | None, size: tuple[int, int]) -> tuple[int, int, int, int]:
    width, height = size
    if bbox:
        if all(key in bbox for key in ("x", "y", "width", "height")):
            x = float(bbox["x"])
            y = float(bbox["y"])
            bw = float(bbox["width"])
            bh = float(bbox["height"])
            if 0 <= x <= 1 and 0 <= y <= 1 and bw <= 1 and bh <= 1:
                left = int(x * width)
                top = int(y * height)
                right = int((x + bw) * width)
                bottom = int((y + bh) * height)
            else:
                left, top, right, bottom = int(x), int(y), int(x + bw), int(y + bh)
            pad_x = max(8, int(width * 0.02))
            pad_y = max(8, int(height * 0.02))
            return (
                max(0, left - pad_x),
                max(0, top - pad_y),
                min(width, right + pad_x),
                min(height, bottom + pad_y),
            )
    return (0, 0, width, height)


def _foreground_alpha(image: Image.Image) -> Image.Image | None:
    arr = np.array(image.convert("RGB"))
    if arr.size == 0:
        return None
    samples = np.concatenate([arr[:3].reshape(-1, 3), arr[-3:].reshape(-1, 3), arr[:, :3].reshape(-1, 3), arr[:, -3:].reshape(-1, 3)])
    bg = np.median(samples, axis=0)
    diff = np.linalg.norm(arr.astype(np.float32) - bg.astype(np.float32), axis=2)
    mask = diff > 24
    if np.mean(mask) < 0.03 or np.mean(mask) > 0.94:
        return None
    return Image.fromarray((mask.astype(np.uint8) * 255)).filter(ImageFilter.GaussianBlur(1.5))


def _worn_top_alpha(image: Image.Image) -> Image.Image | None:
    arr = np.array(image.convert("RGB"))
    if arr.size == 0:
        return None
    hsv = cv2.cvtColor(cv2.cvtColor(arr, cv2.COLOR_RGB2BGR), cv2.COLOR_BGR2HSV)
    value = hsv[:, :, 2]
    saturation = hsv[:, :, 1]
    dark_cloth = value < 104
    saturated_detail = (saturation > 72) & (value > 70)
    mask = (dark_cloth | saturated_detail).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((13, 13), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))

    components, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if components <= 1:
        return _foreground_alpha(image)

    h, w = mask.shape
    best_label = None
    best_score = 0.0
    for label in range(1, components):
        x, y, bw, bh, area = stats[label]
        if area < w * h * 0.035:
            continue
        cx = (x + bw / 2) / max(1, w)
        center_bonus = 1.0 - min(0.7, abs(cx - 0.5))
        lower_bonus = 1.0 + min(0.3, (y + bh / 2) / max(1, h) * 0.3)
        score = float(area) * center_bonus * lower_bonus
        if score > best_score:
            best_score = score
            best_label = label

    if best_label is None:
        return _foreground_alpha(image)

    selected = (labels == best_label).astype(np.uint8) * 255
    selected = cv2.morphologyEx(selected, cv2.MORPH_CLOSE, np.ones((17, 17), np.uint8))
    flood = selected.copy()
    flood_mask = np.zeros((h + 2, w + 2), np.uint8)
    cv2.floodFill(flood, flood_mask, (0, 0), 255)
    holes = cv2.bitwise_not(flood)
    filled = cv2.bitwise_or(selected, holes)
    if np.mean(filled > 0) < 0.03 or np.mean(filled > 0) > 0.92:
        return _foreground_alpha(image)
    return Image.fromarray(filled).filter(ImageFilter.GaussianBlur(1.4))


def _clean_image_url(raw_url: str) -> str:
    cleaned = html.unescape(raw_url).strip().strip('"\'')
    cleaned = cleaned.replace("\\u002F", "/").replace("\\/", "/")
    if cleaned.startswith("//"):
        cleaned = "https:" + cleaned
    return cleaned


def _looks_like_xhs_image_url(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    if not any(part in host for part in XHS_ALLOWED_HOST_PARTS):
        return False
    if any(token in path for token in (".jpg", ".jpeg", ".png", ".webp", "spectrum", "notes_pre_post")):
        return True
    return "image" in path or "sns-" in host or "xhscdn" in host


def _dominant_colors(image: Image.Image) -> list[str]:
    arr = np.array(image.resize((96, 96)).convert("RGB")).reshape(-1, 3)
    pixels = arr[np.mean(arr, axis=1) < 245]
    if len(pixels) == 0:
        pixels = arr
    quantized = (pixels // 32) * 32
    colors, counts = np.unique(quantized, axis=0, return_counts=True)
    order = np.argsort(counts)[::-1][:4]
    return [_name_color(tuple(int(v + 16) for v in colors[i])) for i in order]


def _dominant_rgb(image: Image.Image) -> tuple[int, int, int]:
    arr = np.array(image.resize((96, 96)).convert("RGB")).reshape(-1, 3)
    pixels = arr[np.mean(arr, axis=1) < 245]
    if len(pixels) == 0:
        pixels = arr
    return tuple(int(v) for v in np.median(pixels, axis=0))


def _estimate_garment_bbox(image: Image.Image) -> dict[str, float] | None:
    small = image.resize((256, max(1, int(256 * image.height / image.width)))).convert("RGB")
    arr = np.array(small)
    samples = np.concatenate([arr[:4].reshape(-1, 3), arr[-4:].reshape(-1, 3), arr[:, :4].reshape(-1, 3), arr[:, -4:].reshape(-1, 3)])
    bg = np.median(samples, axis=0)
    diff = np.linalg.norm(arr.astype(np.float32) - bg.astype(np.float32), axis=2)
    hsv = cv2.cvtColor(cv2.cvtColor(arr, cv2.COLOR_RGB2BGR), cv2.COLOR_BGR2HSV)
    saturation = hsv[:, :, 1]
    gray = cv2.cvtColor(cv2.cvtColor(arr, cv2.COLOR_RGB2BGR), cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 70, 150) > 0
    mask = (diff > 28) | ((saturation > 42) & (diff > 12)) | edges
    mask = mask.astype(np.uint8) * 255
    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    h, w = mask.shape
    candidates = []
    for contour in contours:
        x, y, bw, bh = cv2.boundingRect(contour)
        area = bw * bh
        if area < w * h * 0.025:
            continue
        center_bonus = 1.0 - min(0.8, abs((x + bw / 2) / w - 0.5))
        candidates.append((area * center_bonus, x, y, bw, bh))
    if not candidates:
        return None
    _, x, y, bw, bh = max(candidates, key=lambda item: item[0])
    pad_x = int(w * 0.025)
    pad_y = int(h * 0.025)
    x = max(0, x - pad_x)
    y = max(0, y - pad_y)
    bw = min(w - x, bw + pad_x * 2)
    bh = min(h - y, bh + pad_y * 2)
    return {"x": round(x / w, 4), "y": round(y / h, 4), "width": round(bw / w, 4), "height": round(bh / h, 4)}


def _estimate_worn_top_bbox(image: Image.Image, face_stage: dict[str, Any]) -> dict[str, float] | None:
    if face_stage.get("status") not in {"pass", "warn"}:
        return None
    face = face_stage.get("evidence", {}).get("primary_face", {}).get("box")
    if not face:
        return None
    width, height = image.size
    scale_width = 320
    scale_height = max(1, int(scale_width * height / width))
    small = image.resize((scale_width, scale_height)).convert("RGB")
    arr = np.array(small)
    fx = face["x"] * scale_width / width
    fy = face["y"] * scale_height / height
    fw = face["width"] * scale_width / width
    fh = face["height"] * scale_height / height
    center_x = fx + fw / 2
    roi_left = int(max(0, center_x - fw * 1.35))
    roi_right = int(min(scale_width, center_x + fw * 1.35))
    roi_top = int(min(scale_height - 1, fy + fh * 0.72))
    roi_bottom = int(min(scale_height, fy + fh * 4.25))
    if roi_bottom <= roi_top or roi_right <= roi_left:
        return None

    roi = arr[roi_top:roi_bottom, roi_left:roi_right]
    hsv = cv2.cvtColor(cv2.cvtColor(roi, cv2.COLOR_RGB2BGR), cv2.COLOR_BGR2HSV)
    value = hsv[:, :, 2]
    saturation = hsv[:, :, 1]
    gray = cv2.cvtColor(cv2.cvtColor(roi, cv2.COLOR_RGB2BGR), cv2.COLOR_BGR2GRAY)
    dark = value < 82
    colored_dark = (value < 122) & (saturation > 20)
    edges = cv2.Canny(gray, 50, 140) > 0
    mask = (dark | colored_dark).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        mask = edges.astype(np.uint8) * 255
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    roi_h, roi_w = mask.shape
    for contour in contours:
        x, y, bw, bh = cv2.boundingRect(contour)
        area = bw * bh
        if area < roi_w * roi_h * 0.045:
            continue
        cx = (x + bw / 2) / max(1, roi_w)
        center_bonus = 1.0 - min(0.75, abs(cx - 0.5))
        lower_bonus = 1.0 + min(0.35, y / max(1, roi_h) * 0.35)
        candidates.append((area * center_bonus * lower_bonus, x, y, bw, bh))
    if not candidates:
        return None
    _, x, y, bw, bh = max(candidates, key=lambda item: item[0])
    pad_x = int(roi_w * 0.04)
    pad_y = int(roi_h * 0.035)
    left = max(roi_left, roi_left + x - pad_x)
    top = max(roi_top, roi_top + y - pad_y)
    right = min(roi_right, roi_left + x + bw + pad_x)
    bottom = min(roi_bottom, roi_top + y + bh + pad_y)
    if right <= left or bottom <= top:
        return None
    return {
        "x": round(left / scale_width, 4),
        "y": round(top / scale_height, 4),
        "width": round((right - left) / scale_width, 4),
        "height": round((bottom - top) / scale_height, 4),
    }


def _local_has_top_candidate(
    image: Image.Image,
    bbox: dict[str, float] | None,
    edge_density: float,
    saturation: float,
    face_stage: dict[str, Any],
) -> bool:
    if face_stage["status"] in {"pass", "warn"}:
        return True
    if bbox is None:
        return False
    area = bbox["width"] * bbox["height"]
    aspect = bbox["width"] / max(0.01, bbox["height"])
    if area < 0.04 or area > 0.92:
        return False
    if aspect < 0.25 or aspect > 2.6:
        return False
    if edge_density < 0.003 and saturation < 18:
        return False
    return True


def _guess_sleeve(source_type: str, bbox: dict[str, float] | None) -> str:
    if source_type == "person_wearing_top":
        return "unknown"
    if not bbox:
        return "unknown"
    aspect = bbox["width"] / max(0.01, bbox["height"])
    if aspect > 1.05:
        return "short_or_wide_sleeve"
    if bbox["height"] > 0.62:
        return "long_sleeve"
    return "unknown"


def _name_color(rgb: tuple[int, int, int]) -> str:
    r, g, b = rgb
    if max(rgb) < 55:
        return "black"
    if min(rgb) > 210:
        return "white"
    if max(rgb) - min(rgb) < 26:
        return "gray"
    if r > g * 1.25 and r > b * 1.25:
        return "red" if g < 120 else "orange"
    if g > r * 1.15 and g > b * 1.15:
        return "green"
    if b > r * 1.15 and b > g * 1.1:
        return "blue"
    if r > 150 and b > 140 and g < 150:
        return "purple"
    if r > 150 and g > 130 and b < 110:
        return "yellow"
    return "mixed"


def _guess_material(edge_density: float, saturation: float) -> list[str]:
    if edge_density > 0.14:
        return ["knit_or_textured"]
    if saturation < 35:
        return ["cotton_or_blend"]
    return ["smooth_fabric"]


def _guess_pattern(edge_density: float, saturation: float) -> str:
    if edge_density > 0.18:
        return "printed_or_textured"
    if saturation > 85:
        return "solid_bright"
    return "solid"


def _guess_details(edge_density: float) -> list[str]:
    return ["visible_texture"] if edge_density > 0.14 else ["minimal_details"]


def _guess_style_tags(colors: list[str], saturation: float) -> list[str]:
    tags = ["casual"]
    if saturation > 80:
        tags.append("statement")
    if {"black", "white", "gray"}.intersection(colors):
        tags.append("minimal")
    return tags


def _edge_density(image: Image.Image) -> float:
    gray = cv2.cvtColor(_pil_to_bgr(image.resize((256, 256))), cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 80, 160)
    return round(float(np.mean(edges > 0)), 4)


def _median_saturation(image: Image.Image) -> float:
    hsv = cv2.cvtColor(_pil_to_bgr(image.resize((128, 128))), cv2.COLOR_BGR2HSV)
    return round(float(np.median(hsv[:, :, 1])), 2)


def _face_region_difference(original: Image.Image, result: Image.Image, person_stage: dict[str, Any]) -> float:
    box = person_stage["evidence"]["primary_face"]["box"]
    margin = int(box["width"] * 0.18)
    left = max(0, box["x"] - margin)
    top = max(0, box["y"] - margin)
    right = min(original.width, box["x"] + box["width"] + margin)
    bottom = min(original.height, box["y"] + box["height"] + margin)
    a = np.array(original.crop((left, top, right, bottom)).convert("RGB"), dtype=np.float32)
    b = np.array(result.crop((left, top, right, bottom)).convert("RGB"), dtype=np.float32)
    return round(float(np.mean(np.abs(a - b))), 2)


def _protected_region_difference(original: Image.Image, result: Image.Image, mask_path: Path) -> float:
    mask = Image.open(mask_path).convert("RGBA")
    protected = np.array(mask.getchannel("A")) > 220
    a = np.array(original.convert("RGB"), dtype=np.float32)
    b = np.array(result.convert("RGB"), dtype=np.float32)
    if not np.any(protected):
        return 255.0
    return round(float(np.mean(np.abs(a[protected] - b[protected]))), 2)


def _mask_editable_ratio(mask_path: Path) -> float:
    try:
        mask = Image.open(mask_path).convert("RGBA")
    except Exception:
        return 0.0
    alpha = np.array(mask.getchannel("A"))
    return round(float(np.mean(alpha < 128)), 4)


def _sharpness(image: Image.Image) -> float:
    gray = cv2.cvtColor(_pil_to_bgr(image), cv2.COLOR_BGR2GRAY)
    return round(float(cv2.Laplacian(gray, cv2.CV_64F).var()), 2)


def _pil_to_bgr(image: Image.Image) -> np.ndarray:
    rgb = np.array(image.convert("RGB"))
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def _suffix_for_format(fmt: str | None) -> str:
    return { "JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp" }.get(fmt or "", ".jpg")


def _fallback_garment() -> dict[str, Any]:
    return {
        "category": "top",
        "colors": [],
        "material": [],
        "fit": "regular",
        "sleeve": "unknown",
        "neckline": "unknown",
        "pattern": "unknown",
        "details": [],
        "style_tags": [],
    }


def _stage(status: str, confidence: float, evidence: dict[str, Any], issues: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "status": status,
        "confidence": confidence,
        "evidence": evidence,
        "issues": issues,
        "suggestions": [issue["suggestion"] for issue in issues if issue.get("suggestion")],
    }


def _issue(code: str, message: str, suggestion: str) -> dict[str, str]:
    return {"code": code, "message": message, "suggestion": suggestion}
