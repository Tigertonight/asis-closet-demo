from __future__ import annotations

import hashlib
import io
import json
import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from PIL import Image, ImageOps, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool

from app import selfit_assets, selfit_onboarding_store as _store_module
from app import selfit_photo, selfit_report, selfit_share
from app.auth import get_optional_user
from app.ops import env_int
from app.storage import ROOT_DIR

# iPhone 手机直拍默认是 HEIC/HEIF；不注册 opener 的话 PIL 直接打不开，
# 用户会看到「格式不对」（内测反馈：接真实链路后手机直拍全部被拦）。
try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
except Exception:  # pragma: no cover - 依赖缺失时退回 JPEG/PNG/WebP
    register_heif_opener = None

# 注意：SELFIT_ONBOARDING_ASSET_DIR 下的用户原图与分享图是初始数据资产，需要精心保留。
# 会话过期只清理索引记录（sessions.json / 任务 / 报告），资产文件一律不删。
# 后续迁移对象存储时以该目录为同步源，禁止加入任何定期清理任务。
# 接入真实照片检测与属性识别算法；联调时可设 SELFIT_PHOTO_INSPECTOR=accept_all 退回全放行。
if os.getenv("SELFIT_PHOTO_INSPECTOR", "attribute") != "accept_all":
    selfit_photo.register_photo_inspector(selfit_photo.attribute_inspector)

SELFIT_ONBOARDING_DIR = ROOT_DIR / "outputs" / "selfit_onboarding"
SELFIT_ONBOARDING_STORE_PATH = SELFIT_ONBOARDING_DIR / "sessions.json"
SELFIT_ONBOARDING_ASSET_DIR = SELFIT_ONBOARDING_DIR / "assets"

SCHEMA_VERSION = "selfit-onboarding-v1"
PHOTO_MAX_BYTES = 20 * 1024 * 1024
PHOTO_SUPPORTED_FORMATS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}

# 报告任务：POST 创建后由后台线程真实执行 builder 并写入状态迁移；
# GET 只读取，处理中的 stage/progress 为响应层估算（不落库，避免与 worker 写竞争）。
REPORT_POLL_AFTER_MS = 800
REPORT_ESTIMATED_STAGES = (
    (0.0, "profile", 25),
    (1.0, "inspiration", 50),
    (2.0, "composition", 75),
    (3.0, "finalizing", 95),
)

SKIN_OPTIONS = {"冷白肤", "暖白肤", "中性自然肤", "暖黄肤", "橄榄肤", "小麦色"}
FACE_SHAPE_OPTIONS = {"椭圆脸", "圆脸", "方脸", "心形脸", "菱形脸"}
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
    if record.get("suit_completed_at") or all(
        (photos.get(kind) or {}).get("status") == "accepted" for kind in ("face", "body")
    ):
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


def create_session_from_mirror_handoff(
    handoff: dict[str, Any], user: dict[str, Any]
) -> dict[str, Any]:
    """Create the authenticated continuation session after a one-time mirror claim."""

    data = _prune_store(_load_store())
    handoff_id = str(handoff.get("handoff_id") or "")
    existing = next(
        (
            record
            for record in data["sessions"]
            if record.get("mirror_handoff_id") == handoff_id
            and record.get("user_id") == user.get("user_id")
        ),
        None,
    )
    if existing is not None:
        return _public_session(existing)
    now = _now()
    record = {
        "session_id": "ses_" + secrets.token_urlsafe(12),
        "user_id": user.get("user_id"),
        "status": "draft",
        "revision": 1,
        "schema_version": SCHEMA_VERSION,
        "locale": "zh-CN",
        "created_at": _iso(now),
        "expires_at": _iso(now + timedelta(hours=_session_ttl_hours())),
        "source": "mirror_handoff",
        "mirror_handoff_id": handoff_id,
        "suit_completed_at": _iso(now),
        "mirror_analysis": dict(handoff.get("analysis") or {}),
        "mirror_asset_path": handoff.get("asset_path"),
        "mirror_assets": dict(handoff.get("assets") or {}),
        "suit_input_asset_id": handoff.get("suit_asset_id"),
        "mirror_preview_asset_id": handoff.get("mirror_preview_asset_id"),
        "photos": {},
        "manual": {},
        "preferences": {},
        "vibe": {},
    }
    _hydrate_mirror_photos(record, handoff)
    pending_rejected = record.pop("_rejected_photos_pending", [])
    for item in pending_rejected:
        try:
            _save_rejected_photo_record(
                data,
                session_id=record["session_id"],
                kind=str(item.get("kind") or "face"),
                asset_id=str(item.get("asset_id") or ""),
                image_format=str(item.get("format") or "JPEG"),
                width=int(item.get("width") or 0),
                height=int(item.get("height") or 0),
                issues=list(item.get("issues") or []),
                user_id=record.get("user_id"),
                source=str(item.get("source") or "mirror"),
            )
        except Exception:
            pass  # 留存失败不影响 claim 主流程
    data["sessions"].append(record)
    _write_store(data)
    return _public_session(record)


