from __future__ import annotations

import hashlib
import html
import io
import json
import os
import re
import shutil
import base64
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from fastapi import HTTPException, UploadFile
from PIL import Image, ImageDraw, ImageFilter, UnidentifiedImageError

from app.storage import storage_context, user_asset_public_path
from app.tryon import (
    FASHION_ITEM_CATEGORIES,
    HTTP_HEADERS,
    MAX_IMAGE_BYTES,
    SUPPORTED_FORMATS,
    TRYON_OUTPUT_DIR,
    FashionItemDetector,
    _download_candidate_images,
    _extract_image_urls_from_html,
    _extract_xhs_note_image_urls,
    _extract_xhs_note_payload,
    _fashion_category_label,
    _detect_person,
    _normalize_xhs_url,
    _public_output_path,
    _read_upload_image,
    _string_list,
    _has_openai_compatible_provider,
    _has_openai_image_edit_provider,
    _has_runway_google_provider,
    _openai_base_url,
    _openai_compatible_client,
    _default_garment_analysis_provider,
    _default_tryon_vision_model,
    _extract_json_object,
    _extract_runway_google_image,
    _image_to_data_url,
    _path_to_runway_inline_data,
    _response_shape,
    _runway_google_api_key,
    _runway_google_auth_headers,
    _runway_google_error_summary,
    _runway_google_url,
    image_edit_model,
)


ROOT_DIR = Path(__file__).resolve().parents[1]
CLOSET_OUTPUT_DIR = ROOT_DIR / "outputs" / "closet"
CLOSET_SOURCE_DIR = CLOSET_OUTPUT_DIR / "sources"
CLOSET_ITEM_DIR = CLOSET_OUTPUT_DIR / "items"
CLOSET_MANIFEST_PATH = CLOSET_OUTPUT_DIR / "closet_manifest.json"
OUTFIT_DIR = CLOSET_OUTPUT_DIR / "outfits"
OUTFIT_MANIFEST_PATH = CLOSET_OUTPUT_DIR / "outfits_manifest.json"
TRYON_RECORD_DIR = CLOSET_OUTPUT_DIR / "tryon_records"
TRYON_RECORDS_MANIFEST_PATH = CLOSET_OUTPUT_DIR / "tryon_records_manifest.json"
CLOSET_SUPPORTED_CATEGORIES = {"top", "bottom", "skirt", "dress", "shoes", "bag", "accessory"}
MAX_LINK_IMAGES = 12
OUTFIT_LAYOUT_VERSION = "selfit_flatlay_v1_card_safe"
IMPORT_PIPELINE_VERSION = "closet_import_v2"
IMPORT_JOB_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="selfit-closet-import")
IMPORT_JOB_LOCK = threading.Lock()
IMPORT_PIPELINE_LOCK = threading.Lock()
SEGFORMER_CLOTHES_MODEL_ID = "mattmdjaga/segformer_b2_clothes"
SEGFORMER_LABEL_CATEGORY_HINTS = {
    "top": ("upper", "shirt", "blouse", "coat", "jacket", "sweater", "hoodie", "cardigan", "vest", "t-shirt", "top"),
    "bottom": ("pants", "trouser", "jeans", "leggings", "shorts"),
    "skirt": ("skirt",),
    "dress": ("dress", "jumpsuit", "romper"),
    "shoes": ("shoe", "sneaker", "boot", "sandal", "loafer", "heel"),
    "bag": ("bag", "handbag", "backpack", "purse", "clutch"),
    "accessory": ("hat", "cap", "scarf", "belt", "sunglasses", "glove", "sock", "tie", "accessory"),
}

STYLE_TOKEN_ALIASES = {
    "minimal": ("minimal", "minimalist", "clean", "simple", "简洁", "极简", "低装饰", "克制"),
    "structured": ("structured", "tailored", "sharp", "clean lines", "秩序", "利落", "结构", "清晰线条", "剪裁"),
    "soft": ("soft", "gentle", "flowy", "drape", "柔和", "温柔", "轻盈", "垂坠"),
    "classic": ("classic", "timeless", "preppy", "heritage", "经典", "老钱", "学院", "稳定质感"),
    "romantic": ("romantic", "lace", "ruffle", "feminine", "浪漫", "蕾丝", "荷叶", "女性"),
    "casual": ("casual", "relaxed", "everyday", "休闲", "松弛", "日常", "舒适"),
    "sporty": ("sport", "sporty", "athletic", "outdoor", "运动", "户外", "机能"),
    "vintage": ("vintage", "retro", "nostalgic", "复古", "怀旧"),
    "dark": ("dark", "goth", "black", "leather", "暗黑", "冷硬", "黑色", "皮革"),
    "expressive": ("expressive", "bold", "statement", "contrast", "高表达", "大胆", "撞色", "冲突", "夸张"),
    "airy": ("airy", "sheer", "transparent", "satin", "空气感", "薄纱", "半透明", "缎面", "冷雾"),
}

COLOR_TOKEN_ALIASES = {
    "black": ("black", "charcoal", "onyx", "黑", "炭黑", "曜石"),
    "white": ("white", "ivory", "cream", "oat", "白", "象牙", "奶油", "烟白", "雾白"),
    "gray": ("gray", "grey", "silver", "灰", "银", "水泥"),
    "blue": ("blue", "navy", "denim", "蓝", "藏青", "雾蓝", "冰蓝"),
    "brown": ("brown", "camel", "tan", "coffee", "chocolate", "棕", "驼", "咖啡", "焦糖", "巧克力"),
    "red": ("red", "burgundy", "wine", "红", "酒红", "番茄"),
    "pink": ("pink", "rose", "blush", "粉", "玫瑰", "裸粉"),
    "green": ("green", "mint", "olive", "绿", "薄荷", "墨绿"),
    "yellow": ("yellow", "lemon", "champagne", "黄", "柠檬", "香槟"),
    "purple": ("purple", "violet", "lavender", "紫", "薰衣草"),
}


def _legacy_paths_active() -> bool:
    return CLOSET_OUTPUT_DIR != ROOT_DIR / "outputs" / "closet"


def _closet_output_dir() -> Path:
    return CLOSET_OUTPUT_DIR if _legacy_paths_active() else storage_context().closet_output_dir


def _closet_source_dir() -> Path:
    return CLOSET_SOURCE_DIR if _legacy_paths_active() else storage_context().closet_source_dir


def _closet_item_dir() -> Path:
    return CLOSET_ITEM_DIR if _legacy_paths_active() else storage_context().closet_item_dir


def _closet_manifest_path() -> Path:
    return CLOSET_MANIFEST_PATH if _legacy_paths_active() else storage_context().closet_manifest_path


def _outfit_dir() -> Path:
    return OUTFIT_DIR if _legacy_paths_active() else storage_context().outfit_dir


def _outfit_manifest_path() -> Path:
    return OUTFIT_MANIFEST_PATH if _legacy_paths_active() else storage_context().outfit_manifest_path


def _tryon_record_dir() -> Path:
    return TRYON_RECORD_DIR if _legacy_paths_active() else storage_context().tryon_record_dir


def _tryon_records_manifest_path() -> Path:
    return TRYON_RECORDS_MANIFEST_PATH if _legacy_paths_active() else storage_context().tryon_records_manifest_path


def _user_preferences_path() -> Path:
    return storage_context().user_root / "preferences.json"


def _import_job_dir() -> Path:
    return storage_context().user_root / "closet" / "import_jobs"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _public_closet_path(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return user_asset_public_path("closet", path, _closet_output_dir())
    except ValueError:
        try:
            relative = path.relative_to(CLOSET_OUTPUT_DIR)
            return f"/closet-outputs/{relative.as_posix()}"
        except ValueError:
            return str(path)


def _closet_disk_path(public_path: str | None) -> Path | None:
    if not public_path:
        return None
    if public_path.startswith("/user-assets/closet/"):
        return _closet_output_dir() / public_path.replace("/user-assets/closet/", "", 1)
    if public_path.startswith("/user-assets/tryon/"):
        return storage_context().tryon_output_dir / public_path.replace("/user-assets/tryon/", "", 1)
    if public_path.startswith("/closet-outputs/"):
        return CLOSET_OUTPUT_DIR / public_path.replace("/closet-outputs/", "", 1)
    if public_path.startswith("/tryon-outputs/"):
        return TRYON_OUTPUT_DIR / public_path.replace("/tryon-outputs/", "", 1)
    return Path(public_path)


def _ensure_manifest() -> dict[str, Any]:
    _closet_source_dir().mkdir(parents=True, exist_ok=True)
    _closet_item_dir().mkdir(parents=True, exist_ok=True)
    if not _closet_manifest_path().exists():
        return {"version": 1, "items": []}
    try:
        data = json.loads(_closet_manifest_path().read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            return data
    except json.JSONDecodeError:
        pass
    return {"version": 1, "items": []}


def _write_manifest(data: dict[str, Any]) -> None:
    _closet_output_dir().mkdir(parents=True, exist_ok=True)
    tmp_path = _closet_manifest_path().with_suffix(".tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(_closet_manifest_path())


def _ensure_outfit_manifest() -> dict[str, Any]:
    _outfit_dir().mkdir(parents=True, exist_ok=True)
    if not _outfit_manifest_path().exists():
        return {"version": 1, "outfits": [], "plans": []}
    try:
        data = json.loads(_outfit_manifest_path().read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("outfits"), list):
            data.setdefault("plans", [])
            return data
    except json.JSONDecodeError:
        pass
    return {"version": 1, "outfits": [], "plans": []}


def _write_outfit_manifest(data: dict[str, Any]) -> None:
    _outfit_dir().mkdir(parents=True, exist_ok=True)
    tmp_path = _outfit_manifest_path().with_suffix(".tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(_outfit_manifest_path())


def _ensure_tryon_records_manifest() -> dict[str, Any]:
    _tryon_record_dir().mkdir(parents=True, exist_ok=True)
    if not _tryon_records_manifest_path().exists():
        return {"version": 1, "records": []}
    try:
        data = json.loads(_tryon_records_manifest_path().read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("records"), list):
            return data
    except json.JSONDecodeError:
        pass
    return {"version": 1, "records": []}


def _write_tryon_records_manifest(data: dict[str, Any]) -> None:
    _tryon_record_dir().mkdir(parents=True, exist_ok=True)
    tmp_path = _tryon_records_manifest_path().with_suffix(".tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(_tryon_records_manifest_path())


def _save_source_image(raw: bytes, filename: str | None, source_type: str, index: int = 0, source_url: str | None = None) -> dict[str, Any]:
    if not raw:
        raise HTTPException(status_code=400, detail="图片为空")
    if len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="图片超过 12MB")
    try:
        pil_image = Image.open(io.BytesIO(raw))
        pil_image.load()
    except UnidentifiedImageError as exc:
        raise HTTPException(status_code=400, detail="无法识别图片格式") from exc
    if pil_image.format not in SUPPORTED_FORMATS:
        raise HTTPException(status_code=400, detail="仅支持 JPG、PNG、WebP")

    image_id = hashlib.sha256(raw).hexdigest()[:16]
    suffix = { "JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp" }.get(pil_image.format, ".png")
    saved_path = _closet_source_dir() / f"{source_type}_{index:02d}_{image_id}{suffix}"
    _closet_source_dir().mkdir(parents=True, exist_ok=True)
    saved_path.write_bytes(raw)
    image = pil_image.convert("RGB")
    return {
        "image": image,
        "image_id": image_id,
        "saved_path": saved_path,
        "source": {
            "type": source_type,
            "url": source_url,
            "filename": filename,
            "image_index": index,
            "source_path": _public_closet_path(saved_path),
            "width": image.width,
            "height": image.height,
        },
    }


def closet_capabilities() -> dict[str, Any]:
    ai_cutout = AIGarmentCutoutProvider()
    segmenter = SegFormerClothesAdapter()
    rembg = RembgMattingProvider()
    birefnet = BiRefNetMattingProvider()
    model_available = segmenter.available()
    edge_available = rembg.available() or birefnet.available()
    return {
        "status": "ready_for_validation",
        "storage": {
            "mode": "local_json_and_files",
            "manifest_path": str(_closet_manifest_path()),
            "outfit_manifest_path": str(_outfit_manifest_path()),
            "source_dir": str(_closet_source_dir()),
            "item_dir": str(_closet_item_dir()),
            "outfit_dir": str(_outfit_dir()),
            "user_id": storage_context().user_id,
        },
        "imports": {
            "upload": True,
            "outfit_split": True,
            "outfit_max_items": 12,
            "xiaohongshu": True,
            "webpage": True,
            "max_link_images": MAX_LINK_IMAGES,
        },
        "models": {
            "primary": {
                "name": ai_cutout.model,
                "provider": ai_cutout._provider_kind() or ai_cutout.mode,
                "available": ai_cutout.available(),
                "status": ai_cutout.status(),
                "categories": sorted(CLOSET_SUPPORTED_CATEGORIES),
            },
            "alternatives": [
                {
                    "name": segmenter.model_id,
                    "provider": "segformer_b2_clothes",
                    "available": model_available,
                    "status": segmenter.status(),
                }
            ],
            "matting": {
                "rembg": {
                    "available": rembg.available(),
                    "status": rembg.status(),
                },
                "birefnet": {
                    "available": birefnet.available(),
                    "status": birefnet.status(),
                },
            },
            "fallback": {
                "name": "segformer_then_existing_top_detector",
                "available": True,
                "status": "enabled",
            },
            "edge_refine": {
                "name": "rembg_or_birefnet_adapter",
                "available": edge_available,
                "status": "available" if edge_available else "reserved",
            },
        },
        "categories": {
            "supported": sorted(CLOSET_SUPPORTED_CATEGORIES),
            "tryon_ready": ["top", "bottom", "skirt", "dress"],
            "legacy_single_image_tryon": ["top"],
            "match_before_tryon": ["shoes", "bag", "accessory"],
        },
        "outfits": {
            "enabled": True,
            "tryon_mode": "category_aware_outfit_reference",
        },
        "mode": "ai_garment_first" if ai_cutout.available() else "local_open_source_fallback",
    }


class AIGarmentCutoutProvider:
    """Uses the same image service as try-on for the product-facing garment cutout.

    The local segmentation pipeline remains deliberately separate: an AI image result
    has to preserve transparency and pass our quality checks before it can replace it.
    """

    mode = "ai_garment_cutout"
    _availability_cache: dict[tuple[str | None, ...], str | None] = {}

    def __init__(self, model: str | None = None) -> None:
        self.model = model or image_edit_model()
        self.last_attempt: dict[str, Any] = {}

    def available(self) -> bool:
        return self._provider_kind() is not None

    def _provider_kind(self) -> str | None:
        enabled = os.environ.get("SELFIT_GARMENT_AI_ENABLED", "1").strip().lower()
        if enabled in {"0", "false", "no", "off"}:
            return None
        config_signature = (
            enabled,
            os.environ.get("TRYON_RUNWAY_GOOGLE_URL"),
            os.environ.get("RUNWAY_GOOGLE_URL"),
            os.environ.get("TRYON_RUNWAY_GOOGLE_API_KEY"),
            os.environ.get("RUNWAY_GOOGLE_API_KEY"),
            os.environ.get("REDNOTE_RUNWAY_API_KEY"),
            os.environ.get("TRYON_OPENAI_BASE_URL"),
            os.environ.get("OPENAI_BASE_URL"),
            os.environ.get("OPENAI_API_BASE"),
            os.environ.get("LOCAL_OPENAI_BASE_URL"),
            os.environ.get("TRYON_OPENAI_API_KEY"),
            os.environ.get("OPENAI_API_KEY"),
            os.environ.get("LOCAL_OPENAI_API_KEY"),
        )
        if config_signature in self._availability_cache:
            return self._availability_cache[config_signature]
        if _has_runway_google_provider():
            provider = "runway_google_generate_content"
        elif _has_openai_compatible_provider() and _has_openai_image_edit_provider():
            provider = "openai_image_edit"
        else:
            provider = None
        self._availability_cache[config_signature] = provider
        return provider

    def status(self) -> str:
        if os.environ.get("SELFIT_GARMENT_AI_ENABLED", "1").strip().lower() in {"0", "false", "no", "off"}:
            return "disabled_by_env"
        provider = self._provider_kind()
        return "available_via_runway" if provider == "runway_google_generate_content" else "available_via_openai" if provider else "provider_not_configured"

    def _uses_runway(self) -> bool:
        return self._provider_kind() == "runway_google_generate_content"

    def _uses_openai(self) -> bool:
        return self._provider_kind() == "openai_image_edit"

    def extract(self, source: dict[str, Any], work_dir: Path) -> list[dict[str, Any]]:
        provider = self._provider_kind()
        self.last_attempt = {"provider": provider or "none", "model": self.model, "status": "not_started"}
        if provider is None:
            self.last_attempt.update({"status": "skipped", "reason": "provider_not_configured"})
            return []
        try:
            analysis = _default_garment_analysis_provider().analyze(source["image"])
            evidence = analysis.get("evidence") or {}
            garment = evidence.get("garment") or {}
            category = str(garment.get("category") or "").strip().lower()
            confidence = float(analysis.get("confidence") or 0)
            if analysis.get("status") not in {"pass", "warn"} or category not in CLOSET_SUPPORTED_CATEGORIES or confidence < 0.68:
                self.last_attempt.update({"status": "skipped", "reason": "garment_analysis_not_confident", "analysis_status": analysis.get("status"), "analysis_score": round(confidence, 3)})
                return []

            cutout = self._generate_cutout(source["saved_path"], category)
            if cutout is None:
                self.last_attempt.setdefault("reason", "image_provider_did_not_return_an_image")
                self.last_attempt["status"] = "failed"
                return []
            raw_output_path = work_dir / "ai_cutout_raw.png"
            raw_output_path.parent.mkdir(parents=True, exist_ok=True)
            cutout.save(raw_output_path)
            self.last_attempt["raw_output_path"] = _public_closet_path(raw_output_path)
            cutout, matting_status = _ensure_transparent_ai_cutout(cutout)
            if not _has_meaningful_transparency(cutout):
                self.last_attempt.update({"status": "rejected", "reason": "image_provider_result_is_not_transparent"})
                return []
            if matting_status != "native_alpha":
                matted_path = work_dir / "ai_cutout_matted.png"
                cutout.save(matted_path)
                self.last_attempt["matted_output_path"] = _public_closet_path(matted_path)
            item = _closet_item_from_ai_cutout(
                category=category,
                cutout=cutout,
                source=source,
                provider_name=self._provider_kind() or self.mode,
                model=self.model,
                analysis=analysis,
            )
            if item:
                item.setdefault("pipeline", {}).setdefault("matting", {}).update({"provider": matting_status, "status": "transparent_png_verified"})
            self.last_attempt.update({"status": "ok", "category": category, "analysis_score": round(confidence, 3)})
            return [item] if item else []
        except Exception as exc:
            self.last_attempt.update({"status": "failed", "reason": "adapter_exception", "error": str(exc)[:300]})
            return []

    def extract_inventory(self, source: dict[str, Any], work_dir: Path) -> list[dict[str, Any]]:
        """Find every visible fashion item, then create one transparent cutout per item.

        This is deliberately separate from ``extract``: the latter remains the high
        fidelity single-item path, while this method owns outfit/flat-lay splitting.
        """
        provider = self._provider_kind()
        inventory_attempt: dict[str, Any] = {
            "provider": provider or "none",
            "model": self.model,
            "status": "not_started",
            "expected_count": 0,
            "created_count": 0,
        }
        self.last_attempt = inventory_attempt
        if provider is None:
            inventory_attempt.update({"status": "skipped", "reason": "provider_not_configured"})
            return []
        try:
            candidates = self._analyze_inventory(source["image"])
            inventory_attempt["expected_count"] = len(candidates)
            inventory_attempt["categories"] = [candidate["category"] for candidate in candidates]
            if not candidates:
                inventory_attempt.update({
                    "status": "skipped",
                    "reason": "no_inventory",
                })
                return []

            items: list[dict[str, Any]] = []
            failures: list[dict[str, Any]] = []
            for index, candidate in enumerate(candidates):
                candidate_path = _save_inventory_candidate_crop(source, candidate, work_dir, index)
                cutout = self._generate_cutout(candidate_path, candidate["category"])
                if cutout is None:
                    failures.append({"index": index, "category": candidate["category"], "reason": "missing_transparent_cutout"})
                    continue
                raw_output_path = work_dir / f"inventory_{index:02d}_{candidate['category']}_raw.png"
                cutout.save(raw_output_path)
                cutout, matting_status = _ensure_transparent_ai_cutout(cutout)
                if not _has_meaningful_transparency(cutout):
                    failures.append({"index": index, "category": candidate["category"], "reason": "missing_transparent_cutout", "raw_output_path": _public_closet_path(raw_output_path)})
                    continue
                if matting_status != "native_alpha":
                    cutout.save(work_dir / f"inventory_{index:02d}_{candidate['category']}_matted.png")
                analysis = {
                    "status": "pass" if candidate["confidence"] >= 0.68 else "warn",
                    "confidence": candidate["confidence"],
                    "evidence": {
                        "provider": "fashion_inventory",
                        "garment": {
                            "category": candidate["category"],
                            "bbox": candidate["bbox"],
                            "colors": candidate.get("colors", []),
                            "material": candidate.get("material", []),
                            "style_tags": candidate.get("style_tags", []),
                        },
                    },
                }
                item = _closet_item_from_ai_cutout(
                    category=candidate["category"],
                    cutout=cutout,
                    source=source,
                    provider_name=provider,
                    model=self.model,
                    analysis=analysis,
                    instance_key=f"inventory:{index}:{candidate['bbox']}",
                )
                if item:
                    item.setdefault("pipeline", {}).setdefault("matting", {}).update({"provider": matting_status, "status": "transparent_png_verified"})
                    item.setdefault("pipeline", {})["inventory"] = {
                        "provider": provider,
                        "status": "ok",
                        "candidate_index": index,
                        "candidate_count": len(candidates),
                        "bbox": candidate["bbox"],
                    }
                    items.append(item)
                else:
                    failures.append({"index": index, "category": candidate["category"], "reason": "quality_rejected"})

            inventory_attempt.update({
                "status": "ok" if len(items) == len(candidates) else "partial" if items else "failed",
                "created_count": len(items),
                "failures": failures,
            })
            return items
        except Exception as exc:
            inventory_attempt.update({"status": "failed", "reason": "inventory_exception", "error": str(exc)[:300]})
            return []

    def _analyze_inventory(self, image: Image.Image) -> list[dict[str, Any]]:
        prompt = (
            "Analyze this fashion image and enumerate every distinct wearable item that should become a closet item. "
            "Include tops, bottoms, skirts, dresses, shoes as a pair, bags and accessories. Exclude people, skin, hair, "
            "phones, furniture, text, shadows and background objects. Return strict JSON only with schema "
            "{items:[{category:string,bbox:{x:number,y:number,width:number,height:number},confidence:number,fully_visible:boolean,"
            "colors:string[],material:string[],style_tags:string[]}]}. Coordinates must be normalized 0-1. "
            "Every x, y, width and height value must be a decimal from 0.0 through 1.0; never use pixels, percentages, or 0-1000 coordinates. "
            "Use only categories top,bottom,skirt,dress,shoes,bag,accessory. Keep separate garments as separate items, "
            "but treat the two shoes of one pair as one item. Do not split a dress into top and skirt. "
            "Only include real fashion items whose usable silhouette is mostly visible. Ignore base garments that are cut off by the frame, "
            "and never classify towels, blankets, bedding, curtains, upholstery or folded household textiles as accessories."
        )
        if self._uses_runway():
            text = self._analyze_inventory_with_runway(image, prompt)
        else:
            text = self._analyze_inventory_with_openai(image, prompt)
        payload = _extract_json_object(text or "")
        return _normalize_inventory_candidates(payload.get("items"))

    def _analyze_inventory_with_runway(self, image: Image.Image, prompt: str) -> str:
        api_key = _runway_google_api_key()
        if not api_key:
            return ""
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, "JPEG", quality=92)
        payload = {
            "contents": [{"role": "user", "parts": [
                {"inlineData": {"mimeType": "image/jpeg", "data": base64.b64encode(buffer.getvalue()).decode("ascii")}},
                {"text": prompt},
            ]}],
            # The Runway Google proxy rejects an explicit TEXT-only modality for
            # gemini-*-image models. Omitting it still returns text without asking
            # the image model to generate a wasteful image response.
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 4096},
        }
        response = httpx.post(
            _runway_google_url(),
            headers={**_runway_google_auth_headers(_runway_google_url(), api_key), "Content-Type": "application/json"},
            json=payload,
            timeout=90,
        )
        response.raise_for_status()
        data = response.json()
        texts: list[str] = []
        for candidate in data.get("candidates") or []:
            for part in ((candidate.get("content") or {}).get("parts") or []):
                if isinstance(part.get("text"), str):
                    texts.append(part["text"])
        return "\n".join(texts)

    def _analyze_inventory_with_openai(self, image: Image.Image, prompt: str) -> str:
        from openai import OpenAI

        client = _openai_compatible_client(OpenAI)
        vision_model = os.environ.get("TRYON_VISION_MODEL") or _default_tryon_vision_model()
        image_url = _image_to_data_url(image)
        try:
            response = client.responses.create(
                model=vision_model,
                input=[{"role": "user", "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": image_url, "detail": "high"},
                ]}],
            )
            return getattr(response, "output_text", "") or ""
        except Exception as responses_exc:
            response = client.chat.completions.create(
                model=vision_model,
                messages=[{"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ]}],
                max_tokens=1600,
            )
            text = response.choices[0].message.content or ""
            if not text:
                raise responses_exc
            return text

    def _generate_cutout(self, source_path: Path, category: str | None = None) -> Image.Image | None:
        if self._uses_runway():
            return self._generate_runway_cutout(source_path, category)
        if self._uses_openai():
            return self._generate_openai_cutout(source_path, category)
        return None

    def _generate_runway_cutout(self, source_path: Path, category: str | None = None) -> Image.Image | None:
        api_key = _runway_google_api_key()
        if not api_key:
            return None
        prompt = (
            f"请从输入图片中提取唯一的{_fashion_category_label(category) if category else '主服饰/鞋/包'}单品，生成忠实的商品抠图。"
            "完整保留原始单品的轮廓、颜色、面料纹理、蕾丝、纽扣、印花、鞋带、背带和边缘。"
            "必须去除人物、皮肤、手、衣架、背景、地面、阴影、文字、水印和其他物体。"
            "最终只输出一件居中的单品，背景使用单一、均匀、无纹理的纯洋红色 #FF00FF，方便系统转换为透明 alpha。"
            "严禁绘制透明棋盘格、渐变、地面或投影；不要重新设计，不能裁掉单品任何部分。"
            f"使用与试穿一致的图片模型配置：{self.model}。"
        )
        payload = {
            "contents": [{"role": "user", "parts": [_path_to_runway_inline_data(source_path), {"text": prompt}]}],
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
        try:
            response = httpx.post(
                _runway_google_url(),
                headers={**_runway_google_auth_headers(_runway_google_url(), api_key), "Content-Type": "application/json"},
                json=payload,
                timeout=180,
            )
            response.raise_for_status()
            data = response.json()
            provider_error = _runway_google_error_summary(data)
            if provider_error:
                self.last_attempt.update({"status": "failed", "reason": "runway_provider_error", "provider_error": provider_error})
                return None
            image_payload = _extract_runway_google_image(data)
            if not image_payload:
                self.last_attempt.update({"status": "failed", "reason": "runway_response_has_no_image", "response_shape": _response_shape(data)})
                return None
            _, encoded = image_payload
            image = Image.open(io.BytesIO(base64.b64decode(encoded))).convert("RGBA")
            image.load()
            return image
        except Exception as exc:
            self.last_attempt.update({"status": "failed", "reason": "runway_request_failed", "error": str(exc)[:300]})
            return None

    def _generate_openai_cutout(self, source_path: Path, category: str | None = None) -> Image.Image | None:
        try:
            from openai import OpenAI

            client = _openai_compatible_client(OpenAI)
            prompt = (
                f"Extract the single {category or 'main fashion'} item from this image as a faithful product cutout. "
                "Preserve the exact garment silhouette, color, fabric texture, trims, print, buttons, straps and edges. "
                "Remove every person, mannequin, skin, hanger, hand, text, logo overlay, floor and background. "
                "Return one centered item only as a PNG with a fully transparent background. Do not redesign, restyle, "
                "add a shadow, add a studio background, crop off any part of the item, or create a collage."
            )
            with source_path.open("rb") as image_file:
                try:
                    response = client.images.edit(
                        model=self.model,
                        image=image_file,
                        prompt=prompt,
                        size="auto",
                        background="transparent",
                        output_format="png",
                        input_fidelity="high",
                    )
                except Exception:
                    image_file.seek(0)
                    response = client.images.edit(model=self.model, image=image_file, prompt=prompt, size="auto")
            encoded = getattr(response.data[0], "b64_json", None)
            if not encoded:
                return None
            image = Image.open(io.BytesIO(base64.b64decode(encoded))).convert("RGBA")
            image.load()
            return image
        except Exception as exc:
            self.last_attempt.update({"status": "failed", "reason": "openai_request_failed", "error": str(exc)[:300]})
            return None


class SegFormerClothesAdapter:
    def __init__(self, model_id: str | None = None) -> None:
        self.model_id = model_id or os.environ.get("SELFIT_SEGFORMER_MODEL", SEGFORMER_CLOTHES_MODEL_ID)
        self._processor: Any | None = None
        self._model: Any | None = None

    def available(self) -> bool:
        try:
            import transformers  # noqa: F401
            import torch  # noqa: F401
        except Exception:
            return False
        return True

    def status(self) -> str:
        if not self.available():
            return "optional_dependency_missing"
        return "available"

    def extract(self, source: dict[str, Any], work_dir: Path) -> list[dict[str, Any]]:
        if not self.available():
            return []
        try:
            segmentation = self._segment(source["image"])
        except Exception:
            return []

        id_to_label = self._id_to_label()
        label_groups = _segformer_category_label_groups(id_to_label)
        items: list[dict[str, Any]] = []
        for category, label_ids in label_groups.items():
            item = _closet_item_from_segmentation_mask(category, label_ids, segmentation, source, work_dir, self.model_id)
            if item:
                items.append(item)
        return items

    def _load(self) -> None:
        if self._processor is not None and self._model is not None:
            return
        import torch
        from transformers import AutoImageProcessor, AutoModelForSemanticSegmentation

        self._processor = AutoImageProcessor.from_pretrained(self.model_id)
        self._model = AutoModelForSemanticSegmentation.from_pretrained(self.model_id)
        self._model.eval()
        self._device = "cuda" if torch.cuda.is_available() and os.environ.get("SELFIT_SEGFORMER_DEVICE", "auto") != "cpu" else "cpu"
        self._model.to(self._device)

    def _segment(self, image: Image.Image) -> Any:
        self._load()
        import torch

        inputs = self._processor(images=image, return_tensors="pt")
        inputs = {key: value.to(self._device) for key, value in inputs.items()}
        with torch.no_grad():
            outputs = self._model(**inputs)
        logits = outputs.logits
        upsampled = torch.nn.functional.interpolate(logits, size=image.size[::-1], mode="bilinear", align_corners=False)
        return upsampled.argmax(dim=1)[0].detach().cpu().numpy()

    def _id_to_label(self) -> dict[int, str]:
        self._load()
        config = getattr(self._model, "config", None)
        raw = getattr(config, "id2label", {}) if config is not None else {}
        return {int(key): str(value).lower() for key, value in raw.items()}


class RembgMattingProvider:
    def available(self) -> bool:
        if os.environ.get("SELFIT_REMBG_ENABLED", "1").strip().lower() in {"0", "false", "no", "off"}:
            return False
        try:
            import rembg  # noqa: F401
        except Exception:
            return False
        return True

    def status(self) -> str:
        if os.environ.get("SELFIT_REMBG_ENABLED", "1").strip().lower() in {"0", "false", "no", "off"}:
            return "disabled_by_env"
        if not self.available():
            return "optional_dependency_missing"
        return "available"

    def remove_background(self, image: Image.Image) -> Image.Image | None:
        if not self.available():
            return None
        try:
            from rembg import remove

            buffer = io.BytesIO()
            image.convert("RGB").save(buffer, "PNG")
            result = Image.open(io.BytesIO(remove(buffer.getvalue()))).convert("RGBA")
            result.load()
            return result
        except Exception:
            return None

    def refine(self, image: Image.Image, semantic_alpha: Image.Image) -> tuple[Image.Image, str]:
        if not self.available():
            rgba = image.convert("RGBA")
            rgba.putalpha(semantic_alpha)
            return rgba, "semantic_mask_only"
        try:
            from rembg import remove

            buffer = io.BytesIO()
            image.convert("RGB").save(buffer, "PNG")
            refined_bytes = remove(buffer.getvalue())
            refined = Image.open(io.BytesIO(refined_bytes)).convert("RGBA")
            rembg_alpha = refined.getchannel("A")
            alpha = Image.composite(rembg_alpha, semantic_alpha, semantic_alpha)
            refined.putalpha(alpha.filter(ImageFilter.GaussianBlur(radius=0.45)))
            return refined, "rembg_refined"
        except Exception:
            rgba = image.convert("RGBA")
            rgba.putalpha(semantic_alpha)
            return rgba, "semantic_mask_only_after_rembg_error"


class BiRefNetMattingProvider:
    def available(self) -> bool:
        return bool(os.environ.get("SELFIT_BIREFNET_ENDPOINT") or os.environ.get("SELFIT_BIREFNET_MODEL"))

    def status(self) -> str:
        return "configured" if self.available() else "reserved_provider_adapter"


async def import_uploads(images: list[UploadFile]) -> dict[str, Any]:
    if not images:
        raise HTTPException(status_code=422, detail="请至少上传一张图片")
    sources = []
    for index, upload in enumerate(images):
        raw = await upload.read()
        sources.append(_save_source_image(raw, upload.filename, "upload", index))
    return _import_sources(sources, import_type="upload")


async def create_import_upload_job(images: list[UploadFile], user_id: str) -> dict[str, Any]:
    if not images:
        raise HTTPException(status_code=422, detail="请至少上传一张图片")
    sources = []
    for index, upload in enumerate(images):
        raw = await upload.read()
        sources.append(_save_source_image(raw, upload.filename, "upload", index))
    signature = ":".join(source["image_id"] for source in sources)
    job_id = hashlib.sha256(f"{user_id}:{signature}:{_now_iso()}".encode("utf-8")).hexdigest()[:18]
    descriptors = [
        {
            "image_id": source["image_id"],
            "saved_path": str(source["saved_path"]),
            "source": source["source"],
        }
        for source in sources
    ]
    now = _now_iso()
    job = {
        "job_id": job_id,
        "user_id": user_id,
        "pipeline_version": IMPORT_PIPELINE_VERSION,
        "status": "queued",
        "progress": 0,
        "phase": "queued",
        "attempt": 1,
        "sources": descriptors,
        "created_at": now,
        "updated_at": now,
        "result": None,
        "error": None,
    }
    _write_import_job(job)
    IMPORT_JOB_EXECUTOR.submit(_run_import_job, user_id, job_id)
    return _public_import_job(job)


def get_import_job(job_id: str) -> dict[str, Any]:
    return _public_import_job(_read_import_job(job_id))


def retry_import_job(job_id: str, user_id: str) -> dict[str, Any]:
    job = _read_import_job(job_id)
    if job.get("status") in {"queued", "processing"}:
        return _public_import_job(job)
    if job.get("status") == "completed":
        return _public_import_job(job)
    job.update({
        "status": "queued",
        "progress": 0,
        "phase": "retry_queued",
        "attempt": int(job.get("attempt") or 1) + 1,
        "updated_at": _now_iso(),
        "error": None,
    })
    _write_import_job(job)
    IMPORT_JOB_EXECUTOR.submit(_run_import_job, user_id, job_id)
    return _public_import_job(job)


def _import_job_path(job_id: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{18}", str(job_id or "")):
        raise HTTPException(status_code=404, detail="没有找到这个导入任务")
    return _import_job_dir() / f"{job_id}.json"


def _write_import_job(job: dict[str, Any]) -> None:
    path = _import_job_path(str(job.get("job_id") or ""))
    path.parent.mkdir(parents=True, exist_ok=True)
    with IMPORT_JOB_LOCK:
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(path)


def _read_import_job(job_id: str) -> dict[str, Any]:
    path = _import_job_path(job_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="没有找到这个导入任务")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail="导入任务状态无法读取") from exc
    return data


def _public_import_job(job: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in job.items() if key not in {"sources", "user_id"}}


def _update_import_job(job_id: str, **updates: Any) -> dict[str, Any]:
    job = _read_import_job(job_id)
    job.update(updates)
    job["updated_at"] = _now_iso()
    _write_import_job(job)
    return job


def _run_import_job(user_id: str, job_id: str) -> None:
    from app.storage import user_storage

    try:
        with user_storage(user_id):
            job = _read_import_job(job_id)
            sources = []
            for descriptor in job.get("sources", []):
                saved_path = Path(str(descriptor.get("saved_path") or ""))
                image = Image.open(saved_path).convert("RGB")
                image.load()
                sources.append({
                    "image": image,
                    "image_id": descriptor["image_id"],
                    "saved_path": saved_path,
                    "source": descriptor.get("source") or {},
                })
            _update_import_job(job_id, status="processing", phase="analyzing", progress=8)

            def progress(completed: int, total: int, phase: str) -> None:
                percent = 10 + int(78 * completed / max(1, total))
                _update_import_job(job_id, status="processing", phase=phase, progress=min(88, percent))

            with IMPORT_PIPELINE_LOCK:
                result = _import_sources(sources, import_type="upload", progress_callback=progress)
            _update_import_job(job_id, status="completed", phase="completed", progress=100, result=result, error=None)
    except Exception as exc:
        try:
            with user_storage(user_id):
                _update_import_job(job_id, status="failed", phase="failed", error={
                    "message": str(exc)[:500],
                    "retryable": True,
                })
        except Exception:
            return


async def import_link(url: str) -> dict[str, Any]:
    normalized = _normalize_link_url(url)
    work_dir = _closet_output_dir() / "link_cache" / hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    work_dir.mkdir(parents=True, exist_ok=True)
    html_text, final_url = await _fetch_html(normalized)
    note: dict[str, Any] = {}
    if _is_xhs_url(final_url):
        note = _extract_xhs_note_payload(html_text)
        image_urls = _extract_xhs_note_image_urls(note)
        if not image_urls:
            image_urls = _extract_image_urls_from_html(html_text, final_url)
    else:
        image_urls = _extract_webpage_image_urls(html_text, final_url)

    image_urls = _merge_urls(image_urls)[:MAX_LINK_IMAGES]
    downloaded = await _download_candidate_images(image_urls, final_url, work_dir)
    if not downloaded:
        return {
            "status": "failed",
            "source": {"type": "link", "url": normalized, "final_url": final_url, "image_count": len(image_urls)},
            "items": [],
            "summary": {"created": 0, "review": 0, "rejected": 0},
            "message": "这个链接暂时拿不到清晰图片，请改用截图或上传图片。",
        }

    sources = []
    for index, item in enumerate(downloaded):
        source_path = item["source_path"]
        raw = source_path.read_bytes()
        saved = _save_source_image(raw, source_path.name, "xhs_link" if _is_xhs_url(final_url) else "web_link", index, normalized)
        saved["source"]["final_url"] = final_url
        if note:
            saved["source"]["note_title"] = note.get("title") or note.get("display_title")
        sources.append(saved)
    return _import_sources(sources, import_type="link", source_url=normalized, final_url=final_url)


def list_closet_items(category: str | None = None) -> dict[str, Any]:
    data = _ensure_manifest()
    items = [item for item in data.get("items", []) if not item.get("deleted")]
    if category:
        items = [item for item in items if item.get("category") == category]
    items.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return {"total": len(items), "items": items}


def get_closet_item(item_id: str) -> dict[str, Any]:
    data = _ensure_manifest()
    for item in data.get("items", []):
        if item.get("item_id") == item_id and not item.get("deleted"):
            return item
    raise HTTPException(status_code=404, detail="没有找到这件衣物")


def update_closet_item(item_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = _ensure_manifest()
    allowed_categories = CLOSET_SUPPORTED_CATEGORIES
    now = _now_iso()
    for item in data.get("items", []):
        if item.get("item_id") != item_id or item.get("deleted"):
            continue
        edits = item.setdefault("user_edits", {})
        if "category" in payload:
            category = str(payload["category"])
            if category not in allowed_categories:
                raise HTTPException(status_code=400, detail="暂不支持这个衣物类别")
            item["category"] = category
            item["category_label"] = _fashion_category_label(category)
            edits["category"] = category
        if "style_tags" in payload:
            tags = payload.get("style_tags") or []
            if not isinstance(tags, list):
                raise HTTPException(status_code=400, detail="标签格式不正确")
            item.setdefault("attributes", {})["style_tags"] = [str(tag).strip() for tag in tags if str(tag).strip()]
            edits["style_tags"] = item["attributes"]["style_tags"]
        if "note" in payload:
            item["note"] = str(payload.get("note") or "")[:240]
            edits["note"] = item["note"]
        if "favorite" in payload:
            item["favorite"] = bool(payload["favorite"])
            edits["favorite"] = item["favorite"]
        item["updated_at"] = now
        _write_manifest(data)
        _refresh_outfits_for_item(item_id)
        return item
    raise HTTPException(status_code=404, detail="没有找到这件衣物")


def delete_closet_item(item_id: str) -> dict[str, Any]:
    data = _ensure_manifest()
    for item in data.get("items", []):
        if item.get("item_id") == item_id and not item.get("deleted"):
            item["deleted"] = True
            item["updated_at"] = _now_iso()
            _write_manifest(data)
            _refresh_outfits_for_item(item_id)
            return {"status": "deleted", "item_id": item_id}
    raise HTTPException(status_code=404, detail="没有找到这件衣物")


def reprocess_closet_item(item_id: str) -> dict[str, Any]:
    item = get_closet_item(item_id)
    source_path = _closet_disk_path(item.get("source", {}).get("source_path"))
    if source_path is None or not source_path.exists():
        raise HTTPException(status_code=404, detail="原始图片不存在，无法重新处理")
    raw = source_path.read_bytes()
    source = _save_source_image(raw, source_path.name, "reprocess", 0, item.get("source", {}).get("url"))
    result = _import_sources([source], import_type="reprocess")
    return {"status": result["status"], "original_item_id": item_id, "items": result["items"], "summary": result["summary"]}


def closet_item_as_upload(item_id: str) -> dict[str, Any]:
    item = get_closet_item(item_id)
    if item.get("category") != "top":
        raise HTTPException(status_code=400, detail="这件单品已入柜，但当前只支持上衣试穿。")
    public_path = item.get("assets", {}).get("cutout_path") or item.get("assets", {}).get("preview_path")
    disk_path = _closet_disk_path(public_path)
    if disk_path is None or not disk_path.exists():
        raise HTTPException(status_code=404, detail="衣物图片不存在")
    return _read_upload_image(disk_path.read_bytes(), disk_path.name, "garment")


def list_outfits() -> dict[str, Any]:
    data = _ensure_outfit_manifest()
    closet_data = _ensure_manifest()
    items_by_id = {
        str(item.get("item_id")): item
        for item in closet_data.get("items", [])
        if item.get("item_id") and not item.get("deleted")
    }
    outfits = []
    for outfit in data.get("outfits", []):
        if outfit.get("deleted"):
            continue
        resolved = _resolve_outfit(outfit, items_by_id)
        if resolved.get("items"):
            outfits.append(resolved)
    outfits = _dedupe_similar_outfits(outfits)
    outfits.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return {"total": len(outfits), "outfits": outfits}


def _refresh_outfits_for_item(item_id: str) -> None:
    data = _ensure_outfit_manifest()
    changed = False
    for outfit in data.get("outfits", []):
        if outfit.get("deleted") or item_id not in (outfit.get("item_ids") or []):
            continue
        items = []
        for candidate_id in outfit.get("item_ids") or []:
            try:
                items.append(get_closet_item(str(candidate_id)))
            except HTTPException:
                continue
        if not items or (outfit.get("origin") == "auto_split" and len(items) < 2):
            outfit["deleted"] = True
            outfit["updated_at"] = _now_iso()
            changed = True
            continue
        layout = _build_outfit_cover(str(outfit["outfit_id"]), items)
        outfit["item_ids"] = [item["item_id"] for item in items]
        outfit["cover_path"] = _public_closet_path(layout["path"])
        outfit["layout_snapshot_path"] = _public_closet_path(layout["path"])
        outfit["layout_version"] = layout["layout_version"]
        outfit["layout_slots"] = layout["layout_slots"]
        outfit["display_item_ids"] = layout["display_item_ids"]
        outfit["overflow_items"] = layout["overflow_items"]
        outfit["warnings"] = layout["warnings"]
        outfit["updated_at"] = _now_iso()
        changed = True
    if changed:
        _write_outfit_manifest(data)


def _canonical_tokens(values: Any, aliases: dict[str, tuple[str, ...]]) -> set[str]:
    raw_values = values if isinstance(values, list) else [values]
    text = " ".join(str(value or "").strip().lower() for value in raw_values)
    return {
        canonical
        for canonical, terms in aliases.items()
        if any(term.lower() in text for term in terms)
    }


def _persona_style_evidence(persona: dict[str, Any]) -> tuple[set[str], set[str]]:
    metadata = persona.get("metadata") if isinstance(persona.get("metadata"), dict) else {}
    recommendations = persona.get("recommendations") if isinstance(persona.get("recommendations"), dict) else {}
    outfits = recommendations.get("outfits") if isinstance(recommendations.get("outfits"), dict) else {}
    colors = persona.get("colors") if isinstance(persona.get("colors"), dict) else {}
    color_items = colors.get("items") if isinstance(colors.get("items"), list) else []
    persona_text = [
        persona.get("typeId"),
        metadata.get("name"),
        metadata.get("code"),
        persona.get("summary"),
        outfits.get("summary"),
        *(persona.get("keywords") or []),
    ]
    color_text = [item.get("name") for item in color_items if isinstance(item, dict)]
    return _canonical_tokens(persona_text, STYLE_TOKEN_ALIASES), _canonical_tokens(color_text, COLOR_TOKEN_ALIASES)


def _outfit_style_evidence(outfit: dict[str, Any]) -> tuple[set[str], set[str]]:
    style_values: list[Any] = [outfit.get("title"), *(outfit.get("scene_tags") or [])]
    color_values: list[Any] = []
    for item in outfit.get("items", []):
        attributes = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
        style_values.extend(attributes.get("style_tags") or [])
        style_values.extend([attributes.get("material"), attributes.get("fit"), attributes.get("pattern")])
        color_values.extend(attributes.get("colors") or [])
    return _canonical_tokens(style_values, STYLE_TOKEN_ALIASES), _canonical_tokens(color_values, COLOR_TOKEN_ALIASES)


def _score_outfit_for_persona(outfit: dict[str, Any], persona: dict[str, Any]) -> dict[str, Any]:
    persona_styles, persona_colors = _persona_style_evidence(persona)
    outfit_styles, outfit_colors = _outfit_style_evidence(outfit)
    shared_styles = sorted(persona_styles & outfit_styles)
    shared_colors = sorted(persona_colors & outfit_colors)
    categories = {str(item.get("category") or "") for item in outfit.get("items", [])}
    has_main = "dress" in categories or ("top" in categories and bool(categories & {"bottom", "skirt"}))
    completeness = (18 if has_main else 4) + (7 if "shoes" in categories else 0) + (5 if "bag" in categories else 0)
    quality = sum(float(item.get("quality", {}).get("score") or 0) for item in outfit.get("items", [])) / max(1, len(outfit.get("items", [])))
    score = completeness + len(shared_styles) * 24 + len(shared_colors) * 14 + quality * 8
    if outfit.get("favorite"):
        score += 5
    reasons = []
    if shared_styles:
        reasons.append("风格特征呼应：" + "、".join(shared_styles[:2]))
    if shared_colors:
        reasons.append("推荐色呼应：" + "、".join(shared_colors[:2]))
    if has_main:
        reasons.append("主搭配结构完整")
    if not reasons:
        reasons.append("根据单品完整度排序")
    return {
        "score": round(score, 2),
        "reasons": reasons,
        "matched_style_tokens": shared_styles,
        "matched_color_tokens": shared_colors,
        "algorithm": "persona_style_rank_v1",
    }


def recommend_outfits(payload: dict[str, Any]) -> dict[str, Any]:
    persona = payload.get("persona") if isinstance(payload.get("persona"), dict) else {}
    offset = max(0, int(payload.get("offset") or 0))
    limit = max(1, min(20, int(payload.get("limit") or 12)))
    rotate_by = max(1, min(limit, int(payload.get("rotate_by") or 4)))
    outfits = list_outfits()["outfits"]
    ranked = []
    for outfit in outfits:
        recommendation = _score_outfit_for_persona(outfit, persona)
        ranked.append({**outfit, "recommendation": recommendation})
    ranked.sort(
        key=lambda outfit: (
            -float(outfit.get("recommendation", {}).get("score") or 0),
            -int(bool(outfit.get("favorite"))),
            str(outfit.get("outfit_id") or ""),
        )
    )
    if ranked:
        start = offset % len(ranked)
        ordered = ranked[start:] + ranked[:start]
    else:
        ordered = []
    return {
        "total": len(ranked),
        "offset": offset,
        "next_offset": (offset + rotate_by) % max(1, len(ranked)),
        "algorithm": "persona_style_rank_v1",
        "outfits": ordered[:limit],
    }


def get_outfit(outfit_id: str) -> dict[str, Any]:
    data = _ensure_outfit_manifest()
    for outfit in data.get("outfits", []):
        if outfit.get("outfit_id") == outfit_id and not outfit.get("deleted"):
            closet_data = _ensure_manifest()
            items_by_id = {
                str(item.get("item_id")): item
                for item in closet_data.get("items", [])
                if item.get("item_id") and not item.get("deleted")
            }
            return _resolve_outfit(outfit, items_by_id)
    raise HTTPException(status_code=404, detail="没有找到这套搭配")


def create_outfit(payload: dict[str, Any]) -> dict[str, Any]:
    item_ids = _valid_item_ids(payload.get("item_ids"))
    items = [get_closet_item(item_id) for item_id in item_ids]
    if not items:
        raise HTTPException(status_code=400, detail="请至少选择一件衣物")
    now = _now_iso()
    title = str(payload.get("title") or _default_outfit_title(items))[:48]
    scene_tags = _string_list(payload.get("scene_tags"))[:8]
    outfit_id = hashlib.sha256(f"{title}:{item_ids}:{now}".encode("utf-8")).hexdigest()[:16]
    layout = _build_outfit_cover(outfit_id, items)
    outfit = {
        "outfit_id": outfit_id,
        "user_id": storage_context().user_id,
        "title": title,
        "item_ids": item_ids,
        "cover_path": _public_closet_path(layout["path"]),
        "layout_version": layout["layout_version"],
        "layout_snapshot_path": _public_closet_path(layout["path"]),
        "layout_slots": layout["layout_slots"],
        "display_item_ids": layout["display_item_ids"],
        "overflow_items": layout["overflow_items"],
        "warnings": layout["warnings"],
        "scene_tags": scene_tags,
        "favorite_count": int(payload.get("favorite_count") or _initial_favorite_count(item_ids)),
        "favorite": bool(payload.get("favorite")),
        "created_at": now,
        "updated_at": now,
        "deleted": False,
    }
    data = _ensure_outfit_manifest()
    data.setdefault("outfits", []).append(outfit)
    _write_outfit_manifest(data)
    return _resolve_outfit(outfit)


def update_outfit(outfit_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = _ensure_outfit_manifest()
    for outfit in data.get("outfits", []):
        if outfit.get("outfit_id") != outfit_id or outfit.get("deleted"):
            continue
        if "title" in payload:
            outfit["title"] = str(payload.get("title") or outfit.get("title") or "我的搭配")[:48]
        if "scene_tags" in payload:
            outfit["scene_tags"] = _string_list(payload.get("scene_tags"))[:8]
        if "favorite_count" in payload:
            outfit["favorite_count"] = max(0, int(payload.get("favorite_count") or 0))
        if "favorite" in payload:
            outfit["favorite"] = bool(payload.get("favorite"))
        if "draft" in payload:
            outfit["draft"] = bool(payload.get("draft"))
        if "item_ids" in payload:
            item_ids = _valid_item_ids(payload.get("item_ids"))
            items = [get_closet_item(item_id) for item_id in item_ids]
            layout = _build_outfit_cover(outfit_id, items)
            outfit["item_ids"] = item_ids
            outfit["cover_path"] = _public_closet_path(layout["path"])
            outfit["layout_snapshot_path"] = _public_closet_path(layout["path"])
            outfit["layout_version"] = layout["layout_version"]
            outfit["layout_slots"] = layout["layout_slots"]
            outfit["display_item_ids"] = layout["display_item_ids"]
            outfit["overflow_items"] = layout["overflow_items"]
            outfit["warnings"] = layout["warnings"]
        outfit["updated_at"] = _now_iso()
        _write_outfit_manifest(data)
        return _resolve_outfit(outfit)
    raise HTTPException(status_code=404, detail="没有找到这套搭配")


def delete_outfit(outfit_id: str) -> dict[str, Any]:
    data = _ensure_outfit_manifest()
    for outfit in data.get("outfits", []):
        if outfit.get("outfit_id") == outfit_id and not outfit.get("deleted"):
            outfit["deleted"] = True
            outfit["updated_at"] = _now_iso()
            _write_outfit_manifest(data)
            return {"status": "deleted", "outfit_id": outfit_id}
    raise HTTPException(status_code=404, detail="没有找到这套搭配")


def outfit_as_tryon_garment(outfit_id: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    outfit = get_outfit(outfit_id)
    top_item = next((item for item in outfit.get("items", []) if item.get("category") == "top"), None)
    if not top_item:
        return None, outfit
    public_path = top_item.get("assets", {}).get("cutout_path") or top_item.get("assets", {}).get("preview_path")
    disk_path = _closet_disk_path(public_path)
    if disk_path is None or not disk_path.exists():
        raise HTTPException(status_code=404, detail="套装里的上衣图片不存在")
    return _read_upload_image(disk_path.read_bytes(), disk_path.name, "garment"), outfit


def outfit_as_tryon_plan(outfit_id: str, photo_mode: str | None = None, scene_label: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    outfit = get_outfit(outfit_id)
    cover_disk_path = _closet_disk_path(outfit.get("layout_snapshot_path") or outfit.get("cover_path"))
    if cover_disk_path is None or not cover_disk_path.exists():
        layout = _build_outfit_cover(outfit_id, outfit.get("items", []))
        cover_disk_path = layout["path"]

    plan_items: list[dict[str, Any]] = []
    for index, item in enumerate(outfit.get("items", [])):
        slot = _outfit_item_slot(item)
        public_path = item.get("assets", {}).get("cutout_path") or item.get("assets", {}).get("preview_path")
        disk_path = _closet_disk_path(public_path)
        if disk_path is None or not disk_path.exists():
            continue
        plan_items.append(
            {
                "item_id": item.get("item_id"),
                "image_id": item.get("image_id") or item.get("item_id"),
                "slot": slot,
                "category": item.get("category") or slot,
                "category_label": item.get("category_label") or _fashion_category_label(str(item.get("category") or slot)),
                "image_path": str(disk_path),
                "attributes": item.get("attributes") or {},
                "note": item.get("note") or "",
                "wearing_instruction": _outfit_item_wearing_instruction(slot, item),
                "display_order": index,
            }
        )

    plan = {
        "source_mode": "from_outfit",
        "outfit_id": outfit_id,
        "title": outfit.get("title") or "我的搭配",
        "model_photo_mode": photo_mode or "standard",
        "scene_label": scene_label or "",
        "scene_tags": outfit.get("scene_tags", []),
        "style_reference": {
            "image_id": f"outfit_{outfit_id}",
            "image_path": str(cover_disk_path),
            "role": "overall_outfit_reference",
            "meta": {
                "filename": cover_disk_path.name,
                "saved_path": str(cover_disk_path),
            },
        },
        "items": plan_items,
        "style_brief": " ".join(str(tag) for tag in outfit.get("scene_tags", []) if str(tag).strip()),
    }
    return plan, outfit


def _outfit_item_wearing_instruction(slot: str, item: dict[str, Any]) -> str:
    label = item.get("category_label") or _slot_label(slot)
    return {
        "top": f"{label}穿在上半身，保留领口、袖长、衣长和图案。",
        "outer": f"{label}作为外层穿在上半身，保留厚度和开合方式。",
        "bottom": f"{label}穿在下半身，保留裤型、腰线和长度。",
        "skirt": f"{label}穿在下半身，保留裙长、腰线和廓形。",
        "dress": f"{label}作为连衣装穿着，保留整体廓形、腰线和裙长。",
        "shoes": f"{label}穿在双脚，保留鞋型、颜色和鞋底比例。",
        "bag": f"{label}作为包袋搭配在可见手臂、手部或肩侧；手提包需要手握或挂在前臂，肩背包需要贴合肩线，不能悬空。",
    }.get(slot, f"{label}作为配饰自然搭配。")


def outfit_tryon_unavailable(outfit_id: str) -> dict[str, Any]:
    outfit = get_outfit(outfit_id)
    return {
        "status": "failed",
        "mode": "from_outfit",
        "outfit_id": outfit_id,
        "outfit": outfit,
        "decision": {
            "blocking_errors": [
                {
                    "stage": "outfit",
                    "code": "outfit.no_top",
                    "message": "这套搭配暂时没有可试穿上衣",
                    "suggestion": "可以先保存为搭配参考，或加入一件上衣后再试穿。",
                }
            ],
            "warnings": [],
            "user_message": "当前只支持上衣试穿，这套搭配已作为参考保存。",
        },
        "pipeline": {"outfit": {"status": "fail", "confidence": 0.0, "evidence": {"item_count": len(outfit.get("items", []))}, "issues": [], "suggestions": []}},
        "result": {"image_path": None, "mask_path": None, "user_message": "当前只支持上衣试穿，这套搭配已作为参考保存。"},
    }


def list_tryon_records() -> dict[str, Any]:
    data = _ensure_tryon_records_manifest()
    records = [record for record in data.get("records", []) if not record.get("deleted")]
    records.sort(key=lambda record: record.get("created_at", ""), reverse=True)
    return {"total": len(records), "records": records}


def get_user_preferences() -> dict[str, Any]:
    path = _user_preferences_path()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data.setdefault("version", 1)
                data.setdefault("current_model_id", "female_medium_1")
                data.setdefault("current_stylist_session_id", "")
                return data
        except json.JSONDecodeError:
            pass
    return {"version": 1, "current_model_id": "female_medium_1", "current_stylist_session_id": ""}


def update_user_preferences(payload: dict[str, Any]) -> dict[str, Any]:
    data = get_user_preferences()
    if "current_model_id" in payload:
        model_id = str(payload.get("current_model_id") or "").strip()
        if model_id:
            data["current_model_id"] = model_id[:80]
    if "current_stylist_session_id" in payload:
        session_id = str(payload.get("current_stylist_session_id") or "").strip()
        data["current_stylist_session_id"] = session_id[:80]
    data["updated_at"] = _now_iso()
    path = _user_preferences_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)
    return data


def delete_tryon_record(record_id: str) -> dict[str, Any]:
    data = _ensure_tryon_records_manifest()
    for record in data.get("records", []):
        if record.get("record_id") == record_id and not record.get("deleted"):
            record["deleted"] = True
            record["updated_at"] = _now_iso()
            _write_tryon_records_manifest(data)
            return {"status": "deleted", "record_id": record_id}
    raise HTTPException(status_code=404, detail="没有找到这条试穿记录")


def record_selfit_tryon_result(outfit_id: str, tryon_result: dict[str, Any]) -> dict[str, Any] | None:
    if tryon_result.get("status") not in {"generated", "review"}:
        return None
    image_path = tryon_result.get("result", {}).get("image_path")
    if not image_path:
        return None
    tryon_id = str(tryon_result.get("tryon_id") or "")
    data = _ensure_tryon_records_manifest()
    if tryon_id:
        existing = next(
            (
                record
                for record in data.get("records", [])
                if not record.get("deleted") and record.get("tryon_id") == tryon_id and record.get("outfit_id") == outfit_id
            ),
            None,
        )
        if existing:
            return existing
    outfit = get_outfit(outfit_id)
    now = _now_iso()
    record_id = hashlib.sha256(f"selfit-tryon:{outfit_id}:{image_path}:{now}".encode("utf-8")).hexdigest()[:16]
    record = {
        "record_id": record_id,
        "user_id": storage_context().user_id,
        "mode": "selfit_from_outfit_plan",
        "status": tryon_result.get("status") or "generated",
        "tryon_id": tryon_id or None,
        "outfit_id": outfit_id,
        "outfit_title": outfit.get("title") or "我的搭配",
        "image_path": image_path,
        "reference_board_path": tryon_result.get("reference_board_path"),
        "scene_tags": outfit.get("scene_tags", []),
        "photo_mode": tryon_result.get("photo_mode"),
        "generation_strategy": tryon_result.get("generation_strategy"),
        "quality_review": tryon_result.get("pipeline", {}).get("quality_review") if isinstance(tryon_result.get("pipeline"), dict) else None,
        "created_at": now,
        "updated_at": now,
        "deleted": False,
        "note": "selfit 真实试穿链路生成结果。" if tryon_result.get("status") == "generated" else "试穿图已生成，建议复核后使用。",
    }
    data.setdefault("records", []).append(record)
    _write_tryon_records_manifest(data)
    return record


def mock_tryon_from_outfit(outfit_id: str) -> dict[str, Any]:
    outfit = get_outfit(outfit_id)
    now = _now_iso()
    record_id = hashlib.sha256(f"mock-tryon:{outfit_id}:{now}".encode("utf-8")).hexdigest()[:16]
    result_path = _build_mock_tryon_image(record_id, outfit)
    record = {
        "record_id": record_id,
        "user_id": storage_context().user_id,
        "mode": "mock_from_outfit",
        "status": "generated",
        "outfit_id": outfit_id,
        "outfit_title": outfit.get("title") or "我的搭配",
        "image_path": _public_closet_path(result_path),
        "scene_tags": outfit.get("scene_tags", []),
        "created_at": now,
        "updated_at": now,
        "deleted": False,
        "note": "本地模拟试穿结果，用于验证完整产品链路。",
    }
    data = _ensure_tryon_records_manifest()
    data.setdefault("records", []).append(record)
    _write_tryon_records_manifest(data)
    return {
        "status": "generated",
        "mode": "mock_from_outfit",
        "outfit_id": outfit_id,
        "outfit": outfit,
        "record": record,
        "decision": {
            "blocking_errors": [],
            "warnings": [
                {
                    "stage": "mock_tryon",
                    "code": "mock.local_preview",
                    "message": "当前展示的是本地模拟试穿结果",
                    "suggestion": "真实生图接口接入后会替换为正式试穿图。",
                }
            ],
            "user_message": "已生成组合参考试穿。",
        },
        "result": {
            "image_path": record["image_path"],
            "mask_path": None,
            "user_message": "已生成组合参考试穿。",
        },
    }


def _build_mock_tryon_image(record_id: str, outfit: dict[str, Any]) -> Path:
    canvas = Image.new("RGB", (900, 1200), "#f6f7f9")
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((44, 42, 856, 1158), radius=42, fill="#ffffff")
    draw.rounded_rectangle((92, 90, 512, 1064), radius=30, fill="#eef0f3")

    model_path = ROOT_DIR / "tests" / "fixtures" / "tryon_models" / "male_medium_1.png"
    if model_path.exists():
        try:
            model = Image.open(model_path).convert("RGBA")
            model.thumbnail((370, 910), Image.Resampling.LANCZOS)
            canvas.paste(model.convert("RGB"), (118 + (370 - model.width) // 2, 130), model.getchannel("A"))
        except Exception:
            draw.rounded_rectangle((198, 210, 406, 884), radius=104, fill="#d8dde5")
    else:
        draw.rounded_rectangle((198, 210, 406, 884), radius=104, fill="#d8dde5")

    draw.text((560, 116), "组合参考试穿", fill="#050505")
    draw.text((560, 154), str(outfit.get("title") or "我的搭配")[:18], fill="#050505")
    draw.text((560, 196), "先验证选择、保存、试穿闭环", fill="#777777")

    cover_path = _closet_disk_path(outfit.get("cover_path"))
    if cover_path and cover_path.exists():
        try:
            cover = Image.open(cover_path).convert("RGBA")
            cover.thumbnail((250, 250), Image.Resampling.LANCZOS)
            canvas.paste(cover.convert("RGB"), (560, 248), cover.getchannel("A"))
        except Exception:
            pass

    y = 548
    for item in outfit.get("items", [])[:4]:
        source = _closet_disk_path(item.get("assets", {}).get("preview_path") or item.get("assets", {}).get("cutout_path"))
        if source is None or not source.exists():
            continue
        try:
            image = Image.open(source).convert("RGBA")
        except Exception:
            continue
        draw.rounded_rectangle((560, y, 810, y + 120), radius=22, fill="#f6f7f9")
        image.thumbnail((100, 100), Image.Resampling.LANCZOS)
        canvas.paste(image.convert("RGB"), (578, y + 10), image.getchannel("A"))
        draw.text((694, y + 36), str(item.get("category_label") or "单品"), fill="#050505")
        y += 138

    target = _tryon_record_dir() / f"{record_id}.jpg"
    target.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(target, "JPEG", quality=92)
    return target


def _valid_item_ids(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise HTTPException(status_code=400, detail="请选择要加入搭配的衣物")
    item_ids = []
    for raw in value:
        item_id = str(raw or "").strip()
        if item_id and item_id not in item_ids:
            item_ids.append(item_id)
    if not item_ids:
        raise HTTPException(status_code=400, detail="请至少选择一件衣物")
    for item_id in item_ids:
        get_closet_item(item_id)
    return item_ids[:8]


def _resolve_outfit(outfit: dict[str, Any], items_by_id: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    if items_by_id is None:
        closet_data = _ensure_manifest()
        items_by_id = {
            str(item.get("item_id")): item
            for item in closet_data.get("items", [])
            if item.get("item_id") and not item.get("deleted")
        }
    items = [
        items_by_id[str(item_id)]
        for item_id in outfit.get("item_ids", [])
        if str(item_id) in items_by_id
    ]
    layout_patch: dict[str, Any] = {}
    if items and outfit.get("layout_version") != OUTFIT_LAYOUT_VERSION:
        layout = _build_outfit_cover(str(outfit.get("outfit_id") or hashlib.sha256(str(outfit.get("item_ids", [])).encode("utf-8")).hexdigest()[:16]), items)
        layout_patch = {
            "cover_path": _public_closet_path(layout["path"]),
            "layout_snapshot_path": _public_closet_path(layout["path"]),
            "layout_version": layout["layout_version"],
            "layout_slots": layout["layout_slots"],
            "display_item_ids": layout["display_item_ids"],
            "overflow_items": layout["overflow_items"],
            "warnings": [*(outfit.get("warnings") or []), *layout["warnings"]],
        }
    return {
        **outfit,
        **layout_patch,
        "items": items,
        "tryon_ready": any(item.get("category") == "top" for item in items),
    }


def _dedupe_similar_outfits(outfits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best_by_signature: dict[str, dict[str, Any]] = {}
    for outfit in outfits:
        signature = _outfit_similarity_signature(outfit.get("items", []))
        if not signature:
            signature = "exact:" + ":".join(sorted(str(item_id) for item_id in outfit.get("item_ids", []) if item_id))
        current = best_by_signature.get(signature)
        if current is None or _outfit_completeness_score(outfit) > _outfit_completeness_score(current):
            best_by_signature[signature] = outfit
    return list(best_by_signature.values())


def _outfit_similarity_signature(items: list[dict[str, Any]]) -> str:
    slots: dict[str, str] = {}
    for item in items:
        item_id = str(item.get("item_id") or "")
        if not item_id:
            continue
        slot = _outfit_item_slot(item)
        if slot == "dress":
            slots.setdefault("dress", item_id)
        elif slot == "top":
            slots.setdefault("top", item_id)
        elif slot in {"bottom", "skirt"}:
            slots.setdefault("lower", item_id)
    if slots.get("dress"):
        return f"dress:{slots['dress']}"
    if slots.get("top") and slots.get("lower"):
        return f"main:{slots['top']}:{slots['lower']}"
    if slots.get("top"):
        return f"top:{slots['top']}"
    if slots.get("lower"):
        return f"lower:{slots['lower']}"
    return ""


def _outfit_completeness_score(outfit: dict[str, Any]) -> tuple[int, int, int, int, str]:
    items = outfit.get("items", [])
    slots = [_outfit_item_slot(item) for item in items]
    has_shoes = int("shoes" in slots)
    has_bag = int("bag" in slots)
    has_main = int(any(slot in {"dress", "top", "bottom", "skirt"} for slot in slots))
    display_count = len(outfit.get("display_item_ids") or outfit.get("item_ids") or items)
    favorite_count = int(outfit.get("favorite_count") or 0)
    updated_at = str(outfit.get("updated_at") or outfit.get("created_at") or "")
    return (has_main, has_shoes, has_bag, display_count + min(favorite_count, 99), updated_at)


def _build_outfit_cover(outfit_id: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    normalized = _normalize_outfit_layout_items(items)
    canvas = Image.new("RGBA", (900, 900), "#ffffff")
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((24, 24, 876, 876), radius=42, outline="#f0f1f3", width=2)

    layout_slots: list[dict[str, Any]] = []
    for entry in normalized["display_entries"]:
        item = entry["item"]
        slot = entry["slot"]
        box = _flatlay_box(slot, bool(normalized["has_dress"]))
        source = _closet_disk_path(item.get("assets", {}).get("cutout_path") or item.get("assets", {}).get("preview_path"))
        if source is None or not source.exists():
            normalized["warnings"].append(f"{item.get('category_label') or '单品'} 暂时没有可用于排版的图片。")
            continue
        try:
            image = Image.open(source).convert("RGBA")
        except Exception:
            normalized["warnings"].append(f"{item.get('category_label') or '单品'} 图片暂时无法读取。")
            continue
        image = _trim_flatlay_image(image)
        left, top, right, bottom = box
        max_w = right - left
        max_h = bottom - top
        original_w, original_h = image.size
        image.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
        x = left + (max_w - image.width) // 2
        y = top + (max_h - image.height) // 2
        if _needs_flatlay_shadow(image):
            canvas.alpha_composite(_flatlay_shadow(image), (x + 3, y + 7))
        canvas.alpha_composite(image, (x, y))
        layout_slots.append(
            {
                "item_id": item.get("item_id"),
                "slot": slot,
                "box": {"x": x, "y": y, "width": image.width, "height": image.height},
                "source_box": {"x": left, "y": top, "width": max_w, "height": max_h},
                "scale": round(image.width / original_w, 4) if original_w else 1.0,
                "z_index": _flatlay_z_index(slot),
            }
        )

    target = _outfit_dir() / outfit_id / "flatlay.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(target, "PNG")
    return {
        "path": target,
        "layout_version": OUTFIT_LAYOUT_VERSION,
        "layout_slots": layout_slots,
        "display_item_ids": [slot["item_id"] for slot in layout_slots if slot.get("item_id")],
        "overflow_items": normalized["overflow_items"],
        "warnings": normalized["warnings"],
    }


def _normalize_outfit_layout_items(items: list[dict[str, Any]]) -> dict[str, Any]:
    display_entries: list[dict[str, Any]] = []
    overflow_items: list[dict[str, Any]] = []
    warnings: list[str] = []
    used_slots: dict[str, str] = {}
    has_dress = False
    has_separate_main = False
    accessory_count = 0

    for item in items:
        slot = _outfit_item_slot(item)
        label = item.get("category_label") or "这件单品"
        item_id = str(item.get("item_id") or "")
        if slot == "dress":
            if has_separate_main:
                overflow_items.append({"item_id": item_id, "slot": slot, "reason": "main_conflict"})
                warnings.append(f"{label} 与上衣/下装冲突，已保留先选择的主搭配。")
                continue
            if used_slots.get("dress"):
                overflow_items.append({"item_id": item_id, "slot": slot, "reason": "duplicate_slot"})
                warnings.append(f"一套搭配里先保留一件连衣装，{label} 未放入封面。")
                continue
            has_dress = True
        elif slot in {"top", "bottom", "skirt"}:
            if has_dress:
                overflow_items.append({"item_id": item_id, "slot": slot, "reason": "dress_conflict"})
                warnings.append(f"{label} 与连衣装冲突，已保留先选择的连衣装。")
                continue
            if slot == "top":
                if used_slots.get("top"):
                    overflow_items.append({"item_id": item_id, "slot": slot, "reason": "duplicate_slot"})
                    warnings.append(f"一套搭配里先保留一件上衣，{label} 未放入封面。")
                    continue
            else:
                lower_slot = used_slots.get("bottom") or used_slots.get("skirt")
                if lower_slot:
                    overflow_items.append({"item_id": item_id, "slot": slot, "reason": "lower_conflict"})
                    warnings.append(f"裤子和裙子先保留一个，{label} 未放入封面。")
                    continue
            has_separate_main = True
        elif slot in {"hat", "scarf", "socks", "shoes", "bag"}:
            if used_slots.get(slot):
                overflow_items.append({"item_id": item_id, "slot": slot, "reason": "duplicate_slot"})
                warnings.append(f"一套搭配里先保留一件{_slot_label(slot)}，{label} 未放入封面。")
                continue
        else:
            accessory_count += 1
            if accessory_count > 2:
                overflow_items.append({"item_id": item_id, "slot": "accessory", "reason": "accessory_overflow"})
                warnings.append(f"配饰最多展示两件，{label} 已保留在套装里但未放入封面。")
                continue
            slot = f"accessory_{accessory_count}"

        used_slots[slot] = item_id
        display_entries.append({"item": item, "slot": slot})

    display_entries.sort(key=lambda entry: _flatlay_z_index(entry["slot"]))
    return {
        "display_entries": display_entries,
        "overflow_items": overflow_items,
        "warnings": warnings,
        "has_dress": has_dress,
    }


def _outfit_item_slot(item: dict[str, Any]) -> str:
    explicit = str(item.get("slot") or item.get("subcategory") or "").strip().lower()
    allowed = {"hat", "scarf", "top", "bottom", "skirt", "dress", "socks", "shoes", "bag", "accessory"}
    if explicit in allowed:
        return explicit
    tags = [str(tag).strip().lower() for tag in item.get("attributes", {}).get("style_tags", [])]
    tag_text = " ".join(tags)
    tag_map = [
        ("hat", ("hat", "cap", "帽")),
        ("scarf", ("scarf", "围巾", "丝巾")),
        ("socks", ("sock", "袜")),
    ]
    for slot, needles in tag_map:
        if any(needle in tag_text for needle in needles):
            return slot
    category = str(item.get("category") or "accessory")
    if category in {"top", "bottom", "skirt", "dress", "shoes", "bag"}:
        return category
    return "accessory"


def _category_to_layout_slot(category: str) -> str:
    if category in {"top", "bottom", "skirt", "dress", "shoes", "bag"}:
        return category
    return "accessory"


def _flatlay_box(slot: str, has_dress: bool) -> tuple[int, int, int, int]:
    if has_dress:
        boxes = {
            "hat": (128, 54, 300, 190),
            "scarf": (76, 214, 240, 366),
            "dress": (236, 76, 656, 620),
            "socks": (286, 636, 438, 760),
            "shoes": (398, 642, 766, 844),
            "bag": (632, 250, 842, 510),
            "accessory_1": (82, 540, 258, 704),
            "accessory_2": (658, 540, 832, 704),
        }
    else:
        boxes = {
            "hat": (126, 48, 306, 184),
            "scarf": (78, 208, 242, 366),
            "top": (230, 56, 638, 342),
            "bottom": (246, 320, 620, 664),
            "skirt": (246, 326, 620, 640),
            "socks": (292, 646, 452, 762),
            "shoes": (406, 660, 782, 842),
            "bag": (640, 220, 846, 474),
            "accessory_1": (84, 560, 260, 724),
            "accessory_2": (646, 520, 828, 682),
        }
    return boxes.get(slot, boxes.get("accessory_1", (82, 674, 260, 858)))


def _flatlay_z_index(slot: str) -> int:
    order = {
        "hat": 10,
        "scarf": 20,
        "top": 30,
        "dress": 35,
        "bottom": 40,
        "skirt": 40,
        "socks": 50,
        "shoes": 60,
        "bag": 70,
        "accessory_1": 80,
        "accessory_2": 90,
    }
    return order.get(slot, 95)


def _slot_label(slot: str) -> str:
    labels = {"hat": "帽子", "scarf": "围巾", "socks": "袜子", "shoes": "鞋子", "bag": "包"}
    return labels.get(slot, "配饰")


def _needs_flatlay_shadow(image: Image.Image) -> bool:
    pixels = image.convert("RGBA").load()
    total = 0
    bright = 0
    sampled = 0
    step = max(1, min(image.width, image.height) // 90)
    for y in range(0, image.height, step):
        for x in range(0, image.width, step):
            r, g, b, a = pixels[x, y]
            if a <= 30:
                continue
            luminance = (r * 0.299) + (g * 0.587) + (b * 0.114)
            total += luminance
            sampled += 1
            if luminance > 212:
                bright += 1
    if sampled == 0:
        return False
    return (total / sampled) > 205 or (bright / sampled) > 0.72


def _flatlay_shadow(image: Image.Image) -> Image.Image:
    alpha = image.getchannel("A").filter(ImageFilter.GaussianBlur(7))
    shadow = Image.new("RGBA", image.size, (92, 86, 76, 0))
    shadow_alpha = alpha.point(lambda value: min(58, int(value * 0.28)))
    shadow.putalpha(shadow_alpha)
    return shadow


def _trim_flatlay_image(image: Image.Image) -> Image.Image:
    alpha_bbox = image.getchannel("A").getbbox()
    if alpha_bbox and alpha_bbox != (0, 0, image.width, image.height):
        return image.crop(alpha_bbox)
    pixels = image.convert("RGBA").load()
    xs: list[int] = []
    ys: list[int] = []
    for y in range(image.height):
        for x in range(image.width):
            r, g, b, a = pixels[x, y]
            if a > 20 and not (r > 238 and g > 238 and b > 238):
                xs.append(x)
                ys.append(y)
    if not xs:
        return image
    pad_x = max(8, int((max(xs) - min(xs) + 1) * 0.06))
    pad_y = max(8, int((max(ys) - min(ys) + 1) * 0.06))
    return image.crop(
        (
            max(0, min(xs) - pad_x),
            max(0, min(ys) - pad_y),
            min(image.width, max(xs) + pad_x),
            min(image.height, max(ys) + pad_y),
        )
    )


def _default_outfit_title(items: list[dict[str, Any]]) -> str:
    labels = [item.get("category_label") or "单品" for item in items[:3]]
    return " + ".join(labels) if labels else "我的搭配"


def _initial_favorite_count(item_ids: list[str]) -> int:
    digest = hashlib.sha256(":".join(item_ids).encode("utf-8")).hexdigest()
    return 18 + (int(digest[:2], 16) % 36)


def render_closet_demo_page() -> str:
    return """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>我的电子衣橱</title>
  <link rel="icon" type="image/svg+xml" href="/static/brand/favicon.svg" />
  <link rel="icon" type="image/png" sizes="32x32" href="/static/brand/favicon-32.png" />
  <link rel="apple-touch-icon" href="/static/brand/apple-touch-icon.png" />
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
      --soft-ink: #4f454c;
      --muted: #8b8388;
      --line: #eee4e8;
      --success: #23835a;
      --warning: #a46a00;
      --error: #d92c4e;
      --radius-sm: 8px;
      --radius-md: 16px;
      --radius-lg: 24px;
      --radius-pill: 999px;
      --shadow-card: 0 18px 48px rgba(82, 42, 61, .09);
      --shadow-cta: 0 16px 30px rgba(255, 79, 134, .24);
      --screen-w: 430px;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--page);
      color: var(--ink);
      font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Segoe UI", sans-serif;
      letter-spacing: 0;
    }
    button, input, select, textarea { font: inherit; }
    button { cursor: pointer; }
    .shell {
      width: min(100%, var(--screen-w));
      min-height: 100vh;
      margin: 0 auto;
      background: linear-gradient(180deg, #fff9fc 0%, #faf5f8 100%);
      box-shadow: 0 0 0 1px rgba(0,0,0,.04), 0 20px 80px rgba(48, 20, 28, .08);
      overflow: hidden;
      position: relative;
    }
    .topbar {
      position: sticky;
      top: 0;
      z-index: 5;
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 14px 18px 10px;
      background: rgba(255, 250, 253, .88);
      border-bottom: 1px solid rgba(238,228,232,.82);
      backdrop-filter: blur(16px);
    }
    .brand { display: flex; align-items: center; gap: 9px; font-weight: 850; }
    .brand-mark { width: 30px; height: 30px; border-radius: 11px; background: var(--accent); box-shadow: var(--shadow-cta); }
    .topbar a { color: var(--accent-deep); text-decoration: none; font-size: 12px; font-weight: 800; }
    .content { padding: 18px 18px 112px; display: grid; gap: 16px; }
    .hero { display: grid; gap: 12px; }
    h1 { margin: 0; font-size: 30px; line-height: 1.12; font-weight: 800; }
    .subtitle { margin: 0; color: var(--muted); font-size: 14px; line-height: 1.6; }
    .panel {
      border-radius: var(--radius-lg);
      background: rgba(255,255,255,.94);
      border: 1px solid rgba(255,255,255,.9);
      box-shadow: var(--shadow-card);
      padding: 16px;
      display: grid;
      gap: 12px;
    }
    .section-title { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
    .section-title b { font-size: 16px; }
    .section-title small { color: var(--muted); font-size: 12px; }
    .upload-tile {
      min-height: 136px;
      border: 1.5px dashed #f0b7c0;
      border-radius: 22px;
      background: linear-gradient(180deg, #fff 0%, #fff5fa 100%);
      display: grid;
      place-items: center;
      padding: 16px;
      text-align: center;
      color: var(--muted);
    }
    .upload-tile strong { display: block; color: var(--ink); margin-bottom: 5px; font-size: 16px; }
    .file-input { display: none; }
    .url-row { display: grid; gap: 10px; }
    input[type=url], select, textarea {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: var(--radius-pill);
      padding: 13px 16px;
      background: #fff;
      color: var(--ink);
      outline: none;
    }
    textarea { border-radius: 18px; min-height: 74px; resize: vertical; }
    .cta {
      width: 100%;
      min-height: 54px;
      border: 0;
      border-radius: var(--radius-pill);
      color: #fff;
      background: var(--accent);
      box-shadow: var(--shadow-cta);
      font-weight: 800;
      font-size: 15px;
    }
    .cta:disabled { opacity: .52; box-shadow: none; cursor: not-allowed; }
    .secondary {
      min-height: 46px;
      border: 1px solid #f2c6cc;
      border-radius: var(--radius-pill);
      background: #fff;
      color: var(--accent-deep);
      font-weight: 800;
    }
    .status { min-height: 22px; color: var(--muted); font-size: 13px; line-height: 1.5; }
    .tabs { display: flex; gap: 8px; overflow: auto; padding-bottom: 2px; }
    .tab { border: 0; border-radius: var(--radius-pill); padding: 9px 12px; background: #fff; color: var(--muted); font-weight: 800; white-space: nowrap; }
    .tab.active { background: var(--soft); color: var(--accent-deep); }
    .grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
    .item-card {
      border: 1px solid var(--line);
      border-radius: var(--radius-md);
      background: #fff;
      padding: 8px;
      display: grid;
      gap: 8px;
      text-align: left;
      color: inherit;
    }
    .item-card img { width: 100%; aspect-ratio: 1; object-fit: contain; border-radius: 12px; background: var(--canvas); }
    .item-card b { font-size: 13px; }
    .item-card span { color: var(--muted); font-size: 12px; }
    .empty { color: var(--muted); text-align: center; padding: 28px 10px; line-height: 1.6; }
    .drawer {
      position: fixed;
      left: 50%;
      bottom: 0;
      z-index: 10;
      width: min(100%, var(--screen-w));
      transform: translate(-50%, 110%);
      transition: transform .22s ease;
      padding: 14px;
      background: rgba(255,250,253,.96);
      border-top: 1px solid var(--line);
      box-shadow: 0 -22px 60px rgba(54, 25, 38, .12);
      border-radius: 24px 24px 0 0;
      display: grid;
      gap: 12px;
    }
    .drawer.open { transform: translate(-50%, 0); }
    .drawer-head { display: grid; grid-template-columns: 112px 1fr; gap: 12px; align-items: center; }
    .drawer-head img { width: 112px; aspect-ratio: 1; object-fit: contain; border-radius: 16px; background: #fff; border: 1px solid var(--line); }
    .drawer h2 { margin: 0; font-size: 20px; line-height: 1.2; }
    .drawer p { margin: 6px 0 0; color: var(--muted); font-size: 13px; line-height: 1.5; }
    .drawer-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .danger { border-color: #f0b8c0; color: var(--error); }
    details { border: 1px solid var(--line); border-radius: 16px; background: rgba(255,255,255,.72); overflow: hidden; }
    summary { list-style: none; padding: 12px 14px; color: var(--accent-deep); font-weight: 800; font-size: 13px; }
    summary::-webkit-details-marker { display: none; }
    pre { margin: 0; max-height: 220px; overflow: auto; padding: 12px; color: #5f555a; white-space: pre-wrap; font-size: 12px; line-height: 1.45; }
    @media (min-width: 861px) {
      body { padding: 24px 0; }
      .shell { min-height: calc(100vh - 48px); border-radius: 34px; }
      .drawer { bottom: 24px; border-radius: 24px 24px 34px 34px; }
    }
  </style>
</head>
<body>
  <main class="shell">
    <div class="topbar">
      <div class="brand"><span class="brand-mark"></span><span>我的衣橱</span></div>
      <a href="/try-on/demo">去试穿</a>
    </div>
    <div class="content">
      <section class="hero">
        <h1>自动提取衣物，放进你的电子衣橱</h1>
        <p class="subtitle">上传穿搭图、单品图，或粘贴公开网页链接。系统会先帮你入柜，再让你慢慢挑、改、试。</p>
      </section>
      <section class="panel">
        <div class="section-title"><b>导入衣物</b><small id="capabilityText">正在检查能力</small></div>
        <label class="upload-tile" for="imageInput">
          <span id="uploadHint"><strong>上传图片</strong>支持多张 JPG、PNG、WebP</span>
        </label>
        <input id="imageInput" class="file-input" type="file" accept="image/*" multiple />
        <button id="uploadBtn" class="cta" disabled>自动入柜</button>
        <div class="url-row">
          <input id="linkInput" type="url" placeholder="粘贴小红书或网页链接" />
          <button id="linkBtn" class="secondary">从链接导入</button>
        </div>
        <div id="status" class="status">先上传图片，或粘贴一个公开链接。</div>
      </section>
      <section class="panel">
        <div class="section-title"><b>衣橱单品</b><small id="itemCount">0 件</small></div>
        <div class="tabs" id="tabs"></div>
        <div class="grid" id="itemGrid"></div>
      </section>
      <details>
        <summary>查看处理细节</summary>
        <pre id="debugOut">{}</pre>
      </details>
    </div>
  </main>
  <aside class="drawer" id="drawer">
    <div class="drawer-head">
      <img id="drawerImage" alt="衣物预览" />
      <div>
        <h2 id="drawerTitle">衣物</h2>
        <p id="drawerMeta">已入柜</p>
      </div>
    </div>
    <select id="categorySelect">
      <option value="top">上衣</option>
      <option value="bottom">裤子</option>
      <option value="skirt">裙子</option>
      <option value="dress">连衣裙</option>
      <option value="shoes">鞋子</option>
      <option value="bag">包</option>
      <option value="accessory">配饰</option>
    </select>
    <textarea id="noteInput" placeholder="备注，比如：通勤、显白、想搭牛仔裤"></textarea>
    <div class="drawer-actions">
      <button id="saveBtn" class="cta">保存修改</button>
      <button id="tryonBtn" class="secondary">用于试穿</button>
      <button id="reprocessBtn" class="secondary">重新处理</button>
      <button id="deleteBtn" class="secondary danger">删除</button>
    </div>
    <button id="closeBtn" class="secondary">收起</button>
  </aside>
  <script src="/static/vendor/lottie.min.js"></script>
  <script>
    const categories = [
      ["all", "全部"], ["top", "上衣"], ["bottom", "裤子"], ["skirt", "裙子"],
      ["dress", "连衣裙"], ["shoes", "鞋子"], ["bag", "包"], ["accessory", "配饰"]
    ];
    let selectedCategory = "all";
    let selectedItem = null;
    const imageInput = document.getElementById("imageInput");
    const uploadBtn = document.getElementById("uploadBtn");
    const linkBtn = document.getElementById("linkBtn");
    const linkInput = document.getElementById("linkInput");
    const statusLine = document.getElementById("status");
    const debugOut = document.getElementById("debugOut");
    const drawer = document.getElementById("drawer");

    function setStatus(text) { statusLine.textContent = text; }
    function setDebug(data) { debugOut.textContent = JSON.stringify(data, null, 2); }
    function renderTabs() {
      document.getElementById("tabs").innerHTML = categories.map(([key, label]) =>
        `<button class="tab ${key === selectedCategory ? "active" : ""}" data-category="${key}">${label}</button>`
      ).join("");
      document.querySelectorAll("[data-category]").forEach(btn => btn.addEventListener("click", () => {
        selectedCategory = btn.dataset.category;
        loadItems();
      }));
    }
    async function loadCapabilities() {
      const res = await fetch("/closet/capabilities");
      const data = await res.json().catch(() => ({ detail: "服务暂时没有返回可读结果，请稍后再试。" }));
      document.getElementById("capabilityText").textContent = data.mode === "partial_top_fallback" ? "上衣优先模式" : "多品类模式";
      setDebug(data);
    }
    async function loadItems() {
      renderTabs();
      const query = selectedCategory === "all" ? "" : `?category=${encodeURIComponent(selectedCategory)}`;
      const res = await fetch(`/closet/items${query}`);
      const data = await res.json();
      document.getElementById("itemCount").textContent = `${data.total} 件`;
      const grid = document.getElementById("itemGrid");
      if (!data.items.length) {
        grid.innerHTML = `<div class="empty" style="grid-column:1/-1;">还没有衣物。上传图片后，会自动出现在这里。</div>`;
        return;
      }
      grid.innerHTML = data.items.map(item => {
        const img = item.assets?.preview_path || item.assets?.cutout_path || "";
        const quality = item.quality?.status === "usable" ? "可用" : item.quality?.status === "review" ? "待确认" : "暂不可用";
        return `<button class="item-card" data-item="${item.item_id}">
          <img src="${img}" alt="${item.category_label}">
          <b>${item.category_label}</b>
          <span>${quality}</span>
        </button>`;
      }).join("");
      document.querySelectorAll("[data-item]").forEach(btn => btn.addEventListener("click", () => openItem(btn.dataset.item)));
    }
    async function openItem(itemId) {
      const res = await fetch(`/closet/items/${encodeURIComponent(itemId)}`);
      selectedItem = await res.json();
      document.getElementById("drawerImage").src = selectedItem.assets?.preview_path || selectedItem.assets?.cutout_path || "";
      document.getElementById("drawerTitle").textContent = selectedItem.category_label || "衣物";
      document.getElementById("drawerMeta").textContent = selectedItem.quality?.status === "usable" ? "可以用于试穿" : "建议确认后再使用";
      document.getElementById("categorySelect").value = selectedItem.category || "accessory";
      document.getElementById("noteInput").value = selectedItem.note || "";
      drawer.classList.add("open");
      setDebug(selectedItem);
    }
    imageInput.addEventListener("change", () => {
      uploadBtn.disabled = !imageInput.files.length;
      document.getElementById("uploadHint").innerHTML = imageInput.files.length ? `<strong>已选择 ${imageInput.files.length} 张图片</strong>点击自动入柜开始提取` : `<strong>上传图片</strong>支持多张 JPG、PNG、WebP`;
    });
    uploadBtn.addEventListener("click", async () => {
      if (!imageInput.files.length) return;
      uploadBtn.disabled = true;
      setStatus("正在提取衣物...");
      const body = new FormData();
      [...imageInput.files].forEach(file => body.append("images", file));
      try {
        const res = await fetch("/closet/import/upload", { method: "POST", body });
        const data = await res.json();
        setDebug(data);
        setStatus(data.message || `已找到 ${data.summary.created} 件单品，有 ${data.summary.review} 件需要确认。`);
        await loadItems();
      } catch (error) {
        setStatus(error.message || "导入失败，请换一张清晰图片。");
      } finally {
        uploadBtn.disabled = false;
      }
    });
    linkBtn.addEventListener("click", async () => {
      const url = linkInput.value.trim();
      if (!url) {
        setStatus("请先粘贴一个公开链接。");
        return;
      }
      linkBtn.disabled = true;
      setStatus("正在解析链接和提取衣物...");
      const body = new FormData();
      body.append("url", url);
      try {
        const res = await fetch("/closet/import/link", { method: "POST", body });
        const data = await res.json();
        setDebug(data);
        setStatus(data.message || `已找到 ${data.summary.created} 件单品。`);
        await loadItems();
      } catch (error) {
        setStatus(error.message || "这个链接暂时拿不到清晰图片，请改用截图或上传图片。");
      } finally {
        linkBtn.disabled = false;
      }
    });
    document.getElementById("saveBtn").addEventListener("click", async () => {
      if (!selectedItem) return;
      const res = await fetch(`/closet/items/${encodeURIComponent(selectedItem.item_id)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          category: document.getElementById("categorySelect").value,
          note: document.getElementById("noteInput").value
        })
      });
      selectedItem = await res.json();
      setStatus("已保存修改。");
      drawer.classList.remove("open");
      await loadItems();
    });
    document.getElementById("tryonBtn").addEventListener("click", () => {
      if (!selectedItem) return;
      if (selectedItem.category !== "top") {
        setStatus("这件已入柜，当前只支持上衣试穿。");
        return;
      }
      window.location.href = `/try-on/demo?closet_item_id=${encodeURIComponent(selectedItem.item_id)}`;
    });
    document.getElementById("reprocessBtn").addEventListener("click", async () => {
      if (!selectedItem) return;
      setStatus("正在重新处理这件衣物...");
      const res = await fetch(`/closet/items/${encodeURIComponent(selectedItem.item_id)}/reprocess`, { method: "POST" });
      const data = await res.json();
      setDebug(data);
      setStatus(`已重新处理，新增 ${data.summary.created} 件单品。`);
      drawer.classList.remove("open");
      await loadItems();
    });
    document.getElementById("deleteBtn").addEventListener("click", async () => {
      if (!selectedItem) return;
      await fetch(`/closet/items/${encodeURIComponent(selectedItem.item_id)}`, { method: "DELETE" });
      setStatus("已从衣橱删除。");
      drawer.classList.remove("open");
      await loadItems();
    });
    document.getElementById("closeBtn").addEventListener("click", () => drawer.classList.remove("open"));
    renderTabs();
    loadCapabilities();
    loadItems();
  </script>
</body>
</html>
"""


def render_selfit_demo_page() -> str:
    return """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>selfit Demo</title>
  <link rel="icon" type="image/svg+xml" href="/static/brand/favicon.svg" />
  <link rel="icon" type="image/png" sizes="32x32" href="/static/brand/favicon-32.png" />
  <link rel="apple-touch-icon" href="/static/brand/apple-touch-icon.png" />
  <style>
    :root {
      --screen-w: 430px;
      --bg: #fffafa;
      --card: #ffffff;
      --page: #f8f2f5;
      --soft: #fff1f6;
      --soft-2: #eefbff;
      --ink: #1c1b20;
      --soft-ink: #4f454c;
      --muted: #8b8388;
      --line: #eee4e8;
      --rose: #ff4f86;
      --rose-deep: #e83d73;
      --error: #d92c4e;
      --mint: #74f0d2;
      --radius: 24px;
      --pill: 999px;
      --shadow-card: 0 18px 48px rgba(82, 42, 61, .09);
      --shadow-cta: 0 16px 30px rgba(255, 79, 134, .24);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: #fff;
      color: var(--ink);
      font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Segoe UI", sans-serif;
      letter-spacing: 0;
    }
    button, input { font: inherit; }
    button { cursor: pointer; }
    .app {
      width: min(100%, var(--screen-w));
      min-height: 100vh;
      margin: 0 auto;
      background: linear-gradient(180deg, #fffafa 0%, #f8f2f5 100%);
      position: relative;
      overflow: hidden;
    }
    .page {
      display: none;
      min-height: 100vh;
      padding: 22px 16px 104px;
      overflow: auto;
    }
    .page.active { display: block; }
    .top-row { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; margin-bottom: 18px; }
    .brand { font-size: 32px; line-height: 1; font-style: italic; font-weight: 900; letter-spacing: 0; }
    .weather { text-align: right; font-size: 12px; color: #666; line-height: 1.25; padding-top: 4px; }
    .weather b { display: block; font-size: 17px; color: var(--ink); }
    h1, h2, h3, p { margin: 0; }
    h2 { font-size: 26px; line-height: 1.1; font-weight: 900; margin: 0 0 14px; }
    .widget-row, .item-strip, .palette-tabs, .category-row, .today-track {
      scrollbar-width: none !important;
      -ms-overflow-style: none !important;
      -webkit-overflow-scrolling: touch;
      overscroll-behavior-x: contain;
    }
    .widget-row::-webkit-scrollbar,
    .item-strip::-webkit-scrollbar,
    .palette-tabs::-webkit-scrollbar,
    .category-row::-webkit-scrollbar,
    .today-track::-webkit-scrollbar {
      display: none !important;
      width: 0 !important;
      height: 0 !important;
      background: transparent !important;
    }
    .home-section { margin-top: 24px; }
    .section-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
    .section-head h2 { margin: 0; }
    .section-head button { border: 0; background: transparent; color: var(--muted); font-weight: 750; min-height: 38px; }
    .today-carousel { margin: 0 -16px; padding: 0 16px; overflow: hidden; }
    .today-track {
      display: flex;
      gap: 12px;
      overflow-x: auto;
      overflow-y: hidden;
      scroll-snap-type: x mandatory;
      padding: 0 0 6px;
      touch-action: pan-x pan-y;
    }
    .today-card {
      width: 100%;
      flex: 0 0 100%;
      scroll-snap-align: center;
      border: 0;
      border-radius: 28px;
      background: #1f1d20;
      color: #fff;
      text-align: left;
      min-height: 158px;
      padding: 8px 14px;
      overflow: hidden;
      display: grid;
      grid-template-columns: minmax(0, 1fr) 48%;
      gap: 4px;
      box-shadow: var(--shadow-card);
      position: relative;
      touch-action: pan-x pan-y;
    }
    .today-copy { display: grid; align-content: center; gap: 7px; min-width: 0; padding: 0; }
    .tag { width: fit-content; border-radius: var(--pill); background: rgba(255,255,255,.12); padding: 6px 11px; color: #bdf7de; font-size: 12px; font-weight: 850; }
    .today-card h1 { font-size: 24px; line-height: 1.05; font-weight: 900; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; letter-spacing: 0; }
    .today-card p { color: rgba(255,255,255,.72); line-height: 1.42; font-size: 13px; max-width: 15em; }
    .today-art { position: relative; min-width: 0; min-height: 142px; margin: -8px -8px -8px 0; }
    .today-art img { position: absolute; object-fit: contain; filter: drop-shadow(0 14px 24px rgba(0,0,0,.36)); }
    .image-preview-button {
      appearance: none;
      border: 0;
      background: transparent;
      color: inherit;
      font: inherit;
      padding: 0;
      text-align: inherit;
      cursor: zoom-in;
    }
    .today-art.image-preview-button { width: 100%; height: calc(100% + 16px); }
    .today-art .slot-top { width: 100%; height: 64%; left: 1%; top: -8%; }
    .today-art .slot-bottom, .today-art .slot-skirt { width: 96%; height: 72%; left: -12%; top: 34%; }
    .today-art .slot-dress { width: 108%; height: 108%; left: -14%; top: -4%; }
    .today-art .slot-shoes { width: 78%; height: 40%; right: -9%; bottom: -8%; }
    .today-art .slot-bag { width: 70%; height: 50%; right: -9%; top: 18%; }
    .today-art .slot-accessory { width: 54%; height: 38%; right: -3%; top: -4%; }
    .today-art .slot-generic { width: 84%; height: 58%; left: 6%; top: 18%; }
    .today-dots { display: flex; justify-content: center; align-items: center; gap: 7px; min-height: 12px; }
    .today-dot { width: 18px; height: 4px; border: 0; border-radius: var(--pill); background: rgba(28,27,32,.16); padding: 0; transition: width .18s ease, background .18s ease; }
    .today-dot.active { width: 30px; background: var(--ink); }
    .today-empty { background: linear-gradient(135deg, #fff1f6, #eefbff); color: var(--ink); grid-template-columns: 1fr; }
    .today-empty p { color: var(--soft-ink, #4f454c); }
    .widget-row { display: flex; gap: 12px; overflow-x: auto; overflow-y: hidden; padding: 2px 0 4px; margin-right: -16px; scroll-snap-type: x proximity; }
    .widget-card {
      border: 0;
      border-radius: 18px;
      min-width: 154px;
      min-height: 112px;
      padding: 14px;
      color: #fff;
      text-align: left;
      font-size: 18px;
      font-weight: 900;
      background: #fff;
      display: grid;
      align-content: end;
      box-shadow: 0 12px 28px rgba(82, 42, 61, .08);
      scroll-snap-align: start;
      position: relative;
      overflow: hidden;
      isolation: isolate;
      text-shadow: 0 2px 16px rgba(0,0,0,.28);
    }
    .widget-card::before,
    .widget-card::after {
      content: "";
      position: absolute;
      inset: 0;
      z-index: -1;
    }
    .widget-card::before {
      background: var(--widget-bg);
      background-size: cover;
      background-position: center;
      transform: scale(1.03);
    }
    .widget-card::after {
      background: linear-gradient(180deg, rgba(15,12,16,.04) 0%, rgba(15,12,16,.14) 44%, rgba(15,12,16,.54) 100%);
    }
    .widget-card.color {
      --widget-bg:
        linear-gradient(180deg, rgba(255,255,255,.04), rgba(20,12,18,.14)),
        url("/fixture-images/real_social_screenshot_auto_crop.jpg"),
        radial-gradient(circle at 22% 24%, rgba(255,255,255,.95) 0 10%, transparent 11%),
        radial-gradient(circle at 34% 22%, rgba(255,214,224,.98) 0 7%, transparent 8%),
        radial-gradient(circle at 47% 23%, rgba(255,226,166,.98) 0 7%, transparent 8%),
        radial-gradient(circle at 61% 23%, rgba(184,242,225,.98) 0 7%, transparent 8%),
        linear-gradient(135deg, rgba(255,244,237,.96), rgba(234,247,250,.96));
      background-position: center;
      animation: widgetNudge 7.2s ease-in-out infinite;
    }
    .widget-card.color::after {
      background:
        linear-gradient(110deg, transparent 0%, rgba(255,255,255,.0) 34%, rgba(255,255,255,.42) 45%, rgba(255,255,255,.08) 56%, transparent 68%),
        linear-gradient(180deg, rgba(15,12,16,.02) 0%, rgba(15,12,16,.16) 48%, rgba(15,12,16,.58) 100%);
      background-size: 240% 100%, 100% 100%;
      animation: widgetBeam 4.8s ease-in-out infinite;
    }
    .widget-card.ai {
      --widget-bg:
        linear-gradient(180deg, rgba(255,255,255,.02), rgba(20,12,18,.18)),
        var(--widget-image, url("/tryon-models/female_slim_1.webp?v=fullbody-20260705")),
        radial-gradient(circle at 20% 22%, rgba(255,255,255,.96) 0 11%, transparent 12%),
        radial-gradient(circle at 72% 28%, rgba(255,255,255,.92) 0 12%, transparent 13%),
        linear-gradient(145deg, rgba(255,246,241,.96), rgba(239,249,255,.98) 58%, rgba(255,239,247,.94));
    }
    .widget-card.ai::before {
      background:
        var(--widget-bg),
        linear-gradient(90deg, transparent 0 18%, rgba(45,74,96,.18) 18% 25%, transparent 25% 100%),
        linear-gradient(0deg, transparent 0 54%, rgba(28,27,32,.18) 54% 61%, transparent 61% 100%);
      background-position: center, center 18%, center, center, center, center, center;
      background-size: cover, cover, auto, auto, cover, auto, auto;
    }
    .widget-card.upload {
      --widget-bg:
        linear-gradient(180deg, rgba(255,255,255,.02), rgba(20,12,18,.14)),
        var(--widget-image, url("/fixture-images/xhs_low_quality_video_cover.jpg")),
        radial-gradient(ellipse at 30% 42%, rgba(255,255,255,.95) 0 20%, transparent 21%),
        radial-gradient(ellipse at 73% 35%, rgba(255,255,255,.9) 0 17%, transparent 18%),
        linear-gradient(135deg, rgba(255,241,246,.98), rgba(255,249,237,.96));
    }
    .widget-card.upload::before {
      background:
        var(--widget-bg),
        linear-gradient(110deg, transparent 0 32%, rgba(221,171,130,.28) 32% 37%, transparent 37% 100%),
        linear-gradient(18deg, transparent 0 56%, rgba(120,88,70,.22) 56% 62%, transparent 62% 100%);
      background-position: center, center 38%, center, center, center, center, center;
      background-size: cover, cover, auto, auto, cover, auto, auto;
    }
    @keyframes widgetNudge {
      0%, 82%, 100% { transform: translateX(0) rotate(0); }
      86% { transform: translateX(-1px) rotate(-.6deg); }
      90% { transform: translateX(1px) rotate(.6deg); }
      94% { transform: translateX(0) rotate(0); }
    }
    @keyframes widgetBeam {
      0%, 58% { background-position: 170% 0, 0 0; }
      78%, 100% { background-position: -80% 0, 0 0; }
    }
    @media (prefers-reduced-motion: reduce) {
      .widget-card.color,
      .widget-card.color::after { animation: none; }
    }
    .refresh-note { color: var(--muted); font-size: 13px; min-height: 20px; margin-bottom: 10px; }
    .masonry, .item-grid, .record-grid { display: grid; gap: 12px; }
    .masonry, .item-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .outfit-card, .closet-card {
      border: 0;
      background: var(--card);
      border-radius: 22px;
      overflow: hidden;
      color: inherit;
      text-align: left;
      padding: 0;
      min-width: 0;
      box-shadow: var(--shadow-card);
    }
    .outfit-canvas, .closet-img {
      background: #eef0f3;
      width: 100%;
      aspect-ratio: 1;
      display: grid;
      place-items: center;
      overflow: hidden;
    }
    .outfit-canvas img, .closet-img img { width: 100%; height: 100%; object-fit: contain; display: block; }
    .outfit-canvas[data-preview-image], .closet-img[data-preview-image], .detail-hero[data-preview-image], .tryon-hero[data-preview-image], .item-tile[data-preview-image], .record-card[data-preview-image], .model-chip[data-preview-image], .self-upload-zone[data-preview-image] { cursor: zoom-in; }
    .outfit-meta, .closet-meta { min-height: 54px; display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 11px 12px; }
    .favorite-btn { border: 0; background: transparent; display: inline-flex; align-items: center; justify-content: center; padding: 0; color: #050505; width: 40px; height: 40px; min-height: 38px; font-size: 24px; font-weight: 950; line-height: 1; }
    .favorite-btn.active { color: var(--rose); }
    .try-btn, .match-btn {
      border: 0;
      border-radius: var(--pill);
      background: var(--soft);
      color: var(--rose-deep);
      min-width: 78px;
      min-height: 38px;
      padding: 0 16px;
      font-size: 15px;
      font-weight: 850;
    }
    .primary-btn, .secondary-btn {
      border: 0;
      border-radius: var(--pill);
      min-height: 54px;
      padding: 0 22px;
      font-size: 16px;
      font-weight: 850;
    }
    .primary-btn { background: var(--rose); color: #fff; box-shadow: var(--shadow-cta); }
    .secondary-btn { background: #fff; color: var(--rose-deep); border: 1px solid #f2c6cc; }
    .icon-btn { border: 0; width: 44px; height: 44px; border-radius: 50%; background: rgba(255,255,255,.9); font-size: 24px; font-weight: 850; display: grid; place-items: center; }
    .screen-top { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 14px; }
    .screen-title { font-size: 22px; font-weight: 900; }
    .detail-hero, .tryon-hero, .editor-canvas, .color-card {
      background: #fff;
      border-radius: 24px;
      box-shadow: var(--shadow-card);
      overflow: hidden;
    }
    .detail-hero { min-height: 410px; display: grid; place-items: center; padding: 18px; position: relative; }
    .detail-hero img { width: 100%; height: 100%; max-height: 380px; object-fit: contain; }
    .model-chip { position: absolute; right: 18px; bottom: 18px; width: 78px; border-radius: 18px; background: rgba(255,255,255,.92); padding: 6px; box-shadow: 0 12px 28px rgba(0,0,0,.10); }
    .model-chip img { width: 100%; aspect-ratio: 3 / 4; object-fit: cover; border-radius: 12px; display: block; }
    .item-strip { display: flex; gap: 12px; overflow-x: auto; padding: 2px 0 4px; scroll-snap-type: x proximity; }
    .item-tile { min-width: 118px; border-radius: 18px; background: #fff; padding: 10px; box-shadow: var(--shadow-card); scroll-snap-align: start; }
    .item-tile img { width: 100%; aspect-ratio: 1; object-fit: contain; display: block; }
    .item-tile span { display: block; margin-top: 8px; color: var(--muted); font-size: 13px; font-weight: 700; }
    .bottom-actions { position: fixed; left: 50%; bottom: 18px; transform: translateX(-50%); width: min(calc(100% - 32px), 398px); display: grid; grid-template-columns: 1fr 1fr; gap: 12px; z-index: 11; }
    .tryon-hero { min-height: 560px; display: grid; place-items: center; position: relative; background: linear-gradient(180deg, #fff, #f8f2f5); }
    .tryon-hero img { width: 100%; max-height: 560px; object-fit: contain; display: block; }
    .tryon-failure { width: 100%; min-height: 560px; padding: 28px 24px; display: grid; align-content: center; justify-items: center; gap: 16px; text-align: center; }
    .tryon-failure-preview { width: min(100%, 320px); aspect-ratio: 4 / 3; position: relative; border-radius: 18px; overflow: hidden; background: #f5f5f5; }
    .tryon-failure-preview > img { width: 100%; height: 100%; max-height: none; object-fit: contain; }
    .tryon-failure-model { position: absolute; right: 10px; bottom: 10px; width: 62px; height: 82px; padding: 4px; border-radius: 14px; background: rgba(255,255,255,.94); box-shadow: 0 5px 24px rgba(0,0,0,.10); }
    .tryon-failure-model img { width: 100%; height: 100%; max-height: none; border-radius: 10px; object-fit: cover; }
    .tryon-failure h3 { margin: 2px 0 -6px; color: #222; font-size: 18px; line-height: 1.45; }
    .tryon-failure p { max-width: 300px; margin: 0; color: #666; font-size: 14px; line-height: 1.65; }
    .tryon-failure-change { min-height: 44px; padding: 0 24px; border: 1px solid #8a011b; border-radius: 18px; background: #fff; color: #8a011b; font-size: 14px; font-weight: 800; }
    .tryon-hero.is-generating {
      color: #fff;
      background: #8a011b url("/static/selfit/assets/splash-textile@2x.png") center / cover no-repeat;
      box-shadow: none;
      isolation: isolate;
    }
    .tryon-hero.is-generating::after {
      content: "";
      position: absolute;
      inset: 0;
      z-index: 1;
      background: linear-gradient(180deg, rgba(96,0,18,.04), rgba(58,0,11,.16));
      pointer-events: none;
    }
    .tryon-hero.is-generating > .empty { opacity: 0; }
    .tryon-hero.is-generating + .result-actions { visibility: hidden; pointer-events: none; }
    .generating-layer {
      position: absolute;
      inset: 0;
      z-index: 2;
      color: #fff;
      display: none;
      place-items: center;
      text-align: center;
      padding: 18px 24px 20px;
    }
    .generating-layer.active { display: grid; }
    .tryon-generating-card {
      width: min(100%, 342px);
      min-height: 520px;
      padding: 20px 0 6px;
      display: grid;
      justify-items: center;
      align-content: center;
      grid-template-rows: auto auto auto auto auto auto;
      gap: 12px;
    }
    .tryon-loading-art {
      width: min(100%, 282px);
      height: auto;
      max-height: none !important;
      object-fit: contain;
      margin: 0 0 8px;
      opacity: 1;
      transform: translateY(0) scale(1);
      transition: opacity 300ms ease-out, transform 300ms ease-out;
    }
    .tryon-loading-art.is-changing {
      opacity: .16;
      transform: translateY(4px) scale(.985);
    }
    .tryon-generating-kicker {
      margin: 0;
      color: rgba(255,255,255,.64);
      font-family: Georgia, "Times New Roman", serif;
      font-size: 12px;
      line-height: 18px;
      letter-spacing: .16em;
    }
    .tryon-generating-title {
      max-width: 286px;
      font-size: 18px;
      line-height: 26px;
      font-weight: 750;
      color: #fff;
      text-wrap: balance;
    }
    .tryon-generating-copy {
      max-width: 274px;
      margin: -2px 0 0;
      color: rgba(255,255,255,.68);
      font-size: 14px;
      line-height: 22px;
      font-weight: 400;
      text-wrap: balance;
    }
    .tryon-progress-row {
      width: min(100%, 274px);
      display: grid;
      grid-template-columns: 1fr 38px;
      align-items: center;
      gap: 12px;
      margin-top: 4px;
    }
    .tryon-progress {
      width: 100%;
      height: 2px;
      border-radius: 2px;
      background: rgba(255,255,255,.24);
      overflow: hidden;
    }
    .tryon-progress span {
      display: block;
      width: 8%;
      height: 100%;
      border-radius: inherit;
      background: #fff;
      transition: width 420ms ease-out;
    }
    .tryon-progress-value {
      color: rgba(255,255,255,.78);
      font-size: 12px;
      line-height: 18px;
      font-variant-numeric: tabular-nums;
      text-align: right;
    }
    .tryon-cancel {
      min-width: 96px;
      min-height: 44px;
      margin-top: 2px;
      padding: 0 18px;
      border: 0;
      background: transparent;
      color: rgba(255,255,255,.76);
      box-shadow: none;
      font-size: 14px;
      font-weight: 600;
      text-decoration: underline;
      text-decoration-color: rgba(255,255,255,.34);
      text-underline-offset: 5px;
    }
    .tryon-loading-signature {
      width: 72px !important;
      height: auto !important;
      max-height: none !important;
      object-fit: contain;
      margin-top: 0;
      opacity: .74;
    }
    @media (prefers-reduced-motion: reduce) {
      .tryon-loading-art,
      .tryon-progress span { transition: none; }
    }
    .result-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 14px; }
    .color-card { padding: 18px; display: grid; gap: 14px; }
    .upload-zone { border: 2px dashed #f2b4c8; background: #fff8fb; border-radius: 24px; min-height: 240px; display: grid; place-items: center; text-align: center; color: var(--muted); padding: 20px; }
    .upload-zone img { max-width: 100%; max-height: 260px; object-fit: contain; border-radius: 18px; }
    .color-result { background: #fff; border-radius: 18px; padding: 14px; color: var(--soft-ink, #4f454c); line-height: 1.55; display: none; }
    .editor-canvas { height: 488px; position: relative; margin-bottom: 14px; background: #fff; border: 10px solid #f1f2f5; touch-action: none; }
    .canvas-item { position: absolute; width: 132px; height: 132px; display: grid; place-items: center; border: 2px solid transparent; border-radius: 14px; touch-action: none; }
    .canvas-item.active { border-color: #fff; box-shadow: 0 0 0 2px var(--rose); }
    .canvas-item img { width: 100%; height: 100%; object-fit: contain; pointer-events: none; filter: drop-shadow(0 12px 18px rgba(0,0,0,.08)); }
    .canvas-delete { position: absolute; width: 34px; height: 34px; border-radius: 50%; border: 0; background: #050505; color: #fff; display: grid; place-items: center; z-index: 80; font-size: 20px; line-height: 1; }
    .smart-layout { display: block; margin: -2px auto 16px; border: 0; border-radius: var(--pill); min-height: 42px; padding: 0 18px; background: #fff; font-weight: 850; color: var(--ink); box-shadow: var(--shadow-card); }
    .editor-palette { background: #fff; border-radius: 24px 24px 0 0; margin: 0 -16px -104px; padding: 16px 16px 112px; }
    .palette-tabs { display: flex; gap: 22px; overflow-x: auto; border-bottom: 1px solid var(--line); margin: 0 -16px 12px; padding: 0 16px; scroll-snap-type: x proximity; }
    .palette-tab { border: 0; background: transparent; min-height: 42px; font-size: 16px; font-weight: 800; color: var(--muted); white-space: nowrap; scroll-snap-align: start; }
    .palette-tab.active { color: var(--ink); border-bottom: 3px solid var(--ink); }
    .empty {
      grid-column: 1 / -1;
      min-height: 180px;
      display: grid;
      place-items: center;
      text-align: center;
      color: #777;
      line-height: 1.6;
      background: #fff;
      border-radius: 22px;
      padding: 24px;
    }
    .ai-hero {
      min-height: 0;
      position: relative;
      overflow: hidden;
      margin: 22px 0 20px;
      background: var(--bg);
      max-height: 520px;
      opacity: 1;
      transform: translateY(0);
      transition: max-height .42s cubic-bezier(.2,.8,.2,1), opacity .24s ease, transform .32s cubic-bezier(.2,.8,.2,1), margin .32s ease;
    }
    .ai-hero.is-dismissed {
      max-height: 0;
      opacity: 0;
      transform: translateY(-18px);
      margin: 0;
      pointer-events: none;
    }
    .ai-session-bar {
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 10px;
      margin: 0;
      position: fixed;
      top: max(34px, calc(env(safe-area-inset-top) + 24px));
      right: max(18px, calc((100vw - var(--screen-w)) / 2 + 18px));
      z-index: 34;
      pointer-events: none;
    }
    .ai-session-toggle {
      pointer-events: auto;
      border: 0;
      width: 42px;
      height: 42px;
      border-radius: 15px;
      background: rgba(255,255,255,.92);
      color: #73767d;
      display: grid;
      place-items: center;
      box-shadow: 0 14px 32px rgba(82, 42, 61, .12);
      backdrop-filter: blur(16px);
      transition: transform .18s ease, color .18s ease, background .18s ease, box-shadow .18s ease;
    }
    .ai-session-toggle:active { transform: scale(.96); }
    .ai-session-toggle svg {
      width: 24px;
      height: 24px;
      display: block;
      stroke: currentColor;
      fill: none;
      stroke-width: 2;
      stroke-linecap: round;
      stroke-linejoin: round;
    }
    .ai-session-toggle.active { color: var(--rose-deep); background: #fff; }
    .session-toggle-icon {
      display: block;
    }
    .ai-session-toggle .icon-open { display: block; }
    .ai-session-toggle .icon-close { display: none; }
    .ai-session-toggle.active .icon-open { display: none; }
    .ai-session-toggle.active .icon-close { display: block; }
    .ai-copy { position: static; }
    .ai-copy .hi { font-size: 52px; line-height: .95; font-weight: 950; font-style: italic; letter-spacing: 0; }
    .ai-copy h2 { margin: 16px 0 10px; font-size: 24px; line-height: 1.18; max-width: 11em; }
    .ai-copy p { color: #777; font-size: 14px; line-height: 1.5; }
    .chips { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 16px; }
    .chip {
      border: 0;
      border-radius: var(--pill);
      background: #fff;
      min-height: 42px;
      padding: 0 16px;
      font-size: 14px;
      font-weight: 850;
      color: #111;
    }
    .ai-panel {
      display: grid;
      gap: 18px;
      margin: 8px 0 104px;
      padding-bottom: 8px;
    }
    .ai-panel b { font-size: 18px; }
    .ai-panel p { margin: 0; color: var(--ink); line-height: 1.72; font-size: 15px; }
    .ai-panel ul { margin: 0; padding-left: 22px; color: var(--ink); line-height: 1.7; }
    .ai-thread { display: grid; gap: 18px; }
    .ai-thread.has-messages { animation: aiThreadLift .36s cubic-bezier(.2,.8,.2,1); }
    .ai-thread.is-streaming,
    .ai-thread.is-streaming .ai-bubble.user,
    .ai-thread.is-generating,
    .ai-thread.is-generating .ai-bubble.user { animation: none; }
    .ai-bubble {
      border-radius: 20px;
      padding: 14px 16px;
      line-height: 1.55;
      font-size: 15px;
      color: var(--ink);
      background: #fff;
      max-width: 86%;
      text-wrap: pretty;
    }
    .ai-bubble.user {
      justify-self: end;
      background: #edf3ff;
      color: var(--ink);
      font-size: 18px;
      font-weight: 750;
      border-radius: 18px;
      box-shadow: none;
      animation: aiBubbleIn .26s cubic-bezier(.2,.8,.2,1);
    }
    .ai-assistant-turn {
      display: grid;
      gap: 13px;
      color: var(--ink);
      font-size: 15px;
      line-height: 1.72;
      overflow-anchor: none;
    }
    .ai-assistant-copy {
      display: grid;
      gap: 12px;
    }
    .ai-assistant-copy p {
      color: var(--ink);
      font-size: 15px;
      line-height: 1.76;
      margin: 0;
    }
    .ai-assistant-copy strong {
      color: #1c1b20;
      font-weight: 850;
    }
    .ai-md-heading {
      color: #1c1b20;
      font-size: 15px;
      font-weight: 850;
      line-height: 1.48;
      margin-top: 2px;
    }
    .ai-md-list {
      display: grid;
      gap: 8px;
      list-style: none;
      margin: 0;
      padding: 0;
    }
    .ai-md-list li {
      color: #2f2b31;
      font-size: 15px;
      line-height: 1.68;
      padding-left: 18px;
      position: relative;
    }
    .ai-md-list li::before {
      content: "";
      width: 6px;
      height: 6px;
      border-radius: var(--pill);
      background: var(--rose);
      opacity: .7;
      position: absolute;
      left: 2px;
      top: .76em;
    }
    .ai-assistant-copy code {
      background: #fff1f6;
      border-radius: 7px;
      color: var(--rose-deep);
      font-size: .94em;
      padding: 1px 5px;
    }
    .ai-status-label {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      width: fit-content;
      border: 0;
      background: transparent;
      color: #7a7c81;
      font-size: 16px;
      font-weight: 850;
      padding: 0;
    }
    .ai-status-label::after {
      content: "";
      width: 7px;
      height: 7px;
      border-right: 2px solid currentColor;
      border-bottom: 2px solid currentColor;
      transform: rotate(45deg) translateY(-2px);
      opacity: .8;
    }
    .ai-status-label.is-collapsed::after { transform: rotate(-45deg) translateY(1px); }
    .ai-sources { display: flex; gap: 8px; flex-wrap: wrap; }
    .ai-source {
      border-radius: var(--pill);
      background: #fff1f6;
      color: var(--rose-deep);
      min-height: 30px;
      padding: 6px 10px;
      font-size: 12px;
      font-weight: 800;
    }
    .ai-toolchain {
      display: grid;
      gap: 7px;
      padding: 2px 0 4px 10px;
      border-left: 2px solid #ece8eb;
      background: transparent;
    }
    .ai-tool-summary {
      display: inline-flex;
      width: fit-content;
      align-items: center;
      gap: 8px;
      color: #8a8d93;
      font-size: 14px;
      font-weight: 800;
      padding-left: 2px;
    }
    .ai-tool-history {
      width: fit-content;
      max-width: 100%;
    }
    .ai-tool-history > summary {
      list-style: none;
      cursor: pointer;
      width: fit-content;
      border-radius: var(--pill);
    }
    .ai-tool-history > summary::-webkit-details-marker { display: none; }
    .ai-tool-history[open] > summary { margin-bottom: 8px; }
    .ai-tool-summary::before {
      content: "✓";
      color: #b5b7bb;
      font-weight: 900;
    }
    .ai-streaming-cursor::after {
      content: "";
      display: inline-block;
      width: 7px;
      height: 1.1em;
      margin-left: 2px;
      border-radius: 999px;
      background: currentColor;
      vertical-align: -2px;
      animation: aiCursorBlink .86s steps(2, start) infinite;
    }
    @keyframes aiThreadLift {
      from { transform: translateY(24px); }
      to { transform: translateY(0); }
    }
    @keyframes aiBubbleIn {
      from { opacity: 0; transform: translateY(14px) scale(.98); }
      to { opacity: 1; transform: translateY(0) scale(1); }
    }
    @keyframes aiCursorBlink {
      0%, 45% { opacity: 1; }
      46%, 100% { opacity: 0; }
    }
    .ai-tool-step {
      display: grid;
      grid-template-columns: 22px 1fr;
      gap: 8px;
      align-items: start;
      color: #7a7c81;
    }
    .ai-tool-dot {
      width: 18px;
      height: 18px;
      border-radius: 50%;
      display: grid;
      place-items: center;
      background: #f4f1f3;
      color: #999ba1;
      font-size: 11px;
      font-weight: 900;
      margin-top: 1px;
    }
    .ai-tool-step.done .ai-tool-dot { background: #f7f4f6; color: #b5b7bb; }
    .ai-tool-step.running .ai-tool-dot {
      background: #fff1f6;
      color: var(--rose-deep);
      box-shadow: 0 0 0 0 rgba(255,79,134,.3);
      animation: aiBreathingLight 1.45s ease-in-out infinite;
    }
    .ai-tool-step.failed .ai-tool-dot { background: #fff1f6; color: #a84f64; }
    .ai-tool-main { display: grid; gap: 2px; }
    .ai-tool-title-row { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
    .ai-tool-title { font-size: 15px; font-weight: 850; color: #73757a; }
    .ai-tool-status { color: #a4a0a5; font-size: 12px; font-weight: 800; white-space: nowrap; }
    .ai-tool-step.running .ai-tool-title { color: #4f454c; }
    .ai-tool-step.running .ai-tool-status { color: var(--rose-deep); }
    .ai-tool-detail { font-size: 14px; line-height: 1.55; color: #85878d; }
    @keyframes aiBreathingLight {
      0%, 100% { transform: scale(.96); opacity: .82; box-shadow: 0 0 0 0 rgba(255,79,134,.28); }
      50% { transform: scale(1.04); opacity: 1; box-shadow: 0 0 0 8px rgba(255,79,134,0); }
    }
    .xhs-note-strip {
      display: flex;
      gap: 12px;
      overflow-x: auto;
      margin: 2px -16px 0 0;
      padding: 2px 16px 10px 0;
      scroll-snap-type: x mandatory;
      scrollbar-width: none;
    }
    .xhs-note-strip::-webkit-scrollbar { display: none; }
    .xhs-note-card {
      flex: 0 0 154px;
      scroll-snap-align: start;
      border: 1px solid #f0dfe5;
      border-radius: 18px;
      overflow: hidden;
      background: #fff;
      color: var(--ink);
      text-decoration: none;
      box-shadow: 0 10px 24px rgba(82, 42, 61, .06);
    }
    .xhs-note-cover {
      width: 100%;
      aspect-ratio: 4 / 5;
      background: #f7f0f2;
      display: grid;
      place-items: center;
      color: #b3a7ad;
      font-size: 12px;
      overflow: hidden;
    }
    .xhs-note-cover img {
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
    }
    .xhs-note-body {
      display: grid;
      gap: 6px;
      padding: 9px 10px 10px;
    }
    .xhs-note-title {
      min-height: 36px;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
      font-size: 13px;
      line-height: 1.35;
      font-weight: 900;
    }
    .xhs-note-meta {
      display: flex;
      justify-content: space-between;
      gap: 6px;
      color: #7b7e86;
      font-size: 11px;
      line-height: 1.3;
    }
    .xhs-note-meta span {
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .ai-panel .ai-actions { display: flex; gap: 8px; flex-wrap: wrap; }
    .ai-panel .ai-actions button { border: 0; border-radius: var(--pill); min-height: 38px; padding: 0 14px; background: #f4f5f7; font-weight: 850; }
    .ai-panel.error .ai-assistant-turn { color: #9c4359; }
    .ai-input {
      position: fixed;
      left: 50%;
      bottom: 92px;
      transform: translateX(-50%);
      width: min(calc(100% - 28px), 402px);
      height: 58px;
      border-radius: var(--pill);
      padding: 2px;
      background: #fff;
      z-index: 9;
      overflow: hidden;
      box-shadow: 0 14px 38px rgba(64, 33, 48, .10);
      isolation: isolate;
    }
    .ai-input::before {
      content: "";
      position: absolute;
      inset: -120px;
      z-index: -2;
      background:
        conic-gradient(from 0deg,
          rgba(105, 234, 214, .95),
          rgba(255, 255, 255, .25) 16%,
          rgba(255, 79, 134, .92) 32%,
          rgba(235, 236, 255, .96) 52%,
          rgba(105, 234, 214, .95) 72%,
          rgba(255, 79, 134, .82));
      animation: aiInputBorderFlow 5.6s linear infinite;
    }
    .ai-input::after {
      content: "";
      position: absolute;
      inset: 2px;
      z-index: -1;
      border-radius: var(--pill);
      background: #fff;
      box-shadow: inset 0 0 0 1px rgba(255,255,255,.72);
    }
    .ai-input-inner {
      position: relative;
      z-index: 1;
      height: 100%;
      border-radius: var(--pill);
      background: #fff;
      display: grid;
      grid-template-columns: 1fr 46px;
      align-items: center;
      padding: 0 8px 0 24px;
      color: #aaa;
      font-size: 16px;
    }
    .ai-input-inner::after {
      content: "";
      position: absolute;
      inset: 1px auto 1px -36%;
      width: 34%;
      border-radius: inherit;
      pointer-events: none;
      background: linear-gradient(90deg, transparent, rgba(255,255,255,.92), transparent);
      mix-blend-mode: screen;
      opacity: .52;
      transform: skewX(-18deg);
      animation: aiInputSheen 3.8s ease-in-out infinite;
    }
    .ai-input-inner textarea {
      width: 100%;
      min-width: 0;
      height: 42px;
      resize: none;
      border: 0;
      outline: 0;
      background: transparent;
      color: var(--ink);
      font: inherit;
      line-height: 42px;
      padding: 0;
    }
    .ai-input-inner textarea::placeholder { color: #aaa; }
    .circle-icon { width: 42px; height: 42px; border-radius: 50%; border: 0; background: #eff0f2; display: grid; place-items: center; font-size: 23px; font-weight: 800; }
    .circle-icon.is-stopping {
      background: #1c1b20;
      color: #fff;
      font-size: 18px;
      box-shadow: 0 10px 24px rgba(28, 27, 32, .18);
    }
    @keyframes aiInputBorderFlow {
      to { transform: rotate(1turn); }
    }
    @keyframes aiInputSheen {
      0%, 38% { transform: translateX(0) skewX(-18deg); opacity: 0; }
      52% { opacity: .58; }
      74%, 100% { transform: translateX(440%) skewX(-18deg); opacity: 0; }
    }
    .session-list {
      display: grid;
      gap: 6px;
      max-height: none;
      overflow-y: auto;
      padding-right: 2px;
    }
    .session-new-btn {
      border: 0;
      border-radius: 16px;
      background: #fff;
      min-height: 54px;
      padding: 0 14px;
      color: var(--ink);
      font-size: 17px;
      font-weight: 850;
      text-align: left;
      display: inline-flex;
      align-items: center;
      gap: 10px;
      box-shadow: 0 8px 20px rgba(82,42,61,.04);
    }
    .session-new-btn svg {
      width: 22px;
      height: 22px;
      stroke: var(--rose-deep);
      fill: none;
      stroke-width: 2;
      stroke-linecap: round;
      stroke-linejoin: round;
      flex: 0 0 auto;
    }
    .session-section-title {
      color: var(--muted);
      font-size: 13px;
      font-weight: 850;
      margin: 16px 0 6px;
    }
    .session-card {
      border: 0;
      border-radius: 12px;
      background: #fff;
      min-height: 48px;
      padding: 9px 12px;
      display: grid;
      grid-template-columns: auto 1fr;
      align-items: center;
      gap: 10px;
      text-align: left;
      color: var(--ink);
    }
    .session-card.active { background: #f5f2f4; }
    .session-unread-dot {
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: var(--rose);
      box-shadow: 0 0 0 4px rgba(255,79,134,.12);
      opacity: 0;
    }
    .session-card.unread .session-unread-dot { opacity: 1; }
    .session-main { min-width: 0; display: grid; gap: 5px; }
    .session-title { font-size: 16px; font-weight: 760; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .session-preview,
    .session-meta { display: none; }
    .session-empty {
      border-radius: 18px;
      background: #fff;
      color: var(--muted);
      padding: 18px;
      line-height: 1.6;
      text-align: center;
    }
    .session-sidebar {
      position: fixed;
      left: max(0px, calc((100% - var(--screen-w)) / 2));
      right: auto;
      top: 0;
      bottom: 0;
      z-index: 22;
      width: min(78vw, 300px);
      height: 100dvh;
      transform: translateX(-104%);
      transition: transform .24s cubic-bezier(.2,.8,.2,1);
      background: #fff;
      border-radius: 0 24px 24px 0;
      padding: 28px 12px 24px;
      box-shadow: 22px 0 60px rgba(54,25,38,.14);
      display: grid;
      align-content: start;
      gap: 12px;
      overflow: auto;
    }
    .session-sidebar.open { transform: translateX(0); }
    .session-backdrop {
      position: fixed;
      inset: 0;
      z-index: 21;
      width: min(100%, var(--screen-w));
      left: 50%;
      transform: translateX(-50%);
      background: rgba(28,27,32,.22);
      opacity: 0;
      pointer-events: none;
      transition: opacity .22s ease;
    }
    .session-backdrop.open {
      opacity: 1;
      pointer-events: auto;
    }
    .session-action-popover {
      position: fixed;
      z-index: 24;
      left: max(14px, calc((100% - var(--screen-w)) / 2 + 14px));
      top: 120px;
      width: 178px;
      border-radius: 18px;
      background: rgba(255,255,255,.96);
      box-shadow: 0 18px 42px rgba(54,25,38,.18);
      padding: 8px;
      display: none;
      gap: 6px;
    }
    .session-action-popover.open { display: grid; }
    .session-action-popover button {
      border: 0;
      border-radius: 13px;
      background: #fff;
      min-height: 42px;
      padding: 0 12px;
      text-align: left;
      color: var(--ink);
      font-size: 15px;
      font-weight: 850;
    }
    .session-action-popover button.danger { color: var(--error); }
    .session-confirm {
      position: fixed;
      inset: 0;
      z-index: 25;
      width: min(100%, var(--screen-w));
      left: 50%;
      transform: translateX(-50%);
      background: rgba(28,27,32,.24);
      display: none;
      place-items: center;
      padding: 24px;
    }
    .session-confirm.open { display: grid; }
    .session-confirm-card {
      width: min(100%, 310px);
      border-radius: 24px;
      background: #fff;
      box-shadow: 0 22px 60px rgba(54,25,38,.18);
      padding: 20px;
      display: grid;
      gap: 14px;
    }
    .session-confirm-card b { font-size: 18px; }
    .session-confirm-card p { margin: 0; color: var(--muted); line-height: 1.55; font-size: 14px; }
    .session-confirm-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .session-confirm-actions button { border: 0; border-radius: var(--pill); min-height: 46px; font-size: 15px; font-weight: 850; }
    .session-confirm-actions .cancel { background: #f4f5f7; color: var(--ink); }
    .session-confirm-actions .danger { background: var(--rose); color: #fff; }
    .session-confirm-actions .primary { background: var(--rose); color: #fff; }
    .closet-top {
      display: grid;
      grid-template-columns: 1fr auto;
      align-items: center;
      gap: 10px;
      margin-bottom: 12px;
    }
    .closet-tabs { display: flex; gap: 34px; align-items: end; }
    .closet-tab {
      border: 0;
      background: transparent;
      color: #a5a6aa;
      font-size: 26px;
      font-weight: 850;
      padding: 0 0 12px;
      position: relative;
    }
    .closet-tab.active { color: var(--ink); }
    .closet-tab.active::after {
      content: "";
      position: absolute;
      left: 4px;
      right: 4px;
      bottom: 0;
      height: 4px;
      border-radius: 4px;
      background: #050505;
    }
    .tool-row { display: flex; gap: 12px; align-items: center; }
    .tool-row button { border: 0; background: transparent; width: 32px; height: 32px; font-size: 22px; font-weight: 900; color: #111; }
    .category-row { display: flex; gap: 14px; overflow-x: auto; overflow-y: hidden; padding: 8px 0 16px; margin: 0 -16px; padding-left: 16px; scroll-snap-type: x proximity; }
    .cat {
      border: 0;
      background: transparent;
      color: #909298;
      min-width: 62px;
      display: grid;
      justify-items: center;
      gap: 6px;
      font-size: 13px;
      font-weight: 750;
      position: relative;
      scroll-snap-align: start;
    }
    .cat-thumb {
      width: 54px;
      height: 54px;
      border-radius: 50%;
      background: #fff;
      display: grid;
      place-items: center;
      overflow: hidden;
      border: 0;
      position: relative;
    }
    .cat.active .cat-thumb { outline: 2px solid #111; outline-offset: 2px; }
    .cat-thumb img { width: 88%; height: 88%; object-fit: contain; }
    .badge { position: absolute; top: 0; right: 0; background: #050505; color: #fff; border-radius: var(--pill); min-width: 22px; padding: 2px 6px; font-size: 11px; font-weight: 850; z-index: 2; }
    .closet-card { padding: 10px; }
    .closet-img { border-radius: 18px; background: #fff; }
    .closet-meta { padding: 10px 2px 0; }
    .add-mini { border: 0; background: transparent; font-size: 22px; font-weight: 900; width: 40px; height: 40px; }
    .item-favorite { border: 0; background: transparent; color: #111; font-size: 24px; font-weight: 950; width: 40px; height: 40px; line-height: 1; }
    .item-favorite.active { color: var(--rose); }
    .floating-match {
      position: fixed;
      right: max(14px, calc((100% - var(--screen-w)) / 2 + 14px));
      bottom: 128px;
      border: 0;
      border-radius: var(--pill);
      background: #050505;
      color: #fff;
      min-height: 58px;
      padding: 0 28px;
      font-size: 18px;
      font-weight: 900;
      z-index: 8;
    }
    .profile-head { display: grid; grid-template-columns: 74px 1fr 40px; align-items: center; gap: 14px; padding: 18px 0 28px; }
    .avatar { width: 74px; height: 74px; border-radius: 50%; background: #e3e4e6; display: grid; place-items: center; color: #fff; font-size: 40px; font-weight: 900; }
    .profile-name { font-size: 22px; font-weight: 850; }
    .pro-card {
      min-height: 128px;
      border-radius: 22px;
      color: #fff;
      background: radial-gradient(circle at 82% 10%, rgba(255,79,134,.56), transparent 28%), linear-gradient(135deg, #070707, #1d2725 58%, #130b1f);
      padding: 22px;
      display: grid;
      gap: 12px;
      margin-bottom: 16px;
    }
    .pro-card b { font-size: 27px; font-style: italic; }
    .pro-card span { color: rgba(255,255,255,.86); }
    .profile-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 26px; }
    .profile-cell { min-height: 66px; border: 0; color: var(--ink); background: #eef0f3; border-radius: 16px; padding: 18px; display: flex; align-items: center; justify-content: space-between; font-size: 18px; font-weight: 850; text-align: left; }
    .profile-tabs { display: flex; gap: 28px; border-bottom: 1px solid var(--line); margin: 0 -16px 14px; padding: 0 16px; overflow-x: auto; scrollbar-width: none; }
    .profile-tabs::-webkit-scrollbar { display: none; }
    .profile-tab { border: 0; background: transparent; color: #aaa; font-size: 20px; font-weight: 850; padding: 0 0 12px; }
    .profile-tab { white-space: nowrap; }
    .profile-tab.active { color: var(--ink); border-bottom: 4px solid #111; }
    .record-head { color: #999; margin-bottom: 12px; display: flex; align-items: center; justify-content: space-between; gap: 12px; }
    .record-edit-btn { border: 0; background: transparent; color: #999; font-size: 16px; font-weight: 800; min-height: 36px; padding: 0; }
    .record-edit-btn.active { color: var(--rose); }
    .record-delete-bar { display: none; grid-template-columns: 1fr auto; align-items: center; gap: 12px; margin: 0 0 12px; padding: 10px 12px; border-radius: 16px; background: #fff; box-shadow: 0 10px 24px rgba(82, 42, 61, .08); color: var(--muted); font-weight: 750; }
    .record-delete-bar.active { display: grid; }
    .record-delete-btn { border: 0; border-radius: var(--pill); background: var(--rose); color: #fff; min-height: 38px; padding: 0 16px; font-weight: 900; }
    .record-delete-btn:disabled { opacity: .42; }
    .works-subtabs {
      display: none;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      margin: 0 0 12px;
      padding: 4px;
      border-radius: var(--pill);
      background: rgba(255,255,255,.72);
      border: 1px solid var(--line);
    }
    .works-subtabs.active { display: grid; }
    .works-subtab {
      border: 0;
      border-radius: var(--pill);
      min-height: 38px;
      background: transparent;
      color: var(--muted);
      font-size: 14px;
      font-weight: 850;
    }
    .works-subtab.active {
      background: var(--rose);
      color: #fff;
      box-shadow: 0 10px 22px rgba(255,79,134,.18);
    }
    .record-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    .record-card { border: 0; padding: 0; position: relative; border-radius: 16px; background: #ddd; aspect-ratio: 3 / 4; overflow: hidden; }
    .record-card img { width: 100%; height: 100%; object-fit: cover; }
    .record-card.work-item img { object-fit: contain; background: #fff; padding: 10px; }
    .record-card .record-badge { position: absolute; left: 8px; bottom: 8px; z-index: 1; padding: 5px 8px; border-radius: 999px; background: rgba(255,255,255,.9); color: #2b2a2f; font-size: 11px; font-weight: 900; box-shadow: 0 6px 16px rgba(0,0,0,.14); }
    .record-card.editing::after { content: ""; position: absolute; inset: 0; background: rgba(17,17,20,.18); }
    .record-card .check { position: absolute; right: 8px; top: 8px; z-index: 1; width: 24px; height: 24px; border-radius: 50%; display: grid; place-items: center; background: rgba(255,255,255,.9); color: transparent; font-size: 15px; font-weight: 950; box-shadow: 0 6px 16px rgba(0,0,0,.16); }
    .record-card.selected { outline: 3px solid var(--rose); outline-offset: -3px; }
    .record-card.selected .check { background: var(--rose); color: #fff; }
    .bottom-nav {
      position: fixed;
      left: 50%;
      bottom: 0;
      z-index: 10;
      width: min(100%, var(--screen-w));
      transform: translateX(-50%);
      height: 84px;
      background: rgba(255,255,255,.92);
      backdrop-filter: blur(18px);
      display: grid;
      grid-template-columns: 1fr 1fr 82px 1fr 1fr;
      align-items: center;
      border-top: 1px solid rgba(236,238,241,.8);
    }
    .bottom-nav.hidden { display: none; }
    .nav-btn {
      border: 0;
      background: transparent;
      color: #bbb;
      display: grid;
      gap: 5px;
      justify-items: center;
      align-content: center;
      font-size: 12px;
      font-weight: 800;
      min-height: 64px;
    }
    .nav-btn .nav-icon {
      width: 24px;
      height: 24px;
      display: block;
    }
    .nav-btn .nav-icon svg {
      width: 100%;
      height: 100%;
      display: block;
      stroke: currentColor;
      fill: none;
      stroke-width: 2.2;
      stroke-linecap: round;
      stroke-linejoin: round;
    }
    .nav-btn.active { color: #050505; }
    .plus-btn {
      width: 66px;
      height: 66px;
      border-radius: 50%;
      border: 0;
      background:
        radial-gradient(circle at 34% 24%, rgba(255,255,255,.42), transparent 28%),
        linear-gradient(145deg, #19171a, #050505 62%, #1d1b20);
      color: #fff;
      display: flex;
      align-items: center;
      justify-content: center;
      justify-self: center;
      margin-top: -22px;
      box-shadow: 0 18px 34px rgba(5,5,5,.26), inset 0 1px 0 rgba(255,255,255,.24);
      position: relative;
    }
    .plus-btn svg {
      width: 30px;
      height: 30px;
      stroke: currentColor;
      stroke-width: 2.7;
      stroke-linecap: round;
    }
    .sheet {
      position: fixed;
      left: 50%;
      bottom: 0;
      z-index: 20;
      width: min(100%, var(--screen-w));
      transform: translate(-50%, 110%);
      transition: transform .22s ease;
      background: #fff;
      border-radius: 28px 28px 0 0;
      padding: 18px 16px 24px;
      box-shadow: 0 -24px 70px rgba(0,0,0,.16);
      display: grid;
      gap: 12px;
      max-height: 82vh;
      overflow: auto;
    }
    .sheet.open { transform: translate(-50%, 0); }
    .sheet-title { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
    .sheet-title b { font-size: 20px; }
    .close { border: 0; background: #f0f1f3; width: 38px; height: 38px; border-radius: 50%; font-size: 22px; }
    .action-grid { display: grid; gap: 10px; }
    .action-card { border: 0; background: #f5f6f8; border-radius: 18px; min-height: 58px; padding: 0 18px; text-align: left; font-size: 17px; font-weight: 850; }
    .hidden-input { display: none; }
    .link-line { display: grid; grid-template-columns: 1fr 86px; gap: 8px; }
    .link-line input { border: 0; background: #f5f6f8; border-radius: var(--pill); min-height: 48px; padding: 0 16px; outline: none; }
    .black-btn { border: 0; background: #050505; color: #fff; border-radius: var(--pill); font-weight: 850; }
    .import-review-copy { margin: 0; color: #666; font-size: 14px; line-height: 1.6; }
    .import-review-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
    .import-review-card { position: relative; display: grid; gap: 8px; min-width: 0; }
    .import-review-image { width: 100%; aspect-ratio: 1; object-fit: contain; display: block; background: #faf8f8; border-radius: 12px; }
    .import-review-select { width: 100%; min-height: 42px; border: 1px solid #e7e7e7; border-radius: 12px; background: #fff; color: #222; padding: 0 10px; font-size: 14px; }
    .import-review-remove { position: absolute; top: 8px; right: 8px; width: 32px; height: 32px; border: 0; border-radius: 50%; background: rgba(255,255,255,.94); color: #8a011b; font-size: 20px; box-shadow: 0 4px 14px rgba(0,0,0,.08); }
    .import-review-done { min-height: 44px; border: 0; border-radius: 18px; background: #8a011b; color: #fff; font-size: 14px; font-weight: 800; }
    .builder-list { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
    .pick-card { border: 2px solid transparent; border-radius: 16px; background: #f6f7f9; padding: 7px; min-height: 112px; }
    .pick-card.active { border-color: #050505; }
    .pick-card img { width: 100%; aspect-ratio: 1; object-fit: contain; display: block; }
    .model-sheet {
      padding-left: 0;
      padding-right: 0;
      padding-bottom: max(18px, env(safe-area-inset-bottom));
      gap: 12px;
      height: min(80dvh, 690px);
      max-height: none;
      overflow: hidden !important;
      overflow-y: clip !important;
      scrollbar-width: none;
      overscroll-behavior: contain;
      grid-template-rows: auto auto minmax(0, 1fr) auto;
    }
    .model-sheet::-webkit-scrollbar { display: none; }
    .model-sheet .sheet-title { padding: 0 16px; }
    .model-tabs {
      display: flex;
      justify-content: center;
      gap: 54px;
      padding: 2px 16px 8px;
      border-bottom: 1px solid transparent;
    }
    .model-tab {
      border: 0;
      background: transparent;
      color: #9a9aa0;
      font-size: 21px;
      font-weight: 900;
      padding: 0 0 10px;
      position: relative;
    }
    .model-tab.active { color: var(--ink); }
    .model-tab.active::after {
      content: "";
      position: absolute;
      left: 50%;
      bottom: 0;
      width: 34px;
      height: 4px;
      border-radius: 999px;
      background: #050505;
      transform: translateX(-50%);
    }
    .model-carousel {
      display: flex;
      gap: 24px;
      min-height: 0;
      overflow-x: auto;
      overflow-y: clip;
      padding: 18px 0 6px;
      scroll-snap-type: x mandatory;
      scrollbar-width: none;
      align-items: stretch;
    }
    .model-carousel::-webkit-scrollbar { display: none; }
    .model-option {
      flex: 0 0 74%;
      min-height: 0;
      border: 0;
      background: transparent;
      padding: 0;
      display: grid;
      grid-template-rows: minmax(0, 1fr) auto;
      justify-items: center;
      align-items: stretch;
      gap: 12px;
      scroll-snap-align: center;
      color: var(--ink);
      opacity: .86;
      transform: scale(.96);
      transition: opacity .1s ease, transform .1s ease;
      cursor: pointer;
    }
    .model-option.active {
      opacity: 1;
      transform: scale(1);
    }
    .model-option.active .model-figure {
      box-shadow: 0 0 0 3px rgba(255, 79, 134, .72), 0 20px 44px rgba(82, 42, 61, .12);
    }
    .model-figure {
      width: 100%;
      height: 100%;
      min-height: 0;
      display: grid;
      place-items: end center;
      background: linear-gradient(180deg, #f9fafc, #f1f2f5);
      border-radius: 28px;
      overflow: hidden;
      transition: box-shadow .1s ease;
    }
    .model-figure img {
      width: 98%;
      height: 100%;
      object-fit: contain;
      object-position: bottom center;
      filter: none;
      image-rendering: auto;
    }
    .model-tags {
      width: 100%;
      display: flex;
      justify-content: center;
      align-items: center;
      gap: 8px;
      min-height: 28px;
      text-align: center;
    }
    .model-tags span {
      border: 1px solid #d8dbe0;
      border-radius: 9px;
      padding: 4px 9px;
      color: #5f6268;
      font-size: 13px;
      font-weight: 800;
      background: #fff;
    }
    .model-confirm {
      margin: 2px 16px 0;
      min-height: 58px;
      border: 0;
      border-radius: var(--pill);
      background: #050505;
      color: #fff;
      font-size: 17px;
      font-weight: 900;
      box-shadow: 0 14px 30px rgba(0,0,0,.16);
    }
    .my-photo-panel {
      display: none;
      min-height: 0;
      padding: 12px 16px 0;
    }
    .model-sheet[data-mode="photo"] .model-carousel,
    .model-sheet[data-mode="photo"] #confirmModelBtn { display: none; }
    .model-sheet[data-mode="photo"] .my-photo-panel { display: grid; gap: 12px; }
    .self-upload-zone {
      min-height: 0;
      border-radius: 28px;
      border: 2px dashed #d9dce2;
      background: #f7f8fa;
      display: grid;
      place-items: center;
      text-align: center;
      color: #8a8d94;
      padding: 24px;
      overflow: hidden;
    }
    .self-upload-zone img {
      max-width: 100%;
      max-height: 100%;
      object-fit: contain;
      border-radius: 20px;
    }
    .image-lightbox {
      position: fixed;
      inset: 0;
      left: 50%;
      width: min(100%, var(--screen-w));
      transform: translateX(-50%);
      z-index: 90;
      display: none;
      grid-template-rows: auto minmax(0, 1fr) auto;
      gap: 12px;
      padding: max(18px, env(safe-area-inset-top)) 14px max(18px, env(safe-area-inset-bottom));
      background: rgba(18, 17, 20, .86);
      backdrop-filter: blur(14px);
    }
    .image-lightbox.open { display: grid; }
    .image-lightbox-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      color: #fff;
      min-height: 44px;
    }
    .image-lightbox-title {
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-size: 15px;
      font-weight: 850;
    }
    .image-lightbox-actions {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      flex: 0 0 auto;
    }
    .image-lightbox-zoom {
      display: none;
      border: 0;
      min-height: 38px;
      border-radius: var(--pill);
      background: rgba(255,255,255,.14);
      color: #fff;
      padding: 0 13px;
      font-size: 13px;
      font-weight: 850;
    }
    .image-lightbox-close {
      border: 0;
      width: 42px;
      height: 42px;
      border-radius: 50%;
      background: rgba(255,255,255,.14);
      color: #fff;
      font-size: 24px;
      display: grid;
      place-items: center;
      flex: 0 0 auto;
    }
    .image-lightbox-stage {
      min-height: 0;
      display: grid;
      place-items: center;
      overflow: hidden;
      border-radius: 24px;
      background: rgba(255,255,255,.96);
    }
    .image-lightbox-stage img {
      width: 100%;
      height: 100%;
      max-width: 100%;
      max-height: 100%;
      object-fit: contain;
      display: block;
      cursor: default;
    }
    .image-lightbox.actual .image-lightbox-stage {
      place-items: start center;
      background:
        linear-gradient(45deg, #f6f7f9 25%, transparent 25%),
        linear-gradient(-45deg, #f6f7f9 25%, transparent 25%),
        linear-gradient(45deg, transparent 75%, #f6f7f9 75%),
        linear-gradient(-45deg, transparent 75%, #f6f7f9 75%),
        #fff;
      background-size: 24px 24px;
      background-position: 0 0, 0 12px, 12px -12px, -12px 0;
    }
    .image-lightbox.actual .image-lightbox-stage img {
      width: 100%;
      height: 100%;
      max-width: 100%;
      max-height: 100%;
      object-fit: contain;
      cursor: default;
    }
    .image-lightbox-tip {
      color: rgba(255,255,255,.72);
      text-align: center;
      font-size: 13px;
      line-height: 1.45;
    }
    .toast { position: fixed; left: 50%; bottom: 96px; transform: translateX(-50%); background: #050505; color: #fff; border-radius: var(--pill); padding: 12px 18px; font-size: 14px; font-weight: 800; z-index: 40; opacity: 0; pointer-events: none; transition: opacity .2s ease; max-width: 360px; text-align: center; }
    .toast.show { opacity: 1; }
    .login-screen {
      position: fixed;
      top: 0;
      bottom: 0;
      left: 50%;
      width: min(100%, var(--screen-w));
      transform: translateX(-50%);
      z-index: 80;
      background:
        radial-gradient(circle at 88% 10%, rgba(255,241,246,.92), transparent 30%),
        linear-gradient(180deg, #fffafa 0%, #f8f2f5 100%);
      color: var(--ink);
      padding: max(20px, env(safe-area-inset-top)) 18px max(22px, env(safe-area-inset-bottom));
      display: none;
      overflow: hidden;
      min-height: 100%;
    }
    .login-screen.active { display: block; }
    body:has(.login-screen.active) { overflow: hidden; }
    .login-screen::before {
      content: "";
      position: absolute;
      inset: 0;
      background:
        linear-gradient(90deg, rgba(255,79,134,.07) 1px, transparent 1px),
        linear-gradient(180deg, rgba(255,79,134,.05) 1px, transparent 1px);
      background-size: 42px 42px;
      mask-image: linear-gradient(180deg, rgba(0,0,0,.42), transparent 70%);
      pointer-events: none;
    }
    .login-screen::after {
      content: "";
      position: absolute;
      width: min(66vw, 280px);
      aspect-ratio: 1;
      right: -24%;
      top: 10%;
      border-radius: 50%;
      background: rgba(255,79,134,.08);
      filter: blur(2px);
      pointer-events: none;
    }
    .login-shell {
      position: relative;
      height: 100%;
      min-height: 0;
      display: grid;
      grid-template-rows: minmax(348px, 1fr) auto;
      align-content: center;
      gap: 24px;
    }
    .login-brand { display: none; }
    .login-copy {
      display: grid;
      justify-items: center;
      gap: 8px;
      color: var(--soft-ink);
      line-height: 1.18;
      max-width: 300px;
      text-wrap: pretty;
    }
    .login-copy-main {
      color: var(--ink);
      font-family: "Songti SC", "STSong", "Noto Serif CJK SC", "PingFang SC", serif;
      font-size: clamp(25px, 6.8vw, 31px);
      font-weight: 600;
      letter-spacing: .06em;
      padding-left: .06em;
    }
    .login-copy-en {
      font-family: Didot, "Bodoni 72", "Times New Roman", serif;
      color: rgba(189, 74, 111, .78);
      font-size: clamp(16px, 4.35vw, 20px);
      font-style: italic;
      font-weight: 400;
      letter-spacing: .015em;
      line-height: 1.05;
    }
    .login-stage {
      align-self: stretch;
      width: 100%;
      min-height: 348px;
      overflow: hidden;
      position: relative;
      display: grid;
      grid-template-rows: auto minmax(236px, 1fr) auto;
      justify-items: center;
      align-content: start;
      padding-top: clamp(18px, 4vh, 42px);
    }
    .login-stage::before {
      content: "";
      position: absolute;
      left: 50%;
      top: 46%;
      width: min(88%, 340px);
      height: 172px;
      border-radius: 999px;
      background:
        radial-gradient(circle at 24% 50%, rgba(255,79,134,.13), transparent 36%),
        radial-gradient(circle at 72% 48%, rgba(238,251,255,.92), transparent 42%);
      filter: blur(10px);
      transform: translate(-50%, -50%);
    }
    .login-logo-lockup {
      position: relative;
      z-index: 1;
      display: grid;
      justify-items: center;
      gap: 11px;
      animation: loginRise .7s cubic-bezier(.2,.8,.2,1) both;
    }
    .login-logo-en {
      color: var(--ink);
      font-size: clamp(50px, 15.4vw, 66px);
      line-height: .78;
      font-weight: 400;
      letter-spacing: -.065em;
      font-family: Didot, "Bodoni 72", "Times New Roman", serif;
      padding-right: .065em;
      text-rendering: geometricPrecision;
    }
    .login-brand-signature {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 9px;
      width: 100%;
      color: rgba(43, 36, 38, .72);
    }
    .login-brand-signature::before,
    .login-brand-signature::after {
      content: "";
      width: 26px;
      height: 1px;
      background: linear-gradient(90deg, transparent, rgba(236, 75, 127, .5));
    }
    .login-brand-signature::after {
      transform: scaleX(-1);
    }
    .login-wordmark-cn {
      color: inherit;
      font-family: "Songti SC", "STSong", "Noto Serif CJK SC", "PingFang SC", serif;
      font-size: 14px;
      line-height: 1;
      font-weight: 500;
      letter-spacing: .22em;
      padding-left: .22em;
      white-space: nowrap;
    }
    .login-closet-cloud {
      position: relative;
      z-index: 1;
      width: min(100%, 352px);
      min-height: 226px;
      margin-top: 34px;
      isolation: isolate;
    }
    .login-gift-box {
      position: absolute;
      left: 50%;
      top: 49%;
      z-index: 0;
      width: min(61vw, 232px);
      max-width: 68%;
      transform: translate(-50%, -50%) translateZ(0);
      opacity: .22;
      filter: saturate(.96) drop-shadow(0 24px 42px rgba(255,79,134,.10));
      mix-blend-mode: normal;
      pointer-events: none;
      user-select: none;
      animation: loginGiftFloat 8.4s .2s ease-in-out infinite;
      will-change: transform, opacity;
    }
    .login-closet-item {
      --x: 0px;
      --y: 0px;
      --r: 0deg;
      --s: 1;
      --d: 0s;
      position: absolute;
      z-index: 2;
      left: 50%;
      top: 50%;
      width: var(--w, 76px);
      aspect-ratio: 1;
      display: grid;
      place-items: center;
      border-radius: 22px;
      background: rgba(255,255,255,.66);
      box-shadow: 0 16px 34px rgba(82,42,61,.10);
      transform: translate3d(-50%, -50%, 0) scale(.72) rotate(0deg);
      opacity: 0;
      animation: loginItemScatter 8.4s var(--d) cubic-bezier(.2,.78,.2,1) infinite;
      will-change: transform, opacity;
    }
    .login-closet-item img {
      display: block;
      max-width: 116%;
      max-height: 116%;
      object-fit: contain;
      filter: drop-shadow(0 12px 18px rgba(54,25,38,.10));
      user-select: none;
      pointer-events: none;
    }
    .login-closet-item:nth-child(1) { --x: -126px; --y: -48px; --r: -9deg; --s: .96; --w: 88px; --d: .04s; }
    .login-closet-item:nth-child(2) { --x: -30px; --y: -56px; --r: 5deg; --s: .98; --w: 82px; --d: .12s; }
    .login-closet-item:nth-child(3) { --x: 78px; --y: -50px; --r: -5deg; --s: 1; --w: 86px; --d: .20s; }
    .login-closet-item:nth-child(4) { --x: 134px; --y: 8px; --r: 7deg; --s: .92; --w: 72px; --d: .28s; }
    .login-closet-item:nth-child(5) { --x: -112px; --y: 30px; --r: 7deg; --s: .92; --w: 82px; --d: .36s; }
    .login-closet-item:nth-child(6) { --x: -24px; --y: 38px; --r: -5deg; --s: 1.04; --w: 96px; --d: .44s; }
    .login-closet-item:nth-child(7) { --x: 72px; --y: 42px; --r: 5deg; --s: .94; --w: 78px; --d: .52s; }
    .login-closet-item:nth-child(8) { --x: -124px; --y: 112px; --r: -5deg; --s: .86; --w: 72px; --d: .60s; }
    .login-closet-item:nth-child(9) { --x: 6px; --y: 118px; --r: 6deg; --s: .9; --w: 78px; --d: .68s; }
    .login-closet-item:nth-child(10) { --x: 126px; --y: 104px; --r: -7deg; --s: .82; --w: 68px; --d: .76s; }
    .login-hero {
      position: relative;
      z-index: 1;
      display: grid;
      justify-items: center;
      text-align: center;
      margin-top: 2px;
      padding: 10px 18px 0;
      animation: loginRise .72s .18s cubic-bezier(.2,.8,.2,1) both;
    }
    .login-form {
      display: grid;
      gap: 12px;
      align-self: start;
      animation: loginRise .72s .28s cubic-bezier(.2,.8,.2,1) both;
    }
    .login-form input {
      width: 100%;
      min-height: 54px;
      border-radius: 18px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,.78);
      padding: 0 16px;
      font-family: "PingFang SC", "Helvetica Neue", sans-serif;
      font-size: 17px;
      font-weight: 600;
      letter-spacing: .015em;
      color: var(--ink);
      outline: none;
      box-shadow: 0 10px 24px rgba(82, 42, 61, .06);
    }
    .login-form input::placeholder { color: var(--muted); }
    .login-form input:focus { border-color: rgba(255,79,134,.62); box-shadow: 0 0 0 4px rgba(255,79,134,.10), 0 10px 24px rgba(82, 42, 61, .06); }
    .login-form .primary-btn {
      position: relative;
      overflow: hidden;
      color: #fff;
      font-family: "PingFang SC", "Helvetica Neue", sans-serif;
      font-size: 17px;
      font-weight: 650;
      letter-spacing: .025em;
      background:
        linear-gradient(135deg, rgba(255,255,255,.26), rgba(255,255,255,.06) 34%, rgba(255,79,134,.34)),
        linear-gradient(180deg, rgba(255,79,134,.92), rgba(232,61,115,.88));
      border: 1px solid rgba(255,255,255,.72);
      box-shadow:
        inset 0 1px 0 rgba(255,255,255,.62),
        inset 0 -1px 0 rgba(173, 31, 83, .18),
        0 18px 34px rgba(255,79,134,.24),
        0 8px 22px rgba(82,42,61,.10);
      backdrop-filter: blur(18px) saturate(1.25);
      -webkit-backdrop-filter: blur(18px) saturate(1.25);
    }
    .login-form .primary-btn::before {
      content: "";
      position: absolute;
      inset: 1px 1px auto;
      height: 48%;
      border-radius: inherit;
      background: linear-gradient(180deg, rgba(255,255,255,.46), rgba(255,255,255,0));
      pointer-events: none;
    }
    .login-form .primary-btn:active { transform: translateY(1px); box-shadow: inset 0 1px 0 rgba(255,255,255,.48), 0 12px 24px rgba(255,79,134,.20); }
    .login-note { min-height: 20px; color: var(--muted); font-size: 13px; line-height: 1.45; }
    .login-note.error { color: var(--error); }
    @keyframes loginRise { from { opacity: 0; transform: translateY(18px); } to { opacity: 1; transform: translateY(0); } }
    @keyframes loginItemScatter {
      0% { opacity: 0; transform: translate3d(-50%, -50%, 0) scale(.72) rotate(0deg); }
      10% { opacity: 0; transform: translate3d(-50%, -50%, 0) scale(.72) rotate(0deg); }
      24% { opacity: 1; transform: translate3d(calc(-50% + var(--x)), calc(-50% + var(--y)), 0) scale(var(--s)) rotate(var(--r)); }
      62% { opacity: 1; transform: translate3d(calc(-50% + var(--x)), calc(-50% + var(--y) - 5px), 0) scale(var(--s)) rotate(calc(var(--r) * .72)); }
      82% { opacity: .94; transform: translate3d(calc(-50% + var(--x)), calc(-50% + var(--y)), 0) scale(var(--s)) rotate(var(--r)); }
      100% { opacity: 0; transform: translate3d(calc(-50% + var(--x)), calc(-50% + var(--y) + 10px), 0) scale(calc(var(--s) * .96)) rotate(var(--r)); }
    }
    @keyframes loginGiftFloat {
      0%, 100% { opacity: .16; transform: translate(-50%, -50%) translateY(2px) scale(.98); }
      28%, 72% { opacity: .24; transform: translate(-50%, -50%) translateY(-4px) scale(1); }
    }
    @media (prefers-reduced-motion: reduce) {
      .login-hero, .login-form, .login-logo-lockup, .login-closet-item, .login-gift-box { animation: none; }
      .login-closet-item { transform: translate3d(calc(-50% + var(--x)), calc(-50% + var(--y)), 0) scale(var(--s)) rotate(var(--r)); }
      .ai-input::before,
      .ai-input-inner::after { animation: none; }
    }
    .profile-line { color: var(--muted); font-size: 13px; line-height: 1.45; margin-top: 4px; }
    .switch-user { border: 0; background: transparent; color: var(--rose-deep); font-weight: 850; padding: 0; }
    @media (min-width: 861px) {
      body { background: #f1f2f4; padding: 24px 0; }
      .app { min-height: calc(100vh - 48px); border-radius: 34px; box-shadow: 0 24px 90px rgba(0,0,0,.10); }
      .login-screen { top: 24px; bottom: 24px; border-radius: 34px; }
      .bottom-nav { bottom: 24px; border-radius: 0 0 34px 34px; }
      .ai-input { bottom: 116px; }
      .ai-session-bar { top: 58px; }
      .sheet { bottom: 24px; border-radius: 28px 28px 34px 34px; }
    }
  </style>
  <link rel="stylesheet" href="/static/selfit-app/app.css?v=20260901-closet-refine-v3" />
</head>
<body>
  <main class="app auth-pending">
    <section id="personaHandoff" class="persona-handoff" hidden aria-labelledby="handoffTitle">
      <img class="handoff-wordmark" src="/static/selfit/assets/selfit-wordmark.svg" width="55" height="20" alt="selfit" />
      <div class="handoff-ornament" aria-hidden="true">
        <img src="/static/selfit/assets/loading-stage-100@2x.png" width="240" height="163" alt="" />
      </div>
      <div class="handoff-copy">
        <small>我们记住你了</small>
        <h1 id="handoffTitle">从认识自己，开始真正适合你的穿搭</h1>
        <p id="handoffPersonaCopy">你的风格人格、推荐色和穿搭偏好已经带入。</p>
      </div>
      <button id="handoffContinue" class="handoff-action" type="button">开始搭配</button>
    </section>
    <section id="page-home" class="page active">
      <div class="top-row">
        <div class="brand">selfit</div>
        <div class="weather"><b id="weatherTemp">24~29°C</b><span id="weatherText">上海市 小雨</span></div>
      </div>
      <section class="home-section home-actions-section">
        <div class="home-action-grid">
          <button id="homeTryAction" class="home-action-card" type="button"><span class="home-action-icon"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 4h8l3 4-2 12H7L5 8l3-4Z"/><path d="M9 4c0 2 1 3 3 3s3-1 3-3"/></svg></span><b>拍一件试试</b><small>上传衣服看上身</small></button>
          <button id="homeExtractAction" class="home-action-card" type="button"><span class="home-action-icon"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9.5 14.5 14.5 9"/><path d="m7 16.8-1 1a3.4 3.4 0 0 1-4.8-4.8l3.6-3.6a3.4 3.4 0 0 1 4.8 0"/><path d="m17 7.2 1-1A3.4 3.4 0 0 1 22.8 11l-3.6 3.6a3.4 3.4 0 0 1-4.8 0"/></svg></span><b>提取单品</b><small>粘贴喜欢的链接</small></button>
          <button id="homeAskAction" class="home-action-card" type="button"><span class="home-action-icon"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 5.5h14v10H9l-4 3v-13Z"/><path d="M9 10.5h6"/></svg></span><b>问问搭配</b><small>结合风格与衣橱</small></button>
        </div>
      </section>
      <section class="home-section today-section">
        <div class="section-head"><div><small>PERSONAL EDIT</small><h2>今天，怎么穿</h2></div></div>
      <div class="today-carousel" aria-label="今日推荐">
        <div id="todayTrack" class="today-track">
          <article class="today-card today-empty" role="button" tabindex="0">
            <div class="today-copy">
              <span class="tag">今日推荐</span>
              <h1>先放入常穿单品</h1>
              <p>有上衣、下装和鞋后，我会按天气给你排一套今日出门搭配。</p>
            </div>
          </article>
        </div>
        <div id="todayDots" class="today-dots"></div>
      </div>
      </section>
      <section class="home-section">
        <div class="section-head"><div><small>FOR YOUR STYLE</small><h2 id="feedTitle">与你同频的穿搭</h2></div><button id="refreshInspiration">换一批</button></div>
        <div id="refreshNote" class="refresh-note"></div>
        <div id="homeGrid" class="masonry"></div>
      </section>
    </section>

    <section id="page-detail" class="page">
      <div class="screen-top">
        <button class="icon-btn" data-back-detail aria-label="返回"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m15 5-7 7 7 7"/></svg></button>
        <div class="screen-title" id="detailTitle">穿搭详情</div>
        <button class="icon-btn" id="detailShare" aria-label="分享"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 16V4"/><path d="m8 8 4-4 4 4"/><path d="M5 12v7h14v-7"/></svg></button>
      </div>
      <div class="detail-hero" id="detailHero"></div>
      <section class="home-section" id="detailItemsSection">
        <div class="section-head"><div><small id="detailItemsEyebrow">OUTFIT PIECES</small><h2 id="detailItemsTitle">穿搭单品</h2></div></div>
        <p id="detailItemsNote" class="detail-items-note" hidden></p>
        <div id="detailItems" class="item-strip"></div>
      </section>
      <div class="bottom-actions">
        <button id="detailEditBtn" class="secondary-btn">调整搭配</button>
        <button id="detailTryBtn" class="primary-btn">生成试穿图</button>
      </div>
    </section>

    <section id="page-tryon" class="page">
      <div class="screen-top">
        <button class="icon-btn" data-open-detail aria-label="返回"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m15 5-7 7 7 7"/></svg></button>
        <div class="screen-title">试穿</div>
        <button class="icon-btn" id="tryonSaveBtn" aria-label="收藏"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 3 2.7 5.5 6.1.9-4.4 4.3 1 6.1-5.4-2.9-5.4 2.9 1-6.1-4.4-4.3 6.1-.9L12 3Z"/></svg></button>
      </div>
      <div class="tryon-hero" id="tryonHero">
        <div class="empty">选择一套搭配后，就能在这里查看试穿效果。</div>
        <div id="generatingLayer" class="generating-layer">
          <div class="tryon-generating-card" role="status" aria-live="polite">
            <img class="tryon-loading-art" id="tryonLoadingArt" src="/static/selfit/assets/loading-stage-25@2x.png" width="480" height="324" alt="" aria-hidden="true" data-stage="25">
            <p class="tryon-generating-kicker">SUIT × LIKE × VIBE</p>
            <div class="tryon-generating-title" id="generatingText">正在让这套穿搭更像你</div>
            <p class="tryon-generating-copy" id="tryonGeneratingCopy">先整理好你的照片和每件单品。</p>
            <div class="tryon-progress-row"><div class="tryon-progress" role="progressbar" aria-label="试穿图生成进度" aria-valuemin="0" aria-valuemax="100" aria-valuenow="8"><span id="tryonProgressBar"></span></div><span class="tryon-progress-value" id="tryonProgressValue">8%</span></div>
            <button id="cancelGenerate" class="tryon-cancel" type="button">取消生成</button>
            <img class="tryon-loading-signature" src="/static/selfit/assets/splash-signature@2x.png" width="200" height="133" alt="" aria-hidden="true">
          </div>
        </div>
      </div>
      <div class="result-actions">
        <button id="tryAnotherBtn" class="secondary-btn">换一套</button>
        <button id="retryTryonBtn" class="primary-btn">重新生成</button>
      </div>
    </section>

    <section id="page-color" class="page">
      <div class="screen-top">
        <button class="icon-btn" data-back-home aria-label="返回"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m15 5-7 7 7 7"/></svg></button>
        <div class="screen-title">色彩测试</div>
        <span style="width:44px;"></span>
      </div>
      <div class="color-card">
        <h2 style="margin:0;">上传一张自然光自拍</h2>
        <p style="color:var(--muted);line-height:1.55;">脸部清楚、少滤镜，结果会更准。</p>
        <label class="upload-zone" for="colorUploadInput" id="colorUploadZone">
          <span><b style="color:var(--ink);font-size:18px;">选择自拍图片</b><br>支持 JPG、PNG、WebP</span>
        </label>
        <input id="colorUploadInput" class="hidden-input" type="file" accept="image/*" />
        <button id="startColorBtn" class="primary-btn" disabled>开始色彩测试</button>
        <div id="colorResult" class="color-result"></div>
      </div>
    </section>

    <section id="page-editor" class="page">
      <div class="screen-top">
        <button class="icon-btn" data-open-detail aria-label="返回"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m15 5-7 7 7 7"/></svg></button>
        <div class="screen-title">调整搭配</div>
        <button id="editorSaveBtn" class="primary-btn" style="min-height:44px;padding:0 18px;">保存</button>
      </div>
      <div id="editorCanvas" class="editor-canvas"></div>
      <button id="smartLayoutBtn" class="smart-layout">一键排版</button>
      <div class="editor-palette">
        <div id="paletteTabs" class="palette-tabs"></div>
        <div id="paletteGrid" class="item-grid"></div>
      </div>
    </section>

    <section id="page-ai" class="page">
      <div class="ai-session-bar">
        <button id="sessionPickerBtn" class="ai-session-toggle" type="button" aria-label="展开会话侧栏">
          <span class="session-toggle-icon icon-open" aria-hidden="true">
            <svg viewBox="0 0 24 24"><rect x="3.5" y="4" width="17" height="16" rx="4"/><path d="M9 4v16"/><path d="m14 9 3 3-3 3"/></svg>
          </span>
          <span class="session-toggle-icon icon-close" aria-hidden="true">
            <svg viewBox="0 0 24 24"><rect x="3.5" y="4" width="17" height="16" rx="4"/><path d="M15 4v16"/><path d="m10 9-3 3 3 3"/></svg>
          </span>
        </button>
      </div>
      <div class="ai-hero">
        <div class="ai-copy">
          <div class="hi" id="aiHi">穿搭灵感</div>
          <h2 id="aiTitle">今天想以什么样子出现？</h2>
          <p id="aiSubtitle">说说场景和心情，我会结合你的风格与衣橱，整理一套更像你的选择。</p>
          <div id="aiChips" class="chips"></div>
        </div>
      </div>
      <div id="aiResult" class="ai-panel" style="display:none;"></div>
      <div class="ai-input">
        <div class="ai-input-inner"><textarea id="aiPromptInput" rows="1" placeholder="向灵感发送消息"></textarea><button class="circle-icon" id="aiSendBtn" aria-label="发送"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 18V6"/><path d="m7.5 10.5 4.5-4.5 4.5 4.5"/></svg></button></div>
      </div>
    </section>

    <section id="page-closet" class="page">
      <div class="closet-top">
        <div class="closet-tabs">
          <button class="closet-tab active" data-closet-mode="items">单品</button>
          <button class="closet-tab" data-closet-mode="outfits">套装</button>
        </div>
        <div class="tool-row"><button id="floatingMatch" class="closet-compose" type="button">开始搭配</button></div>
      </div>
      <div id="categoryRow" class="category-row"></div>
      <div id="closetGrid" class="item-grid" aria-busy="true" aria-label="正在整理衣橱">
        <div class="closet-skeleton" aria-hidden="true"></div>
        <div class="closet-skeleton" aria-hidden="true"></div>
        <div class="closet-skeleton" aria-hidden="true"></div>
        <div class="closet-skeleton" aria-hidden="true"></div>
      </div>
    </section>

    <section id="page-me" class="page">
      <div class="profile-head">
        <div class="avatar" id="profileAvatar" aria-hidden="true"><svg viewBox="0 0 24 24"><circle cx="12" cy="8" r="3.5"/><path d="M5.5 19.5c1.35-3.8 3.5-5.7 6.5-5.7s5.15 1.9 6.5 5.7"/></svg></div>
        <div><div class="profile-name" id="profileName">本地用户</div><div class="profile-line" id="profileLine">Mock 身份</div></div>
        <button class="circle-icon" id="logoutBtn" aria-label="退出登录"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M10 5H5v14h5"/><path d="M13 8l4 4-4 4M17 12H9"/></svg></button>
      </div>
      <button id="profilePersonaLink" class="profile-persona-card" type="button"><span><small id="profilePersonaCode">MUTE · 你的风格人格</small><b id="profilePersonaName">静音时髦</b><em id="profilePersonaTraits">低表达 · 低装饰 · 秩序感</em></span><span aria-hidden="true">→</span></button>
      <div class="profile-grid">
        <button class="profile-cell" id="modelCell" type="button"><small>试穿形象</small><b>我的模特</b><span id="currentModelName">沙漏型</span></button>
        <button class="profile-cell" id="profileColorCell" type="button"><small>个人档案</small><b>适合我的颜色</b><span id="profileColorDots" class="profile-color-dots"></span></button>
      </div>
      <div class="profile-tabs"><button class="profile-tab active" data-profile-view="records">试穿记录</button><button class="profile-tab" data-profile-view="works">我的作品</button><button class="profile-tab" data-profile-view="favorites">我的收藏</button></div>
      <div class="record-head"><span><span id="recordCount">0</span><span id="recordCountLabel">条试穿记录</span></span><button id="recordEditBtn" class="record-edit-btn" type="button">编辑</button></div>
      <div id="recordDeleteBar" class="record-delete-bar"><span id="recordSelectText">选择要删除的记录</span><button id="recordDeleteBtn" class="record-delete-btn" type="button" disabled>删除</button></div>
      <div id="worksSubtabs" class="works-subtabs"><button class="works-subtab active" data-work-view="outfits" type="button">套装</button><button class="works-subtab" data-work-view="items" type="button">单品</button></div>
      <div id="recordGrid" class="record-grid"></div>
    </section>

    <nav class="bottom-nav">
      <button class="nav-btn active" data-tab="home"><span class="nav-icon"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5h16v14H4z"/><path d="m7 15 3-3 2 2 3-4 2 2"/></svg></span><span class="nav-label">推荐</span></button>
      <button class="nav-btn" data-tab="ai"><span class="nav-icon"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 5.5h14v10H9l-4 3v-13Z"/><path d="M9 10.5h6"/></svg></span><span class="nav-label">问搭配</span></button>
      <button id="mainPlus" class="plus-btn" aria-label="添加"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg></button>
      <button class="nav-btn" data-tab="closet"><span class="nav-icon"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 4h10l2 4v12H5V8l2-4z"/><path d="M5 8h14"/><path d="M9 12h6"/></svg></span><span class="nav-label">衣橱</span></button>
      <button class="nav-btn" data-tab="me"><span class="nav-icon"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="8" r="4"/><path d="M4.5 20c1.5-4 4-6 7.5-6s6 2 7.5 6"/></svg></span><span class="nav-label">我的</span></button>
    </nav>
  </main>

  <aside id="uploadSheet" class="sheet">
    <div class="sheet-title"><b>添加衣服</b><button class="close" data-close="uploadSheet" aria-label="关闭">×</button></div>
    <input id="wearUploadInput" class="hidden-input" type="file" accept="image/*" multiple />
    <div class="action-grid">
      <button id="uploadGarmentBtn" class="action-card"><b>从相册选择</b><span>支持单品图或整套穿搭图</span></button>
      <button id="cameraBtn" class="action-card"><b>现在拍一张</b><span>背景简单，提取会更准确</span></button>
      <div class="link-import"><label for="wearLinkInput">从喜欢的内容提取单品</label><div class="link-line"><input id="wearLinkInput" type="url" placeholder="粘贴小红书或网页链接" /><button id="wearLinkBtn" class="black-btn">提取</button></div></div>
    </div>
    <p id="uploadStatus" style="color:#777;line-height:1.5;">添加后会识别其中的衣服，并放入你的衣橱。</p>
    <button id="retryImportBtn" class="secondary-btn" type="button" hidden>重试这次提取</button>
  </aside>
  <aside id="importReviewSheet" class="sheet">
    <div class="sheet-title"><b id="importReviewTitle">确认识别结果</b><button class="close" data-close="importReviewSheet" aria-label="关闭">×</button></div>
    <p id="importReviewCopy" class="import-review-copy">看看是否每件衣物都完整，分类不对可以直接修改。</p>
    <div id="importReviewGrid" class="import-review-grid"></div>
    <button id="importReviewDone" class="import-review-done" type="button">完成入柜</button>
  </aside>
  <div id="sessionBackdrop" class="session-backdrop"></div>
  <aside id="sessionSheet" class="session-sidebar">
    <button id="sessionSheetNew" class="session-new-btn" type="button"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 6.8C5 5.25 6.25 4 7.8 4h8.4C17.75 4 19 5.25 19 6.8v6.9c0 1.55-1.25 2.8-2.8 2.8H11l-4.15 3.1c-.65.48-1.57.02-1.57-.79V16.3A2.8 2.8 0 0 1 3.5 13.7V6.8"/><path d="M12 8.2v4.8"/><path d="M9.6 10.6h4.8"/></svg><span>新建会话</span></button>
    <div class="session-section-title">历史会话</div>
    <div id="sessionList" class="session-list"></div>
  </aside>
  <div id="sessionActionPopover" class="session-action-popover">
    <button id="sessionRenameBtn" type="button">编辑名称</button>
    <button id="sessionDeleteMenuBtn" class="danger" type="button">删除会话</button>
  </div>
  <div id="sessionDeleteConfirm" class="session-confirm">
    <div class="session-confirm-card">
      <b>删除这个会话？</b>
      <p>删除后这个历史会话会从列表中移除。</p>
      <div class="session-confirm-actions">
        <button id="sessionCancelDeleteBtn" class="cancel" type="button">取消</button>
        <button id="sessionConfirmDeleteBtn" class="danger" type="button">删除</button>
      </div>
    </div>
  </div>
  <div id="logoutConfirm" class="session-confirm" role="dialog" aria-modal="true" aria-labelledby="logoutConfirmTitle">
    <div class="session-confirm-card">
      <b id="logoutConfirmTitle">退出登录？</b>
      <p>退出后需要重新登录，才能查看你的衣橱和试穿记录。</p>
      <div class="session-confirm-actions">
        <button id="logoutCancelBtn" class="cancel" type="button">取消</button>
        <button id="logoutConfirmBtn" class="primary" type="button">退出登录</button>
      </div>
    </div>
  </div>

  <aside id="builderSheet" class="sheet">
    <div class="sheet-title"><b>选择搭配单品</b><button class="close" data-close="builderSheet">×</button></div>
    <p class="builder-help">选择 2-4 件单品，保存成套装，或直接用上衣先试穿。</p>
    <div id="builderList" class="builder-list"></div>
    <div class="builder-actions"><button id="saveOutfitBtn" class="secondary-btn">保存套装</button><button id="tryOutfitBtn" class="match-btn">生成试穿图</button></div>
  </aside>
  <aside id="modelSheet" class="sheet model-sheet" data-mode="preset">
    <div class="sheet-title"><span></span><button class="close" data-close="modelSheet">×</button></div>
    <div class="model-tabs">
      <button class="model-tab active" type="button" data-model-mode="preset">预设模特</button>
      <button class="model-tab" type="button" data-model-mode="photo">我的照片</button>
    </div>
    <div id="modelCarousel" class="model-carousel"></div>
    <div id="myPhotoPanel" class="my-photo-panel">
      <label class="self-upload-zone" for="selfModelInput" id="selfUploadZone">
        <span><b>还没有可用的全身照</b>完成风格测试后会自动带入，也可以点击这里重新上传。</span>
      </label>
      <input id="selfModelInput" class="hidden-input" type="file" accept="image/*" />
      <button id="confirmSelfModel" class="model-confirm" type="button" disabled>确认</button>
    </div>
    <button id="confirmModelBtn" class="model-confirm" type="button">确认</button>
  </aside>
  <div id="imageLightbox" class="image-lightbox" aria-hidden="true">
    <div class="image-lightbox-head">
      <div id="imageLightboxTitle" class="image-lightbox-title">查看图片</div>
      <div class="image-lightbox-actions">
        <button id="imageLightboxZoom" class="image-lightbox-zoom" type="button">适应屏幕</button>
        <button id="imageLightboxClose" class="image-lightbox-close" type="button" aria-label="关闭">×</button>
      </div>
    </div>
    <div class="image-lightbox-stage">
      <img id="imageLightboxImg" alt="放大预览" />
    </div>
    <div id="imageLightboxTip" class="image-lightbox-tip">已按图片比例完整展示，点空白处或按 Esc 关闭</div>
  </div>
  <div id="toast" class="toast"></div>

  <script src="/static/selfit/personality-report-templates.js"></script>
  <script>
    const state = {
      tab: "home",
      closetMode: "items",
      category: "all",
      items: [],
      outfits: [],
      selectedItems: new Set(),
      currentOutfit: null,
      tryonResult: null,
      colorFile: null,
      todayIndex: 0,
      editorItems: [],
      activeEditorItemId: "",
      paletteCategory: "all",
      aiBrief: "",
      aiResult: null,
      aiMessages: [],
      aiStreamingText: null,
      aiStreamingDone: true,
      aiStreamTimer: null,
      aiToolsExpanded: false,
      aiToolTimer: null,
      aiAbortController: null,
      tryonAbortController: null,
      tryonJobId: "",
      aiVisibleToolCount: 0,
      aiLoadingSteps: [],
      aiSessions: [],
      currentSessionId: "",
      sessionActionId: "",
      sessionPendingDeleteId: "",
      sessionPressTimer: null,
      records: [],
      recordEditing: false,
      selectedRecordIds: new Set(),
      selectedWorkIds: new Set(),
      profileView: "records",
      profileWorkView: "outfits",
      homeOutfitLimit: 6,
      currentModelId: "female_medium_1",
      pendingModelId: "female_medium_1",
      selfModelUrl: "",
      profileKey: "student",
      profile: null,
      personalityCatalog: null,
      stylePersona: null,
      currentItem: null,
      detailMode: "outfit",
      detailReturnTab: "home",
      user: null,
      isAuthenticated: false,
      importReviewItems: [],
      importDraftOutfit: null,
      importJobId: "",
      recommendationOffset: 0,
      closetItemLimit: 20,
      closetOutfitLimit: 12,
      dataReady: false,
      stylistSessionsLoaded: false,
      stylistSessionsLoading: false
    };
    const personaProfiles = {
      student: {
        key: "student",
        phone: "13800000001",
        name: "小夏同学",
        avatar: "夏",
        role: "娱乐型学生",
        summary: "学生党",
        weather: "广州 26~32°C",
        weatherNote: "多云 转 晴",
        widgetTitle: "继续了解自己",
        feedTitle: "与你同频的穿搭",
        aiHi: "小夏的穿搭灵感",
        aiTitle: "今天想以什么样子出现？",
        aiSubtitle: "我会结合你的风格，优先考虑显白、拍照效果和预算友好。",
        emptyTitle: "先上传几件常穿单品",
        emptyCopy: "我会帮你凑生日局、约会和校园出片的搭配。",
        chips: ["生日派对怎么穿", "社团拍照 OOTD", "周末约会显白搭", "小红书同款平替", "预算 300 内", "演唱会出片"],
        feed: [
          ["生日局", "甜酷一点但别太用力", "短上衣、亮色小包和好走的鞋，拍照会更有重点。"],
          ["校园拍照", "显白又轻松", "优先浅色上衣和干净下装，画面会更清爽。"],
          ["周末约会", "温柔但有记忆点", "保留一个颜色亮点，其他单品放轻。"],
        ],
        preference: ["拍照好看", "显白", "预算友好", "轻松有趣"],
      },
      professional: {
        key: "professional",
        phone: "13900000001",
        name: "林予安",
        avatar: "予",
        role: "通勤职场人",
        summary: "通勤职场人",
        weather: "上海 24~29°C",
        weatherNote: "小雨",
        widgetTitle: "继续了解自己",
        feedTitle: "与你同频的穿搭",
        aiHi: "予安的穿搭灵感",
        aiTitle: "今天想以什么样子出现？",
        aiSubtitle: "我会结合你的风格，优先考虑得体、低出错和一衣多穿。",
        emptyTitle: "先放入通勤常穿单品",
        emptyCopy: "有上衣、下装和鞋后，我会按天气给你排一套今日出门搭配。",
        chips: ["明天面试怎么穿", "小雨通勤不狼狈", "客户会面要稳", "周五上班接聚餐", "一衣多穿", "胶囊衣橱"],
        feed: [
          ["晨会通勤", "低出错的利落组合", "上衣和下装边界清楚，开会、通勤都稳。"],
          ["小雨天气", "少露肤、鞋包齐", "鞋子稳一点，包里能放伞，早晚不用临时补单品。"],
          ["下班聚餐", "正式里留一点松弛", "保留通勤骨架，加一个柔和亮点就能切换场景。"],
        ],
        preference: ["利落", "低出错", "会议得体", "天气适配"],
      }
    };
    const labels = { top:"上衣", bottom:"长裤", skirt:"半身裙", dress:"连体装", shoes:"鞋", bag:"包", accessory:"配饰" };
    const categoryOrder = ["all", "top", "bottom", "skirt", "dress", "shoes", "bag", "accessory"];
    const aiScenes = ["旅行计划", "OOTD服饰拆解", "参加重要面试", "参加婚礼", "户外运动", "朋友的生日派对", "二人世界"];
    const modelOptions = [
      { id: "female_slim_1", src: "/tryon-models/female_slim_1.webp?v=female-v4-20260705", name: "纤细型", tags: ["纤细型", "直筒"] },
      { id: "female_medium_1", src: "/tryon-models/female_medium_1.webp?v=female-v4-20260705", name: "沙漏型", tags: ["沙漏型", "匀称"] },
      { id: "female_plus_1", src: "/tryon-models/female_plus_1.webp?v=female-v4-20260705", name: "丰满型", tags: ["丰满型", "柔和"] },
      { id: "male_slim_1", src: "/tryon-models/male_slim_1.webp?v=fullbody-20260705", name: "男纤细", tags: ["男生", "纤细"] },
      { id: "male_medium_1", src: "/tryon-models/male_medium_1.webp?v=fullbody-20260705", name: "男匀称", tags: ["男生", "匀称"] },
      { id: "male_plus_1", src: "/tryon-models/male_plus_1.webp?v=fullbody-20260705", name: "男宽松", tags: ["男生", "宽松"] },
    ];

    function $(selector) { return document.querySelector(selector); }
    function $all(selector) { return [...document.querySelectorAll(selector)]; }
    function toast(text) {
      const el = $("#toast");
      el.textContent = text;
      el.classList.add("show");
      window.setTimeout(() => el.classList.remove("show"), 2200);
    }
    function openImagePreview(src, title = "查看图片") {
      if (!src) return;
      const box = $("#imageLightbox");
      $("#imageLightboxImg").src = assetURL(src);
      $("#imageLightboxTitle").textContent = title || "查看图片";
      setImagePreviewZoom(false);
      box.classList.add("open");
      box.setAttribute("aria-hidden", "false");
    }
    function closeImagePreview() {
      const box = $("#imageLightbox");
      box.classList.remove("open");
      box.setAttribute("aria-hidden", "true");
      setImagePreviewZoom(false);
      $("#imageLightboxImg").removeAttribute("src");
    }
    function setImagePreviewZoom(actual) {
      const box = $("#imageLightbox");
      const stage = box?.querySelector(".image-lightbox-stage");
      box?.classList.remove("actual");
      const zoomBtn = $("#imageLightboxZoom");
      if (zoomBtn) zoomBtn.textContent = "适应屏幕";
      const tip = $("#imageLightboxTip");
      if (tip) tip.textContent = "已按图片比例完整展示，点空白处或按 Esc 关闭";
      if (stage) {
        stage.scrollLeft = 0;
        stage.scrollTop = 0;
      }
    }
    function toggleImagePreviewZoom() {
      setImagePreviewZoom(false);
    }
    function bindImagePreviews(root = document) {
      root.querySelectorAll("[data-preview-image]").forEach(node => {
        if (node.dataset.previewBound === "1") return;
        node.dataset.previewBound = "1";
        node.addEventListener("click", event => {
          const src = node.dataset.previewImage || "";
          if (!src || state.recordEditing) return;
          event.preventDefault();
          event.stopPropagation();
          openImagePreview(src, node.dataset.previewTitle || node.querySelector("img")?.alt || "查看图片");
        });
      });
    }
    function withVersion(path, entity) {
      if (!path) return "";
      const version = entity?.updated_at || entity?.created_at || "";
      const versioned = version ? `${path}${path.includes("?") ? "&" : "?"}v=${encodeURIComponent(version)}` : path;
      return assetURL(versioned);
    }
    function publicImg(item) { return withVersion(item?.assets?.preview_path || item?.assets?.cutout_path || "", item); }
    function publicCutoutImg(item) { return withVersion(item?.assets?.cutout_path || item?.assets?.preview_path || "", item); }
    function currentModel() {
      if (state.currentModelId === "self" && state.selfModelUrl) return { id: "self", src: state.selfModelUrl, name: "我的照片", tags: ["我的照片"] };
      return modelOptions.find(model => model.id === state.currentModelId) || modelOptions[0];
    }
    function renderSelfModelPhoto() {
      const zone = $("#selfUploadZone");
      const confirm = $("#confirmSelfModel");
      if (!zone || !confirm) return;
      zone.classList.toggle("has-photo", Boolean(state.selfModelUrl));
      if (state.selfModelUrl) {
        zone.innerHTML = `<img src="${state.selfModelUrl}" alt="我的全身照"><span class="self-photo-source">来自风格测试 · 点击更换</span>`;
        confirm.disabled = false;
        return;
      }
      delete zone.dataset.previewImage;
      delete zone.dataset.previewTitle;
      zone.innerHTML = `<span><b>还没有可用的全身照</b>完成风格测试后会自动带入，也可以点击这里重新上传。</span>`;
      confirm.disabled = true;
    }
    async function loadOnboardingBodyPhoto() {
      try {
        const response = await fetch("/api/v1/selfit/me/photos/body", { headers: await authHeaders() });
        if (response.status === 204) {
          renderSelfModelPhoto();
          return false;
        }
        if (!response.ok) throw new Error("全身照暂时无法读取。");
        if (state.selfModelUrl?.startsWith("blob:")) URL.revokeObjectURL(state.selfModelUrl);
        state.selfModelUrl = URL.createObjectURL(await response.blob());
        renderSelfModelPhoto();
        return true;
      } catch (error) {
        renderSelfModelPhoto();
        return false;
      }
    }
    function isColorBlockItem(item) {
      const filename = `${item?.source?.filename || ""} ${item?.source?.source_path || ""}`.toLowerCase();
      const tags = (item?.attributes?.style_tags || []).join(" ").toLowerCase();
      const colors = (item?.attributes?.colors || []).join(" ").toLowerCase();
      const noRealMask = !item?.assets?.mask_path;
      return filename.includes("acceptance_top") || tags.includes("acceptance") || (noRealMask && item?.category === "top" && colors.includes("red") && colors.includes("mixed"));
    }
    function visibleItems(items = state.items) { return (items || []).filter(item => !isColorBlockItem(item)); }
    function isUserCreatedItem(item) {
      const id = String(item?.item_id || "");
      const source = item?.source || {};
      const sourceType = String(source.type || "");
      return ["upload", "xhs_link", "web_link", "reprocess"].includes(sourceType) || (!!source.upload && !id.startsWith("w_"));
    }
    function isUserCreatedOutfit(outfit) {
      const id = String(outfit?.outfit_id || "");
      return !!id && !id.startsWith("w_outfit_");
    }
    function cleanOutfit(outfit) {
      const items = visibleItems(outfit?.items || []);
      return { ...(outfit || {}), items, item_ids: items.map(item => item.item_id) };
    }
    function visibleOutfits(outfits = state.outfits) {
      return dedupeSimilarOutfits((outfits || []).map(cleanOutfit).filter(outfit => outfit.items.length > 0));
    }
    function dedupeSimilarOutfits(outfits) {
      const best = new Map();
      (outfits || []).forEach(outfit => {
        const signature = outfitSimilaritySignature(outfit) || `exact:${(outfit.item_ids || []).slice().sort().join(":")}`;
        const current = best.get(signature);
        if (!current || outfitCompletenessScore(outfit) > outfitCompletenessScore(current)) best.set(signature, outfit);
      });
      return Array.from(best.values());
    }
    function outfitSimilaritySignature(outfit) {
      const slots = {};
      (outfit.items || []).forEach(item => {
        const slot = itemSlot(item);
        if (slot === "dress" && !slots.dress) slots.dress = item.item_id;
        else if (slot === "top" && !slots.top) slots.top = item.item_id;
        else if ((slot === "bottom" || slot === "skirt") && !slots.lower) slots.lower = item.item_id;
      });
      if (slots.dress) return `dress:${slots.dress}`;
      if (slots.top && slots.lower) return `main:${slots.top}:${slots.lower}`;
      if (slots.top) return `top:${slots.top}`;
      if (slots.lower) return `lower:${slots.lower}`;
      return "";
    }
    function outfitCompletenessScore(outfit) {
      const slots = (outfit.items || []).map(itemSlot);
      const hasMain = slots.some(slot => ["dress", "top", "bottom", "skirt"].includes(slot)) ? 1 : 0;
      const hasShoes = slots.includes("shoes") ? 1 : 0;
      const hasBag = slots.includes("bag") ? 1 : 0;
      const displayCount = (outfit.display_item_ids || outfit.item_ids || outfit.items || []).length;
      const favoriteCount = Math.min(Number(outfit.favorite_count || 0), 99);
      const updated = Date.parse(outfit.updated_at || outfit.created_at || "") || 0;
      return hasMain * 1e13 + hasShoes * 1e12 + hasBag * 1e11 + (displayCount + favoriteCount) * 1e8 + updated;
    }
    function openSheet(id) { $("#" + id).classList.add("open"); }
    function closeSheet(id) {
      $("#" + id).classList.remove("open");
      if (id === "sessionSheet") {
        $("#sessionPickerBtn")?.classList.remove("active");
        $("#sessionBackdrop")?.classList.remove("open");
        closeSessionActionMenu();
      }
    }
    function toggleSessionSidebar() {
      const sheet = $("#sessionSheet");
      const open = !sheet.classList.contains("open");
      renderSessionList();
      sheet.classList.toggle("open", open);
      $("#sessionBackdrop")?.classList.toggle("open", open);
      $("#sessionPickerBtn")?.classList.toggle("active", open);
    }
    function closeSessionActionMenu() {
      state.sessionActionId = "";
      if (state.sessionPressTimer) window.clearTimeout(state.sessionPressTimer);
      state.sessionPressTimer = null;
      $("#sessionActionPopover")?.classList.remove("open");
    }
    function openModelSheet() {
      state.pendingModelId = state.currentModelId === "self" ? modelOptions[0].id : state.currentModelId;
      $("#modelSheet").dataset.mode = "preset";
      $all("[data-model-mode]").forEach(btn => btn.classList.toggle("active", btn.dataset.modelMode === "preset"));
      renderModelPicker();
      openSheet("modelSheet");
      window.setTimeout(() => {
        const active = $("#modelCarousel .model-option.active");
        if (active) {
          $("#modelCarousel").scrollLeft = active.offsetLeft - ($("#modelCarousel").clientWidth - active.clientWidth) / 2;
          syncPendingModelFromScroll();
        }
      }, 60);
    }
    function markPendingModel(id) {
      if (!id || state.pendingModelId === id) return;
      state.pendingModelId = id;
      $all("#modelCarousel .model-option").forEach(option => {
        const active = option.dataset.modelId === id;
        option.classList.toggle("active", active);
        option.setAttribute("aria-pressed", active ? "true" : "false");
      });
    }
    function syncPendingModelFromScroll() {
      const carousel = $("#modelCarousel");
      if (!carousel) return;
      const options = $all("#modelCarousel .model-option");
      if (!options.length) return;
      const center = carousel.scrollLeft + carousel.clientWidth / 2;
      let closest = options[0];
      let closestDistance = Infinity;
      options.forEach(option => {
        const optionCenter = option.offsetLeft + option.offsetWidth / 2;
        const distance = Math.abs(optionCenter - center);
        if (distance < closestDistance) {
          closestDistance = distance;
          closest = option;
        }
      });
      markPendingModel(closest.dataset.modelId);
    }
    function renderModelPicker() {
      $("#modelCarousel").innerHTML = modelOptions.map(model => `
        <button class="model-option ${model.id === state.pendingModelId ? "active" : ""}" type="button" data-model-id="${model.id}" aria-pressed="${model.id === state.pendingModelId ? "true" : "false"}">
          <div class="model-figure"><img src="${model.src}" alt="${model.name}"></div>
          <div class="model-tags">${model.tags.map(tag => `<span>${tag}</span>`).join("")}</div>
        </button>
      `).join("");
      $all("[data-model-id]").forEach(btn => btn.addEventListener("click", () => {
        const carousel = $("#modelCarousel");
        if (carousel) carousel.scrollTo({ left: btn.offsetLeft - (carousel.clientWidth - btn.clientWidth) / 2, behavior: "smooth" });
        markPendingModel(btn.dataset.modelId);
      }));
      const carousel = $("#modelCarousel");
      if (carousel) {
        let scrollFrame = 0;
        carousel.addEventListener("scroll", () => {
          if (scrollFrame) return;
          scrollFrame = window.requestAnimationFrame(() => {
            scrollFrame = 0;
            syncPendingModelFromScroll();
          });
        }, { passive: true });
      }
    }
    function setModelMode(mode) {
      $("#modelSheet").dataset.mode = mode;
      $all("[data-model-mode]").forEach(btn => btn.classList.toggle("active", btn.dataset.modelMode === mode));
    }
    async function saveCurrentModelPreference() {
      try {
        await fetchJSON("/closet/preferences", {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ current_model_id: state.currentModelId })
        });
      } catch (error) {
        toast("模特选择暂时没有保存成功。");
      }
    }
    function confirmPresetModel() {
      state.currentModelId = state.pendingModelId || modelOptions[0].id;
      updateCurrentModelUI();
      closeSheet("modelSheet");
      saveCurrentModelPreference();
      toast("已切换模特。");
    }
    function updateCurrentModelUI() {
      const model = currentModel();
      const label = model.id === "self" ? "我的照片" : model.name;
      const node = $("#currentModelName");
      if (node) node.textContent = label;
      if (state.currentOutfit) renderDetail();
    }
    function setPage(pageId) {
      $all(".page").forEach(page => page.classList.toggle("active", page.id === pageId));
      $(".bottom-nav").classList.toggle("hidden", !["page-home", "page-ai", "page-closet", "page-me"].includes(pageId));
      $(".ai-input").style.display = pageId === "page-ai" ? "block" : "none";
      $("#floatingMatch").style.display = pageId === "page-closet" ? "block" : "none";
      window.scrollTo(0, 0);
    }
    function syncTabURL(tab, historyMode = "replace") {
      if (historyMode === "none") return;
      const next = new URL(window.location.href);
      if (next.searchParams.get("tab") === tab) return;
      next.searchParams.set("tab", tab);
      const method = historyMode === "push" ? "pushState" : "replaceState";
      window.history[method]({}, "", `${next.pathname}${next.search}${next.hash}`);
    }
    function setTab(tab, { historyMode = "replace" } = {}) {
      state.tab = tab;
      if (tab !== "ai") closeSheet("sessionSheet");
      setPage(`page-${tab}`);
      $all(".nav-btn").forEach(btn => btn.classList.toggle("active", btn.dataset.tab === tab));
      syncTabURL(tab, historyMode);
      if (state.dataReady) renderTab(tab);
    }
    const personaStoreKey = "selfit_demo_mock_persona";
    const stylePersonaStoreKey = "selfit.app.persona.v1";
    const sharedAuthStoreKey = "selfit.auth.session.v1";
    const stylistSessionStoreKey = "selfit_demo_current_stylist_session";
    let authTokenPromise = null;
    const memoryStore = {};
    function readStore(key) {
      try {
        return window.localStorage?.getItem(key) || memoryStore[key] || "";
      } catch (error) {
        return memoryStore[key] || "";
      }
    }
    function writeStore(key, value) {
      memoryStore[key] = value;
      try {
        window.localStorage?.setItem(key, value);
      } catch (error) {}
    }
    function removeStore(key) {
      delete memoryStore[key];
      try {
        window.localStorage?.removeItem(key);
      } catch (error) {}
    }
    function currentProfile() {
      return personaProfiles[state.profileKey] || personaProfiles.student;
    }
    function requestedStylePersonaType() {
      const params = new URLSearchParams(window.location.search);
      const requested = String(params.get("persona") || "").toLowerCase();
      if (requested && state.personalityCatalog?.types?.[requested]) return requested;
      const stored = String(readStore(stylePersonaStoreKey) || "").toLowerCase();
      if (stored && state.personalityCatalog?.types?.[stored]) return stored;
      return "";
    }
    function loadStylePersona() {
      state.personalityCatalog = window.__SELFIT_PERSONALITY_TEMPLATES__ || { types: {} };
      const typeId = requestedStylePersonaType();
      state.stylePersona = typeId ? state.personalityCatalog.types?.[typeId] || null : null;
      if (state.stylePersona?.typeId) writeStore(stylePersonaStoreKey, state.stylePersona.typeId);
      renderStylePersona();
    }
    function stylePersonaOutfits() {
      return state.stylePersona?.recommendations?.outfits?.items || [];
    }
    function stylePersonaColors() {
      return (state.stylePersona?.colors?.items || []).slice(0, 5);
    }
    function personaRecommendationPayload() {
      const persona = state.stylePersona;
      if (!persona) return {};
      return {
        typeId: persona.typeId,
        metadata: persona.metadata || {},
        keywords: persona.keywords || [],
        summary: persona.summary || "",
        colors: persona.colors || {},
        recommendations: persona.recommendations || {},
      };
    }
    async function loadRankedOutfits(offset = 0) {
      if (!state.outfits.length) return;
      const data = await fetchJSON("/closet/recommendations/outfits", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ persona: personaRecommendationPayload(), offset, limit: Math.max(12, state.outfits.length), rotate_by: 4 })
      });
      state.outfits = data.outfits || state.outfits;
      state.recommendationOffset = Number(data.next_offset || 0);
    }
    function renderColorDots(node, colors = stylePersonaColors()) {
      if (!node) return;
      node.innerHTML = colors.map(color => `<i style="--tone:${escapeHTML(color.value || "#ddd")}" title="${escapeHTML(color.name || "推荐色")}"></i>`).join("");
    }
    function renderStylePersona() {
      const persona = state.stylePersona;
      const profile = currentProfile();
      if (!persona) {
        const heroNode = $("#personaHero");
        if (heroNode) {
          heroNode.src = "/static/selfit/assets/loading-stage-100@2x.png";
          heroNode.alt = "完成风格测试，认识自己的风格";
        }
        $("#personaCard")?.classList.add("is-empty");
        if ($(".persona-card-label")) $(".persona-card-label").textContent = "个人风格档案";
        if ($("#personaCode")) $("#personaCode").textContent = "SUIT × LIKE × VIBE";
        if ($("#personaCardTitle")) $("#personaCardTitle").textContent = "先认识自己";
        if ($("#personaSummary")) $("#personaSummary").textContent = "完成风格测试后，你的推荐色、穿搭原则和同频灵感会在这里继续陪你做选择。";
        if ($("#personaTraits")) $("#personaTraits").innerHTML = "";
        if ($("#openPersonaReport")) {
          $("#openPersonaReport").firstChild.textContent = "开始风格测试 ";
          $("#openPersonaReport").dataset.reportUrl = "/selfit";
        }
        if ($("#profilePersonaCode")) $("#profilePersonaCode").textContent = "SELFIT · 个人风格档案";
        if ($("#profilePersonaName")) $("#profilePersonaName").textContent = "认识自己的风格";
        if ($("#profilePersonaTraits")) $("#profilePersonaTraits").textContent = "适合的 × 喜欢的 × 想表达的";
        $("#profilePersonaLink")?.setAttribute("data-report-url", "/selfit");
        renderColorDots($("#personaColors"), []);
        renderColorDots($("#profileColorDots"), []);
        return;
      }
      $("#personaCard")?.classList.remove("is-empty");
      if ($(".persona-card-label")) $(".persona-card-label").textContent = "你的风格人格";
      const name = persona.metadata?.name || "我的风格";
      const code = persona.metadata?.code || String(persona.typeId || "").toUpperCase();
      const traits = (persona.keywords || []).filter(Boolean);
      const hero = persona.hero?.image?.src || "";
      const heroNode = $("#personaHero");
      if (heroNode) {
        heroNode.src = hero;
        heroNode.alt = persona.hero?.image?.alt || `${name}风格人格`;
      }
      if ($("#personaCode")) $("#personaCode").textContent = code;
      if ($("#personaCardTitle")) $("#personaCardTitle").textContent = name;
      if ($("#personaSummary")) $("#personaSummary").textContent = String(persona.summary || "你的风格结果会在这里继续陪你做选择。").replace(/\\n+/g, " ");
      if ($("#personaTraits")) $("#personaTraits").innerHTML = traits.map(item => `<span>${escapeHTML(item)}</span>`).join("");
      if ($("#profilePersonaCode")) $("#profilePersonaCode").textContent = `${code} · 你的风格人格`;
      if ($("#profilePersonaName")) $("#profilePersonaName").textContent = name;
      if ($("#profilePersonaTraits")) $("#profilePersonaTraits").textContent = traits.join(" · ");
      if ($("#handoffPersonaCopy")) $("#handoffPersonaCopy").textContent = `“${name}”的推荐色、穿搭原则和灵感已经带入。`;
      renderColorDots($("#personaColors"));
      renderColorDots($("#profileColorDots"));
      const reportUrl = `/selfit?preview=report&type=${encodeURIComponent(persona.typeId || "mute")}`;
      if ($("#openPersonaReport")) {
        $("#openPersonaReport").firstChild.textContent = "查看完整风格报告 ";
        $("#openPersonaReport").setAttribute("data-report-url", `${reportUrl}&from=app-home`);
      }
      $("#profilePersonaLink")?.setAttribute("data-report-url", `${reportUrl}&from=app-profile`);
    }
    function applyProfile(key = state.profileKey) {
      state.profileKey = personaProfiles[key] ? key : "student";
      state.profile = currentProfile();
      writeStore(personaStoreKey, state.profileKey);
      $all("[data-persona]").forEach(btn => btn.classList.toggle("active", btn.dataset.persona === state.profileKey));
      $("#weatherTemp").textContent = state.profile.weather;
      $("#weatherText").textContent = state.profile.weatherNote;
      $("#feedTitle").textContent = state.profile.feedTitle;
      $("#aiHi").textContent = state.profile.aiHi;
      $("#aiTitle").textContent = state.profile.aiTitle;
      $("#aiSubtitle").textContent = state.profile.aiSubtitle;
      $("#aiPromptInput").placeholder = state.profile.chips[0] || "向灵感发送消息";
      renderStylePersona();
      renderProfile();
    }
    function sharedAuthSession() {
      // localStorage 持久化登录态（主流程登录后未主动退出则一直可用），
      // 兼容读取旧版 sessionStorage 会话。
      try {
        let shared = JSON.parse(window.localStorage?.getItem(sharedAuthStoreKey) || "null");
        if (!shared?.accessToken) {
          shared = JSON.parse(window.sessionStorage?.getItem(sharedAuthStoreKey) || "null");
          if (shared?.accessToken) {
            try { window.localStorage?.setItem(sharedAuthStoreKey, JSON.stringify(shared)); } catch (error) {}
          }
        }
        if (!shared?.accessToken) return null;
        if (shared.expiresAt && Date.parse(shared.expiresAt) <= Date.now()) return null;
        return shared;
      } catch (error) {
        return null;
      }
    }
    function clearSharedAuth() {
      try { window.localStorage?.removeItem(sharedAuthStoreKey); } catch (error) {}
      try { window.sessionStorage?.removeItem(sharedAuthStoreKey); } catch (error) {}
      removeStore("selfit_demo_mock_access_token");
    }
    function unifiedLoginUrl() {
      return "/selfit?entry=login";
    }
    function openUnifiedLogin() {
      window.location.replace(unifiedLoginUrl());
    }
    async function currentAuthToken() {
      const existing = sharedAuthSession()?.accessToken || "";
      if (existing) {
        const me = await fetch("/auth/me", { headers: { Authorization: `Bearer ${existing}` } }).catch(() => null);
        if (me?.ok) {
          const data = await me.json().catch(() => ({}));
          state.user = data.user || null;
          state.isAuthenticated = true;
          return existing;
        }
        clearSharedAuth();
      }
      throw new Error("请先登录");
    }
    async function demoAuthToken() {
      if (authTokenPromise) return authTokenPromise;
      authTokenPromise = currentAuthToken().catch(error => {
        authTokenPromise = null;
        openUnifiedLogin();
        throw error;
      });
      return authTokenPromise;
    }
    async function initializeAuth() {
      applyProfile(readStore(personaStoreKey) || "professional");
      const existing = sharedAuthSession()?.accessToken || "";
      if (!existing) {
        openUnifiedLogin();
        return;
      }
      try {
        await demoAuthToken();
        if (!state.stylePersona?.typeId) {
          window.location.replace("/selfit");
          return;
        }
        await loadData();
      } catch (error) {
        openUnifiedLogin();
      }
    }
    function logoutSelfitUser() {
      closeLogoutConfirm();
      clearSharedAuth();
      removeStore(stylistSessionStoreKey);
      state.user = null;
      state.isAuthenticated = false;
      authTokenPromise = null;
      openUnifiedLogin();
    }
    function openLogoutConfirm() {
      $("#logoutConfirm").classList.add("open");
    }
    function closeLogoutConfirm() {
      $("#logoutConfirm").classList.remove("open");
    }
    function assetURL(path) {
      if (!path || !path.startsWith("/user-assets/")) return path || "";
      if (path.includes("access_token=")) return path;
      const token = sharedAuthSession()?.accessToken || "";
      return token ? `${path}${path.includes("?") ? "&" : "?"}access_token=${encodeURIComponent(token)}` : path;
    }
    async function imageObjectURL(path) {
      if (!path || !path.startsWith("/user-assets/")) return path || "";
      const response = await fetch(path, { headers: await authHeaders() });
      if (!response.ok) throw new Error("图片暂时无法加载");
      return URL.createObjectURL(await response.blob());
    }
    async function loadImageInto(selector, path) {
      const img = $(selector);
      if (!img || !path) return;
      try {
        img.src = await imageObjectURL(path);
        img.classList.remove("image-loading");
      } catch (error) {
        const holder = document.createElement("div");
        holder.className = "empty";
        holder.textContent = "试穿图已生成，但图片暂时无法显示。";
        img.replaceWith(holder);
      }
    }
    async function authHeaders(options = {}) {
      const headers = new Headers(options.headers || {});
      if (!headers.has("Authorization")) headers.set("Authorization", `Bearer ${await demoAuthToken()}`);
      return headers;
    }
    async function fetchJSON(url, options = {}) {
      const requestOptions = { ...options, headers: await authHeaders(options) };
      let res = await fetch(url, requestOptions);
      if (res.status === 401) {
        clearSharedAuth();
        authTokenPromise = null;
        openUnifiedLogin();
        throw new Error("登录已过期，请重新登录");
      }
      const raw = await res.text();
      let data = {};
      if (raw.trim()) {
        try {
          data = JSON.parse(raw);
        } catch (error) {
          data = { error: { message: "暂时灵感耗尽，正在努力充能～" }, raw_text: raw.slice(0, 200) };
        }
      }
      if (!res.ok) {
        const error = new Error(data.detail || data.error?.message || "请求失败");
        error.status = res.status;
        error.code = data.error?.code || "";
        error.retryAfterSeconds = Math.max(0, Number(
          res.headers.get("Retry-After") || data.error?.details?.retryAfterSeconds || data.retry_after_seconds || 0
        ));
        throw error;
      }
      return data;
    }
    function waitWithSignal(delayMs, signal) {
      return new Promise((resolve, reject) => {
        if (signal?.aborted) return reject(new DOMException("已取消", "AbortError"));
        const finish = () => {
          signal?.removeEventListener("abort", abort);
          resolve();
        };
        const timer = window.setTimeout(finish, delayMs);
        const abort = () => {
          window.clearTimeout(timer);
          signal?.removeEventListener("abort", abort);
          reject(new DOMException("已取消", "AbortError"));
        };
        signal?.addEventListener("abort", abort, { once: true });
      });
    }
    function normalizeSessionMessages(messages = []) {
      return (messages || []).filter(message => ["user", "assistant"].includes(message.role) && message.content).map(message => ({
        role: message.role,
        content: message.content,
        ...(message.metadata && Array.isArray(message.metadata.tool_steps) ? { tool_steps: message.metadata.tool_steps } : {}),
        ...(message.metadata && Array.isArray(message.metadata.xhs_notes) ? { xhs_notes: message.metadata.xhs_notes } : {}),
        ...(message.metadata && Array.isArray(message.metadata.evidence_sources) ? { evidence_sources: message.metadata.evidence_sources } : {}),
        ...(message.metadata && Array.isArray(message.metadata.rationale) ? { rationale: message.metadata.rationale } : {})
      }));
    }
    function renderSessionList() {
      const list = $("#sessionList");
      if (!list) return;
      const sessions = state.aiSessions || [];
      list.innerHTML = sessions.length ? sessions.map(session => `
        <article class="session-card ${session.session_id === state.currentSessionId ? "active" : ""} ${session.metadata?.unread_completion ? "unread" : ""}" data-session-open="${session.session_id}">
          <span class="session-unread-dot" aria-hidden="true"></span>
          <div class="session-main">
            <div class="session-title">${escapeHTML(session.title || "新的穿搭灵感")}</div>
            <div class="session-preview">${escapeHTML(session.last_message_preview || "还没有消息，开始聊聊穿搭思路。")}</div>
            <div class="session-meta">${Number(session.message_count || 0)} 条消息</div>
          </div>
        </article>
      `).join("") : `<div class="session-empty">还没有灵感会话。</div>`;
      $all("[data-session-open]").forEach(card => card.addEventListener("click", event => {
        if ($("#sessionActionPopover")?.classList.contains("open")) return;
        selectStylistSession(card.dataset.sessionOpen);
      }));
      $all("[data-session-open]").forEach(card => {
        const openMenu = event => {
          event.preventDefault();
          event.stopPropagation();
          showSessionActionMenu(card.dataset.sessionOpen, event);
        };
        card.addEventListener("contextmenu", openMenu);
        card.addEventListener("pointerdown", event => {
          if (event.pointerType === "mouse") return;
          if (state.sessionPressTimer) window.clearTimeout(state.sessionPressTimer);
          state.sessionPressTimer = window.setTimeout(() => openMenu(event), 520);
        });
        ["pointerup", "pointercancel", "pointerleave"].forEach(type => card.addEventListener(type, () => {
          if (state.sessionPressTimer) window.clearTimeout(state.sessionPressTimer);
          state.sessionPressTimer = null;
        }));
      });
    }
    function showSessionActionMenu(sessionId, event) {
      if (!sessionId) return;
      state.sessionActionId = sessionId;
      const popover = $("#sessionActionPopover");
      const x = Math.min(Math.max(14, event?.clientX || 24), window.innerWidth - 192);
      const y = Math.min(Math.max(72, event?.clientY || 130), window.innerHeight - 128);
      popover.style.left = `${x}px`;
      popover.style.top = `${y}px`;
      popover.classList.add("open");
    }
    function updateSessionTitle() {
      const current = state.aiSessions.find(session => session.session_id === state.currentSessionId);
      const title = current?.title || "新的穿搭灵感";
      const node = $("#currentSessionTitle");
      if (node) node.textContent = title;
      const picker = $("#sessionPickerBtn");
      if (picker) picker.setAttribute("aria-label", `展开会话侧栏，当前会话：${title}`);
      renderSessionList();
    }
    async function loadStylistSessions() {
      const data = await fetchJSON("/stylist/sessions");
      state.aiSessions = data.sessions || [];
      if (!state.aiSessions.length) {
        const created = await fetchJSON("/stylist/sessions", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ metadata: { source: "selfit_inspiration", profile_key: state.profileKey } })
        });
        state.aiSessions = [created];
      }
      const savedSessionId = readStore(stylistSessionStoreKey);
      const nextId = state.currentSessionId && state.aiSessions.some(session => session.session_id === state.currentSessionId)
        ? state.currentSessionId
        : savedSessionId && state.aiSessions.some(session => session.session_id === savedSessionId)
          ? savedSessionId
          : state.aiSessions[0]?.session_id;
      if (nextId) await selectStylistSession(nextId, { silent: true, clearUnread: false });
      updateSessionTitle();
    }
    async function ensureStylistSessions() {
      if (state.stylistSessionsLoaded || state.stylistSessionsLoading) return;
      state.stylistSessionsLoading = true;
      try {
        await loadStylistSessions();
        state.stylistSessionsLoaded = true;
      } catch (error) {
        updateSessionTitle();
      } finally {
        state.stylistSessionsLoading = false;
      }
    }
    async function selectStylistSession(sessionId, options = {}) {
      if (!sessionId) return;
      const session = await fetchJSON(`/stylist/sessions/${encodeURIComponent(sessionId)}`);
      state.currentSessionId = session.session_id;
      writeStore(stylistSessionStoreKey, session.session_id);
      if (!options.skipPreferenceSave) {
        fetchJSON("/closet/preferences", {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ current_stylist_session_id: session.session_id })
        }).catch(() => {});
      }
      const summary = state.aiSessions.find(item => item.session_id === session.session_id);
      if (summary?.metadata?.unread_completion && options.clearUnread !== false) {
        summary.metadata.unread_completion = false;
        fetchJSON(`/stylist/sessions/${encodeURIComponent(session.session_id)}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ metadata: { unread_completion: false } })
        }).catch(() => {});
      }
      state.aiMessages = normalizeSessionMessages(session.messages || []);
      state.aiResult = null;
      state.aiBrief = "";
      state.aiStreamingText = null;
      state.aiStreamingDone = true;
      state.aiToolsExpanded = false;
      closeSheet("sessionSheet");
      updateSessionTitle();
      renderAIResult();
      if (!options.silent) toast("已切换会话。");
    }
    async function createNewStylistSession() {
      const created = await fetchJSON("/stylist/sessions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ metadata: { source: "selfit_inspiration", profile_key: state.profileKey } })
      });
      state.aiSessions = [created, ...state.aiSessions.filter(session => session.session_id !== created.session_id)];
      await selectStylistSession(created.session_id, { silent: true });
      setTab("ai");
      toast("已新建会话。");
    }
    async function archiveStylistSession(sessionId) {
      if (!sessionId) return;
      await fetchJSON(`/stylist/sessions/${encodeURIComponent(sessionId)}`, { method: "DELETE" });
      state.aiSessions = state.aiSessions.filter(session => session.session_id !== sessionId);
      if (!state.aiSessions.length) {
        removeStore(stylistSessionStoreKey);
        await createNewStylistSession();
      } else if (state.currentSessionId === sessionId) {
        await selectStylistSession(state.aiSessions[0].session_id, { silent: true });
      } else {
        renderSessionList();
      }
      toast("已归档会话。");
    }
    async function renameSelectedSession() {
      const sessionId = state.sessionActionId;
      if (!sessionId) return;
      const current = state.aiSessions.find(session => session.session_id === sessionId);
      closeSessionActionMenu();
      const nextTitle = window.prompt("修改会话名称", current?.title || "新的穿搭灵感");
      const title = String(nextTitle || "").trim();
      if (!title) return;
      const updated = await fetchJSON(`/stylist/sessions/${encodeURIComponent(sessionId)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title })
      });
      const index = state.aiSessions.findIndex(session => session.session_id === sessionId);
      if (index >= 0) state.aiSessions[index] = updated;
      updateSessionTitle();
      toast("已更新会话名称。");
    }
    function openSessionDeleteConfirm() {
      if (!state.sessionActionId) return;
      state.sessionPendingDeleteId = state.sessionActionId;
      closeSessionActionMenu();
      $("#sessionDeleteConfirm").classList.add("open");
    }
    function closeSessionDeleteConfirm() {
      state.sessionPendingDeleteId = "";
      $("#sessionDeleteConfirm").classList.remove("open");
    }
    async function confirmDeleteSelectedSession() {
      const sessionId = state.sessionPendingDeleteId;
      if (!sessionId) return;
      closeSessionDeleteConfirm();
      await archiveStylistSession(sessionId);
    }
    async function loadData() {
      const [itemsData, outfitsData, recordsData, preferencesData] = await Promise.all([
        fetchJSON("/closet/items"),
        fetchJSON("/closet/outfits"),
        fetchJSON("/closet/tryon-records"),
        fetchJSON("/closet/preferences")
      ]);
      state.items = itemsData.items || [];
      state.outfits = outfitsData.outfits || [];
      state.records = recordsData.records || [];
      const savedModelId = preferencesData.current_model_id;
      if (savedModelId && (savedModelId === "self" || modelOptions.some(model => model.id === savedModelId))) {
        state.currentModelId = savedModelId === "self" && !state.selfModelUrl ? modelOptions[0].id : savedModelId;
      }
      if (preferencesData.current_stylist_session_id) {
        state.currentSessionId = preferencesData.current_stylist_session_id;
      }
      updateCurrentModelUI();
      state.dataReady = true;
      renderTab(state.tab);
      $(".app")?.classList.remove("auth-pending");
      maybeShowPersonaHandoff();
      loadDeferredData();
    }
    async function loadDeferredData() {
      const ranked = loadRankedOutfits(0).then(() => {
        if (state.tab === "home") renderHome();
      }).catch(() => {});
      const bodyPhoto = loadOnboardingBodyPhoto().catch(() => false);
      if (state.tab === "ai") ensureStylistSessions();
      await Promise.allSettled([ranked, bodyPhoto]);
    }
    function maybeShowPersonaHandoff() {
      const params = new URLSearchParams(window.location.search);
      if (params.get("from") !== "report") return;
      const handoff = $("#personaHandoff");
      handoff.hidden = false;
      handoff.setAttribute("aria-hidden", "false");
    }
    function closePersonaHandoff() {
      const handoff = $("#personaHandoff");
      handoff.hidden = true;
      handoff.setAttribute("aria-hidden", "true");
      const next = new URL(window.location.href);
      next.searchParams.delete("from");
      next.searchParams.delete("persona");
      window.history.replaceState({}, "", `${next.pathname}${next.search}${next.hash}`);
      setTab("home");
    }
    function renderAll() {
      renderHome();
      renderAI();
      renderCategories();
      renderCloset();
      renderProfile();
      renderDetail();
      renderEditor();
    }
    function renderTab(tab = state.tab) {
      if (tab === "home") renderHome();
      if (tab === "ai") {
        renderAI();
        ensureStylistSessions();
      }
      if (tab === "closet") {
        renderCategories();
        renderCloset();
      }
      if (tab === "me") renderProfile();
    }
    function renderHome() {
      applyProfile(state.profileKey);
      const visibleCards = visibleOutfits();
      const cards = visibleCards.length ? visibleCards : buildSyntheticOutfits();
      renderTodayRecommendation(cards);
      renderHomeWidgets(cards);
      if (cards.length) {
        $("#homeGrid").innerHTML = cards.slice(0, state.homeOutfitLimit).map(card => outfitCardHTML(card)).join("");
        bindOutfitActions();
      } else {
        $("#homeGrid").innerHTML = personaFeedHTML();
        $all("[data-persona-question]").forEach(btn => btn.addEventListener("click", () => {
          setTab("ai");
          $("#aiPromptInput").value = btn.dataset.personaQuestion;
          askStylist();
        }));
      }
    }
    function renderHomeWidgets(cards) {
      const inspiration = $(".widget-card.ai");
      const upload = $(".widget-card.upload");
      const firstCover = (cards || []).map(card => withVersion(card.layout_snapshot_path || card.cover_path || card.cover || "", card)).find(Boolean);
      const firstItem = visibleItems()[0];
      const firstItemImage = firstItem ? publicCutoutImg(firstItem) : "";
      if (inspiration && firstCover) inspiration.style.setProperty("--widget-image", `url("${firstCover}")`);
      if (upload && firstItemImage) upload.style.setProperty("--widget-image", `url("${firstItemImage}")`);
    }
    function maybeLoadMoreHomeOutfits() {
      if (state.tab !== "home") return;
      const total = (visibleOutfits().length ? visibleOutfits() : buildSyntheticOutfits()).length;
      if (state.homeOutfitLimit >= total) return;
      const nearBottom = window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 260;
      if (!nearBottom) return;
      state.homeOutfitLimit = Math.min(total, state.homeOutfitLimit + 6);
      renderHome();
    }
    function renderTodayRecommendation(cards) {
      const track = $("#todayTrack");
      const dots = $("#todayDots");
      const carousel = (cards || []).filter(card => card?.outfit_id).slice(0, 4);
      if (!carousel.length) {
        state.todayIndex = 0;
        const persona = state.stylePersona;
        const inspiration = stylePersonaOutfits()[0] || null;
        const image = inspiration?.image?.src || "";
        const personaName = persona?.metadata?.name || "你的风格";
        track.innerHTML = `<article class="today-card" role="button" tabindex="0" data-today-empty><div class="today-copy"><span class="tag">根据你的${escapeHTML(personaName)}</span><h1>${escapeHTML(inspiration?.name || "先从一个清晰重点开始")}</h1><p>${escapeHTML(persona?.recommendations?.outfits?.summary || currentProfile().emptyCopy)}</p></div><div class="today-art">${image ? `<img class="today-cover" src="${image}" alt="${escapeHTML(inspiration?.image?.alt || inspiration?.name || "风格灵感")}">` : ""}</div></article>`;
        dots.innerHTML = "";
        $("[data-today-empty]").addEventListener("click", () => {
          setTab("ai");
          $("#aiPromptInput").value = `按我的${personaName}风格，用衣橱里的单品搭一套今天能穿的`;
          updateAISendButton();
        });
        return;
      }
      state.todayIndex = Math.max(0, Math.min(state.todayIndex, carousel.length - 1));
      track.innerHTML = carousel.map((card, index) => todayCardHTML(card, index)).join("");
      dots.innerHTML = todayDots(carousel);
      window.requestAnimationFrame(() => {
        track.scrollLeft = state.todayIndex * Math.max(1, track.clientWidth);
      });
      bindTodayRail(track, carousel);
      $all("[data-today-outfit]").forEach(cardNode => cardNode.addEventListener("click", () => openOutfitDetail(cardNode.dataset.todayOutfit)));
      $all("[data-today-index]").forEach(btn => btn.addEventListener("click", event => {
        event.preventDefault();
        event.stopPropagation();
        state.todayIndex = Number(btn.dataset.todayIndex) || 0;
        renderTodayRecommendation(carousel);
      }));
    }
    function bindTodayRail(track, carousel) {
      if (carousel.length < 2) return;
      let scrollTimer = 0;
      track.onscroll = () => {
        window.clearTimeout(scrollTimer);
        scrollTimer = window.setTimeout(() => {
          const index = Math.round(track.scrollLeft / Math.max(1, track.clientWidth));
          state.todayIndex = Math.max(0, Math.min(index, carousel.length - 1));
          $all("[data-today-index]").forEach(btn => btn.classList.toggle("active", Number(btn.dataset.todayIndex) === state.todayIndex));
        }, 80);
      };
    }
    function todayCardHTML(card, index) {
      const copy = todayRecommendationCopy(card, index);
      const cover = withVersion(card.layout_snapshot_path || card.cover_path || card.cover || "", card);
      return `<article class="today-card" role="button" tabindex="0" data-today-outfit="${card.outfit_id}" aria-label="${escapeHTML(card.title || "今日推荐")}">
        <div class="today-copy"><span class="tag">${copy.tag}</span><h1>${escapeHTML(copy.title)}</h1><p>${copy.reason}</p></div>
        <div class="today-art">${cover ? `<img class="today-cover" src="${cover}" alt="${escapeHTML(card.title || copy.title)}">` : todayOutfitArt(card)}</div>
      </article>`;
    }
    function todayRecommendationCopy(card, index) {
      const items = visibleItems(card.items || []);
      const slots = new Set(items.map(itemSlot));
      const rawTitle = String(card.title || "").trim();
      const genericTitle = !rawTitle || ["自由搭配", "灵感搭配", "我的搭配", "AI 推荐搭配", "推荐套装"].includes(rawTitle);
      const hasDress = slots.has("dress");
      const hasTop = slots.has("top");
      const hasBottom = slots.has("bottom") || slots.has("skirt");
      const hasShoes = slots.has("shoes");
      const hasBag = slots.has("bag");
      const complete = (hasDress || (hasTop && hasBottom)) && hasShoes;
      const variants = [
        {
          tag: "今日推荐",
          title: complete ? "小雨通勤套装" : "轻便出门组合",
          reason: complete ? "小雨天少露肤、鞋包齐，早晚通勤不用再临时补单品。" : "天气偏湿，先用轻便主服装打底，适合补一双好走的鞋。",
        },
        {
          tag: "换个思路",
          title: hasDress ? "一件成套" : "上短下长",
          reason: hasDress ? "连衣装省搭配时间，配鞋就能出门，适合赶时间的早上。" : "上衣和下装比例清楚，视觉更利落，适合办公室和咖啡约见。",
        },
        {
          tag: "显气色",
          title: hasBag ? "带包更完整" : "清爽不闷",
          reason: hasBag ? "包放在侧边能提完整度，也方便雨天带伞和随身物。" : "颜色和层次都轻，24~29°C 穿起来不厚重。",
        },
        {
          tag: "周末可穿",
          title: hasShoes ? "好走一整天" : "午后轻装",
          reason: hasShoes ? "鞋子已经配好，适合通勤后直接去逛街或见朋友。" : "主搭配简单干净，午后出门不需要复杂配饰。",
        },
        {
          tag: "少想一步",
          title: hasDress ? "省心连衣装" : "三件就够",
          reason: hasDress ? "一件定主风格，鞋包只做收尾，出门前不用反复试。" : "主服装、鞋或包已经成组，今天直接按这套开始。",
        },
        {
          tag: "雨天友好",
          title: hasShoes ? "稳妥鞋装" : "不拖沓",
          reason: hasShoes ? "鞋子收在底部，整体重心稳，小雨天也不显狼狈。" : "版型和层次都简洁，潮湿天气看起来更干净。",
        },
        {
          tag: "拍照好看",
          title: hasBag ? "侧边有重点" : "比例清楚",
          reason: hasBag ? "包在侧边形成视觉落点，平铺和上身都更完整。" : "上下装边界清楚，镜头里更容易显精神。",
        },
        {
          tag: "轻正式",
          title: hasTop && hasBottom ? "上班不费力" : "干净见人",
          reason: hasTop && hasBottom ? "上衣和下装都利落，适合开会、通勤和临时见人。" : "颜色不吵、层次不多，见人场景更稳。",
        },
        {
          tag: "约会轻松",
          title: hasBag || hasShoes ? "温柔有收口" : "柔和一点",
          reason: hasBag || hasShoes ? "鞋包把风格收住，整体更完整，适合晚一点的安排。" : "主服装不复杂，留一点轻松感，约会和散步都能穿。",
        },
        {
          tag: "显高一点",
          title: hasTop && hasBottom ? "竖向更清楚" : "重心上移",
          reason: hasTop && hasBottom ? "上下装边界清楚，视觉线条更顺，拍照也更利落。" : "把视觉重点放在上半身，小个子也更容易穿出精神。",
        },
      ];
      const picked = variants[index % variants.length];
      const recommendationReason = card.recommendation?.reasons?.[0];
      return {
        tag: card.recommendation ? "与你同频" : picked.tag,
        title: genericTitle ? picked.title : rawTitle,
        reason: recommendationReason || picked.reason,
      };
    }
    function todayOutfitArt(card) {
      const items = visibleItems(card.items || []);
      const visible = items.slice(0, 5);
      if (!visible.length) return "";
      return visible.map((item, index) => {
        const slot = itemSlot(item);
        const className = ["top", "bottom", "skirt", "dress", "shoes", "bag", "accessory"].includes(slot) ? `slot-${slot}` : "slot-generic";
        return `<img class="${className}" style="z-index:${2 + index};" src="${publicCutoutImg(item)}" alt="${escapeHTML(item.category_label || "单品")}">`;
      }).join("");
    }
    function todayDots(cards) {
      if (!cards.length) return "";
      return `<div class="today-dots">${cards.map((_, index) => `<button class="today-dot ${index === state.todayIndex % cards.length ? "active" : ""}" data-today-index="${index}" aria-label="第 ${index + 1} 套"></button>`).join("")}</div>`;
    }
    function outfitCardHTML(card) {
      const cover = withVersion(card.layout_snapshot_path || card.cover_path || card.cover || "", card);
      const img = cover ? `<img src="${cover}" alt="${escapeHTML(card.title || "搭配")}" loading="lazy" decoding="async">` : `<div class="empty" style="min-height:100%;border-radius:0;">这套搭配正在生成封面</div>`;
      const heart = card.favorite ? "♥" : "♡";
      return `<article class="outfit-card" data-open-outfit="${card.outfit_id || ""}">
        <div class="outfit-canvas">${img}</div>
        <div class="outfit-meta"><button class="favorite-btn ${card.favorite ? "active" : ""}" data-favorite-outfit="${card.outfit_id || ""}" aria-label="${card.favorite ? "取消收藏" : "收藏"}搭配" aria-pressed="${Boolean(card.favorite)}">${heart}</button><button class="try-btn" data-home-outfit="${card.outfit_id || ""}">试穿</button></div>
      </article>`;
    }
    function personaFeedHTML() {
      const profile = currentProfile();
      const personaName = state.stylePersona?.metadata?.name || "我的风格";
      const outfitImages = stylePersonaOutfits();
      if (outfitImages.length) return outfitImages.slice(0, 4).map((item, index) => {
        const fallback = profile.feed[index % profile.feed.length] || ["穿搭灵感", item.name, ""];
        const title = item.name || fallback[1];
        const image = item.image?.src || "";
        return `<article class="outfit-card persona-inspiration-card">
          <div class="outfit-canvas"><img src="${image}" alt="${escapeHTML(item.image?.alt || title)}"><div class="persona-inspiration-copy"><small>${escapeHTML(personaName)}</small><b>${escapeHTML(title)}</b></div></div>
          <div class="outfit-meta"><button class="try-btn" data-persona-question="${escapeHTML(`参考${title}，用我的衣橱搭一套`)}">用我的衣橱搭</button></div>
        </article>`;
      }).join("");
      return profile.feed.map(([tag, title, reason]) => `<article class="outfit-card"><div class="outfit-canvas"><div class="persona-inspiration-copy"><small>${escapeHTML(tag)}</small><b>${escapeHTML(title)}</b></div></div><div class="outfit-meta"><button class="try-btn" data-persona-question="${escapeHTML(title)}">问问搭配</button></div></article>`).join("");
    }
    function escapeHTML(value) {
      return String(value ?? "").replace(/[&<>"']/g, char => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[char]));
    }
    function generatingLayerHTML() {
      return `<div class="tryon-generating-card" role="status" aria-live="polite">
        <img class="tryon-loading-art" id="tryonLoadingArt" src="/static/selfit/assets/loading-stage-25@2x.png" width="480" height="324" alt="" aria-hidden="true" data-stage="25">
        <p class="tryon-generating-kicker">SUIT × LIKE × VIBE</p>
        <div class="tryon-generating-title" id="generatingText">正在让这套穿搭更像你</div>
        <p class="tryon-generating-copy" id="tryonGeneratingCopy">先整理好你的照片和每件单品。</p>
        <div class="tryon-progress-row"><div class="tryon-progress" role="progressbar" aria-label="试穿图生成进度" aria-valuemin="0" aria-valuemax="100" aria-valuenow="8"><span id="tryonProgressBar"></span></div><span class="tryon-progress-value" id="tryonProgressValue">8%</span></div>
        <button id="cancelGenerate" class="tryon-cancel" type="button">取消生成</button>
        <img class="tryon-loading-signature" src="/static/selfit/assets/splash-signature@2x.png" width="200" height="133" alt="" aria-hidden="true">
      </div>`;
    }
    const tryonLoadingStages = {
      queued: { stage: 25, title: "正在让这套穿搭更像你", copy: "先整理好你的照片和每件单品。" },
      preparing: { stage: 25, title: "先把每件单品放到合适的位置", copy: "正在识别穿搭中可以自然替换的部分。" },
      generating: { stage: 50, title: "正在让这套穿搭更像你", copy: "会保留你的脸、身形和照片氛围，再逐件替换可见单品。" },
      finishing: { stage: 75, title: "再看一眼整体比例", copy: "正在检查服装边缘、身形和上身效果。" },
    };
    [25, 50, 75].forEach(stage => {
      const image = new Image();
      image.src = `/static/selfit/assets/loading-stage-${stage}@2x.png`;
    });
    function updateTryonGeneratingState(job = {}) {
      const progress = Math.max(1, Math.min(96, Number(job.progress || 8)));
      const phase = job.phase === "preparing"
        ? "preparing"
        : progress >= 72
          ? "finishing"
          : job.phase === "generating" || progress >= 30
            ? "generating"
            : "queued";
      const presentation = tryonLoadingStages[phase];
      const title = $("#generatingText");
      const copy = $("#tryonGeneratingCopy");
      const bar = $("#tryonProgressBar");
      const value = $("#tryonProgressValue");
      const progressbar = bar?.closest('[role="progressbar"]');
      const art = $("#tryonLoadingArt");
      if (title) title.textContent = presentation.title;
      if (copy) copy.textContent = presentation.copy;
      if (bar) bar.style.width = `${progress}%`;
      if (value) value.textContent = `${progress}%`;
      if (progressbar) progressbar.setAttribute("aria-valuenow", String(progress));
      if (art && art.dataset.stage !== String(presentation.stage)) {
        art.classList.add("is-changing");
        window.setTimeout(() => {
          art.src = `/static/selfit/assets/loading-stage-${presentation.stage}@2x.png`;
          art.dataset.stage = String(presentation.stage);
          requestAnimationFrame(() => requestAnimationFrame(() => art.classList.remove("is-changing")));
        }, window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 150);
      }
    }
    function shouldUseXHSSkill(message = "") {
      const text = String(message || "");
      if (/不用小红书|不要小红书|别用小红书|不看小红书|只看衣橱|只用衣橱|只用我的衣橱|不要外部参考|不用外部参考/i.test(text)) return false;
      if (/小红书|红书|xhs|rednote|笔记|同款|平替|趋势|流行|博主|种草|参考|灵感/i.test(text)) return true;
      const outfitTopic = /穿|搭|上班|通勤|面试|客户|会议|约会|聚餐|看展|旅行|上课|校园|生日|派对|演唱会|音乐节|婚礼|宴会|运动|户外|居家|鞋|包|帽|裙|裤|衬衫|针织|西装|外套|配饰|显瘦|显白|出片|拍照|ootd|氛围感|风格|颜色|身材|体型|雨|冷|热|降温|升温|天气|防水|防滑/i.test(text);
      return outfitTopic;
    }
    function shouldUseCapsuleSkill(message = "") {
      return /胶囊|capsule|一衣多穿|少买|基础款|通勤衣橱|衣橱规划|万能衣橱/i.test(String(message || ""));
    }
    function inferAIIntent(message = "") {
      const text = String(message || "");
      return {
        useXHS: shouldUseXHSSkill(text),
        useCapsule: shouldUseCapsuleSkill(text),
        isFollowup: /继续|刚才|上一|前面|这个|那|如果|还是|换成|调整|不要|不想|下雨|显瘦/i.test(text) && state.aiMessages.some(item => item.role === "assistant"),
        hasWeather: /雨|冷|热|降温|升温|天气|防水|防滑/i.test(text),
        hasOccasion: /上班|通勤|面试|客户|会议|约会|聚餐|看展|旅行|上课|校园|生日|派对|演唱会/i.test(text),
      };
    }
    function recentUserQueries(nextMessage = "") {
      const queries = state.aiMessages.filter(item => item.role === "user").map(item => String(item.content || "").trim()).filter(Boolean);
      const current = String(nextMessage || "").trim();
      if (current && queries[queries.length - 1] !== current) queries.push(current);
      return queries.slice(-5);
    }
    function buildAIConversationContext(message = "") {
      const queries = recentUserQueries(message);
      const lastAssistant = [...state.aiMessages].reverse().find(item => item.role === "assistant");
      const lastSources = [
        ...(Array.isArray(lastAssistant?.xhs_notes) ? lastAssistant.xhs_notes.slice(0, 4).map(note => ({ title: note.title || "", source: note.source_label || "小红书" })) : []),
        ...(Array.isArray(lastAssistant?.evidence_sources) ? lastAssistant.evidence_sources.slice(0, 2) : []),
      ];
      return {
        current_query: String(message || "").trim(),
        recent_user_queries: queries,
        previous_query: queries.length >= 2 ? queries[queries.length - 2] : "",
        previous_assistant_summary: String(lastAssistant?.content || "").replace(/\\s+/g, " ").slice(0, 220),
        previous_xhs_sources: lastSources.filter(item => item && (item.title || item.label)).slice(0, 6),
        conversation_turn_count: state.aiMessages.length,
        must_answer_current_query: true,
      };
    }
    function defaultAIToolSteps(message = "") {
      const intent = inferAIIntent(message);
      const steps = [
        {
          id: "understand",
          title: intent.isFollowup ? "接上文理解问题" : "理解这次问题",
          status: "running",
          detail: intent.isFollowup ? "先保留前面的场景，再聚焦你这句新约束" : "识别场景、预算、天气和风格偏好",
        },
      ];
      if (intent.useCapsule) {
        steps.push({ id: "capsule", title: "整理胶囊衣橱思路", status: "pending", detail: "用少量核心单品覆盖更多场景" });
      }
      if (intent.useXHS) {
        steps.push({ id: "xhs", title: "找小红书参考", status: "pending", detail: "只在你需要笔记/同款/趋势时检索" });
        steps.push({ id: "filter", title: "过滤不相关笔记", status: "pending", detail: "留下和本轮场景真正贴近的卡片" });
      }
      steps.push({ id: "style", title: "组织成可执行建议", status: "pending", detail: "把信息收成衣服、鞋包、颜色和取舍" });
      return steps;
    }
    function visibleLoadingToolSteps() {
      const source = state.aiLoadingSteps.length ? state.aiLoadingSteps : defaultAIToolSteps(state.aiBrief);
      const visibleCount = Math.max(1, Math.min(state.aiVisibleToolCount || 1, source.length));
      return source.slice(0, visibleCount).map((step, index) => {
        const id = String(step.id || "");
        const isExternalEvidence = ["xhs", "filter", "read"].includes(id);
        const status = index < visibleCount - 1 && !isExternalEvidence ? "done" : index === visibleCount - 1 ? "running" : "pending";
        return { ...step, status };
      });
    }
    function stopAIToolProgress() {
      if (state.aiToolTimer) window.clearInterval(state.aiToolTimer);
      state.aiToolTimer = null;
    }
    function startAIToolProgress() {
      stopAIToolProgress();
      state.aiVisibleToolCount = 1;
      state.aiToolTimer = window.setInterval(() => {
        if (!state.aiResult || state.aiResult.status !== "loading") return stopAIToolProgress();
        const total = state.aiLoadingSteps.length || defaultAIToolSteps(state.aiBrief).length;
        if (state.aiVisibleToolCount < total) {
          state.aiVisibleToolCount += 1;
          renderAIResult();
        }
      }, 900);
    }
    function renderAIToolchain(steps = []) {
      const list = (steps.length ? steps : defaultAIToolSteps(state.aiBrief)).slice(0, 6);
      return `<div class="ai-toolchain" aria-label="灵感处理进度">${list.map((step, index) => {
        const status = ["done", "running", "failed", "pending", "complete", "active"].includes(step.status) ? step.status : "pending";
        const normalized = status === "complete" ? "done" : status === "active" ? "running" : status;
        const label = normalized === "done" ? "已完成" : normalized === "running" ? "进行中" : normalized === "failed" ? "未完成" : "稍后";
        return `<div class="ai-tool-step ${normalized}"><span class="ai-tool-dot">${index + 1}</span><span class="ai-tool-main"><span class="ai-tool-title-row"><span class="ai-tool-title">${escapeHTML(step.title || "处理灵感")}</span><span class="ai-tool-status">${label}</span></span><span class="ai-tool-detail">${escapeHTML(step.detail || "")}</span></span></div>`;
      }).join("")}</div>`;
    }
    function renderAIToolSummary(steps = []) {
      const hasFailed = steps.some(step => step.status === "failed" || step.status === "error");
      const usedXHS = steps.some(step => /小红书|笔记|参考|xhs/i.test(`${step.title || ""}${step.detail || ""}`));
      const text = hasFailed ? "有参考源不可用，已换成可执行建议" : usedXHS ? "已看过上下文和小红书参考" : "已看过上下文";
      return `<div class="ai-tool-summary">${escapeHTML(text)}</div>`;
    }
    function renderInlineMarkdown(text = "") {
      return escapeHTML(text)
        .replace(/`([^`]+)`/g, "<code>$1</code>")
        .replace(/\\*\\*([^*]+)\\*\\*/g, "<strong>$1</strong>");
    }
    function renderAssistantMarkdown(text = "", options = {}) {
      const lines = String(text || "").split(/\\n+/).map(line => line.trim()).filter(Boolean);
      const blocks = [];
      let listItems = [];
      const flushList = () => {
        if (!listItems.length) return;
        blocks.push(`<ul class="ai-md-list">${listItems.map(line => `<li>${renderInlineMarkdown(line)}</li>`).join("")}</ul>`);
        listItems = [];
      };
      lines.forEach(line => {
        const bullet = line.match(/^[-•]\\s+(.+)$/);
        if (bullet) {
          listItems.push(bullet[1]);
          return;
        }
        flushList();
        const heading = line.match(/^#{1,3}\\s+(.+)$/);
        if (heading) {
          blocks.push(`<div class="ai-md-heading">${renderInlineMarkdown(heading[1])}</div>`);
          return;
        }
        const boldHeading = line.match(/^\\*\\*([^*：:]{2,20}[：:]?)\\*\\*$/);
        if (boldHeading) {
          blocks.push(`<div class="ai-md-heading">${renderInlineMarkdown(line)}</div>`);
          return;
        }
        blocks.push(`<p>${renderInlineMarkdown(line)}</p>`);
      });
      flushList();
      const streamingClass = options.streaming ? " ai-streaming-cursor" : "";
      if (!blocks.length && options.streaming) return `<div class="ai-assistant-copy"><p class="ai-streaming-cursor"></p></div>`;
      return blocks.length ? `<div class="ai-assistant-copy${streamingClass}">${blocks.join("")}</div>` : "";
    }
    function renderAssistantCopy(text = "") {
      return renderAssistantMarkdown(text);
    }
    function renderAssistantStream(text = "") {
      return renderAssistantMarkdown(text, { streaming: true });
    }
    function normalizeAIInputText(text = "") {
      return String(text || "")
        .replace(/\\r\\n?/g, "\\n")
        .split("\\n")
        .map(line => line.trim())
        .filter(Boolean)
        .join(" ")
        .replace(/\\s{2,}/g, " ")
        .trim();
    }
    function insertNormalizedPromptText(textarea, text = "") {
      const normalized = normalizeAIInputText(text);
      if (!normalized) return;
      const start = textarea.selectionStart ?? textarea.value.length;
      const end = textarea.selectionEnd ?? textarea.value.length;
      const before = textarea.value.slice(0, start);
      const after = textarea.value.slice(end);
      const needsLead = before && !/\\s$/.test(before) ? " " : "";
      const needsTrail = after && !/^\\s/.test(after) ? " " : "";
      textarea.value = `${before}${needsLead}${normalized}${needsTrail}${after}`.replace(/\\s{2,}/g, " ");
      const cursor = (before + needsLead + normalized).length;
      textarea.setSelectionRange(cursor, cursor);
      updateAISendButton();
    }
    function stopAITextStream() {
      if (state.aiStreamTimer) window.clearInterval(state.aiStreamTimer);
      state.aiStreamTimer = null;
    }
    function isAIResponding() {
      return !!(state.aiAbortController || state.aiResult?.status === "loading" || (state.aiStreamingText !== null && !state.aiStreamingDone));
    }
    function updateAISendButton() {
      const button = $("#aiSendBtn");
      if (!button) return;
      const stopping = isAIResponding();
      button.disabled = !stopping && !normalizeAIInputText($("#aiPromptInput")?.value || "");
      button.classList.toggle("is-stopping", stopping);
      button.innerHTML = stopping
        ? `<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="7" y="7" width="10" height="10" rx="2"/></svg>`
        : `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 18V6"/><path d="m7.5 10.5 4.5-4.5 4.5 4.5"/></svg>`;
      button.setAttribute("aria-label", stopping ? "停止输出" : "发送");
      button.setAttribute("title", stopping ? "停止输出" : "发送");
    }
    function stopAIResponse() {
      if (state.aiAbortController) {
        state.aiAbortController.abort();
        state.aiAbortController = null;
      }
      stopAITextStream();
      stopAIToolProgress();
      if (state.aiResult?.status === "loading") {
        state.aiToolsExpanded = false;
        state.aiResult = { status: "stopped", assistant_message: "已停止输出。你可以调整问题后重新发送。", tool_steps: [] };
      } else if (state.aiStreamingText !== null && !state.aiStreamingDone) {
        state.aiStreamingDone = true;
      }
      renderAIResult();
      updateAISendButton();
      toast("已停止输出。");
    }
    function startAITextStream(fullText = "") {
      stopAITextStream();
      const target = String(fullText || "");
      state.aiStreamingText = "";
      state.aiStreamingDone = false;
      state.aiToolsExpanded = false;
      renderAIResult();
      if (!target) {
        state.aiStreamingDone = true;
        renderAIResult();
        return;
      }
      let index = 0;
      state.aiStreamTimer = window.setInterval(() => {
        const step = target.length > 180 ? 10 : 6;
        index = Math.min(target.length, index + step);
        state.aiStreamingText = target.slice(0, index);
        if (index >= target.length) {
          stopAITextStream();
          state.aiStreamingDone = true;
        }
        renderAIResult();
      }, 48);
    }
    function renderXHSNotes(notes = []) {
      const cards = notes.slice(0, 6).map(note => {
        const cover = note.cover_url
          ? `<img src="${escapeHTML(note.cover_url)}" alt="${escapeHTML(note.title || "小红书笔记")}" loading="lazy" onerror="this.replaceWith(document.createTextNode('封面缓存中'))">`
          : "暂无封面";
        const stats = [note.liked_count ? `赞 ${note.liked_count}` : "", note.collected_count ? `藏 ${note.collected_count}` : ""].filter(Boolean).join(" · ");
        const content = `<div class="xhs-note-cover">${cover}</div><div class="xhs-note-body"><div class="xhs-note-title">${escapeHTML(note.title || "小红书笔记")}</div><div class="xhs-note-meta"><span>${escapeHTML(note.author_name || "小红书用户")}</span><span>${escapeHTML(stats || note.source_label || "推荐")}</span></div></div>`;
        return note.url ? `<a class="xhs-note-card" href="${escapeHTML(note.url)}" target="_blank" rel="noopener noreferrer">${content}</a>` : `<article class="xhs-note-card">${content}</article>`;
      }).join("");
      return cards ? `<div class="xhs-note-strip" aria-label="小红书推荐笔记">${cards}</div>` : "";
    }
    function renderAISources(sources = []) {
      return (sources || []).slice(0, 4).map(source => {
        const type = source.type === "xiaohongshu" || source.type === "xhs" ? "小红书推荐" : source.type === "closet" ? "本地衣橱" : source.type === "style_kb" ? "风格知识" : source.label || "灵感来源";
        const count = source.count ? ` · ${source.count}` : "";
        return `<span class="ai-source">${escapeHTML(source.label || type)}${escapeHTML(count)}</span>`;
      }).join("");
    }
    function renderStoredAssistantMessage(item) {
      const toolchain = Array.isArray(item.tool_steps) && item.tool_steps.length
        ? `<details class="ai-tool-history"><summary>${renderAIToolSummary(item.tool_steps)}</summary>${renderAIToolchain(item.tool_steps)}</details>`
        : "";
      const notes = renderXHSNotes(item.xhs_notes || []);
      const sources = renderAISources(item.evidence_sources || []);
      return `<div class="ai-assistant-turn">
        ${toolchain}
        ${renderAssistantCopy(item.content)}
        ${notes}
        ${sources ? `<div class="ai-sources">${sources}</div>` : ""}
      </div>`;
    }
    function preserveCurrentAIArtifactsOnLastMessage() {
      const result = state.aiResult || {};
      if (result.status === "loading" || result.status === "failed") return;
      const hasArtifacts = Array.isArray(result.tool_steps) || Array.isArray(result.xhs_notes) || Array.isArray(result.evidence_sources) || Array.isArray(result.rationale);
      if (!hasArtifacts) return;
      for (let index = state.aiMessages.length - 1; index >= 0; index -= 1) {
        const item = state.aiMessages[index];
        if (!item || item.role !== "assistant") continue;
        if (!Array.isArray(item.tool_steps) && Array.isArray(result.tool_steps)) item.tool_steps = result.tool_steps;
        if (!Array.isArray(item.xhs_notes) && Array.isArray(result.xhs_notes)) item.xhs_notes = result.xhs_notes;
        if (!Array.isArray(item.evidence_sources) && Array.isArray(result.evidence_sources)) item.evidence_sources = result.evidence_sources;
        if (!Array.isArray(item.rationale) && Array.isArray(result.rationale)) item.rationale = result.rationale;
        break;
      }
    }
    function buildSyntheticOutfits() {
      const chunks = [];
      const cleanItems = visibleItems();
      for (let i = 0; i < cleanItems.length; i += 3) {
        const items = cleanItems.slice(i, i + 3);
        if (items.length) chunks.push({ outfit_id: "", title: "灵感搭配", items, favorite_count: 24 + i * 3 });
      }
      return chunks;
    }
    function renderAI() {
      updateSessionTitle();
      const scenes = currentProfile().chips || aiScenes;
      $("#aiChips").innerHTML = scenes.map(scene => `<button class="chip" data-scene="${scene}">${scene}</button>`).join("");
      $all("[data-scene]").forEach(btn => btn.addEventListener("click", () => {
        state.aiBrief = btn.dataset.scene;
        $("#aiPromptInput").value = `${btn.dataset.scene}：帮我推荐穿搭`;
        askStylist();
      }));
      renderAIResult();
    }
    function renderAIResult() {
      const panel = $("#aiResult");
      updateAISendButton();
      $(".ai-hero").classList.toggle("is-dismissed", state.aiMessages.length > 0 || !!state.aiResult);
      if (!state.aiResult) {
        if (!state.aiMessages.length) {
          panel.style.display = "none";
          return;
        }
        panel.style.display = "grid";
        panel.classList.remove("error");
        const thread = state.aiMessages.slice(-8).map(item => {
          if (item.role === "assistant") return renderStoredAssistantMessage(item);
          return `<div class="ai-bubble user">${escapeHTML(item.content || "")}</div>`;
        }).join("");
        panel.innerHTML = `<div class="ai-thread has-messages">${thread}</div>`;
        return;
      }
      panel.style.display = "grid";
      panel.classList.toggle("error", state.aiResult.status === "failed");
      const result = state.aiResult;
      const recentMessages = state.aiMessages.slice(-8);
      const lastAssistantIndex = recentMessages.map(item => item.role).lastIndexOf("assistant");
      const thread = recentMessages.map((item, index) => {
        if (item.role === "assistant" && index === lastAssistantIndex && result.status !== "loading") return "";
        if (item.role === "assistant") return renderStoredAssistantMessage(item);
        return `<div class="ai-bubble user">${escapeHTML(item.content)}</div>`;
      }).join("");
      const toolSteps = result.status === "loading" ? visibleLoadingToolSteps() : Array.isArray(result.tool_steps) ? result.tool_steps : [];
      const isFinal = result.status !== "loading";
      const finalText = result.assistant_message || (result.status === "loading" ? "正在理解你的场景和衣橱..." : "我已经理解你的需求。");
      const isStreaming = isFinal && state.aiStreamingText !== null && !state.aiStreamingDone;
      const visibleText = isFinal && state.aiStreamingText !== null ? state.aiStreamingText : finalText;
      const toolsCollapsed = toolSteps.length && !state.aiToolsExpanded;
      const toolchain = result.status === "loading"
        ? (toolsCollapsed ? renderAIToolSummary(toolSteps) : renderAIToolchain(toolSteps))
        : toolsCollapsed
          ? renderAIToolSummary(toolSteps)
          : toolSteps.length ? renderAIToolchain(toolSteps) : "";
      const xhsNotes = renderXHSNotes(result.xhs_notes || []);
      const sources = renderAISources(result.evidence_sources || []);
      const outfits = (result.recommended_outfits || []).slice(0, 2).map(outfit => `<button data-ai-outfit="${outfit.outfit_id || ""}">${escapeHTML(outfit.title || "推荐套装")}</button>`).join("");
      const nextActions = (result.next_actions || []).slice(0, 3).map(action => {
        const type = action.type === "retry_xhs" ? "retry_xhs" : action.type === "open_closet" ? "closet" : "";
        return type ? `<button data-ai-action="${type}">${escapeHTML(action.label || "继续")}</button>` : "";
      }).join("");
      const actions = outfits || nextActions || `<button data-ai-action="closet">去衣橱选择</button>`;
      const statusLabel = result.status === "loading" ? "进行中" : result.status === "failed" ? "未完成" : result.status === "stopped" ? "已停止" : "已完成";
      const assistantText = isStreaming ? renderAssistantStream(visibleText) : renderAssistantCopy(visibleText);
      const showPostContent = result.status === "loading" || state.aiStreamingDone || state.aiStreamingText === null;
      const richAssistant = `<div class="ai-assistant-turn">
        <button class="ai-status-label ${toolsCollapsed ? "is-collapsed" : ""}" type="button" data-ai-toggle-tools>${statusLabel}</button>
        ${toolchain}
        ${assistantText}
        ${showPostContent ? xhsNotes : ""}
        ${showPostContent && sources ? `<div class="ai-sources">${sources}</div>` : ""}
        ${showPostContent ? `<div class="ai-actions">${actions}</div>` : ""}
      </div>`;
      const isGenerating = result.status === "loading" || isStreaming;
      panel.innerHTML = `<div class="ai-thread ${state.aiMessages.length ? "has-messages" : ""} ${isStreaming ? "is-streaming" : ""} ${isGenerating ? "is-generating" : ""}">${thread}${richAssistant}</div>`;
      updateAISendButton();
      $all("[data-ai-toggle-tools]").forEach(btn => btn.addEventListener("click", () => {
        state.aiToolsExpanded = !state.aiToolsExpanded;
        renderAIResult();
      }));
      $all("[data-ai-outfit]").forEach(btn => btn.addEventListener("click", () => openOutfitDetail(btn.dataset.aiOutfit)));
      $all("[data-ai-action='closet']").forEach(btn => btn.addEventListener("click", () => setTab("closet")));
      $all("[data-ai-action='retry_xhs']").forEach(btn => btn.addEventListener("click", () => askStylist(state.aiBrief || "帮我找小红书穿搭灵感")));
    }
    function renderCategories() {
      const cleanItems = visibleItems();
      const counts = categoryOrder.reduce((acc, key) => ({ ...acc, [key]: key === "all" ? cleanItems.length : cleanItems.filter(item => item.category === key).length }), {});
      $("#categoryRow").innerHTML = categoryOrder.map(key => {
        const label = key === "all" ? "全部" : labels[key];
        return `<button class="cat ${state.category === key ? "active" : ""}" data-category="${key}" aria-pressed="${state.category === key}"><span class="cat-label">${escapeHTML(label)}</span><span class="badge">${counts[key] || 0}</span></button>`;
      }).join("");
      $all("[data-category]").forEach(btn => btn.addEventListener("click", () => {
        state.category = btn.dataset.category;
        state.closetItemLimit = 20;
        renderCategories();
        renderCloset();
      }));
    }
    function renderCloset() {
      if (state.closetMode === "plans") state.closetMode = "items";
      $all("[data-closet-mode]").forEach(btn => btn.classList.toggle("active", btn.dataset.closetMode === state.closetMode));
      $("#categoryRow").style.display = state.closetMode === "items" ? "flex" : "none";
      $("#floatingMatch").style.display = state.tab === "closet" ? "block" : "none";
      if (state.closetMode === "items") renderItemGrid();
      if (state.closetMode === "outfits") renderOutfitGrid();
    }
    function renderItemGrid() {
      const cleanItems = visibleItems();
      const items = state.category === "all" ? cleanItems : cleanItems.filter(item => item.category === state.category);
      const visiblePage = items.slice(0, state.closetItemLimit);
      const remaining = Math.max(0, items.length - visiblePage.length);
      $("#closetGrid").className = "item-grid";
      $("#closetGrid").removeAttribute("aria-busy");
      $("#closetGrid").removeAttribute("aria-label");
      $("#closetGrid").innerHTML = items.length ? `${visiblePage.map(item => `<article class="closet-card">
        <button class="closet-img" type="button" data-open-item="${item.item_id}" aria-label="查看${escapeHTML(item.category_label || "单品")}详情"><img src="${publicCutoutImg(item)}" alt="${escapeHTML(item.category_label || "单品")}" loading="lazy" decoding="async"></button>
        <button class="item-favorite ${item.favorite ? "active" : ""}" type="button" data-favorite-item="${item.item_id}" aria-label="${item.favorite ? "取消收藏" : "收藏"}${escapeHTML(item.category_label || "单品")}" aria-pressed="${Boolean(item.favorite)}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 20.4 4.1 13A5.2 5.2 0 0 1 11.5 5.6l.5.5.5-.5A5.2 5.2 0 0 1 19.9 13L12 20.4Z"/></svg></button>
        <div class="closet-card-label">${escapeHTML(item.category_label || labels[item.category] || "单品")}</div>
      </article>`).join("")}${remaining ? `<button class="closet-load-more" type="button" data-closet-more="items">继续浏览 · 还有 ${remaining} 件</button>` : ""}` : `<div class="empty">这个分类还没有衣物。点底部 + 上传一张试试。</div>`;
      $all("[data-open-item]").forEach(node => node.addEventListener("click", () => openItemDetail(node.dataset.openItem)));
      $all("[data-favorite-item]").forEach(btn => btn.addEventListener("click", event => {
        event.preventDefault();
        event.stopPropagation();
        toggleItemFavorite(btn.dataset.favoriteItem);
      }));
      $("[data-closet-more='items']")?.addEventListener("click", () => {
        state.closetItemLimit += 20;
        renderItemGrid();
      });
    }
    function renderOutfitGrid() {
      $("#closetGrid").className = "masonry";
      $("#closetGrid").removeAttribute("aria-busy");
      $("#closetGrid").removeAttribute("aria-label");
      const outfits = visibleOutfits();
      const visiblePage = outfits.slice(0, state.closetOutfitLimit);
      const remaining = Math.max(0, outfits.length - visiblePage.length);
      $("#closetGrid").innerHTML = outfits.length ? `${visiblePage.map(outfit => outfitCardHTML(outfit)).join("")}${remaining ? `<button class="closet-load-more" type="button" data-closet-more="outfits">继续浏览 · 还有 ${remaining} 套</button>` : ""}` : `<div class="empty">还没有套装。选择几件单品，保存成一套搭配。</div>`;
      bindOutfitActions();
      $("[data-closet-more='outfits']")?.addEventListener("click", () => {
        state.closetOutfitLimit += 12;
        renderOutfitGrid();
      });
    }
    function renderPlans() {
      $("#closetGrid").className = "item-grid";
      $("#closetGrid").innerHTML = `<div class="empty">行程模式已预留。下一步可以为旅行、面试、约会创建穿搭计划。</div>`;
    }
    function renderBuilder() {
      $("#builderList").innerHTML = visibleItems().map(item => `<button class="pick-card ${state.selectedItems.has(item.item_id) ? "active" : ""}" data-builder-item="${item.item_id}"><img src="${publicCutoutImg(item)}" alt="${item.category_label}" loading="lazy" decoding="async"><span>${item.category_label}</span></button>`).join("");
      $all("[data-builder-item]").forEach(btn => btn.addEventListener("click", () => {
        const id = btn.dataset.builderItem;
        if (state.selectedItems.has(id)) state.selectedItems.delete(id);
        else {
          const warning = builderConflictWarning(id);
          state.selectedItems.add(id);
          if (warning) toast(warning);
        }
        renderBuilder();
      }));
    }
    function itemSlot(item) {
      const tags = (item?.attributes?.style_tags || []).join(" ");
      if (tags.includes("帽")) return "hat";
      if (tags.includes("围巾") || tags.includes("丝巾")) return "scarf";
      if (tags.includes("袜")) return "socks";
      return item?.category || "accessory";
    }
    function builderConflictWarning(nextId) {
      const next = state.items.find(item => item.item_id === nextId);
      if (!next) return "";
      const nextSlot = itemSlot(next);
      const selected = [...state.selectedItems].map(id => state.items.find(item => item.item_id === id)).filter(Boolean);
      const selectedSlots = selected.map(itemSlot);
      if (nextSlot === "shoes" && selectedSlots.includes("shoes")) return "一套搭配里先保留一双鞋。";
      if ((nextSlot === "bottom" || nextSlot === "skirt") && selectedSlots.some(slot => slot === "bottom" || slot === "skirt")) return "裤子和裙子先保留一个。";
      if (nextSlot === "top" && selectedSlots.includes("top")) return "一套搭配里先保留一件上衣。";
      if (nextSlot === "dress" && selectedSlots.some(slot => ["top", "bottom", "skirt", "dress"].includes(slot))) return "连衣装会作为主搭配，其他主服装会作为参考。";
      if (["top", "bottom", "skirt"].includes(nextSlot) && selectedSlots.includes("dress")) return "已选择连衣装，其他主服装会作为参考。";
      if (nextSlot === "bag" && selectedSlots.includes("bag")) return "一套搭配里先保留一个包。";
      return "";
    }
    function renderProfile() {
      const profile = currentProfile();
      const records = state.records || [];
      const favoriteItems = visibleItems().filter(item => item.favorite).map(item => ({ id: item.item_id, type: "item", image_path: publicCutoutImg(item), label: item.category_label || "收藏单品" }));
      const favoriteOutfits = visibleOutfits().filter(outfit => outfit.favorite).map(outfit => ({ id: outfit.outfit_id, type: "outfit", image_path: withVersion(outfit.layout_snapshot_path || outfit.cover_path || outfit.cover || "", outfit), label: outfit.title || "收藏套装" }));
      const favorites = [...favoriteOutfits, ...favoriteItems].filter(item => item.image_path);
      const workItems = visibleItems().filter(isUserCreatedItem).map(item => ({ id: `item:${item.item_id}`, raw_id: item.item_id, type: "item", image_path: publicCutoutImg(item), label: item.category_label || "上传单品", card_class: "work-item" })).filter(item => item.image_path);
      const workOutfits = visibleOutfits().filter(isUserCreatedOutfit).map(outfit => ({ id: `outfit:${outfit.outfit_id}`, raw_id: outfit.outfit_id, type: "outfit", image_path: withVersion(outfit.layout_snapshot_path || outfit.cover_path || outfit.cover || "", outfit), label: outfit.title || "我的搭配", card_class: "work-outfit" })).filter(item => item.image_path);
      const isRecords = state.profileView === "records";
      const isWorks = state.profileView === "works";
      const currentWorks = isWorks ? (state.profileWorkView === "items" ? workItems : workOutfits) : [];
      if ((!records.length && isRecords && state.recordEditing) || (!currentWorks.length && isWorks && state.recordEditing)) {
        state.recordEditing = false;
        state.selectedRecordIds.clear();
        state.selectedWorkIds.clear();
      }
      $("#profileName").textContent = profile.name;
      $("#profileLine").textContent = profile.summary || profile.role || "";
      $all("[data-profile-view]").forEach(btn => btn.classList.toggle("active", btn.dataset.profileView === state.profileView));
      $all("[data-work-view]").forEach(btn => btn.classList.toggle("active", btn.dataset.workView === state.profileWorkView));
      $("#worksSubtabs").classList.toggle("active", isWorks);
      $("#recordCount").textContent = isRecords ? records.length : isWorks ? currentWorks.length : favorites.length;
      $("#recordCountLabel").textContent = isRecords ? "条试穿记录" : isWorks ? (state.profileWorkView === "items" ? "个单品" : "套搭配") : "条收藏";
      const editBtn = $("#recordEditBtn");
      editBtn.style.display = isRecords || isWorks ? "inline-flex" : "none";
      editBtn.textContent = state.recordEditing ? "完成" : "编辑";
      editBtn.classList.toggle("active", state.recordEditing);
      editBtn.disabled = isRecords ? !records.length : isWorks ? !currentWorks.length : true;
      $("#recordDeleteBar").classList.toggle("active", (isRecords || isWorks) && state.recordEditing);
      const selectedCount = isWorks ? state.selectedWorkIds.size : state.selectedRecordIds.size;
      $("#recordSelectText").textContent = selectedCount ? `已选择 ${selectedCount} ${isWorks ? "个作品" : "条记录"}` : isWorks ? "选择要删除的作品" : "选择要删除的记录";
      $("#recordDeleteBtn").disabled = !selectedCount;
      if (state.profileView === "favorites") {
        $("#recordGrid").innerHTML = favorites.length ? favorites.slice(0, 18).map(item => item.type === "outfit"
          ? `<button class="record-card" type="button" data-profile-outfit="${item.id}"><img src="${item.image_path}" alt="${escapeHTML(item.label)}"></button>`
          : `<button class="record-card" type="button" data-profile-item="${item.id}"><img src="${item.image_path}" alt="${escapeHTML(item.label)}"></button>`).join("") : `<div class="empty" style="grid-column:1/-1;">收藏单品和套装会出现在这里。</div>`;
        $all("[data-profile-outfit]").forEach(card => card.addEventListener("click", () => openOutfitDetail(card.dataset.profileOutfit)));
        $all("[data-profile-item]").forEach(card => card.addEventListener("click", () => openItemDetail(card.dataset.profileItem)));
        return;
      }
      if (isWorks) {
        const emptyCopy = state.profileWorkView === "items" ? "你上传或从链接提取的单品会出现在这里。" : "你保存的搭配会出现在这里。";
        $("#recordGrid").innerHTML = currentWorks.length ? currentWorks.slice(0, 36).map(item => {
          const selected = state.selectedWorkIds.has(item.id);
          return `<button class="record-card ${item.card_class} ${state.recordEditing ? "editing" : ""} ${selected ? "selected" : ""}" type="button" data-work-id="${item.id}"><img src="${item.image_path}" alt="${escapeHTML(item.label)}">${state.recordEditing ? `<span class="check">✓</span>` : ""}</button>`;
        }).join("") : `<div class="empty" style="grid-column:1/-1;">${emptyCopy}</div>`;
        $all("[data-work-id]").forEach(card => card.addEventListener("click", () => {
          const id = card.dataset.workId;
          if (!id) return;
          if (!state.recordEditing) {
            const [type, rawId] = id.split(":");
            if (type === "outfit") return openOutfitDetail(rawId);
            if (type === "item") return openItemDetail(rawId);
            return;
          }
          if (state.selectedWorkIds.has(id)) state.selectedWorkIds.delete(id);
          else state.selectedWorkIds.add(id);
          renderProfile();
        }));
        return;
      }
      $("#recordGrid").innerHTML = records.length ? records.slice(0, 18).map(record => {
        const selected = state.selectedRecordIds.has(record.record_id);
        const badge = record.status === "review" ? `<span class="record-badge">需复核</span>` : "";
        return `<button class="record-card ${state.recordEditing ? "editing" : ""} ${selected ? "selected" : ""}" type="button" data-record-id="${record.record_id || ""}" data-preview-image="${assetURL(record.image_path)}" data-preview-title="试穿记录"><img src="${assetURL(record.image_path)}" alt="试穿记录">${badge}${state.recordEditing ? `<span class="check">✓</span>` : ""}</button>`;
      }).join("") : `<div class="empty" style="grid-column:1/-1;">试穿记录会出现在这里。</div>`;
      $all("[data-record-id]").forEach(card => card.addEventListener("click", () => {
        if (!state.recordEditing) return;
        const id = card.dataset.recordId;
        if (!id) return;
        if (state.selectedRecordIds.has(id)) state.selectedRecordIds.delete(id);
        else state.selectedRecordIds.add(id);
        renderProfile();
      }));
      bindImagePreviews();
    }
    function toggleRecordEditing() {
      const workCount = state.profileWorkView === "items" ? visibleItems().filter(isUserCreatedItem).length : visibleOutfits().filter(isUserCreatedOutfit).length;
      const canEdit = state.profileView === "records" ? state.records.length : state.profileView === "works" ? workCount : 0;
      if (!canEdit) return toast(state.profileView === "works" ? "暂无作品。" : "暂无试穿记录。");
      state.recordEditing = !state.recordEditing;
      state.selectedRecordIds.clear();
      state.selectedWorkIds.clear();
      renderProfile();
    }
    async function deleteSelectedWorks() {
      const ids = [...state.selectedWorkIds];
      if (!ids.length) return toast("先选择要删除的作品。");
      $("#recordDeleteBtn").disabled = true;
      try {
        await Promise.all(ids.map(id => {
          const [type, rawId] = id.split(":");
          if (type === "item") return fetchJSON(`/closet/items/${encodeURIComponent(rawId)}`, { method: "DELETE" });
          if (type === "outfit") return fetchJSON(`/closet/outfits/${encodeURIComponent(rawId)}`, { method: "DELETE" });
          return Promise.resolve();
        }));
        state.items = state.items.filter(item => !state.selectedWorkIds.has(`item:${item.item_id}`));
        state.outfits = state.outfits.filter(outfit => !state.selectedWorkIds.has(`outfit:${outfit.outfit_id}`));
        state.selectedWorkIds.clear();
        state.recordEditing = false;
        renderAll();
        toast("已删除作品。");
      } catch (error) {
        renderProfile();
        toast(error.message || "删除失败，请稍后再试。");
      }
    }
    async function deleteSelectedTryonRecords() {
      const ids = [...state.selectedRecordIds];
      if (!ids.length) return toast("先选择要删除的记录。");
      $("#recordDeleteBtn").disabled = true;
      try {
        await Promise.all(ids.map(id => fetchJSON(`/closet/tryon-records/${encodeURIComponent(id)}`, { method: "DELETE" })));
        state.records = state.records.filter(record => !state.selectedRecordIds.has(record.record_id));
        state.selectedRecordIds.clear();
        state.recordEditing = false;
        renderProfile();
        toast("已删除试穿记录。");
      } catch (error) {
        renderProfile();
        toast(error.message || "删除失败，请稍后再试。");
      }
    }
    async function deleteSelectedProfileEntries() {
      if (state.profileView === "works") return deleteSelectedWorks();
      return deleteSelectedTryonRecords();
    }
    async function openOutfitDetail(outfitId) {
      if (!outfitId) {
        openBuilder();
        return toast("先保存套装后再查看详情。");
      }
      const outfit = cleanOutfit(state.outfits.find(item => item.outfit_id === outfitId) || await fetchJSON(`/closet/outfits/${encodeURIComponent(outfitId)}`));
      state.detailReturnTab = state.tab || "home";
      state.detailMode = "outfit";
      state.currentItem = null;
      state.currentOutfit = outfit;
      state.editorItems = visibleItems(outfit.items || []).map((item, index) => editorItemFromClosetItem(item, index));
      renderDetail();
      renderEditor();
      setPage("page-detail");
    }
    function openItemDetail(itemId) {
      const item = visibleItems().find(entry => entry.item_id === itemId);
      if (!item) return toast("这件单品暂时无法查看。");
      state.detailReturnTab = state.tab || "closet";
      state.detailMode = "item";
      state.currentItem = item;
      renderDetail();
      setPage("page-detail");
    }
    function recommendationGroup(item) {
      const slot = itemSlot(item);
      if (["bottom", "skirt"].includes(slot)) return "lower";
      if (["hat", "scarf", "socks", "accessory"].includes(slot)) return "accessory";
      return slot;
    }
    function recommendationTokens(values = []) {
      const aliases = {
        minimal: ["minimal", "minimalist", "clean", "simple", "简洁", "极简", "低装饰", "克制"],
        structured: ["structured", "tailored", "sharp", "clean lines", "秩序", "利落", "结构", "清晰线条", "剪裁"],
        soft: ["soft", "gentle", "flowy", "drape", "柔和", "温柔", "轻盈", "垂坠"],
        classic: ["classic", "timeless", "preppy", "heritage", "经典", "老钱", "学院", "稳定质感"],
        romantic: ["romantic", "lace", "ruffle", "feminine", "浪漫", "蕾丝", "荷叶", "女性"],
        casual: ["casual", "relaxed", "everyday", "休闲", "松弛", "日常", "舒适"],
        sporty: ["sport", "sporty", "athletic", "outdoor", "运动", "户外", "机能"],
        vintage: ["vintage", "retro", "nostalgic", "复古", "怀旧"],
        dark: ["dark", "goth", "black", "leather", "暗黑", "冷硬", "黑色", "皮革"],
        expressive: ["expressive", "bold", "statement", "contrast", "高表达", "大胆", "撞色", "冲突", "夸张"],
        airy: ["airy", "sheer", "transparent", "satin", "空气感", "薄纱", "半透明", "缎面", "冷雾"],
      };
      const text = (Array.isArray(values) ? values : [values]).map(value => String(value || "").trim().toLowerCase()).join(" ");
      return Object.entries(aliases).filter(([, terms]) => terms.some(term => text.includes(term))).map(([token]) => token);
    }
    function recommendationColorRoots(item) {
      const aliases = {
        black: ["black", "charcoal", "onyx", "黑", "炭黑", "曜石"], white: ["white", "ivory", "cream", "oat", "白", "象牙", "奶油", "烟白", "雾白"],
        gray: ["gray", "grey", "silver", "灰", "银", "水泥"], blue: ["blue", "navy", "denim", "蓝", "藏青", "雾蓝", "冰蓝"],
        brown: ["brown", "camel", "tan", "coffee", "chocolate", "棕", "驼", "咖啡", "焦糖"], red: ["red", "burgundy", "wine", "红", "酒红"],
        pink: ["pink", "rose", "blush", "粉", "玫瑰"], green: ["green", "mint", "olive", "绿", "薄荷", "墨绿"],
        yellow: ["yellow", "lemon", "champagne", "黄", "柠檬", "香槟"], purple: ["purple", "violet", "lavender", "紫", "薰衣草"]
      };
      const text = (item?.attributes?.colors || []).map(value => String(value || "").toLowerCase()).join(" ");
      return Object.entries(aliases).filter(([, terms]) => terms.some(term => text.includes(term))).map(([token]) => token);
    }
    function smartItemRecommendations(anchor, limit = 6) {
      if (!anchor?.item_id) return [];
      const anchorGroup = recommendationGroup(anchor);
      const compatibility = {
        top: { lower: 72, shoes: 42, bag: 38, accessory: 26 },
        lower: { top: 72, shoes: 42, bag: 38, accessory: 26 },
        dress: { shoes: 68, bag: 62, accessory: 38 },
        shoes: { dress: 64, top: 54, lower: 54, bag: 32, accessory: 22 },
        bag: { dress: 64, top: 54, lower: 54, shoes: 34, accessory: 22 },
        accessory: { dress: 58, top: 52, lower: 52, shoes: 30, bag: 30, accessory: 12 },
      };
      const coOccurrence = new Map();
      visibleOutfits().forEach(outfit => {
        const outfitItems = visibleItems(outfit.items || []);
        if (!outfitItems.some(item => item.item_id === anchor.item_id)) return;
        outfitItems.forEach(item => {
          if (item.item_id !== anchor.item_id) coOccurrence.set(item.item_id, (coOccurrence.get(item.item_id) || 0) + 1);
        });
      });
      const anchorTags = new Set(recommendationTokens(anchor.attributes?.style_tags || []));
      const anchorColors = recommendationColorRoots(anchor);
      const personaColors = stylePersonaColors().flatMap(color => recommendationColorRoots({ attributes: { colors: [color.name || ""] } }));
      const personaStyleTokens = new Set(recommendationTokens([...(state.stylePersona?.keywords || []), state.stylePersona?.summary || "", state.stylePersona?.recommendations?.outfits?.summary || ""]));
      const neutralRoots = new Set(["black", "white", "gray", "blue", "brown"]);
      const ranked = visibleItems().filter(item => item.item_id !== anchor.item_id).map(item => {
        const group = recommendationGroup(item);
        const coCount = coOccurrence.get(item.item_id) || 0;
        let score = compatibility[anchorGroup]?.[group];
        if (score == null && coCount) score = 44;
        if (score == null) return null;
        const itemTags = recommendationTokens(item.attributes?.style_tags || []);
        const sharedTags = itemTags.filter(tag => anchorTags.has(tag));
        const personaTags = itemTags.filter(tag => personaStyleTokens.has(tag));
        const colors = recommendationColorRoots(item);
        const sharedColors = colors.filter(color => anchorColors.includes(color));
        const neutralHarmony = colors.some(color => neutralRoots.has(color)) && anchorColors.some(color => neutralRoots.has(color));
        const personaHarmony = colors.some(color => personaColors.includes(color));
        score += coCount * 120;
        score += sharedTags.length * 18;
        score += personaTags.length * 16;
        score += sharedColors.length * 10;
        score += neutralHarmony ? 6 : 0;
        score += personaHarmony ? 7 : 0;
        score += Math.max(0, Math.min(1, Number(item.quality?.score || 0))) * 6;
        const reason = coCount
          ? "衣橱常搭"
          : personaTags[0]
            ? "符合你的风格"
            : sharedTags[0]
              ? "风格特征呼应"
            : sharedColors.length || neutralHarmony || personaHarmony
              ? "配色协调"
              : "补全搭配";
        return { item, group, score, reason };
      }).filter(Boolean).sort((a, b) => b.score - a.score || String(a.item.item_id).localeCompare(String(b.item.item_id)));
      const groupCaps = anchorGroup === "top"
        ? { lower: 2, shoes: 1, bag: 1, accessory: 2 }
        : anchorGroup === "lower"
          ? { top: 2, shoes: 1, bag: 1, accessory: 2 }
          : { dress: 2, top: 2, lower: 2, shoes: 1, bag: 1, accessory: 1 };
      const selected = [];
      const groupCounts = {};
      ranked.forEach(entry => {
        if (selected.length >= limit) return;
        const cap = groupCaps[entry.group] ?? 1;
        if ((groupCounts[entry.group] || 0) >= cap) return;
        selected.push(entry);
        groupCounts[entry.group] = (groupCounts[entry.group] || 0) + 1;
      });
      if (selected.length < limit) {
        ranked.forEach(entry => {
          if (selected.length >= limit || selected.some(selectedEntry => selectedEntry.item.item_id === entry.item.item_id)) return;
          selected.push(entry);
        });
      }
      return selected.slice(0, limit);
    }
    function renderDetail() {
      const item = state.detailMode === "item" ? state.currentItem : null;
      if (item) {
        const model = currentModel();
        const label = item.category_label || labels[item.category] || "单品详情";
        $("#detailTitle").textContent = label;
        $("#detailHero").classList.add("is-item");
        delete $("#detailHero").dataset.previewImage;
        delete $("#detailHero").dataset.previewTitle;
        $("#detailHero").innerHTML = `<img src="${publicCutoutImg(item)}" alt="${escapeHTML(label)}"><div class="model-chip"><img src="${model.src}" alt="${escapeHTML(model.name || "当前模特")}"></div>`;
        const recommendations = smartItemRecommendations(item);
        $("#detailItemsSection").hidden = false;
        $("#detailItemsEyebrow").textContent = "SMART MATCH";
        $("#detailItemsTitle").textContent = "适合搭配";
        $("#detailItemsNote").hidden = false;
        $("#detailItemsNote").textContent = "根据这件单品、你的风格和衣橱搭配关系推荐";
        $("#detailItems").innerHTML = recommendations.length ? recommendations.map(({ item: recommendation, reason }) => `<button class="item-tile recommendation-tile" data-detail-item="${recommendation.item_id}"><img src="${publicCutoutImg(recommendation)}" alt="${escapeHTML(recommendation.category_label || "推荐单品")}"><span>${escapeHTML(recommendation.category_label || "推荐单品")}</span><small>${escapeHTML(reason)}</small></button>`).join("") : `<div class="empty" style="min-width:100%;">衣橱里暂时没有合适的互补单品，先去添加一件试试。</div>`;
        $all("[data-detail-item]").forEach(node => node.addEventListener("click", () => openItemDetail(node.dataset.detailItem)));
        $("#detailEditBtn").textContent = "加入搭配";
        $("#detailTryBtn").textContent = ["top", "bottom", "skirt", "dress"].includes(item.category) ? "试穿这件" : "搭配这件";
        return;
      }
      const outfit = state.currentOutfit;
      if (!outfit) return;
      $("#detailTitle").textContent = outfit.title || "穿搭详情";
      const cover = withVersion(outfit.layout_snapshot_path || outfit.cover_path || "", outfit);
      const model = currentModel();
      $("#detailHero").classList.remove("is-item");
      delete $("#detailHero").dataset.previewImage;
      delete $("#detailHero").dataset.previewTitle;
      $("#detailHero").innerHTML = `${cover ? `<img src="${cover}" alt="${escapeHTML(outfit.title || "穿搭")}">` : `<div class="empty">这套搭配正在生成封面</div>`}<div class="model-chip"><img src="${model.src}" alt="${escapeHTML(model.name || "当前模特")}"></div>`;
      $("#detailItemsSection").hidden = false;
      $("#detailItemsEyebrow").textContent = "OUTFIT PIECES";
      $("#detailItemsTitle").textContent = "穿搭单品";
      $("#detailItemsNote").hidden = true;
      $("#detailItemsNote").textContent = "";
      $("#detailEditBtn").textContent = "调整搭配";
      $("#detailTryBtn").textContent = "生成试穿图";
      $("#detailItems").innerHTML = visibleItems(outfit.items || []).map(item => `<button class="item-tile" data-detail-item="${item.item_id}"><img src="${publicCutoutImg(item)}" alt="${escapeHTML(item.category_label || "单品")}"><span>${escapeHTML(item.category_label || "单品")}</span></button>`).join("") || `<div class="empty" style="min-width:100%;">这套搭配还没有单品。</div>`;
      $all("[data-detail-item]").forEach(node => node.addEventListener("click", () => openItemDetail(node.dataset.detailItem)));
    }
    function editorItemFromClosetItem(item, index) {
      const slot = itemSlot(item);
      const defaults = {
        top: [112, 34, 1.55], bottom: [58, 168, 1.7], skirt: [58, 176, 1.6],
        dress: [88, 60, 1.85], shoes: [188, 298, 1.12], bag: [232, 96, 1.02], accessory: [228, 38, .9]
      };
      const base = defaults[slot] || [54 + (index % 3) * 112, 80 + Math.floor(index / 3) * 126, .82];
      return { id: item.item_id, item, x: base[0], y: base[1], scale: base[2], rotation: 0, z: 2 + index };
    }
    function renderEditor() {
      renderEditorCanvas();
      renderPalette();
    }
    function renderEditorCanvas() {
      const canvas = $("#editorCanvas");
      if (!canvas) return;
      const itemsHTML = state.editorItems.map(entry => {
        const active = entry.id === state.activeEditorItemId ? "active" : "";
        return `<div class="canvas-item ${active}" data-canvas-item="${entry.id}" style="left:${entry.x}px;top:${entry.y}px;transform:rotate(${entry.rotation}deg) scale(${entry.scale});z-index:${entry.z};"><img src="${publicCutoutImg(entry.item)}" alt="${escapeHTML(entry.item.category_label || "单品")}"></div>`;
      }).join("");
      const activeEntry = state.editorItems.find(entry => entry.id === state.activeEditorItemId);
      const deleteHTML = activeEntry ? `<button class="canvas-delete" data-delete-canvas="${activeEntry.id}" type="button" style="left:${activeEntry.x + 132 * activeEntry.scale - 18}px;top:${activeEntry.y - 18}px;" onpointerdown="event.preventDefault();event.stopPropagation();deleteCanvasItem('${activeEntry.id}')" onclick="event.preventDefault();event.stopPropagation();deleteCanvasItem('${activeEntry.id}')">×</button>` : "";
      canvas.innerHTML = itemsHTML + deleteHTML;
      bindCanvasItems();
    }
    function renderPalette() {
      $("#paletteTabs").innerHTML = categoryOrder.map(key => `<button class="palette-tab ${state.paletteCategory === key ? "active" : ""}" data-palette-category="${key}">${key === "all" ? "全部" : labels[key]}</button>`).join("");
      const cleanItems = visibleItems();
      const items = state.paletteCategory === "all" ? cleanItems : cleanItems.filter(item => item.category === state.paletteCategory);
      $("#paletteGrid").innerHTML = items.length ? items.map(item => `<button class="pick-card" data-add-editor-item="${item.item_id}"><img src="${publicCutoutImg(item)}" alt="${escapeHTML(item.category_label || "单品")}"><span>${escapeHTML(item.category_label || "单品")}</span></button>`).join("") : `<div class="empty">这个分类还没有单品。</div>`;
      $all("[data-palette-category]").forEach(btn => btn.addEventListener("click", () => {
        state.paletteCategory = btn.dataset.paletteCategory;
        renderPalette();
      }));
      $all("[data-add-editor-item]").forEach(btn => btn.addEventListener("click", () => addEditorItem(btn.dataset.addEditorItem)));
    }
    function addEditorItem(itemId) {
      const item = visibleItems().find(next => next.item_id === itemId);
      if (!item) return;
      if (state.editorItems.some(entry => entry.id === itemId)) return toast("这件已经在画布里了。");
      state.editorItems.push(editorItemFromClosetItem(item, state.editorItems.length));
      state.activeEditorItemId = itemId;
      renderEditorCanvas();
    }
    function bindCanvasItems() {
      $all("[data-canvas-item]").forEach(el => {
        const handlePress = event => {
          if (event.target.closest("[data-delete-canvas]")) return;
          startCanvasDrag(event, el.dataset.canvasItem);
        };
        el.addEventListener("pointerdown", handlePress);
        el.addEventListener("mousedown", handlePress);
        el.addEventListener("click", event => {
          if (event.target.closest("[data-delete-canvas]")) return;
          const rect = el.getBoundingClientRect();
          const deleteHitSize = 52;
          if (event.clientX >= rect.right - deleteHitSize && event.clientY <= rect.top + deleteHitSize) {
            event.preventDefault();
            event.stopPropagation();
            deleteCanvasItem(el.dataset.canvasItem);
          }
        });
      });
      $all("[data-delete-canvas]").forEach(btn => {
        const remove = event => {
          event.preventDefault();
          event.stopPropagation();
          deleteCanvasItem(btn.dataset.deleteCanvas);
        };
        btn.addEventListener("pointerdown", remove);
        btn.addEventListener("mousedown", remove);
        btn.addEventListener("click", remove);
      });
    }
    function deleteCanvasItem(itemId) {
      state.editorItems = state.editorItems.filter(entry => entry.id !== itemId);
      state.activeEditorItemId = "";
      renderEditorCanvas();
    }
    function startCanvasDrag(event, itemId) {
      const entry = state.editorItems.find(item => item.id === itemId);
      if (!entry) return;
      const rect = event.currentTarget.getBoundingClientRect();
      const deleteHitSize = 46;
      if (event.clientX >= rect.right - deleteHitSize && event.clientY <= rect.top + deleteHitSize) {
        event.preventDefault();
        event.stopPropagation();
        deleteCanvasItem(itemId);
        return;
      }
      state.activeEditorItemId = itemId;
      const startX = event.clientX;
      const startY = event.clientY;
      const originX = entry.x;
      const originY = entry.y;
      const target = event.currentTarget;
      target.setPointerCapture?.(event.pointerId);
      function move(moveEvent) {
        entry.x = Math.max(-24, Math.min(310, originX + moveEvent.clientX - startX));
        entry.y = Math.max(-24, Math.min(382, originY + moveEvent.clientY - startY));
        renderEditorCanvas();
      }
      function up() {
        window.removeEventListener("pointermove", move);
        window.removeEventListener("pointerup", up);
      }
      window.addEventListener("pointermove", move);
      window.addEventListener("pointerup", up);
      renderEditorCanvas();
    }
    function applySmartLayout() {
      state.editorItems = state.editorItems.map((entry, index) => editorItemFromClosetItem(entry.item, index));
      state.activeEditorItemId = "";
      renderEditorCanvas();
      toast("已整理版面。");
    }
    async function saveEditorOutfit() {
      const itemIds = state.editorItems.map(entry => entry.id);
      if (!itemIds.length) return toast("请先添加单品。");
      const data = await fetchJSON("/closet/outfits", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ item_ids: itemIds, title: "我的搭配", scene_tags: ["自主搭配"] })
      });
      state.outfits.unshift(data);
      state.currentOutfit = data;
      renderAll();
      setPage("page-detail");
      toast("已保存新的穿搭方案。");
    }
    function renderTryonResult(imagePath) {
      const imageId = `tryonResultImage_${Date.now()}`;
      const hero = $("#tryonHero");
      hero.classList.remove("is-generating");
      hero.dataset.previewImage = imagePath ? assetURL(imagePath) : "";
      hero.dataset.previewTitle = imagePath ? "试穿结果" : "";
      hero.innerHTML = `${imagePath ? `<img id="${imageId}" class="image-loading" alt="试穿结果">` : `<div class="empty">选择一套搭配后，就能在这里查看试穿效果。</div>`}<div id="generatingLayer" class="generating-layer">${generatingLayerHTML()}</div>`;
      if (imagePath) loadImageInto(`#${imageId}`, imagePath);
      bindImagePreviews();
      $("#cancelGenerate")?.addEventListener("click", cancelTryonGeneration);
    }
    function renderTryonFailure(message) {
      const hero = $("#tryonHero");
      const outfit = state.currentOutfit || {};
      const outfitImage = outfit.cover_path ? withVersion(outfit.cover_path, outfit) : "";
      const model = currentModel();
      hero.classList.remove("is-generating");
      hero.dataset.previewImage = "";
      hero.dataset.previewTitle = "";
      hero.innerHTML = `<div class="tryon-failure">
        ${outfitImage ? `<div class="tryon-failure-preview"><img src="${escapeHTML(outfitImage)}" alt="${escapeHTML(outfit.title || "已选搭配")}"><span class="tryon-failure-model"><img src="${escapeHTML(model.src)}" alt="${escapeHTML(model.name || "当前照片")}"></span></div>` : ""}
        <h3>${escapeHTML(outfit.title || "已保留这套搭配")}</h3>
        <p>${escapeHTML(message || "这张照片暂时不适合这套搭配，可以更换照片后继续。")}</p>
        <button class="tryon-failure-change" id="changeTryonPhotoBtn" type="button">更换照片</button>
      </div>`;
      $("#changeTryonPhotoBtn")?.addEventListener("click", () => {
        openModelSheet();
        setModelMode("photo");
      });
    }
    function cancelTryonGeneration() {
      state.tryonAbortController?.abort();
      state.tryonAbortController = null;
      $("#generatingLayer")?.classList.remove("active");
      $("#tryonHero")?.classList.remove("is-generating");
    }
    async function currentModelFile() {
      const model = currentModel();
      const response = await fetch(model.src);
      if (!response.ok) throw new Error("当前模特图片暂时不可用。");
      const blob = await response.blob();
      return new File([blob], `${model.id || "model"}.png`, { type: blob.type || "image/png" });
    }
    function openBuilder(seedIds = []) {
      seedIds.forEach(id => state.selectedItems.add(id));
      renderBuilder();
      openSheet("builderSheet");
    }
    async function saveOutfit() {
      const itemIds = [...state.selectedItems];
      if (!itemIds.length) return toast("请先选择衣物。");
      const data = await fetchJSON("/closet/outfits", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ item_ids: itemIds, title: state.aiBrief || "我的搭配", scene_tags: state.aiBrief ? [state.aiBrief] : [] })
      });
      state.outfits.unshift(data);
      state.selectedItems.clear();
      closeSheet("builderSheet");
      state.closetMode = "outfits";
      setTab("closet");
      renderAll();
      toast(data.warnings?.[0] || "已保存为套装。");
    }
    async function tryOutfit(outfitId, options = {}) {
      if (!outfitId) {
        openBuilder();
        return toast("先保存套装后再试穿。");
      }
      const outfit = cleanOutfit(state.outfits.find(item => item.outfit_id === outfitId) || state.currentOutfit || await fetchJSON(`/closet/outfits/${encodeURIComponent(outfitId)}`));
      state.detailMode = "outfit";
      state.currentItem = null;
      state.currentOutfit = outfit;
      renderDetail();
      setPage("page-tryon");
      renderTryonResult("");
      $("#tryonHero").classList.add("is-generating");
      $("#generatingLayer").classList.add("active");
      updateTryonGeneratingState({ phase: "queued", progress: 8 });
      const body = new FormData();
      body.append("outfit_id", outfitId);
      body.append("photo_mode", state.currentModelId === "self" ? "standard" : "standard");
      body.append("person_image", await currentModelFile());
      if (options.forceRegenerate) body.append("force_regenerate", "true");
      const abortController = new AbortController();
      state.tryonAbortController = abortController;
      try {
        const job = options.retryJob && state.tryonJobId
          ? await fetchJSON(`/selfit/try-on/jobs/${encodeURIComponent(state.tryonJobId)}/retry`, { method: "POST", signal: abortController.signal })
          : await fetchJSON("/selfit/try-on/jobs", { method: "POST", body, signal: abortController.signal });
        state.tryonJobId = job.job_id;
        const data = await waitForTryonJob(job.job_id, abortController.signal);
        state.tryonResult = data;
        renderTryonResult(data.result?.image_path || "");
        if (data.record?.image_path) state.records.unshift(data.record);
        renderProfile();
        toast(data.result?.user_message || data.decision?.user_message || "已生成试穿记录。");
      } catch (error) {
        const message = error.name === "AbortError" ? "已取消生成。" : (error.message || "这次没有生成成功，可以换张更清楚的照片再试。");
        renderTryonFailure(message);
        toast(message);
      } finally {
        if (state.tryonAbortController === abortController) state.tryonAbortController = null;
      }
    }
    async function waitForTryonJob(jobId, signal) {
      for (let attempt = 0; attempt < 360; attempt += 1) {
        if (signal?.aborted) throw new DOMException("已取消", "AbortError");
        let job;
        try {
          job = await fetchJSON(`/selfit/try-on/jobs/${encodeURIComponent(jobId)}`, { signal });
        } catch (error) {
          if (error.status !== 429) throw error;
          const retryDelay = Math.max(1200, Math.min(15000, Number(error.retryAfterSeconds || 2) * 1000));
          const title = $("#generatingText");
          const copy = $("#tryonGeneratingCopy");
          if (title) title.textContent = "试穿任务还在继续";
          if (copy) copy.textContent = "进度查询暂时拥挤，已为你保留任务，稍后会自动继续查看。";
          await waitWithSignal(retryDelay, signal);
          continue;
        }
        if (job.status === "processing") {
          updateTryonGeneratingState(job);
        }
        if (job.status === "completed") return job.result;
        if (job.status === "failed") {
          const error = new Error(job.error?.message || "这次试穿没有完成。");
          error.result = job.result;
          throw error;
        }
        const pollDelay = attempt < 5 ? 1000 : attempt < 20 ? 1500 : 2500;
        await waitWithSignal(pollDelay, signal);
      }
      throw new Error("试穿生成时间较长，任务仍在后台进行。");
    }
    async function tryCurrentItem() {
      const item = state.currentItem;
      if (!item) return toast("先选择一件单品。");
      if (!["top", "bottom", "skirt", "dress"].includes(item.category)) {
        const companions = smartItemRecommendations(item, 3).map(entry => entry.item.item_id);
        openBuilder([item.item_id, ...companions]);
        return toast("鞋包和配饰需要和主服装一起试穿，已为你选了一组搭配。");
      }
      const label = item.category_label || labels[item.category] || "单品";
      try {
        const outfit = await fetchJSON("/closet/outfits", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ item_ids: [item.item_id], title: `试穿·${label}`, scene_tags: ["单品试穿"] })
        });
        state.outfits.unshift(outfit);
        await tryOutfit(outfit.outfit_id);
      } catch (error) {
        toast(error.message || "这件单品暂时无法试穿。");
      }
    }
    async function toggleFavorite(outfitId) {
      if (!outfitId) return toast("这套搭配保存后就能收藏。");
      const outfit = state.outfits.find(item => item.outfit_id === outfitId);
      if (!outfit) return;
      const nextFavorite = !outfit.favorite;
      const nextCount = Math.max(0, (Number(outfit.favorite_count) || 0) + (nextFavorite ? 1 : -1));
      const data = await fetchJSON(`/closet/outfits/${outfitId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ favorite: nextFavorite, favorite_count: nextCount })
      });
      const index = state.outfits.findIndex(item => item.outfit_id === outfitId);
      if (index >= 0) state.outfits[index] = data;
      renderAll();
      toast(nextFavorite ? "已收藏。" : "已取消收藏。");
    }
    async function toggleItemFavorite(itemId) {
      if (!itemId) return;
      const item = state.items.find(next => next.item_id === itemId);
      if (!item) return;
      const nextFavorite = !item.favorite;
      const data = await fetchJSON(`/closet/items/${itemId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ favorite: nextFavorite })
      });
      const index = state.items.findIndex(next => next.item_id === itemId);
      if (index >= 0) state.items[index] = data;
      renderCloset();
      toast(nextFavorite ? "已收藏单品。" : "已取消收藏。");
    }
    async function askStylist(prefillMessage = "") {
      const input = $("#aiPromptInput");
      if (isAIResponding()) return stopAIResponse();
      const message = normalizeAIInputText(prefillMessage || input.value);
      if (!message) return toast("先输入想问的穿搭问题。");
      if (!state.currentSessionId) await createNewStylistSession();
      preserveCurrentAIArtifactsOnLastMessage();
      stopAITextStream();
      stopAIToolProgress();
      const abortController = new AbortController();
      state.aiAbortController = abortController;
      const intent = inferAIIntent(message);
      const useXHSSkill = intent.useXHS;
      const conversationContext = buildAIConversationContext(message);
      state.aiBrief = message;
      state.aiMessages.push({ role: "user", content: message });
      input.value = "";
      state.aiStreamingText = null;
      state.aiStreamingDone = true;
      state.aiToolsExpanded = true;
      state.aiLoadingSteps = defaultAIToolSteps(message);
      state.aiVisibleToolCount = 1;
      state.aiResult = { status: "loading", assistant_message: useXHSSkill ? "正在找和你这句相关的参考..." : "正在整理你的穿搭需求...", tool_steps: state.aiLoadingSteps };
      renderAIResult();
      startAIToolProgress();
      try {
        const data = await fetchJSON("/stylist/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          signal: abortController.signal,
          body: JSON.stringify({
            message,
            session_id: state.currentSessionId || "selfit-inspiration",
            context: {
              source: "inspiration_tab",
              item_count: state.items.length,
              outfit_count: state.outfits.length,
              conversation: state.aiMessages.slice(-8),
              current_query: message,
              recent_user_queries: conversationContext.recent_user_queries,
              conversation_context: conversationContext,
              user_intent: intent,
              mock_profile: {
                type: state.profile.key,
                role: state.profile.role,
                preferences: state.profile.preference,
                feed_focus: state.profile.feed.map(item => item[0]),
                style_persona: state.stylePersona ? {
                  type_id: state.stylePersona.typeId,
                  name: state.stylePersona.metadata?.name,
                  code: state.stylePersona.metadata?.code,
                  keywords: state.stylePersona.keywords || [],
                  summary: state.stylePersona.summary || "",
                  colors: stylePersonaColors().map(color => ({ name: color.name, value: color.value })),
                } : null,
              },
              xiaohongshu_preferred: useXHSSkill,
              requested_skills: [
                ...(intent.useCapsule ? ["capsule-wardrobe"] : []),
                ...(useXHSSkill ? ["xhs-trend-research"] : []),
              ],
            }
          })
        });
        if (abortController.signal.aborted) return;
        stopAIToolProgress();
        state.aiAbortController = null;
        state.aiResult = data;
        if (data.session_id) {
          state.currentSessionId = data.session_id;
          writeStore(stylistSessionStoreKey, data.session_id);
        }
        const assistantMessage = data.assistant_message || "我已经理解你的需求。";
        state.aiStreamingText = "";
        state.aiStreamingDone = false;
        state.aiToolsExpanded = false;
        state.aiMessages.push({
          role: "assistant",
          content: assistantMessage,
          tool_steps: Array.isArray(data.tool_steps) ? data.tool_steps : [],
          xhs_notes: Array.isArray(data.xhs_notes) ? data.xhs_notes : [],
          evidence_sources: Array.isArray(data.evidence_sources) ? data.evidence_sources : [],
          rationale: Array.isArray(data.rationale) ? data.rationale : [],
        });
        if (data.recommended_outfits?.length) state.outfits = [...data.recommended_outfits, ...state.outfits.filter(outfit => !data.recommended_outfits.some(next => next.outfit_id === outfit.outfit_id))];
        renderAll();
        loadStylistSessions().catch(() => updateSessionTitle());
        startAITextStream(assistantMessage);
        toast(data.mode === "demo" ? "当前是演示建议。" : "已生成穿搭建议。");
      } catch (error) {
        if (abortController.signal.aborted || error.name === "AbortError") {
          state.aiAbortController = null;
          if (state.aiResult?.status !== "stopped") stopAIResponse();
          else updateAISendButton();
          return;
        }
        stopAITextStream();
        stopAIToolProgress();
        state.aiAbortController = null;
        const content = error.message || "暂时灵感耗尽，正在努力充能～";
        state.aiMessages.push({ role: "assistant", content });
        state.aiStreamingText = null;
        state.aiStreamingDone = true;
        state.aiToolsExpanded = false;
        state.aiResult = { status: "failed", assistant_message: content, error: { message: content } };
        renderAIResult();
        toast(error.message || "暂时灵感耗尽，正在努力充能～");
      }
    }
    function handleAISend() {
      if (isAIResponding()) {
        stopAIResponse();
        return;
      }
      askStylist();
    }
    function bindOutfitActions() {
      bindImagePreviews();
      $all("[data-open-outfit]").forEach(card => card.addEventListener("click", () => openOutfitDetail(card.dataset.openOutfit)));
      $all("[data-home-outfit]").forEach(btn => btn.addEventListener("click", event => {
        event.stopPropagation();
        openOutfitDetail(btn.dataset.homeOutfit);
      }));
      $all("[data-favorite-outfit]").forEach(btn => btn.addEventListener("click", event => {
        event.preventDefault();
        event.stopPropagation();
        toggleFavorite(btn.dataset.favoriteOutfit);
      }));
    }
    function renderImportReview(message = "") {
      const items = state.importReviewItems || [];
      $("#importReviewTitle").textContent = items.length ? `识别到 ${items.length} 件单品` : "没有可入柜的单品";
      $("#importReviewCopy").textContent = message || (items.length ? "看看是否每件衣物都完整，分类不对可以直接修改。" : "换一张衣物完整、光线清晰的图片再试试。");
      $("#importReviewGrid").innerHTML = items.map(item => `
        <article class="import-review-card" data-import-review-item="${item.item_id}">
          <img class="import-review-image" src="${publicCutoutImg(item)}" alt="${escapeHTML(item.category_label || labels[item.category] || "单品")}">
          <button class="import-review-remove" type="button" data-import-remove="${item.item_id}" aria-label="移除这件单品">×</button>
          <select class="import-review-select" data-import-category="${item.item_id}" aria-label="修改单品分类">
            ${categoryOrder.filter(category => category !== "all").map(category => `<option value="${category}" ${item.category === category ? "selected" : ""}>${escapeHTML(labels[category])}</option>`).join("")}
          </select>
        </article>
      `).join("");
      $("#importReviewDone").textContent = items.length ? "完成入柜" : "返回重新上传";
      $all("[data-import-category]").forEach(select => select.addEventListener("change", async () => {
        try {
          const updated = await fetchJSON(`/closet/items/${encodeURIComponent(select.dataset.importCategory)}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ category: select.value })
          });
          const index = state.importReviewItems.findIndex(item => item.item_id === updated.item_id);
          if (index >= 0) state.importReviewItems[index] = updated;
          await loadData();
          toast("已更新分类。");
        } catch (error) {
          toast(error.message || "分类修改失败。");
        }
      }));
      $all("[data-import-remove]").forEach(button => button.addEventListener("click", async () => {
        try {
          const itemId = button.dataset.importRemove;
          await fetchJSON(`/closet/items/${encodeURIComponent(itemId)}`, { method: "DELETE" });
          state.importReviewItems = state.importReviewItems.filter(item => item.item_id !== itemId);
          await loadData();
          renderImportReview();
        } catch (error) {
          toast(error.message || "移除失败。");
        }
      }));
    }
    function showImportReview(data) {
      state.importReviewItems = data.items || [];
      state.importDraftOutfit = data.draft_outfit || null;
      const draftCopy = state.importDraftOutfit ? " 这些单品已按原图关系组成一套待确认穿搭。" : "";
      renderImportReview(`${data.message || ""}${draftCopy}`.trim());
      closeSheet("uploadSheet");
      openSheet("importReviewSheet");
    }
    async function uploadFiles(files) {
      if (!files.length) return;
      $("#uploadStatus").textContent = "正在准备提取...";
      $("#retryImportBtn").hidden = true;
      const body = new FormData();
      [...files].forEach(file => body.append("images", file));
      try {
        const job = await fetchJSON("/closet/import/jobs", { method: "POST", body });
        state.importJobId = job.job_id;
        const data = await waitForImportJob(job.job_id);
        $("#uploadStatus").textContent = data.message || "已放入衣橱。";
        await loadData();
        showImportReview(data);
      } catch (error) {
        $("#uploadStatus").textContent = error.message || "这张图暂时无法拆解，请换一张更清晰的图片。";
        $("#retryImportBtn").hidden = !state.importJobId;
        toast($("#uploadStatus").textContent);
      } finally {
        $("#wearUploadInput").value = "";
      }
    }
    async function waitForImportJob(jobId) {
      for (let attempt = 0; attempt < 300; attempt += 1) {
        const job = await fetchJSON(`/closet/import/jobs/${encodeURIComponent(jobId)}`);
        $("#uploadStatus").textContent = job.status === "queued"
          ? "已排队，马上开始识别。"
          : job.status === "processing"
            ? `正在提取并抟图·${Math.max(1, Number(job.progress || 0))}%`
            : $("#uploadStatus").textContent;
        if (job.status === "completed") return job.result || { items: [], summary: { created: 0 } };
        if (job.status === "failed") throw new Error(job.error?.message || "这次提取没有完成。");
        await new Promise(resolve => window.setTimeout(resolve, 900));
      }
      throw new Error("提取时间较长，任务仍在后台处理，请稍后重试查看。");
    }
    async function retryCurrentImport() {
      if (!state.importJobId) return;
      $("#retryImportBtn").hidden = true;
      try {
        const job = await fetchJSON(`/closet/import/jobs/${encodeURIComponent(state.importJobId)}/retry`, { method: "POST" });
        const data = await waitForImportJob(job.job_id);
        await loadData();
        showImportReview(data);
      } catch (error) {
        $("#uploadStatus").textContent = error.message || "重试失败，请换一张图片。";
        $("#retryImportBtn").hidden = false;
      }
    }
    function openColorUpload() {
      setPage("page-color");
    }
    function previewColorFile(file) {
      state.colorFile = file || null;
      $("#startColorBtn").disabled = !state.colorFile;
      $("#colorResult").style.display = "none";
      if (!file) {
        $("#colorUploadZone").innerHTML = `<span><b style="color:var(--ink);font-size:18px;">选择自拍图片</b><br>支持 JPG、PNG、WebP</span>`;
        return;
      }
      const url = URL.createObjectURL(file);
      $("#colorUploadZone").innerHTML = `<img src="${url}" alt="自拍预览">`;
    }
    async function runColorTest() {
      if (!state.colorFile) return toast("请先选择自拍图片。");
      $("#startColorBtn").disabled = true;
      $("#startColorBtn").textContent = "正在分析";
      const body = new FormData();
      body.append("image", state.colorFile);
      try {
        const data = await fetchJSON("/analyze", { method: "POST", body });
        const result = data.result || data.seasonal_result || data;
        const season = result.season || result.primary_season || data.consumer_result?.title || "已完成初步分析";
        $("#colorResult").style.display = "block";
        $("#colorResult").innerHTML = `<b>${escapeHTML(season)}</b><br>结果已记录为selfit风格参考，后续推荐会优先考虑更适合你的颜色方向。`;
        toast("色彩测试完成。");
      } catch (error) {
        $("#colorResult").style.display = "block";
        $("#colorResult").innerHTML = escapeHTML(error.message || "这张照片暂时无法分析，换一张自然光自拍会更准。");
      } finally {
        $("#startColorBtn").disabled = false;
        $("#startColorBtn").textContent = "开始色彩测试";
      }
    }
    async function importLink() {
      const url = $("#wearLinkInput").value.trim();
      if (!url) return toast("请先粘贴链接。");
      $("#uploadStatus").textContent = "正在解析链接...";
      const body = new FormData();
      body.append("url", url);
      const data = await fetchJSON("/closet/import/link", { method: "POST", body });
      $("#uploadStatus").textContent = data.message || "已导入衣橱。";
      await loadData();
      showImportReview(data);
    }
    $all("[data-tab]").forEach(btn => btn.addEventListener("click", () => setTab(btn.dataset.tab, { historyMode: "push" })));
    window.addEventListener("popstate", () => {
      const requestedTab = new URLSearchParams(window.location.search).get("tab");
      setTab(["home", "ai", "closet", "me"].includes(requestedTab) ? requestedTab : "home", { historyMode: "none" });
    });
    window.addEventListener("scroll", maybeLoadMoreHomeOutfits, { passive: true });
    $("#logoutBtn").addEventListener("click", openLogoutConfirm);
    $("#logoutCancelBtn").addEventListener("click", closeLogoutConfirm);
    $("#logoutConfirmBtn").addEventListener("click", logoutSelfitUser);
    $("#logoutConfirm").addEventListener("click", event => {
      if (event.target.id === "logoutConfirm") closeLogoutConfirm();
    });
    $all("[data-tab-shortcut]").forEach(btn => btn.addEventListener("click", () => setTab(btn.dataset.tabShortcut, { historyMode: "push" })));
    $all("[data-closet-mode]").forEach(btn => btn.addEventListener("click", () => { state.closetMode = btn.dataset.closetMode; renderCloset(); }));
    $all("[data-close]").forEach(btn => btn.addEventListener("click", () => closeSheet(btn.dataset.close)));
    $all("[data-back-home]").forEach(btn => btn.addEventListener("click", () => setTab("home")));
    $all("[data-back-detail]").forEach(btn => btn.addEventListener("click", () => setTab(state.detailReturnTab || "home")));
    $all("[data-open-detail]").forEach(btn => btn.addEventListener("click", () => state.currentOutfit ? setPage("page-detail") : setTab("home")));
    $("#mainPlus").addEventListener("click", () => openSheet("uploadSheet"));
    $("#homeTryAction").addEventListener("click", () => {
      const first = visibleOutfits()[0];
      if (first?.outfit_id) return openOutfitDetail(first.outfit_id);
      $("#uploadStatus").textContent = "先上传一件想试的衣服，识别完成后就可以直接生成试穿图。";
      openSheet("uploadSheet");
    });
    $("#homeExtractAction").addEventListener("click", () => {
      $("#uploadStatus").textContent = "粘贴喜欢的内容链接，我会提取其中可识别的衣服。";
      openSheet("uploadSheet");
      window.setTimeout(() => $("#wearLinkInput").focus(), 220);
    });
    $("#homeAskAction").addEventListener("click", () => setTab("ai"));
    $("#handoffContinue").addEventListener("click", closePersonaHandoff);
    [$("#profilePersonaLink")].forEach(button => button?.addEventListener("click", () => {
      window.location.href = button.dataset.reportUrl || "/selfit";
    }));
    $("#profileColorCell").addEventListener("click", openColorUpload);
    $("#modelCell").addEventListener("click", openModelSheet);
    $("#sessionPickerBtn").addEventListener("click", toggleSessionSidebar);
    $("#sessionBackdrop").addEventListener("click", () => closeSheet("sessionSheet"));
    $("#sessionSheetNew").addEventListener("click", () => createNewStylistSession().catch(error => toast(error.message || "新建会话失败。")));
    $("#sessionRenameBtn").addEventListener("click", () => renameSelectedSession().catch(error => toast(error.message || "修改失败。")));
    $("#sessionDeleteMenuBtn").addEventListener("click", openSessionDeleteConfirm);
    $("#sessionCancelDeleteBtn").addEventListener("click", closeSessionDeleteConfirm);
    $("#sessionDeleteConfirm").addEventListener("click", event => {
      if (event.target.id === "sessionDeleteConfirm") closeSessionDeleteConfirm();
    });
    $("#sessionConfirmDeleteBtn").addEventListener("click", () => confirmDeleteSelectedSession().catch(error => toast(error.message || "删除失败。")));
    $("#recordEditBtn").addEventListener("click", toggleRecordEditing);
    $("#recordDeleteBtn").addEventListener("click", deleteSelectedProfileEntries);
    $all("[data-profile-view]").forEach(btn => btn.addEventListener("click", () => {
      state.profileView = btn.dataset.profileView || "records";
      state.recordEditing = false;
      state.selectedRecordIds.clear();
      state.selectedWorkIds.clear();
      renderProfile();
    }));
    $all("[data-work-view]").forEach(btn => btn.addEventListener("click", () => {
      state.profileWorkView = btn.dataset.workView || "outfits";
      state.recordEditing = false;
      state.selectedWorkIds.clear();
      renderProfile();
    }));
    $all("[data-model-mode]").forEach(btn => btn.addEventListener("click", () => setModelMode(btn.dataset.modelMode)));
    $("#confirmModelBtn").addEventListener("click", confirmPresetModel);
    $("#selfModelInput").addEventListener("change", event => {
      const file = event.target.files?.[0];
      if (!file) return;
      if (state.selfModelUrl?.startsWith("blob:")) URL.revokeObjectURL(state.selfModelUrl);
      state.selfModelUrl = URL.createObjectURL(file);
      renderSelfModelPhoto();
    });
    $("#confirmSelfModel").addEventListener("click", () => {
      if (!state.selfModelUrl) return toast("请先上传一张照片。");
      state.currentModelId = "self";
      updateCurrentModelUI();
      closeSheet("modelSheet");
      saveCurrentModelPreference();
      toast("已使用我的照片。");
    });
    $("#refreshInspiration").addEventListener("click", async () => {
      $("#refreshNote").textContent = "正在刷新灵感穿搭...";
      try {
        await loadRankedOutfits(state.recommendationOffset);
        state.todayIndex = 0;
        renderHome();
        $("#refreshNote").textContent = state.outfits.length ? "已经换了一组与你风格相近的灵感。" : `已按${state.stylePersona?.metadata?.name || "你的风格"}换了一组参考。`;
      } catch (error) {
        $("#refreshNote").textContent = "暂时没有更多符合的穿搭。";
      }
    });
    $("#uploadGarmentBtn").addEventListener("click", () => $("#wearUploadInput").click());
    $("#cameraBtn").addEventListener("click", () => $("#wearUploadInput").click());
    $("#wearUploadInput").addEventListener("change", event => uploadFiles(event.target.files || []));
    $("#retryImportBtn").addEventListener("click", retryCurrentImport);
    $("#wearLinkBtn").addEventListener("click", importLink);
    $("#importReviewDone").addEventListener("click", async () => {
      const hasItems = state.importReviewItems.length > 0;
      const draftOutfit = state.importDraftOutfit;
      closeSheet("importReviewSheet");
      if (!hasItems) return openSheet("uploadSheet");
      if (draftOutfit?.outfit_id) {
        try {
          const confirmed = await fetchJSON(`/closet/outfits/${encodeURIComponent(draftOutfit.outfit_id)}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ draft: false })
          });
          const index = state.outfits.findIndex(outfit => outfit.outfit_id === confirmed.outfit_id);
          if (index >= 0) state.outfits[index] = confirmed;
        } catch (error) {}
      }
      setTab("closet", { historyMode: "push" });
      toast(draftOutfit ? `已入柜 ${state.importReviewItems.length} 件单品，并保留为一套待确认穿搭。` : `已将 ${state.importReviewItems.length} 件单品放入衣橱。`);
      state.importReviewItems = [];
      state.importDraftOutfit = null;
    });
    $("#detailEditBtn").addEventListener("click", () => {
      if (state.detailMode === "item" && state.currentItem) return openBuilder([state.currentItem.item_id]);
      if (!state.currentOutfit) return toast("先选择一套搭配。");
      if (!state.editorItems.length) state.editorItems = visibleItems(state.currentOutfit.items || []).map((item, index) => editorItemFromClosetItem(item, index));
      renderEditor();
      setPage("page-editor");
    });
    $("#detailTryBtn").addEventListener("click", () => state.detailMode === "item" ? tryCurrentItem() : (state.currentOutfit ? tryOutfit(state.currentOutfit.outfit_id) : toast("先选择一套搭配。")));
    $("#detailShare").addEventListener("click", async () => {
      const title = state.detailMode === "item" ? (state.currentItem?.category_label || "我的 selfit 单品") : (state.currentOutfit?.title || "我的 selfit 穿搭");
      if (navigator.share) {
        await navigator.share({ title, text: `这套搭配很像我：${title}` }).catch(() => {});
      } else {
        await navigator.clipboard?.writeText(`${title} · selfit`).catch(() => {});
        toast("搭配名称已复制。\\n可以发给朋友一起看看。");
      }
    });
    $("#tryAnotherBtn").addEventListener("click", () => setTab("home"));
    $("#retryTryonBtn").addEventListener("click", () => state.currentOutfit ? tryOutfit(state.currentOutfit.outfit_id, { forceRegenerate: true, retryJob: true }) : toast("先选择一套搭配。"));
    $("#tryonSaveBtn").addEventListener("click", () => toast("已保存到试穿记录。"));
    $("#colorUploadInput").addEventListener("change", event => previewColorFile(event.target.files?.[0]));
    $("#startColorBtn").addEventListener("click", runColorTest);
    $("#smartLayoutBtn").addEventListener("click", applySmartLayout);
    $("#editorSaveBtn").addEventListener("click", saveEditorOutfit);
    $("#floatingMatch").addEventListener("click", () => openBuilder());
    $("#saveOutfitBtn").addEventListener("click", saveOutfit);
    $("#tryOutfitBtn").addEventListener("click", async () => {
      await saveOutfit();
      const first = state.outfits[0];
      if (first) await tryOutfit(first.outfit_id);
    });
    $("#aiSendBtn").addEventListener("click", () => {
      handleAISend();
    });
    $("#imageLightboxImg").addEventListener("click", event => {
      event.preventDefault();
      event.stopPropagation();
    });
    $("#imageLightboxZoom").addEventListener("click", event => {
      event.preventDefault();
      event.stopPropagation();
      toggleImagePreviewZoom();
    });
    $("#imageLightboxClose").addEventListener("click", closeImagePreview);
    $("#imageLightbox").addEventListener("click", event => {
      if (event.target.id === "imageLightbox" || event.target.classList.contains("image-lightbox-stage")) closeImagePreview();
    });
    window.addEventListener("keydown", event => {
      if (event.key === "Escape" && $("#imageLightbox").classList.contains("open")) closeImagePreview();
    });
    $("#aiPromptInput").addEventListener("keydown", event => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        handleAISend();
      }
    });
    $("#aiPromptInput").addEventListener("input", updateAISendButton);
    $("#aiPromptInput").addEventListener("paste", event => {
      const text = event.clipboardData?.getData("text/plain") || "";
      if (!text) return;
      event.preventDefault();
      insertNormalizedPromptText(event.currentTarget, text);
    });
    $("#cancelGenerate")?.addEventListener("click", cancelTryonGeneration);
    document.addEventListener("error", event => {
      const image = event.target;
      if (!(image instanceof HTMLImageElement) || image.closest(".login-screen")) return;
      image.style.display = "none";
      image.parentElement?.classList.add("asset-missing");
    }, true);
    $(".ai-input").style.display = "none";
    loadStylePersona();
    const initialTab = new URLSearchParams(window.location.search).get("tab");
    setTab(["home", "ai", "closet", "me"].includes(initialTab) ? initialTab : "home", { historyMode: "none" });
    initializeAuth().catch(error => toast(error.message || "加载失败"));
  </script>
</body>
</html>
"""


def _normalize_inventory_candidates(raw_items: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_items, list):
        return []
    candidates: list[dict[str, Any]] = []
    for raw in raw_items[:16]:
        if not isinstance(raw, dict):
            continue
        category = str(raw.get("category") or "").strip().lower()
        if category not in CLOSET_SUPPORTED_CATEGORIES:
            continue
        bbox = _normalize_inventory_bbox(raw.get("bbox"))
        if bbox is None:
            continue
        try:
            confidence = max(0.0, min(1.0, float(raw.get("confidence") or 0.68)))
        except (TypeError, ValueError):
            confidence = 0.68
        if confidence < 0.5:
            continue
        candidate = {
            "category": category,
            "bbox": bbox,
            "confidence": confidence,
            "colors": _string_list(raw.get("colors")),
            "material": _string_list(raw.get("material")),
            "style_tags": _string_list(raw.get("style_tags")),
        }
        if raw.get("fully_visible") is False or _inventory_candidate_is_nonfashion(candidate) or _inventory_candidate_is_clipped(candidate):
            continue
        if any(
            previous["category"] == category and _inventory_bbox_iou(previous["bbox"], bbox) >= 0.82
            for previous in candidates
        ):
            continue
        candidates.append(candidate)
    return candidates[:12]


def _inventory_candidate_is_nonfashion(candidate: dict[str, Any]) -> bool:
    if candidate.get("category") != "accessory":
        return False
    evidence = " ".join([*candidate.get("material", []), *candidate.get("style_tags", [])]).lower()
    blocked_terms = {
        "towel", "terrycloth", "bath towel", "blanket", "bedding", "bedsheet", "bed sheet",
        "curtain", "upholstery", "pillow", "napkin", "tablecloth", "rug", "carpet",
        "毛巾", "浴巾", "毯", "床单", "窗帘", "枕", "地毯", "桌布",
    }
    return any(term in evidence for term in blocked_terms)


def _inventory_candidate_is_clipped(candidate: dict[str, Any]) -> bool:
    """Drop garments whose primary silhouette clearly runs outside the image."""
    category = candidate.get("category")
    if category not in {"top", "bottom", "skirt", "dress", "shoes", "bag"}:
        return False
    bbox = candidate["bbox"]
    right = bbox["x"] + bbox["width"]
    bottom = bbox["y"] + bbox["height"]
    return bbox["x"] <= 0.002 or bbox["y"] <= 0.002 or right >= 0.998 or bottom >= 0.998


def _normalize_inventory_bbox(raw: Any) -> dict[str, float] | None:
    if not isinstance(raw, dict):
        return None
    try:
        x = float(raw.get("x"))
        y = float(raw.get("y"))
        width = float(raw.get("width"))
        height = float(raw.get("height"))
    except (TypeError, ValueError):
        return None
    # Gemini-family vision models occasionally return percentages or their
    # conventional 0-1000 coordinate space despite a normalized-coordinate
    # prompt. Accept those deterministic variants instead of dropping every
    # otherwise valid candidate during clamping.
    coordinate_max = max(abs(x), abs(y), abs(width), abs(height))
    if coordinate_max > 1.0:
        scale = 100.0 if coordinate_max <= 100.0 else 1000.0
        x, y, width, height = x / scale, y / scale, width / scale, height / scale
    x = max(0.0, min(1.0, x))
    y = max(0.0, min(1.0, y))
    width = max(0.0, min(1.0 - x, width))
    height = max(0.0, min(1.0 - y, height))
    if width * height < 0.0025 or width < 0.025 or height < 0.025:
        return None
    return {"x": round(x, 5), "y": round(y, 5), "width": round(width, 5), "height": round(height, 5)}


def _inventory_bbox_iou(left: dict[str, float], right: dict[str, float]) -> float:
    lx2, ly2 = left["x"] + left["width"], left["y"] + left["height"]
    rx2, ry2 = right["x"] + right["width"], right["y"] + right["height"]
    overlap_width = max(0.0, min(lx2, rx2) - max(left["x"], right["x"]))
    overlap_height = max(0.0, min(ly2, ry2) - max(left["y"], right["y"]))
    intersection = overlap_width * overlap_height
    union = left["width"] * left["height"] + right["width"] * right["height"] - intersection
    return intersection / max(0.000001, union)


def _save_inventory_candidate_crop(source: dict[str, Any], candidate: dict[str, Any], work_dir: Path, index: int) -> Path:
    image: Image.Image = source["image"].convert("RGB")
    bbox = candidate["bbox"]
    left = int(bbox["x"] * image.width)
    top = int(bbox["y"] * image.height)
    right = int((bbox["x"] + bbox["width"]) * image.width)
    bottom = int((bbox["y"] + bbox["height"]) * image.height)
    pad = max(8, int(max(right - left, bottom - top) * 0.08))
    crop_box = (
        max(0, left - pad),
        max(0, top - pad),
        min(image.width, right + pad),
        min(image.height, bottom + pad),
    )
    target = work_dir / f"inventory_{index:02d}_{candidate['category']}.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    image.crop(crop_box).save(target, "PNG")
    return target


def _merge_inventory_items(primary: list[dict[str, Any]], supplements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged = list(primary)
    primary_categories = {item.get("category") for item in primary}
    for item in supplements:
        if item.get("category") in primary_categories:
            continue
        merged.append(item)
    return merged


def _items_for_source(manifest: dict[str, Any], image_id: str) -> list[dict[str, Any]]:
    return [
        item
        for item in manifest.get("items", [])
        if not item.get("deleted")
        and str(item.get("source", {}).get("image_id") or item.get("source", {}).get("source_group_id") or "") == image_id
    ]


def _ensure_source_outfit(source_group_id: str, items: list[dict[str, Any]]) -> dict[str, Any] | None:
    usable_items = [item for item in items if not item.get("deleted") and item.get("item_id")]
    if len(usable_items) < 2 or not any(item.get("category") in {"top", "bottom", "skirt", "dress"} for item in usable_items):
        return None
    data = _ensure_outfit_manifest()
    existing = next(
        (
            outfit
            for outfit in data.get("outfits", [])
            if not outfit.get("deleted") and outfit.get("source_group_id") == source_group_id
        ),
        None,
    )
    if existing:
        return _resolve_outfit(existing)
    item_ids = [str(item["item_id"]) for item in usable_items[:8]]
    outfit_id = hashlib.sha256(f"auto-split:{source_group_id}:{':'.join(item_ids)}".encode("utf-8")).hexdigest()[:16]
    layout = _build_outfit_cover(outfit_id, usable_items[:8])
    now = _now_iso()
    outfit = {
        "outfit_id": outfit_id,
        "user_id": storage_context().user_id,
        "title": "本次拆出的穿搭",
        "item_ids": item_ids,
        "cover_path": _public_closet_path(layout["path"]),
        "layout_version": layout["layout_version"],
        "layout_snapshot_path": _public_closet_path(layout["path"]),
        "layout_slots": layout["layout_slots"],
        "display_item_ids": layout["display_item_ids"],
        "overflow_items": layout["overflow_items"],
        "warnings": layout["warnings"],
        "scene_tags": ["拆款待确认"],
        "source_group_id": source_group_id,
        "origin": "auto_split",
        "draft": True,
        "favorite_count": 0,
        "favorite": False,
        "created_at": now,
        "updated_at": now,
        "deleted": False,
    }
    data.setdefault("outfits", []).append(outfit)
    _write_outfit_manifest(data)
    return _resolve_outfit(outfit)


def _import_sources(
    sources: list[dict[str, Any]],
    import_type: str,
    source_url: str | None = None,
    final_url: str | None = None,
    progress_callback: Any | None = None,
) -> dict[str, Any]:
    manifest = _ensure_manifest()
    all_items: list[dict[str, Any]] = []
    cached_items: list[dict[str, Any]] = []
    rejected = 0
    used_fallback = False
    ai_attempts: list[dict[str, Any]] = []
    inventory_attempts: list[dict[str, Any]] = []
    extraction_modes: list[str] = []
    ai_cutout = AIGarmentCutoutProvider()
    segmenter = SegFormerClothesAdapter()

    for index, source in enumerate(sources):
        cached_for_source = _items_for_source(manifest, source["image_id"])
        if cached_for_source:
            cached_items.extend(cached_for_source)
            extraction_modes.append("source_cache")
            if progress_callback:
                progress_callback(index + 1, len(sources), "cached")
            continue
        work_dir = _closet_item_dir() / source["image_id"]
        work_dir.mkdir(parents=True, exist_ok=True)
        extracted = ai_cutout.extract_inventory(source, work_dir)
        inventory_attempt = {"image_id": source["image_id"], **ai_cutout.last_attempt}
        inventory_attempts.append(inventory_attempt)
        inventory_confirmed_empty = inventory_attempt.get("reason") == "no_inventory"
        if extracted:
            extraction_modes.append("ai_inventory")
            expected_count = int(inventory_attempt.get("expected_count") or 0)
            if len(extracted) < expected_count and segmenter.available():
                supplements = segmenter.extract(source, work_dir)
                extracted = _merge_inventory_items(extracted, supplements)
                used_fallback = bool(supplements)
        else:
            if inventory_confirmed_empty:
                # A valid AI inventory response explicitly found no fashion
                # objects. Give the semantic single-item analyzer one second
                # opinion, but do not let a generic segmentation/fallback shape
                # detector turn towels or scenery into closet items.
                extracted = ai_cutout.extract(source, work_dir)
                ai_attempts.append({"image_id": source["image_id"], **ai_cutout.last_attempt})
                if extracted:
                    extraction_modes.append("single_ai_after_empty_inventory")
            else:
                segmented = segmenter.extract(source, work_dir) if segmenter.available() else []
                if len(segmented) >= 2:
                    used_fallback = True
                    extracted = segmented
                    extraction_modes.append("segformer_inventory")
                else:
                    extracted = ai_cutout.extract(source, work_dir)
                    ai_attempts.append({"image_id": source["image_id"], **ai_cutout.last_attempt})
                    if extracted:
                        extraction_modes.append("single_ai")
                    elif segmented:
                        used_fallback = True
                        extracted = segmented
                        extraction_modes.append("single_segformer")
        if not extracted and not inventory_confirmed_empty:
            used_fallback = True
            extracted = _extract_with_top_fallback(source, index, work_dir)
            if extracted:
                extraction_modes.append("single_legacy_fallback")
        if not extracted:
            rejected += 1
        for item in extracted:
            if item.get("quality", {}).get("status") == "rejected":
                rejected += 1
                continue
            all_items.append(item)
        if progress_callback:
            progress_callback(index + 1, len(sources), "extracted")

    now = _now_iso()
    existing_ids = {item.get("item_id") for item in manifest.get("items", [])}
    new_items = []
    for item in all_items:
        if item["item_id"] in existing_ids:
            continue
        item["user_id"] = storage_context().user_id
        item["created_at"] = now
        item["updated_at"] = now
        item.setdefault("user_edits", {})
        item.setdefault("favorite", False)
        manifest["items"].append(item)
        new_items.append(item)
        existing_ids.add(item["item_id"])
    _write_manifest(manifest)

    returned_items: list[dict[str, Any]] = []
    returned_ids: set[str] = set()
    for item in [*new_items, *cached_items]:
        item_id = str(item.get("item_id") or "")
        if not item_id or item_id in returned_ids:
            continue
        returned_items.append(item)
        returned_ids.add(item_id)

    auto_outfits: list[dict[str, Any]] = []
    refreshed_manifest = _ensure_manifest()
    for source in sources:
        source_items = _items_for_source(refreshed_manifest, source["image_id"])
        outfit = _ensure_source_outfit(source["image_id"], source_items)
        if outfit and not any(existing.get("outfit_id") == outfit.get("outfit_id") for existing in auto_outfits):
            auto_outfits.append(outfit)

    review = sum(1 for item in new_items if item.get("quality", {}).get("status") == "review")
    usable = sum(1 for item in new_items if item.get("quality", {}).get("status") == "usable")
    rejected_items = sum(1 for item in new_items if item.get("quality", {}).get("status") == "rejected")
    status = "imported" if new_items and not used_fallback else "partial" if new_items else "cached" if returned_items else "no_items_found"
    return {
        "status": status,
        "import_type": import_type,
        "source": {
            "url": source_url,
            "final_url": final_url,
            "image_count": len(sources),
        },
        "items": returned_items,
        "outfits": auto_outfits,
        "draft_outfit": auto_outfits[0] if auto_outfits else None,
        "summary": {
            "created": len(new_items),
            "cached": len(returned_items) - len(new_items),
            "usable": usable,
            "review": review,
            "rejected": rejected + rejected_items,
            "fallback_used": used_fallback,
            "ai_attempts": ai_attempts,
            "inventory_attempts": inventory_attempts,
            "extraction_modes": extraction_modes,
        },
        "message": "已找到之前拆出的单品，无需重复处理。" if status == "cached" else _import_message(len(new_items), review, used_fallback),
    }


def _extract_with_top_fallback(source: dict[str, Any], index: int, work_dir: Path) -> list[dict[str, Any]]:
    detector = FashionItemDetector()
    detected = detector.detect(
        {
            "url": source.get("source", {}).get("url") or source.get("source", {}).get("source_path") or f"upload:{source['image_id']}",
            "image": source["image"],
            "source_path": source["saved_path"],
        },
        index,
        work_dir,
    )
    items = []
    for item in detected.get("fashion_items", []):
        items.append(_closet_item_from_fashion_item(item, source))
    return items


def _segformer_category_label_groups(id_to_label: dict[int, str]) -> dict[str, list[int]]:
    groups: dict[str, list[int]] = {category: [] for category in CLOSET_SUPPORTED_CATEGORIES}
    for label_id, raw_label in id_to_label.items():
        label = raw_label.replace("_", " ").replace("-", " ").lower()
        if label in {"background", "hair", "face", "skin", "arm", "left arm", "right arm", "leg", "left leg", "right leg"}:
            continue
        for category, hints in SEGFORMER_LABEL_CATEGORY_HINTS.items():
            if any(hint in label for hint in hints):
                groups[category].append(label_id)
                break
    return {category: ids for category, ids in groups.items() if ids}


def _closet_item_from_segmentation_mask(
    category: str,
    label_ids: list[int],
    segmentation: Any,
    source: dict[str, Any],
    work_dir: Path,
    provider_name: str,
) -> dict[str, Any] | None:
    try:
        import numpy as np
    except Exception:
        return None

    mask_array = np.isin(segmentation, label_ids).astype("uint8") * 255
    ys, xs = np.where(mask_array > 0)
    if len(xs) == 0 or len(ys) == 0:
        return None

    image: Image.Image = source["image"].convert("RGBA")
    image_area = max(1, image.width * image.height)
    mask_area = int(len(xs))
    min_area_ratio = 0.003 if category in {"shoes", "bag", "accessory"} else 0.012
    if mask_area / image_area < min_area_ratio:
        return None

    left, top, right, bottom = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
    pad = max(8, int(max(right - left, bottom - top) * 0.08))
    box = (
        max(0, left - pad),
        max(0, top - pad),
        min(image.width, right + pad),
        min(image.height, bottom + pad),
    )
    if box[2] - box[0] < 12 or box[3] - box[1] < 12:
        return None

    alpha = Image.fromarray(mask_array, mode="L").filter(ImageFilter.GaussianBlur(radius=0.75))
    cutout_full = image.copy()
    cutout_full.putalpha(alpha)
    mask = alpha.crop(box)
    crop_rgb = image.crop(box).convert("RGB")
    cutout, matting_status = RembgMattingProvider().refine(crop_rgb, mask)
    raw_id = f"{source['image_id']}:{category}:{box}:{mask_area}:{provider_name}"
    item_id = hashlib.sha256(raw_id.encode("utf-8")).hexdigest()[:16]
    item_dir = _closet_item_dir() / item_id
    item_dir.mkdir(parents=True, exist_ok=True)
    cutout_path = item_dir / "cutout.png"
    mask_path = item_dir / "mask.png"
    preview_path = item_dir / "preview.png"
    cutout.save(cutout_path)
    mask.save(mask_path)
    _build_closet_item_preview(cutout_path, preview_path)

    confidence = min(0.94, max(0.56, mask_area / image_area * 7.5))
    quality = _closet_cutout_quality(
        category=category,
        cutout_path=cutout_path,
        base_score=confidence,
        base_reasons=["semantic_segmentation_mask"],
    )
    return {
        "item_id": item_id,
        "category": category,
        "category_label": _fashion_category_label(category),
        "source": {
            **source.get("source", {}),
            "image_id": source["image_id"],
            "source_group_id": source["image_id"],
            "crop_box": list(box),
        },
        "assets": {
            "cutout_path": _public_closet_path(cutout_path),
            "mask_path": _public_closet_path(mask_path),
            "preview_path": _public_closet_path(preview_path),
        },
        "attributes": {
            "colors": [],
            "material": None,
            "fit": None,
            "sleeve": None,
            "neckline": None,
            "pattern": None,
            "style_tags": [],
            "slot": _category_to_layout_slot(category),
        },
        "quality": {
            **quality,
            "confidence": round(confidence, 3),
        },
        "pipeline": {
            "segmentation": {
                "provider": "segformer_b2_clothes",
                "model": provider_name,
                "status": "ok",
                "label_ids": label_ids,
                "mask_area_ratio": round(mask_area / image_area, 4),
            },
            "matting": {
                "provider": "rembg" if matting_status == "rembg_refined" else "mask_alpha",
                "status": matting_status,
            },
        },
    }


def _has_meaningful_transparency(image: Image.Image) -> bool:
    """Reject AI image-edit results that quietly return an opaque background."""
    alpha = image.convert("RGBA").getchannel("A")
    histogram = alpha.resize((192, 192)).histogram()
    total = max(1, sum(histogram))
    transparent_ratio = sum(histogram[:245]) / total
    visible_ratio = sum(histogram[20:]) / total
    return transparent_ratio >= 0.025 and visible_ratio >= 0.06


def _ensure_transparent_ai_cutout(image: Image.Image) -> tuple[Image.Image, str]:
    """Convert opaque/faux-checkerboard AI output into a real alpha cutout."""
    rgba = image.convert("RGBA")
    if _has_meaningful_transparency(rgba):
        return rgba, "native_alpha"
    keyed = _remove_uniform_chroma_background(rgba)
    if keyed is not None and _has_meaningful_transparency(keyed):
        return keyed, "chroma_key_after_ai"
    matted = RembgMattingProvider().remove_background(rgba)
    if matted is not None and _has_meaningful_transparency(matted):
        return matted, "rembg_after_ai"
    return rgba, "opaque_rejected"


def _remove_uniform_chroma_background(image: Image.Image) -> Image.Image | None:
    """Key a model-generated high-chroma border background into soft alpha."""
    try:
        import numpy as np
    except Exception:
        return None
    rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
    height, width = rgb.shape[:2]
    strip = max(2, min(height, width) // 30)
    border = np.concatenate([
        rgb[:strip].reshape(-1, 3), rgb[-strip:].reshape(-1, 3),
        rgb[:, :strip].reshape(-1, 3), rgb[:, -strip:].reshape(-1, 3),
    ])
    background = np.median(border, axis=0)
    if float(background.max() - background.min()) < 60.0:
        return None
    border_distance = np.linalg.norm(border - background, axis=1)
    if float((border_distance <= 45.0).mean()) < 0.65:
        return None
    distance = np.linalg.norm(rgb - background, axis=2)
    alpha = np.clip((distance - 18.0) / 52.0 * 255.0, 0.0, 255.0).astype("uint8")
    # The image model may antialias foreground edges against the requested
    # magenta key. Remove pixels that still carry that distinctive two-channel
    # spill before softening alpha; otherwise a bright pink one-pixel halo is
    # visible on the closet's warm-white cards.
    magenta_spill = np.minimum(rgb[:, :, 0] - rgb[:, :, 1], rgb[:, :, 2] - rgb[:, :, 1])
    alpha[magenta_spill > 22.0] = 0
    alpha_image = Image.fromarray(alpha, mode="L").filter(ImageFilter.GaussianBlur(radius=0.45))
    # Replace magenta-contaminated antialias RGB with the nearest opaque
    # foreground color. Keeping the soft alpha while decontaminating RGB avoids
    # a pink fringe when the cutout is rendered on warm-white closet cards.
    try:
        from scipy.ndimage import distance_transform_edt

        softened_alpha = np.asarray(alpha_image)
        opaque = softened_alpha >= 235
        if opaque.any():
            _, nearest = distance_transform_edt(~opaque, return_indices=True)
            nearest_rgb = rgb[nearest[0], nearest[1]]
            rgb[softened_alpha < 250] = nearest_rgb[softened_alpha < 250]
    except Exception:
        pass
    result = Image.fromarray(rgb.clip(0, 255).astype("uint8"), mode="RGB").convert("RGBA")
    result.putalpha(alpha_image)
    return result


def _closet_item_from_ai_cutout(
    category: str,
    cutout: Image.Image,
    source: dict[str, Any],
    provider_name: str,
    model: str,
    analysis: dict[str, Any],
    instance_key: str = "single",
) -> dict[str, Any] | None:
    if category not in CLOSET_SUPPORTED_CATEGORIES or not _has_meaningful_transparency(cutout):
        return None
    evidence = analysis.get("evidence") or {}
    garment = evidence.get("garment") or {}
    confidence = max(0.0, min(1.0, float(analysis.get("confidence") or analysis.get("score") or 0.72)))
    raw_id = f"{source['image_id']}:{category}:{provider_name}:{model}:{instance_key}"
    item_id = hashlib.sha256(raw_id.encode("utf-8")).hexdigest()[:16]
    item_dir = _closet_item_dir() / item_id
    item_dir.mkdir(parents=True, exist_ok=True)
    cutout_path = item_dir / "cutout.png"
    mask_path = item_dir / "mask.png"
    preview_path = item_dir / "preview.png"
    normalized = cutout.convert("RGBA")
    normalized.save(cutout_path)
    normalized.getchannel("A").save(mask_path)
    _build_closet_item_preview(cutout_path, preview_path)
    quality = _closet_cutout_quality(
        category=category,
        cutout_path=cutout_path,
        base_score=min(0.94, max(0.7, confidence)),
        base_reasons=["ai_garment_extraction", "transparent_background_verified"],
    )
    if quality["status"] == "rejected":
        return None
    attributes = {
        "colors": _string_list(garment.get("colors")),
        "material": ", ".join(_string_list(garment.get("material"))) or None,
        "fit": garment.get("fit"),
        "sleeve": garment.get("sleeve"),
        "neckline": garment.get("neckline"),
        "pattern": garment.get("pattern"),
        "style_tags": _string_list(garment.get("style_tags")),
        "slot": _category_to_layout_slot(category),
    }
    return {
        "item_id": item_id,
        "category": category,
        "category_label": _fashion_category_label(category),
        "source": {
            **source.get("source", {}),
            "image_id": source["image_id"],
            "source_group_id": source["image_id"],
            "crop_box": garment.get("bbox"),
        },
        "assets": {
            "cutout_path": _public_closet_path(cutout_path),
            "mask_path": _public_closet_path(mask_path),
            "preview_path": _public_closet_path(preview_path),
        },
        "attributes": attributes,
        "quality": {**quality, "confidence": round(confidence, 3)},
        "pipeline": {
            "ai_cutout": {
                "provider": provider_name,
                "model": model,
                "status": "ok",
                "background": "transparent",
                "analysis_provider": evidence.get("provider"),
                "analysis_confidence": round(confidence, 3),
            },
            "segmentation": {"provider": "ai_generated_alpha", "status": "ok"},
            "matting": {"provider": "ai_image_edit", "status": "transparent_png_verified"},
        },
    }


def _closet_item_from_fashion_item(item: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    category = item.get("category") if item.get("category") in FASHION_ITEM_CATEGORIES else "accessory"
    raw_id = f"{source['image_id']}:{item.get('item_id')}:{category}"
    item_id = hashlib.sha256(raw_id.encode("utf-8")).hexdigest()[:16]
    cutout = _copy_asset_to_closet(item.get("cutout_path"), item_id, "cutout")
    clean = _copy_asset_to_closet(item.get("clean_reference_path") or item.get("cutout_path"), item_id, "clean_reference")
    mask = _copy_asset_to_closet(item.get("mask_path"), item_id, "mask")
    preview = _build_closet_item_preview(clean or cutout, _closet_item_dir() / item_id / "preview.png")
    return {
        "item_id": item_id,
        "category": category,
        "category_label": _fashion_category_label(category),
        "source": {
            **source.get("source", {}),
            "image_id": source["image_id"],
            "source_group_id": source["image_id"],
            "crop_box": item.get("source", {}).get("crop_box"),
        },
        "assets": {
            "cutout_path": _public_closet_path(cutout),
            "mask_path": _public_closet_path(mask),
            "preview_path": _public_closet_path(preview or clean or cutout),
            "clean_reference_path": _public_closet_path(clean),
        },
        "attributes": item.get("attributes") or {},
        "quality": item.get("quality") or {"status": "review", "score": 0.42, "reasons": ["fallback_quality_unknown"]},
        "pipeline": {
            "detector": item.get("pipeline", {}).get("detector", {}),
            "clean_reference": item.get("pipeline", {}).get("clean_reference", {}),
            "segmentation": {
                "provider": "top_fallback",
                "status": "partial",
                "note": "SegFormer clothes adapter is not available in this environment.",
            },
        },
    }


def _copy_asset_to_closet(public_path: str | None, item_id: str, kind: str) -> Path | None:
    source_path = _closet_disk_path(public_path)
    if source_path is None or not source_path.exists():
        return None
    suffix = ".png" if kind in {"cutout", "mask", "preview", "clean_reference"} else source_path.suffix
    target = _closet_item_dir() / item_id / f"{kind}{suffix}"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_path, target)
    return target


def _build_closet_item_preview(source_path: Path | None, target_path: Path, canvas_size: int = 900) -> Path | None:
    if source_path is None or not source_path.exists():
        return None
    try:
        image = Image.open(source_path).convert("RGBA")
    except Exception:
        return None

    item = _trim_closet_preview_image(image)
    if item.width < 8 or item.height < 8:
        return None

    canvas = Image.new("RGBA", (canvas_size, canvas_size), "#fffafa")
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(
        (24, 24, canvas_size - 24, canvas_size - 24),
        radius=42,
        fill="#ffffff",
        outline="#f1e6eb",
        width=2,
    )

    max_side = int(canvas_size * 0.78)
    item.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    x = (canvas_size - item.width) // 2
    y = (canvas_size - item.height) // 2
    canvas.alpha_composite(_closet_preview_shadow(item), (x + 5, y + 10))
    canvas.alpha_composite(item, (x, y))

    target_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(target_path, "PNG")
    return target_path


def _trim_closet_preview_image(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    alpha_bbox = rgba.getchannel("A").getbbox()
    if alpha_bbox and alpha_bbox != (0, 0, rgba.width, rgba.height):
        return rgba.crop(alpha_bbox)

    pixels = rgba.load()
    xs: list[int] = []
    ys: list[int] = []
    for y in range(rgba.height):
        for x in range(rgba.width):
            r, g, b, a = pixels[x, y]
            if a > 20 and not (r > 238 and g > 238 and b > 238):
                xs.append(x)
                ys.append(y)
    if not xs:
        return rgba
    pad_x = max(8, int((max(xs) - min(xs) + 1) * 0.04))
    pad_y = max(8, int((max(ys) - min(ys) + 1) * 0.04))
    return rgba.crop(
        (
            max(0, min(xs) - pad_x),
            max(0, min(ys) - pad_y),
            min(rgba.width, max(xs) + pad_x),
            min(rgba.height, max(ys) + pad_y),
        )
    )


def _closet_preview_shadow(image: Image.Image) -> Image.Image:
    alpha = image.getchannel("A").filter(ImageFilter.GaussianBlur(10))
    shadow = Image.new("RGBA", image.size, (96, 72, 82, 0))
    shadow.putalpha(alpha.point(lambda value: min(64, int(value * 0.2))))
    return shadow


def _closet_cutout_quality(
    category: str,
    cutout_path: Path,
    base_score: float,
    base_reasons: list[str] | None = None,
) -> dict[str, Any]:
    reasons = list(base_reasons or [])
    score = float(base_score)
    try:
        image = Image.open(cutout_path).convert("RGBA")
        width, height = image.size
        alpha = image.getchannel("A")
        alpha_histogram = alpha.resize((96, 96)).histogram()
        visible_ratio = sum(alpha_histogram[19:]) / max(1, sum(alpha_histogram))
        aspect_ratio = width / max(1, height)
        face_stage = _detect_person(image.convert("RGB"))
    except Exception:
        return {"status": "review", "score": 0.32, "reasons": [*reasons, "reference_unreadable"]}

    if width < 160 or height < 160:
        score -= 0.22
        reasons.append("reference_too_small")
    if visible_ratio < 0.08:
        score -= 0.25
        reasons.append("foreground_too_sparse")
    if visible_ratio > 0.86:
        score -= 0.18
        reasons.append("person_or_background_contamination")
    if category == "top" and not (0.35 <= aspect_ratio <= 2.4):
        score -= 0.12
        reasons.append("top_aspect_unusual")
    if face_stage["status"] in {"pass", "warn"}:
        score -= 0.28
        reasons.append("contains_person_face")

    score = round(max(0.0, min(1.0, score)), 3)
    status = "usable" if score >= 0.62 else "review" if score >= 0.42 else "rejected"
    return {"status": status, "score": score, "reasons": reasons}


def _import_message(created: int, review: int, used_fallback: bool) -> str:
    if created == 0:
        return "暂时没有找到可稳定入柜的衣物，请换一张更清晰的图片。"
    if used_fallback:
        return f"已找到 {created} 件单品，请确认图片和分类是否准确。"
    if review:
        return f"已找到 {created} 件单品，有 {review} 件建议确认后使用。"
    return f"已找到 {created} 件单品，已经放入衣橱。"


def _normalize_link_url(url: str) -> str:
    text = str(url or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="请先粘贴链接")
    parsed = urlparse(text)
    if not parsed.scheme:
        text = f"https://{text}"
    if _is_xhs_url(text):
        return _normalize_xhs_url(text)
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="链接格式不正确")
    return text


def _is_xhs_url(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return "xiaohongshu.com" in host or "xhslink.com" in host or "xhscdn.com" in host


async def _fetch_html(url: str) -> tuple[str, str]:
    async with httpx.AsyncClient(follow_redirects=True, timeout=18, headers=HTTP_HEADERS) as client:
        try:
            response = await client.get(url)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=400, detail="这个链接暂时打不开，请改用截图或上传图片。") from exc
    content_type = response.headers.get("content-type", "")
    if "image/" in content_type:
        return _image_html_wrapper(str(response.url)), str(response.url)
    return response.text, str(response.url)


def _image_html_wrapper(url: str) -> str:
    return f'<html><head><meta property="og:image" content="{html.escape(url)}"></head></html>'


def _extract_webpage_image_urls(html_text: str, base_url: str) -> list[str]:
    urls = _extract_image_urls_from_html(html_text, base_url)
    for pattern in [
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+(?:property|name)=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
        r'<img[^>]+(?:src|data-src)=["\']([^"\']+)["\']',
        r'<source[^>]+srcset=["\']([^"\']+)["\']',
    ]:
        for match in re.findall(pattern, html_text, flags=re.IGNORECASE):
            first = str(match).split(",")[0].strip().split(" ")[0]
            if first:
                urls.append(urljoin(base_url, html.unescape(first)))
    return _merge_urls(urls)


def _merge_urls(urls: list[str]) -> list[str]:
    seen = set()
    merged = []
    for url in urls:
        if not url:
            continue
        cleaned = html.unescape(str(url)).strip()
        if cleaned.startswith("//"):
            cleaned = "https:" + cleaned
        if cleaned not in seen and urlparse(cleaned).scheme in {"http", "https"}:
            seen.add(cleaned)
            merged.append(cleaned)
    return merged
