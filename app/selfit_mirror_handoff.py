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
from app.ops import env_int
from app.storage import ROOT_DIR


router = APIRouter(prefix="/api/v1/selfit/mirror", tags=["selfit-mirror-handoff"])
MIRROR_DIR = ROOT_DIR / "outputs" / "selfit_mirror"
HANDOFF_STORE_PATH = MIRROR_DIR / "handoffs.json"
MIRROR_ASSET_DIR = MIRROR_DIR / "assets"
MAX_PHOTO_BYTES = 12 * 1024 * 1024
SUPPORTED_FORMATS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}
_STORE_LOCK = threading.RLock()


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


@router.post("/analyze", status_code=201)
async def create_mirror_handoff(
    request: Request,
    photo: UploadFile = File(...),
    result: str | None = Form(default=None),
) -> JSONResponse:
    validated = await _validated_photo(photo)
    if isinstance(validated, JSONResponse):
        return validated
    raw, image_format = validated
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
            photo.filename or "mirror-capture.jpg",
            False,
            None,
            True,
        )
    now = _now()
    ttl_seconds = max(60, env_int("SELFIT_MIRROR_HANDOFF_TTL_SECONDS", 600))
    token = secrets.token_urlsafe(32)
    handoff_id = "mho_" + secrets.token_urlsafe(12)
    MIRROR_ASSET_DIR.mkdir(parents=True, exist_ok=True)
    asset_path = MIRROR_ASSET_DIR / f"{handoff_id}{SUPPORTED_FORMATS[image_format]}"
    asset_path.write_bytes(raw)
    record = {
        "handoff_id": handoff_id,
        "token_hash": _token_hash(token),
        "status": "pending",
        "created_at": _iso(now),
        "expires_at": _iso(now + timedelta(seconds=ttl_seconds)),
        "asset_path": str(asset_path),
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