# 镜子全身照 → 大头照：裁剪框边长为脸宽的倍数。
# 2.8 倍时脸占裁剪图约 36% 边长（area_ratio ≈ 0.17），稳过 face ≥ 0.08 门禁。
HEAD_CROP_FACE_RATIO = 2.8
# 眼/耳线位于裁剪框顶部下方的比例：上方留头顶头发，下方留下巴与脖颈。
HEAD_CROP_ANCHOR_TOP = 0.35
# 头部关键点最低可见性（与 attribute_pipeline.BODY_MIN_VISIBILITY 对齐）。
HEAD_CROP_MIN_VISIBILITY = 0.5
# 耳距 / 瞳距 → 全脸宽的换算系数（成年人颅面比例先验）。
_HEAD_WIDTH_FROM_EARS = 1.2
_HEAD_WIDTH_FROM_EYES = 2.3


def _head_crop_box_from_pose(rgb: np.ndarray, img_w: int, img_h: int) -> tuple[int, int, int] | None:
    """用 body pose 的眼/耳关键点定位头部裁剪框；全身照小脸时比人脸检测器可靠。"""

    from app.attribute_pipeline import _detect_body_pose

    pose = _detect_body_pose(rgb)
    if pose is None or len(pose) < 9:
        return None

    def point(index: int) -> tuple[float, float, float]:
        landmark = pose[index]
        return (
            float(landmark.x) * img_w,
            float(landmark.y) * img_h,
            float(getattr(landmark, "visibility", 1.0)),
        )

    left_ear, right_ear = point(7), point(8)
    left_eye, right_eye = point(2), point(5)
    ear_span = abs(left_ear[0] - right_ear[0])
    eye_span = abs(left_eye[0] - right_eye[0])
    ears_usable = left_ear[2] >= HEAD_CROP_MIN_VISIBILITY and right_ear[2] >= HEAD_CROP_MIN_VISIBILITY and ear_span > 2
    eyes_usable = left_eye[2] >= HEAD_CROP_MIN_VISIBILITY and right_eye[2] >= HEAD_CROP_MIN_VISIBILITY and eye_span > 2
    if ears_usable:
        center_x = (left_ear[0] + right_ear[0]) / 2
        anchor_y = (left_ear[1] + right_ear[1]) / 2
        face_width = ear_span * _HEAD_WIDTH_FROM_EARS
    elif eyes_usable:
        center_x = (left_eye[0] + right_eye[0]) / 2
        anchor_y = (left_eye[1] + right_eye[1]) / 2
        face_width = eye_span * _HEAD_WIDTH_FROM_EYES
    else:
        return None
    side = min(int(face_width * HEAD_CROP_FACE_RATIO), img_w, img_h)
    if side < 80:
        return None
    left = int(center_x - side / 2)
    top = int(anchor_y - side * HEAD_CROP_ANCHOR_TOP)
    return left, top, side


def _head_crop_box_from_face_detector(rgb: np.ndarray, img_w: int, img_h: int) -> tuple[int, int, int] | None:
    """回退方案：人脸检测框（取语义检测器优先、面积最大者）扩成头部裁剪框。"""

    from app.cv_pipeline import _detect_face_candidates

    bgr = np.ascontiguousarray(rgb[:, :, ::-1])
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    candidates = _detect_face_candidates(bgr, gray)
    if not candidates:
        return None
    semantic = [item for item in candidates if item[4].startswith("mediapipe")]
    pool = semantic or candidates
    x, y, w, h, _detector = max(pool, key=lambda item: item[2] * item[3])
    if w <= 0 or h <= 0:
        return None
    side = min(int(max(w, h) * HEAD_CROP_FACE_RATIO), img_w, img_h)
    if side < 80:
        return None
    left = int(x + w / 2 - side / 2)
    top = int(y - h * 0.9)
    return left, top, side


