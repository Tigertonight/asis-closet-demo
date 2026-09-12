"""管理后台：用户提交（报告 + 照片）的查询与下载，服务现场打印流程。

数据口径：
- 「提交」= onboarding 会话（App 上传或智能镜扫码领取），关联最新报告与照片；
- 智能镜拍摄保留两个版本：原始照片（算法留存）与美颜照片（现场打印），
  会话记录里的 mirror_assets 与 handoff 记录里的 assets 都可解析；
- 未扫码领取的镜子拍摄单独列在「镜子拍摄记录」，保证照片仍可下载；
- 会话过期只影响用户端续填，管理后台不做 TTL 过滤：资产只增不删，
  路演后仍可回看与导出。

鉴权：全部接口走 get_admin_user（管理员密码登录，Bearer 或 cookie），
与 /admin/api/analytics 同一保护级别。
"""

from __future__ import annotations

import json
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse, Response
from app.image_delivery import ImageFileResponse as FileResponse

from app import selfit_assets, selfit_mirror_handoff, selfit_onboarding, selfit_photo
from app.auth import get_admin_user
from app.selfit_persona import (
    ALGORITHM_VERSION,
    DIMENSIONS,
    REGIONAL_STYLES,
    candidate_persona_codes,
    classify_persona,
    persona_breakdown,
    persona_guide,
    rank_personas,
)
from app.storage import ROOT_DIR

router = APIRouter(prefix="/admin/api", tags=["selfit-admin-submissions"])

MIRROR_PHOTO_VARIANTS = ("original", "retouched")
VARIANT_LABELS = {"original": "原始照片", "retouched": "美颜照片"}

# 「删除」是软删除：只把 id 记进隐藏名单，列表不再返回；
# 磁盘上的会话记录与照片资产一律不动（尴尬照片误拍后可撤回，审计也需要原件）。
HIDDEN_STORE_PATH = ROOT_DIR / "outputs" / "admin_hidden.json"
_HIDDEN_LOCK = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_hidden() -> dict[str, dict[str, Any]]:
    if not HIDDEN_STORE_PATH.exists():
        return {"submissions": {}, "captures": {}}
    try:
        data = json.loads(HIDDEN_STORE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"submissions": {}, "captures": {}}
    if not isinstance(data, dict):
        return {"submissions": {}, "captures": {}}
    data.setdefault("submissions", {})
    data.setdefault("captures", {})
    return data


