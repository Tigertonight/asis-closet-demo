from __future__ import annotations

import hashlib
import io
import json
import os
import secrets
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import qrcode
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from PIL import Image, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool

from app.analyzer import analyze_image_bytes
from app.auth import get_current_user
from app import selfit_assets
from app.ops import env_int
from app.storage import ROOT_DIR


router = APIRouter(prefix="/api/v1/selfit/mirror", tags=["selfit-mirror-handoff"])
MIRROR_DIR = ROOT_DIR / "outputs" / "selfit_mirror"
HANDOFF_STORE_PATH = MIRROR_DIR / "handoffs.json"
MIRROR_ASSET_DIR = MIRROR_DIR / "assets"
MAX_PHOTO_BYTES = 12 * 1024 * 1024
SUPPORTED_FORMATS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}
_STORE_LOCK = threading.RLock()

COLOR_GRADE_DEFAULTS: dict[str, Any] = {
    "exposure": 0.0,
    "brightness": 0.0,
    "contrast": 0.0,
    "highlights": 0.0,
    "shadows": 0.0,
    "saturation": 0.0,
    "temperature": 0.0,
    "tint": 0.0,
    "hsl": {
        color: {"hue": 0.0, "saturation": 0.0, "lightness": 0.0}
        for color in ("red", "orange", "yellow", "green", "cyan", "blue", "purple")
    },
}
COLOR_GRADE_RANGES = {
    "exposure": (-0.5, 0.5),
    "brightness": (-0.2, 0.2),
    "contrast": (-0.3, 0.3),
    "highlights": (-0.5, 0.3),
    "shadows": (-0.3, 0.5),
    "saturation": (-0.3, 0.3),
    "temperature": (-0.2, 0.2),
    "tint": (-0.1, 0.1),
}
HSL_RANGES = {
    "hue": (-0.1, 0.1),
    "saturation": (-0.3, 0.3),
    "lightness": (-0.2, 0.2),
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


def _token_hash(token: str) -> str:
    pepper = os.getenv("SELFIT_MIRROR_HANDOFF_SECRET") or os.getenv(
        "SELFIT_AUTH_SECRET", "selfit-local-auth-secret"
    )
    return hashlib.sha256(f"{pepper}:{token}".encode("utf-8")).hexdigest()


def _load_store() -> dict[str, Any]:
    if not HANDOFF_STORE_PATH.exists():
        return {"version": 1, "handoffs": []}
    try:
        data = json.loads(HANDOFF_STORE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"version": 1, "handoffs": []}
    if not isinstance(data, dict):
        return {"version": 1, "handoffs": []}
    data.setdefault("version", 1)
    data.setdefault("handoffs", [])
    return data


def _write_store(data: dict[str, Any]) -> None:
    MIRROR_DIR.mkdir(parents=True, exist_ok=True)
    temporary = HANDOFF_STORE_PATH.with_name(
        f"{HANDOFF_STORE_PATH.name}.{secrets.token_urlsafe(8)}.tmp"
    )
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(HANDOFF_STORE_PATH)


def _color_grade_store_path() -> Path:
    return MIRROR_DIR / "color_grade.json"


def _default_color_grade() -> dict[str, Any]:
    return {
        "config_id": "mirro_color_grade",
        "version": 1,
        "updated_at": None,
        "parameters": json.loads(json.dumps(COLOR_GRADE_DEFAULTS)),
    }


def _load_color_grade_data() -> dict[str, Any]:
    path = _color_grade_store_path()
    if not path.exists():
        return {"current": _default_color_grade(), "history": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"current": _default_color_grade(), "history": []}
    if not isinstance(data, dict) or not isinstance(data.get("current"), dict):
        return {"current": _default_color_grade(), "history": []}
    data.setdefault("history", [])
    return data


def _write_color_grade_data(data: dict[str, Any]) -> None:
    path = _color_grade_store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{secrets.token_urlsafe(8)}.tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _number_in_range(value: Any, bounds: tuple[float, float]) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("must be a number")
    numeric = float(value)
    if not bounds[0] <= numeric <= bounds[1]:
        raise ValueError(f"must be between {bounds[0]} and {bounds[1]}")
    return round(numeric, 4)


def _validated_color_grade_parameters(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("parameters must be an object")
    unknown = set(value) - {*COLOR_GRADE_RANGES, "hsl"}
    if unknown:
        raise ValueError(f"unsupported parameters: {', '.join(sorted(unknown))}")
    parameters = json.loads(json.dumps(COLOR_GRADE_DEFAULTS))
    for name, bounds in COLOR_GRADE_RANGES.items():
        if name in value:
            parameters[name] = _number_in_range(value[name], bounds)
    hsl = value.get("hsl", {})
    if not isinstance(hsl, dict):
        raise ValueError("hsl must be an object")
    unknown_colors = set(hsl) - set(parameters["hsl"])
    if unknown_colors:
        raise ValueError(f"unsupported HSL colors: {', '.join(sorted(unknown_colors))}")
    for color, adjustments in hsl.items():
        if not isinstance(adjustments, dict):
            raise ValueError(f"hsl.{color} must be an object")
        unknown_adjustments = set(adjustments) - set(HSL_RANGES)
        if unknown_adjustments:
            raise ValueError(
                f"unsupported HSL parameters: {', '.join(sorted(unknown_adjustments))}"
            )
        for name, bounds in HSL_RANGES.items():
            if name in adjustments:
                parameters["hsl"][color][name] = _number_in_range(adjustments[name], bounds)
    return parameters


def _public_color_grade(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "configId": str(record.get("config_id") or "mirro_color_grade"),
        "version": int(record.get("version") or 1),
        "updatedAt": record.get("updated_at"),
        "parameters": record.get("parameters") or json.loads(json.dumps(COLOR_GRADE_DEFAULTS)),
    }


def _find_by_token(data: dict[str, Any], token: str) -> dict[str, Any] | None:
    digest = _token_hash(token)
    return next(
        (item for item in data["handoffs"] if secrets.compare_digest(str(item.get("token_hash") or ""), digest)),
        None,
    )


def _public_status(record: dict[str, Any]) -> dict[str, Any]:
    status = str(record.get("status") or "pending")
    expires_at = _parse_iso(record.get("expires_at"))
    if status == "pending" and (expires_at is None or expires_at <= _now()):
        status = "expired"
    return {
        "handoffId": record["handoff_id"],
        "status": status,
        "expiresAt": record["expires_at"],
        "nextStep": "like",
        "suitCompleted": True,
    }


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "retryable": status_code >= 500}},
    )