def _crop_head_from_photo(image: Image.Image) -> Image.Image | None:
    """从全身照裁出可用作 face 输入的头部方图；定位失败时返回 None。"""

    rgb = np.asarray(image.convert("RGB"))
    img_h, img_w = rgb.shape[:2]
    crop_box = _head_crop_box_from_pose(rgb, img_w, img_h)
    if crop_box is None:
        crop_box = _head_crop_box_from_face_detector(rgb, img_w, img_h)
    if crop_box is None:
        return None
    left, top, side = crop_box
    left = max(0, min(left, img_w - side))
    top = max(0, min(top, img_h - side))
    return image.crop((left, top, left + side, top + side))


def _encode_photo_jpeg(image: Image.Image) -> bytes:
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=90)
    return output.getvalue()


def _accepted_photo_record(
    session_id: str, kind: str, image: Image.Image, inspection: selfit_photo.PhotoInspection, source: str
) -> dict[str, Any]:
    _archive_photo_to_qa(image, kind, "mirror" if source.startswith("mirror") else "app")
    return {
        "asset_id": _save_photo_asset(session_id, kind, _encode_photo_jpeg(image), "JPEG"),
        "status": "accepted",
        "format": "JPEG",
        "width": image.width,
        "height": image.height,
        "attributes": dict(inspection.attributes),
        "source": source,
    }


def _archive_photo_to_qa(image: Image.Image, kind: str, source: str) -> None:
    """用户照片归档进 QA 数据集（算法分析资产）。旁路失败不影响主流程。"""

    try:
        from app.qa_onboarding import archive_user_photo

        archive_user_photo(image, kind, source)
    except Exception:
        pass


def _hydrate_mirror_photos(record: dict[str, Any], handoff: dict[str, Any]) -> None:
    """镜子拍摄原图回填 suit 照片：全身照直接检测，大头照从原图裁头部识别。

    任一环节失败都静默降级（对应 photos 槽位留空，报告层回退默认属性），
    绝不让 claim 因照片质量问题失败；被拒的检测同样留存 rejected_photos，
    供管理后台回看与算法优化（原图本身已在 mirror assets 里，不重复落盘）。
    """

    # onboarding record 用 mirror_* 前缀；原始 handoff 记录用 assets / asset_path。
    # 两个来源都兜底，保证回填在旧记录与新记录上都可用。
    assets = record.get("mirror_assets") or handoff.get("assets") or {}
    original = assets.get("original") or {}
    asset_path = (
        record.get("mirror_asset_path")
        or handoff.get("asset_path")
        or original.get("asset_path")
    )
    if not asset_path:
        return
    path = Path(str(asset_path))
    if not path.is_file():
        return
    try:
        image = Image.open(path)
        image.load()
    except (UnidentifiedImageError, OSError):
        return
    if image.mode != "RGB":
        image = image.convert("RGB")

    session_id = record["session_id"]
    photos = record.setdefault("photos", {})
    rejected: list[dict[str, Any]] = record.setdefault("_rejected_photos_pending", [])

    body_inspection = selfit_photo.inspect_photo(image, "body")
    if body_inspection.accepted:
        photos["body"] = _accepted_photo_record(session_id, "body", image, body_inspection, "mirror")
    else:
        issues = selfit_photo.sanitize_issues(list(body_inspection.issues)) or [
            selfit_photo.ISSUE_UNSUPPORTED_CONTENT
        ]
        rejected.append(
            {
                "kind": "body",
                "asset_id": original.get("asset_id"),
                "format": original.get("image_format") or "JPEG",
                "width": image.width,
                "height": image.height,
                "issues": issues,
                "source": "mirror",
            }
        )

    head_crop = _crop_head_from_photo(image)
    if head_crop is not None:
        face_inspection = selfit_photo.inspect_photo(head_crop, "face")
        if face_inspection.accepted:
            photos["face"] = _accepted_photo_record(
                session_id, "face", head_crop, face_inspection, "mirror_head_crop"
            )
        else:
            issues = selfit_photo.sanitize_issues(list(face_inspection.issues)) or [
                selfit_photo.ISSUE_UNSUPPORTED_CONTENT
            ]
            rejected.append(
                {
                    "kind": "face",
                    "asset_id": original.get("asset_id"),
                    "format": original.get("image_format") or "JPEG",
                    "width": head_crop.width,
                    "height": head_crop.height,
                    "issues": issues,
                    "source": "mirror_head_crop",
                }
            )


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