def _write_hidden(data: dict[str, Any]) -> None:
    HIDDEN_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = HIDDEN_STORE_PATH.with_name(f"{HIDDEN_STORE_PATH.name}.{secrets.token_urlsafe(8)}.tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(HIDDEN_STORE_PATH)


def _phone_by_user() -> dict[str, str]:
    from app.auth import _load_store as load_auth_store

    data = load_auth_store()
    mapping: dict[str, str] = {}
    for user in data.get("users", []):
        user_id = str(user.get("user_id") or "")
        if user_id:
            mapping[user_id] = str(user.get("phone_e164") or "")
    return mapping


def _parse_ts(value: Any) -> datetime | None:
    text = str(value or "")
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _download_filename(record: dict[str, Any], label: str, key: str) -> str:
    created = _parse_ts(record.get("created_at"))
    stamp = created.strftime("%Y%m%d_%H%M%S") if created else "snapshot"
    return f"selfit_{stamp}_{label}{Path(key).suffix or '.jpg'}"


def _serve_asset(
    store: selfit_assets.AssetStore, key: str, *, download: bool, filename: str
) -> Response:
    if download:
        path = store.local_path(key)
        if path is None:
            raise HTTPException(status_code=404, detail="没有找到这个文件")
        return FileResponse(
            path,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    public_url = store.public_url(key)
    path = store.local_path(key)
    if path is None:
        if public_url:
            return RedirectResponse(public_url, status_code=302)
        raise HTTPException(status_code=404, detail="没有找到这个文件")
    return FileResponse(path, headers={"Cache-Control": "private, max-age=300"})


def _latest_report(data: dict[str, Any], session_id: str) -> dict[str, Any] | None:
    reports = [item for item in data.get("reports", []) if item.get("session_id") == session_id]
    return max(reports, key=lambda item: str(item.get("created_at") or ""), default=None)


def _report_summary(report: dict[str, Any] | None) -> dict[str, Any] | None:
    if report is None:
        return None
    report_data = report.get("data") or {}
    return {
        "reportId": report.get("report_id"),
        "createdAt": report.get("created_at"),
        "typeId": report_data.get("typeId"),
        "title": report_data.get("title"),
        "traits": report_data.get("traits") or [],
    }


def _photo_entry(session_id: str, kind: str, photo: Any) -> dict[str, Any] | None:
    if not isinstance(photo, dict) or not photo.get("asset_id"):
        return None
    # 算法识别的属性（肤色/脸型/身型）只在管理后台展示，用户端契约不回传。
    attributes = photo.get("attributes") or {}
    return {
        "kind": kind,
        "label": selfit_photo.KIND_LABELS.get(kind, kind),
        "assetId": photo.get("asset_id"),
        "status": photo.get("status"),
        "source": photo.get("source") or "app",
        "attributes": {
            name: {"label": attr.get("label"), "confidence": attr.get("confidence")}
            for name, attr in attributes.items()
            if isinstance(attr, dict) and attr.get("label")
        },
        "previewUrl": f"/admin/api/submissions/{session_id}/photos/{kind}",
        "downloadUrl": f"/admin/api/submissions/{session_id}/photos/{kind}?download=1",
    }


def _mirror_photo_entry(base_url: str, variant: str, asset: Any) -> dict[str, Any] | None:
    if not isinstance(asset, dict) or not asset.get("object_key"):
        return None
    return {
        "variant": variant,
        "label": VARIANT_LABELS.get(variant, variant),
        "assetId": asset.get("asset_id"),
        "editState": asset.get("edit_state"),
        "previewUrl": f"{base_url}/{variant}",
        "downloadUrl": f"{base_url}/{variant}?download=1",
    }


def _submission_row(
    record: dict[str, Any], data: dict[str, Any], phones: dict[str, str]
) -> dict[str, Any]:
    session_id = str(record.get("session_id") or "")
    user_id = record.get("user_id")
    photos = []
    for kind in ("face", "body"):
        entry = _photo_entry(session_id, kind, (record.get("photos") or {}).get(kind))
        if entry is not None:
            photos.append(entry)
    mirror_assets = record.get("mirror_assets") or {}
    mirror_photos = None
    if isinstance(mirror_assets, dict) and mirror_assets:
        mirror_photos = {
            variant: _mirror_photo_entry(
                f"/admin/api/submissions/{session_id}/mirror-photos", variant, mirror_assets.get(variant)
            )
            for variant in MIRROR_PHOTO_VARIANTS
        }
    return {
        "sessionId": session_id,
        "status": record.get("status"),
        "source": "mirror" if record.get("source") == "mirror_handoff" else "app",
        "userId": user_id,
        "phone": phones.get(str(user_id)) if user_id else None,
        "createdAt": record.get("created_at"),
        "expiresAt": record.get("expires_at"),
        "completedSteps": selfit_onboarding._completed_steps(record),
        "manual": record.get("manual") or {},
        "preferences": record.get("preferences") or {},
        "vibe": record.get("vibe") or {},
        "report": _report_summary(_latest_report(data, session_id)),
        "photos": photos,
        "mirrorPhotos": mirror_photos,
    }


def _find_submission(data: dict[str, Any], session_id: str) -> dict[str, Any] | None:
    return next(
        (record for record in data.get("sessions", []) if record.get("session_id") == session_id),
        None,
    )


def _mirror_asset_for(record: dict[str, Any], variant: str) -> dict[str, Any] | None:
    """优先用会话记录里的 mirror_assets，旧记录回退到 handoff 存储解析。"""

    asset = (record.get("mirror_assets") or {}).get(variant)
    if isinstance(asset, dict) and asset.get("object_key"):
        return asset
    handoff_id = str(record.get("mirror_handoff_id") or "")
    if not handoff_id:
        return None
    handoff = next(
        (
            item
            for item in selfit_mirror_handoff._load_store().get("handoffs", [])
            if item.get("handoff_id") == handoff_id
        ),
        None,
    )
    asset = (handoff.get("assets") or {}).get(variant) if handoff else None
    if isinstance(asset, dict) and asset.get("object_key"):
        return asset
    return None


@router.get("/submissions")
async def list_submissions(admin: dict[str, Any] = Depends(get_admin_user)) -> JSONResponse:
    data = selfit_onboarding._load_store()
    phones = _phone_by_user()
    hidden = _load_hidden()
    hidden_ids = set(hidden["submissions"])
    rows = [
        _submission_row(record, data, phones)
        for record in data.get("sessions", [])
        if record.get("session_id") not in hidden_ids
    ]
    rows.sort(key=lambda row: str(row.get("createdAt") or ""), reverse=True)
    return JSONResponse(
        content={"submissions": rows},
        headers={"Cache-Control": "no-store"},
    )


@router.get("/submissions/{session_id}")
async def get_submission(
    session_id: str, admin: dict[str, Any] = Depends(get_admin_user)
) -> JSONResponse:
    data = selfit_onboarding._load_store()
    record = _find_submission(data, session_id)
    if record is None:
        return JSONResponse(status_code=404, content={"detail": "没有找到这份提交"})
    phones = _phone_by_user()
    row = _submission_row(record, data, phones)
    report = _latest_report(data, session_id)
    row["reportData"] = (report.get("data") or {}) if report else {}
    row["shareAssets"] = [
        {
            "assetId": item.get("asset_id"),
            "slideIndex": item.get("slide_index"),
            "channel": item.get("channel"),
            "createdAt": item.get("created_at"),
            "downloadUrl": (
                f"/admin/api/submissions/{session_id}/share-assets/{item.get('asset_id')}?download=1"
            ),
        }
        for item in data.get("share_assets", [])
        if item.get("session_id") == session_id
    ]
    return JSONResponse(content={"submission": row}, headers={"Cache-Control": "no-store"})


@router.get("/submissions/{session_id}/persona-breakdown")
async def get_submission_persona_breakdown(
    session_id: str, admin: dict[str, Any] = Depends(get_admin_user)
) -> JSONResponse:
    """人格匹配过程分解：7 维向量来源 + 16 型逐维距离贡献 + 排名。

    给管理后台「人格匹配」展示用（内测对齐口径：结果怎么来的、每一维
    贡献多少）。算法口径变化时本接口随 selfit_persona.persona_breakdown
    自动同步，前端展示层需要同步维护（见 docs/PERSONA_ALGORITHM.md）。
    """

    data = selfit_onboarding._load_store()
    record = _find_submission(data, session_id)
    if record is None:
        return JSONResponse(status_code=404, content={"detail": "没有找到这份提交"})
    try:
        breakdown = persona_breakdown(record)
    except Exception:
        return JSONResponse(status_code=422, content={"detail": "这份提交的问卷输入不完整，无法计算人格匹配"})
    return JSONResponse(content=breakdown, headers={"Cache-Control": "no-store"})


@router.get("/persona-guide")
async def get_persona_guide(admin: dict[str, Any] = Depends(get_admin_user)) -> JSONResponse:
    """十六型人格判定手册：7 维坐标系 + 16 型档案（中心点 / 核心 / 信号 / 易混淆）。

    给管理后台「十六型人格」报告页用：判断某个人属于什么型格的参考资料。
    数据由 selfit_persona.persona_guide 从 PERSONAS 唯一来源导出，算法
    口径变化时自动同步，无需前端维护第二份人格配置。
    """

    return JSONResponse(content=persona_guide(), headers={"Cache-Control": "no-store"})


@router.post("/persona-guide/classify")
async def post_persona_guide_classify(
    payload: dict[str, Any] = Body(...), admin: dict[str, Any] = Depends(get_admin_user)
) -> JSONResponse:
    """手动判定：输入某人 7 维得分（0-100，算法坐标系）+ 地域倾向，返回分型结果。

    与问卷分型共用 classify_persona / rank_personas 同一代码路径，
    缺失维度按中性值 50 计算，地域传「无倾向」或不传不计罚分。
    """

    vector: dict[str, Any] = {}
    for dimension in DIMENSIONS:
        value = payload.get(dimension)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            vector[dimension] = 50.0
        else:
            vector[dimension] = float(min(100.0, max(0.0, value)))
    regional = payload.get("regionalStyle")
    vector["regional_style"] = regional if regional in REGIONAL_STYLES else None
    gender = payload.get("gender")
    if gender not in (None, "female", "male"):
        return JSONResponse(status_code=422, content={"detail": "请选择有效的性别范围"})

    return JSONResponse(
        content={
            "algorithmVersion": ALGORITHM_VERSION,
            "gender": gender,
            "candidateCodes": list(candidate_persona_codes(gender)),
            "regionalStyle": vector["regional_style"],
            "classification": classify_persona(vector, gender),
            "ranking": rank_personas(vector, gender),
        },
        headers={"Cache-Control": "no-store"},
    )


@router.get("/submissions/{session_id}/photos/{kind}")
async def download_submission_photo(
    session_id: str,
    kind: str,
    download: bool = False,
    admin: dict[str, Any] = Depends(get_admin_user),
) -> Response:
    if kind not in selfit_photo.PHOTO_KINDS:
        raise HTTPException(status_code=404, detail="没有找到这个资源")
    data = selfit_onboarding._load_store()
    record = _find_submission(data, session_id)
    if record is None:
        raise HTTPException(status_code=404, detail="没有找到这份提交")
    photo = (record.get("photos") or {}).get(kind) or {}
    asset_id = photo.get("asset_id")
    suffix = selfit_onboarding.PHOTO_SUPPORTED_FORMATS.get(str(photo.get("format") or ""), "")
    if not asset_id or not suffix:
        raise HTTPException(status_code=404, detail="这张照片没有可下载的文件")
    key = f"{session_id}/{asset_id}{suffix}"
    store = selfit_onboarding._asset_store()
    return _serve_asset(
        store, key, download=download, filename=_download_filename(record, f"photo_{kind}", key)
    )


@router.get("/submissions/{session_id}/mirror-photos/{variant}")
async def download_submission_mirror_photo(
    session_id: str,
    variant: str,
    download: bool = False,
    admin: dict[str, Any] = Depends(get_admin_user),
) -> Response:
    if variant not in MIRROR_PHOTO_VARIANTS:
        raise HTTPException(status_code=404, detail="没有找到这个资源")
    data = selfit_onboarding._load_store()
    record = _find_submission(data, session_id)
    if record is None:
        raise HTTPException(status_code=404, detail="没有找到这份提交")
    asset = _mirror_asset_for(record, variant)
    if asset is None:
        raise HTTPException(status_code=404, detail="没有找到这张镜子照片")
    key = str(asset.get("object_key") or "")
    store = selfit_assets.asset_store_from_env(selfit_mirror_handoff.MIRROR_ASSET_DIR)
    return _serve_asset(
        store,
        key,
        download=download,
        filename=_download_filename(record, f"mirror_{variant}", key),
    )


@router.get("/submissions/{session_id}/share-assets/{asset_id}")
async def download_submission_share_asset(
    session_id: str,
    asset_id: str,
    download: bool = False,
    admin: dict[str, Any] = Depends(get_admin_user),
) -> Response:
    data = selfit_onboarding._load_store()
    asset = next(
        (
            item
            for item in data.get("share_assets", [])
            if item.get("session_id") == session_id and item.get("asset_id") == asset_id
        ),
        None,
    )
    if asset is None or not asset.get("filename"):
        raise HTTPException(status_code=404, detail="没有找到这份分享素材")
    record = _find_submission(data, session_id) or {}
    key = f"shared/{asset['filename']}"
    store = selfit_onboarding._asset_store()
    return _serve_asset(
        store, key, download=download, filename=_download_filename(record, "share", key)
    )


# ---------------------------------------------------------------------------
# 检测被拒照片：用户上传/镜拍回填失败的照片留存，供算法优化。
# App 上传的被拒照片在 onboarding assets；镜拍被拒引用 mirror assets 的原图。
# ---------------------------------------------------------------------------

REJECTED_ISSUE_LABELS = {
    "insufficient_light": "光线不充足",
    "overexposed": "过曝",
    "blurred": "不够清晰",
    "face_not_found": "检测不到人脸",
    "multiple_people": "照片里有多个人",
    "body_not_complete": "全身不完整",
    "unsupported_content": "内容无法识别",
    "bangs_forehead": "刘海遮额头",
    "side_pose": "角度偏侧",
    "body_unclear": "身形轮廓不稳定",
}

# 历史记录没有 algorithm_version 字段时展示的占位（引入版本号之前的旧算法）。
REJECTED_LEGACY_ALGORITHM_LABEL = "旧版"


def _rejected_algorithm_label(version: Any) -> str:
    value = str(version or "").strip()
    return value or REJECTED_LEGACY_ALGORITHM_LABEL


def _rejected_row(
    item: dict[str, Any], phones: dict[str, str]
) -> dict[str, Any]:
    record_id = str(item.get("record_id") or "")
    session_id = str(item.get("session_id") or "")
    kind = str(item.get("kind") or "")
    source = str(item.get("source") or "app")
    issues = list(item.get("issues") or [])
    algorithm_version = str(item.get("algorithm_version") or "").strip()
    row: dict[str, Any] = {
        "recordId": record_id,
        "sessionId": session_id,
        "kind": kind,
        "kindLabel": selfit_photo.KIND_LABELS.get(kind, kind),
        "source": source,
        "issues": issues,
        "issueLabels": [REJECTED_ISSUE_LABELS.get(code, code) for code in issues],
        "primaryIssue": item.get("primary_issue") or (
            issues[0] if issues else "unsupported_content"
        ),
        "algorithmVersion": algorithm_version,
        "algorithmLabel": _rejected_algorithm_label(algorithm_version),
        "width": item.get("width"),
        "height": item.get("height"),
        "createdAt": item.get("created_at"),
        "phone": phones.get(str(item.get("user_id") or "")) or None,
    }
    if source.startswith("mirror"):
        # 镜拍被拒引用的是 mirror handoff 原图（onboarding 会话里有 handoff_id）
        data = selfit_onboarding._load_store()
        submission = _find_submission(data, session_id) or {}
        handoff_id = str(submission.get("mirror_handoff_id") or "")
        if handoff_id:
            base = f"/admin/api/mirror-captures/{handoff_id}/photos/original"
            row["previewUrl"] = base
            row["downloadUrl"] = f"{base}?download=1"
            row["handoffId"] = handoff_id
    else:
        suffix = selfit_onboarding.PHOTO_SUPPORTED_FORMATS.get(str(item.get("format") or ""), "")
        asset_id = str(item.get("asset_id") or "")
        if asset_id and suffix:
            row["previewUrl"] = f"/admin/api/rejected-photos/{record_id}"
            row["downloadUrl"] = f"/admin/api/rejected-photos/{record_id}?download=1"
    return row


@router.get("/rejected-photos")
async def list_rejected_photos(
    kind: str | None = None,
    issue: str | None = None,
    algorithm: str | None = None,
    admin: dict[str, Any] = Depends(get_admin_user),
) -> JSONResponse:
    """被拒照片列表。

    可选过滤参数（前端两级筛选 + 版本筛选的服务端支持）：
    - kind: face | body
    - issue: 具体拦截原因枚举（primary_issue 或 issues 命中即算）
    - algorithm: 算法版本（"legacy" 表示未记录版本的旧数据）
    """

    data = selfit_onboarding._load_store()
    phones = _phone_by_user()
    hidden = _load_hidden()
    hidden_submissions = set(hidden["submissions"])
    kind_filter = kind if kind in {"face", "body"} else None
    issue_filter = issue.strip() if issue and issue.strip() else None
    algorithm_filter = algorithm.strip() if algorithm and algorithm.strip() else None
    rows = []
    for item in data.get("rejected_photos", []):
        if item.get("session_id") in hidden_submissions:
            continue
        if kind_filter and str(item.get("kind") or "") != kind_filter:
            continue
        if issue_filter:
            item_issues = list(item.get("issues") or [])
            if issue_filter not in item_issues and str(item.get("primary_issue") or "") != issue_filter:
                continue
        if algorithm_filter:
            version = str(item.get("algorithm_version") or "").strip()
            if (version or "legacy") != algorithm_filter:
                continue
        rows.append(_rejected_row(item, phones))
    rows.sort(key=lambda row: str(row.get("createdAt") or ""), reverse=True)
    # 按主问题聚合，快速看出哪类拦截最多（算法优化的第一入口）
    counter: dict[str, int] = {}
    for row in rows:
        counter[str(row["primaryIssue"])] = counter.get(str(row["primaryIssue"]), 0) + 1
    breakdown = [
        {"issue": issue, "label": REJECTED_ISSUE_LABELS.get(issue, issue), "count": count}
        for issue, count in sorted(counter.items(), key=lambda kv: kv[1], reverse=True)
    ]
    # 筛选项数据：kind 计数 / 各 kind 下出现过的原因 / 算法版本计数。
    # 从全量（仅排除隐藏）统计，保证筛选项不受当前过滤影响。
    all_rows = [
        _rejected_row(item, phones)
        for item in data.get("rejected_photos", [])
        if item.get("session_id") not in hidden_submissions
    ]
    kind_counts = {"face": 0, "body": 0}
    issues_by_kind: dict[str, dict[str, int]] = {"face": {}, "body": {}}
    algorithm_counts: dict[str, int] = {}
    for row in all_rows:
        row_kind = str(row["kind"]) if row["kind"] in {"face", "body"} else ""
        if row_kind:
            kind_counts[row_kind] += 1
            row_issue_codes = {str(row["primaryIssue"] or ""), *(row["issues"] or [])}
            for code in row_issue_codes:
                if code:
                    issues_by_kind[row_kind][code] = issues_by_kind[row_kind].get(code, 0) + 1
        version = str(row["algorithmVersion"]) or "legacy"
        algorithm_counts[version] = algorithm_counts.get(version, 0) + 1
    issue_filters = [
        {
            "kind": row_kind,
            "issue": code,
            "label": REJECTED_ISSUE_LABELS.get(code, code),
            "count": count,
        }
        for row_kind in ("face", "body")
        for code, count in sorted(
            issues_by_kind[row_kind].items(), key=lambda kv: kv[1], reverse=True
        )
    ]
    algorithm_filters = [
        {
            "algorithm": version,
            "label": _rejected_algorithm_label(version) if version != "legacy" else REJECTED_LEGACY_ALGORITHM_LABEL,
            "count": count,
        }
        for version, count in sorted(algorithm_counts.items(), key=lambda kv: kv[0], reverse=True)
    ]
    return JSONResponse(
        content={
            "rejected": rows,
            "breakdown": breakdown,
            "filters": {
                "kindCounts": kind_counts,
                "issueFilters": issue_filters,
                "algorithmFilters": algorithm_filters,
            },
        },
        headers={"Cache-Control": "no-store"},
    )


@router.get("/rejected-photos/{record_id}")
async def download_rejected_photo(
    record_id: str,
    download: bool = False,
    admin: dict[str, Any] = Depends(get_admin_user),
) -> Response:
    data = selfit_onboarding._load_store()
    item = next(
        (row for row in data.get("rejected_photos", []) if row.get("record_id") == record_id),
        None,
    )
    if item is None:
        raise HTTPException(status_code=404, detail="没有找到这条被拒记录")
    if str(item.get("source") or "").startswith("mirror"):
        raise HTTPException(status_code=404, detail="镜拍被拒照片请从镜子拍摄记录下载原图")
    suffix = selfit_onboarding.PHOTO_SUPPORTED_FORMATS.get(str(item.get("format") or ""), "")
    asset_id = str(item.get("asset_id") or "")
    if not asset_id or not suffix:
        raise HTTPException(status_code=404, detail="这张照片没有可下载的文件")
    key = f"{item.get('session_id')}/{asset_id}{suffix}"
    store = selfit_onboarding._asset_store()
    return _serve_asset(
        store, key, download=download, filename=_download_filename(item, "rejected", key)
    )


@router.get("/mirror-captures")
async def list_mirror_captures(admin: dict[str, Any] = Depends(get_admin_user)) -> JSONResponse:
    data = selfit_mirror_handoff._load_store()
    phones = _phone_by_user()
    hidden = _load_hidden()
    hidden_ids = set(hidden["captures"])
    rows = []
    for record in data.get("handoffs", []):
        handoff_id = str(record.get("handoff_id") or "")
        if handoff_id in hidden_ids:
            continue
        public = selfit_mirror_handoff._public_status(record)
        claimed_user = record.get("claimed_by_user_id")
        assets = record.get("assets") or {}
        rows.append(
            {
                "handoffId": handoff_id,
                "status": public.get("status"),
                "createdAt": record.get("created_at"),
                "claimedAt": record.get("claimed_at"),
                "phone": phones.get(str(claimed_user)) if claimed_user else None,
                "sessionId": record.get("claimed_session_id"),
                "original": _mirror_photo_entry(
                    f"/admin/api/mirror-captures/{handoff_id}/photos", "original", assets.get("original")
                ),
                "retouched": _mirror_photo_entry(
                    f"/admin/api/mirror-captures/{handoff_id}/photos", "retouched", assets.get("retouched")
                ),
            }
        )
    rows.sort(key=lambda row: str(row.get("createdAt") or ""), reverse=True)
    return JSONResponse(
        content={"captures": rows},
        headers={"Cache-Control": "no-store"},
    )


@router.get("/mirror-captures/{handoff_id}/photos/{variant}")
async def download_mirror_capture_photo(
    handoff_id: str,
    variant: str,
    download: bool = False,
    admin: dict[str, Any] = Depends(get_admin_user),
) -> Response:
    if variant not in MIRROR_PHOTO_VARIANTS:
        raise HTTPException(status_code=404, detail="没有找到这个资源")
    data = selfit_mirror_handoff._load_store()
    record = next(
        (
            item
            for item in data.get("handoffs", [])
            if item.get("handoff_id") == handoff_id
        ),
        None,
    )
    if record is None:
        raise HTTPException(status_code=404, detail="没有找到这次拍摄")
    asset = (record.get("assets") or {}).get(variant) or {}
    key = str(asset.get("object_key") or "")
    if not key:
        raise HTTPException(status_code=404, detail="没有找到这张镜子照片")
    store = selfit_assets.asset_store_from_env(selfit_mirror_handoff.MIRROR_ASSET_DIR)
    return _serve_asset(
        store,
        key,
        download=download,
        filename=_download_filename(record, f"mirror_{variant}", key),
    )


# ---------------------------------------------------------------------------
# 软删除（隐藏）：只从后台列表里移除，磁盘上的记录与照片资产不动。
# ---------------------------------------------------------------------------


def _hide_entry(kind: str, entry_id: str) -> JSONResponse:
    """软删除标记。已隐藏条目不出现在任何后台接口里；恢复只能离线洗数据
    （把条目从 admin_hidden.json 里删掉即可）。"""

    with _HIDDEN_LOCK:
        data = _load_hidden()
        data[kind][entry_id] = {"hidden_at": _now_iso()}
        _write_hidden(data)
    return JSONResponse(content={"status": "ok", "hidden": True})


@router.post("/submissions/{session_id}/hide")
async def hide_submission(
    session_id: str, admin: dict[str, Any] = Depends(get_admin_user)
) -> JSONResponse:
    data = selfit_onboarding._load_store()
    if _find_submission(data, session_id) is None:
        return JSONResponse(status_code=404, content={"detail": "没有找到这份提交"})
    return _hide_entry("submissions", session_id)


@router.post("/mirror-captures/{handoff_id}/hide")
async def hide_mirror_capture(
    handoff_id: str, admin: dict[str, Any] = Depends(get_admin_user)
) -> JSONResponse:
    data = selfit_mirror_handoff._load_store()
    exists = any(item.get("handoff_id") == handoff_id for item in data.get("handoffs", []))
    if not exists:
        return JSONResponse(status_code=404, content={"detail": "没有找到这次拍摄"})
    return _hide_entry("captures", handoff_id)