def _handoff_url(request: Request, token: str) -> str:
    configured = os.getenv("SELFIT_PUBLIC_BASE_URL", "").strip().rstrip("/")
    base_url = configured or str(request.base_url).rstrip("/")
    return f"{base_url}/selfit?{urlencode({'handoff': token})}"


async def _validated_photo(photo: UploadFile) -> tuple[bytes, str] | JSONResponse:
    raw = await photo.read(MAX_PHOTO_BYTES + 1)
    if not raw:
        return _error(400, "mirror.photo_required", "没有收到拍摄照片，请重新拍摄。")
    if len(raw) > MAX_PHOTO_BYTES:
        return _error(413, "mirror.photo_too_large", "照片过大，请重新拍摄。")
    try:
        with Image.open(io.BytesIO(raw)) as image:
            image.verify()
            image_format = str(image.format or "").upper()
    except (UnidentifiedImageError, OSError):
        return _error(415, "mirror.photo_invalid", "照片格式无法识别，请重新拍摄。")
    if image_format not in SUPPORTED_FORMATS:
        return _error(415, "mirror.photo_unsupported", "仅支持 JPG、PNG 或 WebP 照片。")
    return raw, image_format


@router.get("/color-grade")
async def get_mirror_color_grade() -> JSONResponse:
    with _STORE_LOCK:
        current = _load_color_grade_data()["current"]
    return JSONResponse(
        content=_public_color_grade(current),
        headers={"Cache-Control": "no-store"},
    )