def _session_linkage(data: dict[str, Any], session_id: str) -> dict[str, Any]:
    """会话恢复关联：最新报告任务与已生成报告，供前端刷新/重入后续接。

    契约允许在 session 响应上补充字段，前端不依赖时可安全忽略。
    """

    linkage: dict[str, Any] = {}
    jobs = [job for job in data["report_jobs"] if job.get("session_id") == session_id]
    latest_job = max(jobs, key=lambda job: str(job.get("created_at") or ""), default=None)
    if latest_job is not None:
        _resubmit_stale_queued_job(latest_job)
        if _expire_processing_job(data, latest_job):
            _write_store(data)
        linkage["latestReportJob"] = _public_job(latest_job)
    reports = [item for item in data["reports"] if item.get("session_id") == session_id]
    latest_report = max(reports, key=lambda item: str(item.get("created_at") or ""), default=None)
    if latest_report is not None:
        linkage["latestReport"] = {
            "reportId": latest_report["report_id"],
            "createdAt": latest_report.get("created_at"),
        }
    return linkage


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
    body["session"].update(_session_linkage(data, session_id))
    return JSONResponse(status_code=status_code, content=body)


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    user: dict[str, Any] | None = Depends(get_optional_user),
) -> JSONResponse:
    """用户主动删除：级联清除会话、任务、报告、穿搭请求与分享素材记录，并删除资产文件。

    这是资产"只增不删"策略的唯一例外（隐私契约要求的用户删除机制）。
    """

    data = _load_store()
    record = _load_active_session(data, session_id, user)
    if isinstance(record, JSONResponse):
        return record

    store = _asset_store()
    photos = record.get("photos") or {}
    for kind, photo in photos.items():
        asset_id = (photo or {}).get("asset_id")
        image_format = (photo or {}).get("format")
        suffix = PHOTO_SUPPORTED_FORMATS.get(str(image_format or ""), "")
        if asset_id and suffix:
            store.delete(f"{session_id}/{asset_id}{suffix}")
    for item in data["share_assets"]:
        if item.get("session_id") == session_id and item.get("filename"):
            store.delete(f"shared/{item['filename']}")

    data["sessions"] = [item for item in data["sessions"] if item.get("session_id") != session_id]
    data["report_jobs"] = [item for item in data["report_jobs"] if item.get("session_id") != session_id]
    data["reports"] = [item for item in data["reports"] if item.get("session_id") != session_id]
    data["outfit_requests"] = [item for item in data["outfit_requests"] if item.get("session_id") != session_id]
    data["share_assets"] = [item for item in data["share_assets"] if item.get("session_id") != session_id]
    _write_store(data)
    return JSONResponse(
        status_code=200,
        content={"requestId": _request_id(), "session": {"sessionId": session_id, "status": "deleted"}},
    )


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


def _asset_store() -> selfit_assets.AssetStore:
    return selfit_assets.asset_store_from_env(SELFIT_ONBOARDING_ASSET_DIR)


def _save_photo_asset(session_id: str, kind: str, raw: bytes, image_format: str) -> str:
    asset_id = f"asset_{kind}_{hashlib.sha256(raw).hexdigest()[:12]}"
    suffix = PHOTO_SUPPORTED_FORMATS[image_format]
    content_type = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}[image_format]
    _asset_store().save(f"{session_id}/{asset_id}{suffix}", raw, content_type)
    return asset_id


