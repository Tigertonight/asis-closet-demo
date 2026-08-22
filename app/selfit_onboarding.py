from __future__ import annotations

import hashlib
import io
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, JSONResponse
from PIL import Image, UnidentifiedImageError

from app import selfit_onboarding_store as _store_module
from app import selfit_photo, selfit_report, selfit_share
from app.auth import get_optional_user
from app.ops import env_int
from app.storage import ROOT_DIR

# 注意：SELFIT_ONBOARDING_ASSET_DIR 下的用户原图与分享图是初始数据资产，需要精心保留。
# 会话过期只清理索引记录（sessions.json / 任务 / 报告），资产文件一律不删。
# 后续迁移对象存储时以该目录为同步源，禁止加入任何定期清理任务。
SELFIT_ONBOARDING_DIR = ROOT_DIR / "outputs" / "selfit_onboarding"
SELFIT_ONBOARDING_STORE_PATH = SELFIT_ONBOARDING_DIR / "sessions.json"
SELFIT_ONBOARDING_ASSET_DIR = SELFIT_ONBOARDING_DIR / "assets"

SCHEMA_VERSION = "selfit-onboarding-v1"
PHOTO_MAX_BYTES = 12 * 1024 * 1024
PHOTO_SUPPORTED_FORMATS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}

# 报告任务的演示节奏：按创建后的耗时映射阶段与进度，前端轮询读取。
REPORT_STAGE_SCHEDULE_MS = (
    (0, "profile", 25),
    (800, "inspiration", 50),
    (1600, "composition", 75),
    (2400, "finalizing", 100),
)
REPORT_TOTAL_MS = 3200
REPORT_POLL_AFTER_MS = 800

SKIN_OPTIONS = {"白皙色", "自然白", "自然色", "健康色", "小麦色", "蜜糖色"}
FACE_SHAPE_OPTIONS = {"椭圆脸", "圆脸", "方脸", "心形脸", "长脸"}
BODY_SHAPE_OPTIONS = {"梨型", "倒三角型", "沙漏型", "矩型", "苹果型"}
MANUAL_FIELDS = {"skin": SKIN_OPTIONS, "faceShape": FACE_SHAPE_OPTIONS, "bodyShape": BODY_SHAPE_OPTIONS}

PREFERENCE_AXES = {"shape", "energy", "trend"}
PALETTE_OPTIONS = {"mono", "earth", "ocean", "jewel", "bright", "pastel"}

VIBE_QUESTIONS = {"occasion", "wardrobe", "expression"}
VIBE_OPTIONS = {"A", "B", "C", "D", "E"}