@router.put("/color-grade")
async def update_mirror_color_grade(request: Request) -> JSONResponse:
    try:
        payload = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _error(400, "mirror.color_grade_invalid", "调色配置格式不正确。")
    if not isinstance(payload, dict):
        return _error(400, "mirror.color_grade_invalid", "调色配置格式不正确。")
    try:
        parameters = _validated_color_grade_parameters(payload.get("parameters"))
    except ValueError as exc:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "mirror.color_grade_invalid",
                    "message": "调色参数超出允许范围。",
                    "detail": str(exc),
                    "retryable": False,
                }
            },
        )
    with _STORE_LOCK:
        data = _load_color_grade_data()
        current = data["current"]
        expected_revision = request.headers.get("if-match", "").strip().strip('"')
        if expected_revision and expected_revision != str(current.get("version") or 1):
            return JSONResponse(
                status_code=409,
                content={
                    "error": {
                        "code": "mirror.color_grade_conflict",
                        "message": "配置已被其他设备更新，请重新载入后再调整。",
                        "retryable": True,
                    },
                    "current": _public_color_grade(current),
                },
            )
        data.setdefault("history", []).append(json.loads(json.dumps(current)))
        data["history"] = data["history"][-50:]
        updated = {
            "config_id": "mirro_color_grade",
            "version": int(current.get("version") or 1) + 1,
            "updated_at": _iso(_now()),
            "parameters": parameters,
        }
        data["current"] = updated
        _write_color_grade_data(data)
    return JSONResponse(content=_public_color_grade(updated), headers={"Cache-Control": "no-store"})


@router.post("/analyze", status_code=201)
async def create_mirror_handoff(
    request: Request,
    photo: UploadFile | None = File(default=None),
    original: UploadFile | None = File(default=None),
    retouched: UploadFile | None = File(default=None),
    metadata: str | None = Form(default=None),
    result: str | None = Form(default=None),
) -> JSONResponse:
    source_photo = original or photo
    if source_photo is None:
        return _error(400, "mirror.photo_required", "没有收到拍摄照片，请重新拍摄。")
    validated = await _validated_photo(source_photo)
    if isinstance(validated, JSONResponse):
        return validated
    raw, image_format = validated
    retouched_raw = raw
    retouched_format = image_format
    retouch_state = "passthrough"
    if retouched is not None:
        validated_retouched = await _validated_photo(retouched)
        if isinstance(validated_retouched, JSONResponse):
            return validated_retouched
        retouched_raw, retouched_format = validated_retouched
        retouch_state = "retouched"
    capture_metadata: dict[str, Any] = {}
    if metadata:
        try:
            parsed_metadata = json.loads(metadata)
        except json.JSONDecodeError:
            return _error(400, "mirror.metadata_invalid", "拍摄信息格式不正确。")
        if not isinstance(parsed_metadata, dict):
            return _error(400, "mirror.metadata_invalid", "拍摄信息格式不正确。")
        capture_metadata = parsed_metadata
    analysis: dict[str, Any]
    if result:
        try:
            parsed_result = json.loads(result)
        except json.JSONDecodeError:
            return _error(400, "mirror.result_invalid", "测试结果格式不正确。")
        if not isinstance(parsed_result, dict):
            return _error(400, "mirror.result_invalid", "测试结果格式不正确。")
        analysis = parsed_result
    else:
        analysis = await run_in_threadpool(
            analyze_image_bytes,
            raw,
            source_photo.filename or "mirror-capture-original.jpg",
            False,
            None,
            True,
        )
    now = _now()
    ttl_seconds = max(60, env_int("SELFIT_MIRROR_HANDOFF_TTL_SECONDS", 600))
    token = secrets.token_urlsafe(32)
    handoff_id = "mho_" + secrets.token_urlsafe(12)
    original_asset_id = f"asset_original_{hashlib.sha256(raw).hexdigest()[:12]}"
    retouched_asset_id = f"asset_retouched_{hashlib.sha256(retouched_raw).hexdigest()[:12]}"
    original_key = f"{handoff_id}/{original_asset_id}{SUPPORTED_FORMATS[image_format]}"
    retouched_key = f"{handoff_id}/{retouched_asset_id}{SUPPORTED_FORMATS[retouched_format]}"
    content_types = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
    asset_store = selfit_assets.asset_store_from_env(MIRROR_ASSET_DIR)
    asset_store.save(original_key, raw, content_types[image_format])
    asset_store.save(retouched_key, retouched_raw, content_types[retouched_format])
    original_local_path = asset_store.local_path(original_key)
    retouched_local_path = asset_store.local_path(retouched_key)
    color_grade = capture_metadata.get("colorGrade")
    if not isinstance(color_grade, dict):
        color_grade = {}
    assets = {
        "original": {
            "asset_id": original_asset_id,
            "edit_state": "original",
            "role": "suit_input",
            "object_key": original_key,
            "asset_path": str(original_local_path) if original_local_path else None,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "image_format": image_format,
        },
        "retouched": {
            "asset_id": retouched_asset_id,
            "edit_state": retouch_state,
            "role": "mirro_preview",
            "derived_from": original_asset_id,
            "object_key": retouched_key,
            "asset_path": str(retouched_local_path) if retouched_local_path else None,
            "sha256": hashlib.sha256(retouched_raw).hexdigest(),
            "image_format": retouched_format,
            "color_grade": color_grade,
        },
    }
    record = {
        "handoff_id": handoff_id,
        "token_hash": _token_hash(token),
        "status": "pending",
        "created_at": _iso(now),
        "expires_at": _iso(now + timedelta(seconds=ttl_seconds)),
        # Legacy consumers continue to resolve this field as the Suit source.
        "asset_path": assets["original"]["asset_path"],
        "assets": assets,
        "suit_asset_id": original_asset_id,
        "mirror_preview_asset_id": retouched_asset_id,
        "image_format": image_format,
        "analysis": {"source": "mirror", "suit_completed": True, "result": analysis},
        "claimed_by_user_id": None,
        "claimed_session_id": None,
        "claimed_at": None,
    }
    with _STORE_LOCK:
        data = _load_store()
        data["handoffs"].append(record)
        _write_store(data)
    return JSONResponse(
        status_code=201,
        content={
            "handoffId": handoff_id,
            "status": "pending",
            "expiresAt": record["expires_at"],
            "qrImageUrl": f"/api/v1/selfit/mirror/handoffs/{token}/qr",
            "statusUrl": f"/api/v1/selfit/mirror/handoffs/{token}",
        },
    )