def _save_rejected_photo_record(
    data: dict[str, Any],
    *,
    session_id: str,
    kind: str,
    asset_id: str,
    image_format: str,
    width: int,
    height: int,
    issues: list[str],
    user_id: Any,
    source: str | None,
) -> None:
    """检测被拒的照片留存：资产照常落盘 + 索引记录，供后台查看与算法优化。

    不会因为保存失败让用户上传失败路径出错（留存是旁路）。
    """

    record = {
        "record_id": "rej_" + secrets.token_urlsafe(12),
        "session_id": session_id,
        "user_id": user_id,
        "kind": kind,
        "asset_id": asset_id,
        "format": image_format,
        "width": width,
        "height": height,
        "issues": list(issues),
        "primary_issue": selfit_photo.primary_issue(issues),
        "source": source or "app",
        "created_at": _iso(_now()),
    }
    data["rejected_photos"].append(record)


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
        return _error_response(413, "photo.too_large", "照片超过 20MB，请压缩后再试。")

    try:
        pil_image = Image.open(io.BytesIO(raw))
        pil_image.load()
    except (UnidentifiedImageError, OSError):
        return _error_response(400, "photo.invalid_image", "无法识别照片内容，请更换一张照片。")
    source_format = str(pil_image.format or "")

    # EXIF 方向转正：手机直拍竖照的 orientation 在像素里不生效，不转正的话
    # 人脸/姿态检测会拿到横躺的图。对所有格式统一做，幂等。
    pil_image = ImageOps.exif_transpose(pil_image)
    # exif_transpose 转置后副本的 format 会丢失，用 source_format 补记。
    stored_format = source_format
    if source_format not in PHOTO_SUPPORTED_FORMATS:
        # 手机可能交付 HEIC/HEIF/AVIF/MPO 等容器。只要 Pillow 能真实解码，
        # 就取主图并统一重编码为 JPEG，不再用格式名称二次误拒。
        buffer = io.BytesIO()
        pil_image.convert("RGB").save(buffer, format="JPEG", quality=92)
        raw = buffer.getvalue()
        pil_image = Image.open(io.BytesIO(raw))
        pil_image.load()
        stored_format = "JPEG"

    # 照片检测为 CPU 密集的同步 CV 计算，丢线程池执行，避免阻塞事件循环。
    inspection = await run_in_threadpool(selfit_photo.inspect_photo, pil_image.convert("RGB"), kind)
    issues = selfit_photo.sanitize_issues(list(inspection.issues))
    accepted = bool(inspection.accepted) and not issues

    record["revision"] = int(record.get("revision") or 1) + 1
    photos = record.setdefault("photos", {})
    request_id = _request_id()
    if accepted:
        asset_id = _save_photo_asset(session_id, kind, raw, stored_format)
        # 用户照片归档进 QA 数据集：镜子流程（mirror_handoff）归 mirror，其余归 app。
        _archive_photo_to_qa(
            pil_image, kind, "mirror" if record.get("source") == "mirror_handoff" else "app"
        )
        photos[kind] = {
            "asset_id": asset_id,
            "status": "accepted",
            "format": stored_format,
            "width": pil_image.width,
            "height": pil_image.height,
            # 算法推断的肤色/脸型/身型标签，供报告任务与「手动纠正优先」合并消费。
            "attributes": dict(inspection.attributes),
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
        # 被拒照片同样落盘留存（asset 只增不删），并索引到 rejected_photos，
        # 供管理后台回看与检测算法离线优化。
        try:
            rejected_asset_id = _save_photo_asset(session_id, kind, raw, stored_format)
            _save_rejected_photo_record(
                data,
                session_id=session_id,
                kind=kind,
                asset_id=rejected_asset_id,
                image_format=stored_format,
                width=pil_image.width,
                height=pil_image.height,
                issues=issues,
                user_id=record.get("user_id"),
                source="app" if record.get("source") != "mirror_handoff" else "mirror",
            )
        except Exception:
            pass  # 留存失败不影响用户主流程
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


_REPORT_EXECUTOR = ThreadPoolExecutor(
    max_workers=env_int("SELFIT_REPORT_JOB_WORKERS", 2),
    thread_name_prefix="selfit-report",
)

_REPORT_JOB_FAILED_ERROR = {
    "code": "report.generation_failed",
    "message": "报告生成失败，请返回问卷页重试。",
    "retryable": True,
    "details": {},
}


def _estimated_stage_progress(elapsed_seconds: float) -> tuple[str, int]:
    stage, progress = REPORT_ESTIMATED_STAGES[0][1], REPORT_ESTIMATED_STAGES[0][2]
    for threshold, candidate_stage, candidate_progress in REPORT_ESTIMATED_STAGES:
        if elapsed_seconds >= threshold:
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
    if job["status"] == "processing":
        # 处理中的进度为估算投影：builder 真实耗时不可预知，完成只由 worker 写入。
        started = _parse_iso(job.get("started_at")) or _parse_iso(job.get("created_at"))
        elapsed = (_now() - started).total_seconds() if started else 0.0
        stage, progress = _estimated_stage_progress(elapsed)
        payload["stage"] = stage
        payload["progress"] = max(payload["progress"], progress)
    if job["status"] == "completed" and job.get("report_id"):
        payload["reportId"] = job["report_id"]
        if report is not None:
            payload["report"] = report.get("data") or {}
    if job["status"] == "failed" and job.get("error"):
        payload["error"] = job["error"]
    return payload


def _run_report_job(job_id: str) -> None:
    """后台 worker：真实执行报告生成算法并落库状态迁移。"""

    data = _prune_store(_load_store())
    job = _find_report_job(data, job_id)
    if job is None or job.get("status") != "queued":
        return
    job["status"] = "processing"
    job["stage"] = "profile"
    job["progress"] = 10
    job["started_at"] = _iso(_now())
    _write_store(data)

    session = _find_session(data, str(job.get("session_id") or ""))
    try:
        if session is None:
            raise ValueError("session missing")
        report_data = selfit_report.build_report(session)
    except Exception:
        data = _load_store()
        job = _find_report_job(data, job_id)
        if job is not None and job.get("status") == "processing":
            job["status"] = "failed"
            job["error"] = dict(_REPORT_JOB_FAILED_ERROR)
            _write_store(data)
        return

    data = _load_store()
    job = _find_report_job(data, job_id)
    if job is None or job.get("status") != "processing":
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
    _write_store(data)


def _resubmit_stale_queued_job(job: dict[str, Any]) -> None:
    """服务重启后 queued 任务的兜底重投（worker 已随进程消失）。"""

    if job.get("status") != "queued":
        return
    created_at = _parse_iso(job.get("created_at")) or _now()
    if (_now() - created_at).total_seconds() < 30:
        return
    _REPORT_EXECUTOR.submit(_run_report_job, str(job["job_id"]))


def _expire_processing_job(data: dict[str, Any], job: dict[str, Any]) -> bool:
    """processing 超时熔断（对齐前端 120s 总等待上限）；返回是否有落盘。"""

    if job.get("status") != "processing":
        return False
    started = _parse_iso(job.get("started_at")) or _parse_iso(job.get("created_at")) or _now()
    if (_now() - started).total_seconds() <= env_int("SELFIT_REPORT_JOB_TIMEOUT_SECONDS", 110):
        return False
    job["status"] = "failed"
    job["error"] = dict(_REPORT_JOB_FAILED_ERROR)
    return True


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
    _REPORT_EXECUTOR.submit(_run_report_job, job["job_id"])
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

    _resubmit_stale_queued_job(job)
    if _expire_processing_job(data, job):
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


@router.get("/outfit-requests/{request_id}")
async def get_outfit_request(
    request_id: str,
    user: dict[str, Any] | None = Depends(get_optional_user),
) -> JSONResponse:
    data = _load_store()
    outfit_request = next(
        (item for item in data["outfit_requests"] if item.get("request_id") == request_id),
        None,
    )
    if outfit_request is None or not _session_visible_to(outfit_request, user):
        return _error_response(404, "outfit.request_not_found", "没有找到这个穿搭请求。")
    return JSONResponse(
        status_code=200,
        content={
            "requestId": _request_id(),
            "request": {
                "requestId": outfit_request["request_id"],
                "reportId": outfit_request.get("report_id"),
                "status": outfit_request.get("status") or "queued",
            },
        },
    )


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
    _asset_store().save(f"shared/{filename}", content, f"image/{image_format}")

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
) -> Response:
    data = _load_store()
    asset = next(
        (item for item in data["share_assets"] if item.get("asset_id") == asset_id),
        None,
    )
    if asset is None or not _session_visible_to(asset, user):
        return _error_response(404, "share.asset_not_found", "没有找到这份分享素材。")
    key = f"shared/{asset.get('filename') or ''}"
    store = _asset_store()
    public_url = store.public_url(key)
    if public_url:
        return RedirectResponse(public_url, status_code=302)
    path = store.local_path(key)
    if path is None:
        return _error_response(404, "share.asset_not_found", "没有找到这份分享素材。")
    return FileResponse(path, media_type=f"image/{asset.get('format') or 'png'}")