router = APIRouter(prefix="/api/v1/selfit", tags=["selfit-onboarding"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _session_ttl_hours() -> int:
    return env_int("SELFIT_ONBOARDING_SESSION_TTL_HOURS", 24)


def _request_id() -> str:
    return "req_" + secrets.token_urlsafe(12)


def _error_response(
    status_code: int,
    code: str,
    message: str,
    *,
    retryable: bool = False,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "requestId": _request_id(),
            "error": {
                "code": code,
                "message": message,
                "retryable": retryable,
                "details": details or {},
            },
        },
    )


_STORE_KEYS = tuple(_store_module.COLLECTIONS)


def _store_backend() -> str:
    return os.getenv("SELFIT_ONBOARDING_STORE_BACKEND", "json").strip().lower()


def _sqlite_store() -> _store_module.SqliteOnboardingStore:
    return _store_module.SqliteOnboardingStore(SELFIT_ONBOARDING_DIR / "sessions.sqlite3")


def _load_store() -> dict[str, Any]:
    if _store_backend() == "sqlite":
        return _sqlite_store().load()
    if not SELFIT_ONBOARDING_STORE_PATH.exists():
        return _store_module.empty_store()
    try:
        data = json.loads(SELFIT_ONBOARDING_STORE_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("version", 1)
            for key in _STORE_KEYS:
                data.setdefault(key, [])
            return data
    except json.JSONDecodeError:
        pass
    return _store_module.empty_store()


def _write_store(data: dict[str, Any]) -> None:
    if _store_backend() == "sqlite":
        _sqlite_store().save(data)
        return
    SELFIT_ONBOARDING_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = SELFIT_ONBOARDING_STORE_PATH.with_name(f"{SELFIT_ONBOARDING_STORE_PATH.name}.{secrets.token_urlsafe(8)}.tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(SELFIT_ONBOARDING_STORE_PATH)


def _prune_store(data: dict[str, Any]) -> dict[str, Any]:
    now = _now()
    sessions = []
    for record in data["sessions"]:
        expires_at = _parse_iso(record.get("expires_at"))
        if expires_at is not None and expires_at <= now:
            continue
        sessions.append(record)
    data["sessions"] = sessions
    horizon = _iso(now - timedelta(hours=max(_session_ttl_hours(), 1)))
    data["idempotency"] = [
        entry for entry in data["idempotency"] if str(entry.get("created_at") or "") >= horizon
    ]
    live_session_ids = {record.get("session_id") for record in sessions}
    data["report_jobs"] = [
        job for job in data["report_jobs"] if job.get("session_id") in live_session_ids
    ]
    data["reports"] = [
        report for report in data["reports"] if report.get("session_id") in live_session_ids
    ]
    data["outfit_requests"] = [
        item for item in data["outfit_requests"] if item.get("session_id") in live_session_ids
    ]
    data["share_assets"] = [
        item for item in data["share_assets"] if item.get("session_id") in live_session_ids
    ]
    return data


def _find_session(data: dict[str, Any], session_id: str) -> dict[str, Any] | None:
    return next(
        (record for record in data["sessions"] if record.get("session_id") == session_id),
        None,
    )


def _session_visible_to(record: dict[str, Any], user: dict[str, Any] | None) -> bool:
    owner = record.get("user_id")
    if not owner:
        return True
    return bool(user) and user.get("user_id") == owner


def _completed_steps(record: dict[str, Any]) -> list[str]:
    steps: list[str] = []
    photos = record.get("photos") or {}
    if all((photos.get(kind) or {}).get("status") == "accepted" for kind in ("face", "body")):
        steps.append("photos")
    if record.get("manual"):
        steps.append("profile")
    if record.get("preferences"):
        steps.append("preferences")
    if record.get("vibe"):
        steps.append("vibe")
    return steps


def _public_session(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "sessionId": record["session_id"],
        "status": record["status"],
        "revision": int(record.get("revision") or 1),
        "expiresAt": record["expires_at"],
        "completedSteps": _completed_steps(record),
    }


def _session_response(record: dict[str, Any], *, status_code: int = 200) -> tuple[int, dict[str, Any]]:
    return status_code, {"requestId": _request_id(), "session": _public_session(record)}


def _idempotency_scope(request: Request, user: dict[str, Any] | None) -> str:
    if user and user.get("user_id"):
        return f"user:{user['user_id']}"
    client_host = request.client.host if request.client else "unknown"
    return f"anon:{client_host}"


def _idempotency_replay(
    data: dict[str, Any], scope: str, key: str | None
) -> tuple[int, dict[str, Any]] | None:
    if not key:
        return None
    full_key = f"{scope}:{key}"
    entry = next(
        (item for item in data["idempotency"] if item.get("key") == full_key),
        None,
    )
    if entry is None:
        return None
    body = entry.get("body")
    if not isinstance(body, dict):
        return None
    replayed = dict(body)
    replayed["requestId"] = _request_id()
    return int(entry.get("status_code") or 200), replayed


def _idempotency_store(
    data: dict[str, Any], scope: str, key: str | None, status_code: int, body: dict[str, Any]
) -> None:
    if not key:
        return
    full_key = f"{scope}:{key}"
    data["idempotency"] = [item for item in data["idempotency"] if item.get("key") != full_key]
    data["idempotency"].append(
        {
            "key": full_key,
            "status_code": status_code,
            "body": body,
            "created_at": _iso(_now()),
        }
    )


async def _read_json_object(request: Request) -> dict[str, Any] | JSONResponse:
    raw = await request.body()
    if not raw or not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return _error_response(422, "validation.invalid_value", "提交的内容不是有效的 JSON。")
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        return _error_response(422, "validation.invalid_value", "提交的内容应为 JSON 对象。")
    return payload


def _load_active_session(
    data: dict[str, Any], session_id: str, user: dict[str, Any] | None
) -> dict[str, Any] | JSONResponse:
    record = _find_session(data, session_id)
    if record is None or not _session_visible_to(record, user):
        return _error_response(404, "session.expired", "会话已失效，请重新开始。")
    expires_at = _parse_iso(record.get("expires_at"))
    if expires_at is None or expires_at <= _now():
        return _error_response(404, "session.expired", "会话已失效，请重新开始。")
    return record


def _check_revision(record: dict[str, Any], if_match: str | None) -> JSONResponse | None:
    if if_match is None:
        return None
    try:
        expected = int(str(if_match).strip().strip('"'))
    except ValueError:
        return _error_response(409, "session.revision_conflict", "会话已被更新，请刷新后重试。")
    if expected != int(record.get("revision") or 1):
        return _error_response(409, "session.revision_conflict", "会话已被更新，请刷新后重试。")
    return None


def _validate_manual(manual: Any) -> dict[str, Any] | JSONResponse:
    if not isinstance(manual, dict) or not manual:
        return _error_response(422, "validation.invalid_value", "请提交要保存的手动信息。")
    unknown = sorted(set(manual) - set(MANUAL_FIELDS))
    if unknown:
        return _error_response(
            422,
            "validation.invalid_enum",
            "存在不支持的信息字段，请修正后重试。",
            details={"fields": unknown},
        )
    cleaned: dict[str, Any] = {}
    for field, options in MANUAL_FIELDS.items():
        if field not in manual:
            continue
        value = manual[field]
        if not isinstance(value, str) or value not in options:
            return _error_response(
                422,
                "validation.invalid_enum",
                "所选选项不在支持范围内，请重新选择。",
                details={"field": field, "value": value},
            )
        cleaned[field] = value
    if not cleaned:
        return _error_response(422, "validation.invalid_value", "请至少提交一项手动信息。")
    return cleaned


def _validate_axes_value(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and 0 <= value <= 100:
        return value
    return None


def _validate_preferences(payload: dict[str, Any]) -> dict[str, Any] | JSONResponse:
    axes = payload.get("axes")
    palette = payload.get("palette")
    cleaned: dict[str, Any] = {}
    if axes is not None:
        if not isinstance(axes, dict) or not axes:
            return _error_response(422, "validation.invalid_value", "偏好轴格式不正确。")
        unknown = sorted(set(axes) - PREFERENCE_AXES)
        if unknown:
            return _error_response(
                422,
                "validation.invalid_enum",
                "存在不支持的偏好轴，请修正后重试。",
                details={"fields": unknown},
            )
        cleaned_axes: dict[str, int] = {}
        for axis, value in axes.items():
            parsed = _validate_axes_value(value)
            if parsed is None:
                return _error_response(
                    422,
                    "validation.invalid_value",
                    "偏好取值需在 0 到 100 之间。",
                    details={"field": axis, "value": value},
                )
            cleaned_axes[axis] = parsed
        cleaned["axes"] = cleaned_axes
    if palette is not None:
        if not isinstance(palette, str) or palette not in PALETTE_OPTIONS:
            return _error_response(
                422,
                "validation.invalid_enum",
                "所选色板不在支持范围内，请重新选择。",
                details={"field": "palette", "value": palette},
            )
        cleaned["palette"] = palette
    if not cleaned:
        return _error_response(422, "validation.invalid_value", "请至少提交一项偏好。")
    return cleaned


def _validate_vibe(answers: Any) -> dict[str, Any] | JSONResponse:
    if not isinstance(answers, dict) or not answers:
        return _error_response(422, "validation.invalid_value", "请提交问卷答案。")
    unknown = sorted(set(answers) - VIBE_QUESTIONS)
    if unknown:
        return _error_response(
            422,
            "validation.invalid_enum",
            "存在不支持的题目，请修正后重试。",
            details={"fields": unknown},
        )
    cleaned: dict[str, str] = {}
    for question, value in answers.items():
        if not isinstance(value, str) or value not in VIBE_OPTIONS:
            return _error_response(
                422,
                "validation.invalid_enum",
                "所选选项不在支持范围内，请重新选择。",
                details={"field": question, "value": value},
            )
        cleaned[question] = value
    return cleaned


@router.post("/sessions", status_code=201)
async def create_session(
    request: Request,
    user: dict[str, Any] | None = Depends(get_optional_user),
) -> JSONResponse:
    payload = await _read_json_object(request)
    if isinstance(payload, JSONResponse):
        return payload
    data = _prune_store(_load_store())
    scope = _idempotency_scope(request, user)
    idempotency_key = request.headers.get("x-idempotency-key")
    replay = _idempotency_replay(data, scope, idempotency_key)
    if replay is not None:
        status_code, body = replay
        return JSONResponse(status_code=status_code, content=body)

    now = _now()
    record = {
        "session_id": "ses_" + secrets.token_urlsafe(12),
        "user_id": user.get("user_id") if user else None,
        "status": "draft",
        "revision": 1,
        "schema_version": str(payload.get("schemaVersion") or SCHEMA_VERSION),
        "locale": str(payload.get("locale") or "zh-CN"),
        "created_at": _iso(now),
        "expires_at": _iso(now + timedelta(hours=_session_ttl_hours())),
        "photos": {},
        "manual": {},
        "preferences": {},
        "vibe": {},
    }
    data["sessions"].append(record)
    status_code, body = _session_response(record, status_code=201)
    _idempotency_store(data, scope, idempotency_key, status_code, body)
    _write_store(data)
    return JSONResponse(status_code=status_code, content=body)


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    user: dict[str, Any] | None = Depends(get_optional_user),
) -> JSONResponse:
    data = _load_store()
    record = _load_active_session(data, session_id, user)
    if isinstance(record, JSONResponse):
        return record
    status_code, body = _session_response(record)
    return JSONResponse(status_code=status_code, content=body)


async def _patch_session(
    request: Request,
    session_id: str,
    user: dict[str, Any] | None,
    apply_patch: Any,
) -> JSONResponse:
    payload = await _read_json_object(request)
    if isinstance(payload, JSONResponse):
        return payload
    data = _prune_store(_load_store())
    scope = _idempotency_scope(request, user)
    idempotency_key = request.headers.get("x-idempotency-key")
    replay = _idempotency_replay(data, scope, idempotency_key)
    if replay is not None:
        status_code, body = replay
        return JSONResponse(status_code=status_code, content=body)

    record = _load_active_session(data, session_id, user)
    if isinstance(record, JSONResponse):
        return record
    conflict = _check_revision(record, request.headers.get("if-match"))
    if conflict is not None:
        return conflict

    patched = apply_patch(record, payload)
    if isinstance(patched, JSONResponse):
        return patched
    record["revision"] = int(record.get("revision") or 1) + 1
    status_code, body = _session_response(record)
    _idempotency_store(data, scope, idempotency_key, status_code, body)
    _write_store(data)
    return JSONResponse(status_code=status_code, content=body)


@router.patch("/sessions/{session_id}/profile")
async def patch_session_profile(
    session_id: str,
    request: Request,
    user: dict[str, Any] | None = Depends(get_optional_user),
) -> JSONResponse:
    def apply(record: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any] | JSONResponse:
        manual = _validate_manual(payload.get("manual"))
        if isinstance(manual, JSONResponse):
            return manual
        merged = dict(record.get("manual") or {})
        merged.update(manual)
        record["manual"] = merged
        return record

    return await _patch_session(request, session_id, user, apply)


@router.patch("/sessions/{session_id}/preferences")
async def patch_session_preferences(
    session_id: str,
    request: Request,
    user: dict[str, Any] | None = Depends(get_optional_user),
) -> JSONResponse:
    def apply(record: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any] | JSONResponse:
        preferences = _validate_preferences(payload)
        if isinstance(preferences, JSONResponse):
            return preferences
        merged = dict(record.get("preferences") or {})
        if "axes" in preferences:
            axes = dict(merged.get("axes") or {})
            axes.update(preferences["axes"])
            merged["axes"] = axes
        if "palette" in preferences:
            merged["palette"] = preferences["palette"]
        record["preferences"] = merged
        return record

    return await _patch_session(request, session_id, user, apply)


@router.patch("/sessions/{session_id}/vibe")
async def patch_session_vibe(
    session_id: str,
    request: Request,
    user: dict[str, Any] | None = Depends(get_optional_user),
) -> JSONResponse:
    def apply(record: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any] | JSONResponse:
        answers = _validate_vibe(payload.get("answers"))
        if isinstance(answers, JSONResponse):
            return answers
        merged = dict(record.get("vibe") or {})
        merged.update(answers)
        record["vibe"] = merged
        return record

    return await _patch_session(request, session_id, user, apply)


def _photo_response(
    request_id: str,
    revision: int,
    kind: str,
    *,
    asset_id: str | None,
    status: str,
    code: str,
    message: str,
    issues: list[str],
) -> dict[str, Any]:
    return {
        "requestId": request_id,
        "revision": revision,
        "photo": {
            "kind": kind,
            "assetId": asset_id,
            "status": status,
            "code": code,
            "message": message,
            "issues": issues,
        },
    }


def _save_photo_asset(session_id: str, kind: str, raw: bytes, image_format: str) -> str:
    asset_id = f"asset_{kind}_{hashlib.sha256(raw).hexdigest()[:12]}"
    suffix = PHOTO_SUPPORTED_FORMATS[image_format]
    target_dir = SELFIT_ONBOARDING_ASSET_DIR / session_id
    target_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = target_dir / f"{asset_id}{suffix}.{secrets.token_urlsafe(4)}.tmp"
    tmp_path.write_bytes(raw)
    tmp_path.replace(target_dir / f"{asset_id}{suffix}")
    return asset_id


@router.post("/sessions/{session_id}/photos/{kind}")
async def upload_session_photo(
    session_id: str,
    kind: str,
    request: Request,
    user: dict[str, Any] | None = Depends(get_optional_user),
) -> JSONResponse:
    if kind not in selfit_photo.PHOTO_KINDS:
        return _error_response(
            422,
            "validation.invalid_enum",
            "照片类型不正确。",
            details={"field": "kind", "value": kind},
        )

    data = _prune_store(_load_store())
    scope = _idempotency_scope(request, user)
    idempotency_key = request.headers.get("x-idempotency-key")
    replay = _idempotency_replay(data, scope, idempotency_key)
    if replay is not None:
        status_code, body = replay
        return JSONResponse(status_code=status_code, content=body)

    record = _load_active_session(data, session_id, user)
    if isinstance(record, JSONResponse):
        return record

    form = await request.form()
    upload = form.get("image")
    if upload is None or not hasattr(upload, "read"):
        return _error_response(400, "photo.image_missing", "请选择要上传的照片。")
    raw = await upload.read()
    if not raw:
        return _error_response(400, "photo.image_missing", "请选择要上传的照片。")
    if len(raw) > PHOTO_MAX_BYTES:
        return _error_response(413, "photo.too_large", "照片超过 12MB，请压缩后再试。")

    try:
        pil_image = Image.open(io.BytesIO(raw))
        pil_image.load()
    except (UnidentifiedImageError, OSError):
        return _error_response(400, "photo.invalid_image", "无法识别照片内容，请更换一张照片。")
    if pil_image.format not in PHOTO_SUPPORTED_FORMATS:
        return _error_response(415, "photo.unsupported_type", "仅支持 JPG、PNG、WebP 格式的照片。")

    inspection = selfit_photo.inspect_photo(pil_image.convert("RGB"), kind)
    issues = selfit_photo.sanitize_issues(list(inspection.issues))
    accepted = bool(inspection.accepted) and not issues

    record["revision"] = int(record.get("revision") or 1) + 1
    photos = record.setdefault("photos", {})
    request_id = _request_id()
    if accepted:
        asset_id = _save_photo_asset(session_id, kind, raw, str(pil_image.format))
        photos[kind] = {
            "asset_id": asset_id,
            "status": "accepted",
            "format": pil_image.format,
            "width": pil_image.width,
            "height": pil_image.height,
        }
        label = selfit_photo.KIND_LABELS[kind]
        body = _photo_response(
            request_id,
            record["revision"],
            kind,
            asset_id=asset_id,
            status="accepted",
            code="photo.accepted",
            message=f"{label}可用",
            issues=[],
        )
    else:
        if not issues:
            issues = [selfit_photo.ISSUE_UNSUPPORTED_CONTENT]
        primary = selfit_photo.primary_issue(issues)
        photos[kind] = {"asset_id": None, "status": "rejected", "code": f"photo.{primary}"}
        body = _photo_response(
            request_id,
            record["revision"],
            kind,
            asset_id=None,
            status="rejected",
            code=f"photo.{primary}",
            message=selfit_photo.issue_message(primary, kind),
            issues=issues,
        )

    _idempotency_store(data, scope, idempotency_key, 200, body)
    _write_store(data)
    return JSONResponse(status_code=200, content=body)


def _find_report_job(data: dict[str, Any], job_id: str) -> dict[str, Any] | None:
    return next(
        (job for job in data["report_jobs"] if job.get("job_id") == job_id),
        None,
    )


def _find_report(data: dict[str, Any], report_id: str) -> dict[str, Any] | None:
    return next(
        (report for report in data["reports"] if report.get("report_id") == report_id),
        None,
    )


def _job_progress(elapsed_ms: float) -> tuple[str, int]:
    stage, progress = REPORT_STAGE_SCHEDULE_MS[0][1], REPORT_STAGE_SCHEDULE_MS[0][2]
    for threshold, candidate_stage, candidate_progress in REPORT_STAGE_SCHEDULE_MS:
        if elapsed_ms >= threshold:
            stage, progress = candidate_stage, candidate_progress
    return stage, progress


def _public_job(job: dict[str, Any], report: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "jobId": job["job_id"],
        "status": job["status"],
        "progress": int(job.get("progress") or 0),
        "pollAfterMs": REPORT_POLL_AFTER_MS,
    }
    if job.get("stage"):
        payload["stage"] = job["stage"]
    if job["status"] == "completed" and job.get("report_id"):
        payload["reportId"] = job["report_id"]
        if report is not None:
            payload["report"] = report.get("data") or {}
    if job["status"] == "failed" and job.get("error"):
        payload["error"] = job["error"]
    return payload


def _finalize_report_job(data: dict[str, Any], job: dict[str, Any]) -> None:
    """到达演示时长的任务在这里真正调用报告生成算法。"""

    session = _find_session(data, str(job.get("session_id") or ""))
    try:
        if session is None:
            raise ValueError("session missing")
        report_data = selfit_report.build_report(session)
    except Exception:
        job["status"] = "failed"
        job["error"] = {
            "code": "report.generation_failed",
            "message": "报告生成失败，请返回问卷页重试。",
            "retryable": True,
            "details": {},
        }
        return
    report = {
        "report_id": "rep_" + secrets.token_urlsafe(12),
        "session_id": session["session_id"],
        "user_id": session.get("user_id"),
        "created_at": _iso(_now()),
        "data": report_data,
    }
    data["reports"].append(report)
    job["status"] = "completed"
    job["progress"] = 100
    job["stage"] = "finalizing"
    job["report_id"] = report["report_id"]


def _refresh_report_job(data: dict[str, Any], job: dict[str, Any]) -> bool:
    """按耗时推进任务状态；返回是否有状态变化需要落盘。"""

    if job["status"] in {"completed", "failed"}:
        return False
    created_at = _parse_iso(job.get("created_at")) or _now()
    elapsed_ms = (_now() - created_at).total_seconds() * 1000
    if elapsed_ms >= REPORT_TOTAL_MS:
        _finalize_report_job(data, job)
        return True
    stage, progress = _job_progress(elapsed_ms)
    changed = job.get("stage") != stage or job.get("progress") != progress or job.get("status") != "processing"
    job["status"] = "processing"
    job["stage"] = stage
    job["progress"] = progress
    return changed


@router.post("/sessions/{session_id}/report-jobs", status_code=202)
async def create_report_job(
    session_id: str,
    request: Request,
    user: dict[str, Any] | None = Depends(get_optional_user),
) -> JSONResponse:
    data = _prune_store(_load_store())
    scope = _idempotency_scope(request, user)
    idempotency_key = request.headers.get("x-idempotency-key")
    replay = _idempotency_replay(data, scope, idempotency_key)
    if replay is not None:
        status_code, body = replay
        return JSONResponse(status_code=status_code, content=body)

    record = _load_active_session(data, session_id, user)
    if isinstance(record, JSONResponse):
        return record

    job = {
        "job_id": "job_" + secrets.token_urlsafe(12),
        "session_id": record["session_id"],
        "user_id": record.get("user_id"),
        "status": "queued",
        "progress": 0,
        "stage": None,
        "report_id": None,
        "error": None,
        "created_at": _iso(_now()),
    }
    data["report_jobs"].append(job)
    status_code, body = 202, {"requestId": _request_id(), "job": _public_job(job)}
    _idempotency_store(data, scope, idempotency_key, status_code, body)
    _write_store(data)
    return JSONResponse(status_code=status_code, content=body)


@router.get("/report-jobs/{job_id}")
async def get_report_job(
    job_id: str,
    user: dict[str, Any] | None = Depends(get_optional_user),
) -> JSONResponse:
    data = _load_store()
    job = _find_report_job(data, job_id)
    if job is not None and not _session_visible_to(job, user):
        job = None
    if job is None:
        return _error_response(404, "report.job_not_found", "没有找到报告任务。")

    if _refresh_report_job(data, job):
        _write_store(data)

    report = _find_report(data, str(job.get("report_id") or "")) if job.get("report_id") else None
    return JSONResponse(
        status_code=200,
        content={"requestId": _request_id(), "job": _public_job(job, report)},
    )


@router.get("/reports/{report_id}")
async def get_report(
    report_id: str,
    user: dict[str, Any] | None = Depends(get_optional_user),
) -> JSONResponse:
    data = _load_store()
    report = _find_report(data, report_id)
    if report is not None and not _session_visible_to(report, user):
        report = None
    if report is None:
        return _error_response(404, "report.not_found", "没有找到这份报告。")
    return JSONResponse(
        status_code=200,
        content={"requestId": _request_id(), "report": report.get("data") or {}},
    )


def _load_visible_report(
    data: dict[str, Any], report_id: str, user: dict[str, Any] | None
) -> dict[str, Any] | JSONResponse:
    report = _find_report(data, report_id)
    if report is None or not _session_visible_to(report, user):
        return _error_response(404, "report.not_found", "没有找到这份报告。")
    return report


@router.post("/reports/{report_id}/outfit-requests", status_code=202)
async def create_outfit_request(
    report_id: str,
    request: Request,
    user: dict[str, Any] | None = Depends(get_optional_user),
) -> JSONResponse:
    payload = await _read_json_object(request)
    if isinstance(payload, JSONResponse):
        return payload
    data = _prune_store(_load_store())
    scope = _idempotency_scope(request, user)
    idempotency_key = request.headers.get("x-idempotency-key")
    replay = _idempotency_replay(data, scope, idempotency_key)
    if replay is not None:
        status_code, body = replay
        return JSONResponse(status_code=status_code, content=body)

    report = _load_visible_report(data, report_id, user)
    if isinstance(report, JSONResponse):
        return report

    outfit_request = {
        "request_id": "outfit_" + secrets.token_urlsafe(12),
        "report_id": report["report_id"],
        "session_id": report.get("session_id"),
        "user_id": report.get("user_id"),
        "status": "queued",
        "source": str(payload.get("source") or "report"),
        "intent": str(payload.get("intent") or "complete_look"),
        "created_at": _iso(_now()),
    }
    data["outfit_requests"].append(outfit_request)
    status_code, body = 202, {
        "requestId": _request_id(),
        "request": {"requestId": outfit_request["request_id"], "status": "queued"},
    }
    _idempotency_store(data, scope, idempotency_key, status_code, body)
    _write_store(data)
    return JSONResponse(status_code=status_code, content=body)


def _validate_share_payload(payload: dict[str, Any]) -> tuple[int, str, str] | JSONResponse:
    slide_index = payload.get("slideIndex", 0)
    if isinstance(slide_index, bool) or not isinstance(slide_index, int) or not 0 <= slide_index < selfit_share.SHARE_SLIDE_COUNT:
        return _error_response(
            422,
            "validation.invalid_value",
            "分享页序号不正确。",
            details={"field": "slideIndex", "value": slide_index},
        )
    channel = payload.get("channel", "保存单张")
    if not isinstance(channel, str) or channel not in selfit_share.SHARE_CHANNELS:
        return _error_response(
            422,
            "validation.invalid_enum",
            "分享渠道不在支持范围内。",
            details={"field": "channel", "value": channel},
        )
    image_format = payload.get("format", "png")
    if not isinstance(image_format, str) or image_format not in selfit_share.SHARE_FORMATS:
        return _error_response(
            422,
            "validation.invalid_enum",
            "分享图格式不在支持范围内。",
            details={"field": "format", "value": image_format},
        )
    return slide_index, channel, image_format


def _share_asset_expiry(data: dict[str, Any], report: dict[str, Any]) -> str:
    session = _find_session(data, str(report.get("session_id") or ""))
    if session is not None and session.get("expires_at"):
        return str(session["expires_at"])
    return _iso(_now() + timedelta(hours=_session_ttl_hours()))


@router.post("/reports/{report_id}/share-assets")
async def create_share_asset(
    report_id: str,
    request: Request,
    user: dict[str, Any] | None = Depends(get_optional_user),
) -> JSONResponse:
    payload = await _read_json_object(request)
    if isinstance(payload, JSONResponse):
        return payload
    data = _prune_store(_load_store())
    scope = _idempotency_scope(request, user)
    idempotency_key = request.headers.get("x-idempotency-key")
    replay = _idempotency_replay(data, scope, idempotency_key)
    if replay is not None:
        status_code, body = replay
        return JSONResponse(status_code=status_code, content=body)

    report = _load_visible_report(data, report_id, user)
    if isinstance(report, JSONResponse):
        return report
    validated = _validate_share_payload(payload)
    if isinstance(validated, JSONResponse):
        return validated
    slide_index, channel, image_format = validated

    try:
        content = selfit_share.render_share_image(report.get("data") or {}, slide_index, channel, image_format)
    except Exception:
        return _error_response(500, "share.render_failed", "分享图生成失败，请稍后重试。", retryable=True)

    asset_id = "share_" + secrets.token_urlsafe(12)
    filename = f"{asset_id}.{image_format}"
    target_dir = SELFIT_ONBOARDING_ASSET_DIR / "shared"
    target_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = target_dir / f"{filename}.{secrets.token_urlsafe(4)}.tmp"
    tmp_path.write_bytes(content)
    tmp_path.replace(target_dir / filename)

    data["share_assets"].append(
        {
            "asset_id": asset_id,
            "report_id": report["report_id"],
            "session_id": report.get("session_id"),
            "user_id": report.get("user_id"),
            "slide_index": slide_index,
            "channel": channel,
            "format": image_format,
            "filename": filename,
            "created_at": _iso(_now()),
        }
    )
    body = {
        "requestId": _request_id(),
        "asset": {
            "assetId": asset_id,
            "status": "ready",
            "slideIndex": slide_index,
            "channel": channel,
            "downloadUrl": f"/api/v1/selfit/share-assets/{asset_id}/download",
            "expiresAt": _share_asset_expiry(data, report),
        },
    }
    _idempotency_store(data, scope, idempotency_key, 200, body)
    _write_store(data)
    return JSONResponse(status_code=200, content=body)


@router.get("/share-assets/{asset_id}/download", response_model=None)
async def download_share_asset(
    asset_id: str,
    user: dict[str, Any] | None = Depends(get_optional_user),
) -> FileResponse | JSONResponse:
    data = _load_store()
    asset = next(
        (item for item in data["share_assets"] if item.get("asset_id") == asset_id),
        None,
    )
    if asset is None or not _session_visible_to(asset, user):
        return _error_response(404, "share.asset_not_found", "没有找到这份分享素材。")
    path = SELFIT_ONBOARDING_ASSET_DIR / "shared" / str(asset.get("filename") or "")
    if not path.is_file():
        return _error_response(404, "share.asset_not_found", "没有找到这份分享素材。")
    return FileResponse(path, media_type=f"image/{asset.get('format') or 'png'}")