@router.get("/handoffs/{token}")
async def get_mirror_handoff(token: str) -> JSONResponse:
    with _STORE_LOCK:
        data = _load_store()
        record = _find_by_token(data, token)
        if record is None:
            return _error(404, "mirror.handoff_not_found", "这个测试链接无效，请重新扫码。")
        public = _public_status(record)
        if public["status"] == "expired" and record.get("status") == "pending":
            record["status"] = "expired"
            _write_store(data)
    return JSONResponse(content={"handoff": public})


@router.get("/handoffs/{token}/qr")
async def mirror_handoff_qr(request: Request, token: str) -> Response:
    with _STORE_LOCK:
        record = _find_by_token(_load_store(), token)
        if record is None:
            return _error(404, "mirror.handoff_not_found", "二维码已失效。")
        if _public_status(record)["status"] == "expired":
            return _error(410, "mirror.handoff_expired", "二维码已过期。")
    # The original mirror artwork uses a one-module internal margin. The white
    # result card supplies the remaining optical quiet zone without doubling
    # the visible border around the code.
    qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=1)
    qr.add_data(_handoff_url(request, token))
    qr.make(fit=True)
    image = qr.make_image(fill_color="#171313", back_color="#ffffff")
    output = io.BytesIO()
    image.save(output, format="PNG")
    return Response(
        output.getvalue(),
        media_type="image/png",
        headers={"Cache-Control": "no-store, private", "X-Content-Type-Options": "nosniff"},
    )


@router.post("/handoffs/{token}/claim")
async def claim_mirror_handoff(
    token: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> JSONResponse:
    # 照片回填含 CPU 密集 CV 检测（pose/face/肤色），整体移入线程池避免阻塞事件循环。
    return await run_in_threadpool(_claim_mirror_handoff, token, user)


def _claim_mirror_handoff(token: str, user: dict[str, Any]) -> JSONResponse:
    with _STORE_LOCK:
        data = _load_store()
        record = _find_by_token(data, token)
        if record is None:
            return _error(404, "mirror.handoff_not_found", "这个测试链接无效，请重新扫码。")
        status = _public_status(record)["status"]
        user_id = str(user["user_id"])
        if status == "expired":
            return _error(410, "mirror.handoff_expired", "二维码已过期，请回到镜子重新生成。")
        if status == "claimed":
            if record.get("claimed_by_user_id") != user_id:
                return _error(409, "mirror.handoff_claimed", "这份测试结果已经被领取。")
            return JSONResponse(
                content={
                    "handoff": _public_status(record),
                    "session": {"sessionId": record["claimed_session_id"]},
                    "nextStep": "like",
                }
            )

        from app.selfit_onboarding import create_session_from_mirror_handoff

        session = create_session_from_mirror_handoff(record, user)
        record["status"] = "claimed"
        record["claimed_by_user_id"] = user_id
        record["claimed_session_id"] = session["sessionId"]
        record["claimed_at"] = _iso(_now())
        _write_store(data)
        return JSONResponse(
            content={"handoff": _public_status(record), "session": session, "nextStep": "like"}
        )
