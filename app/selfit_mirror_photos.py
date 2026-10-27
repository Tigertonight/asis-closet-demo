"""Smart-mirror keepsakes. Originals stay separate from the composited print.

No face analysis or generation is needed. A secret in the phone URL fragment
authorizes retrieval; it never appears in access-log paths or referrer headers.
"""
from __future__ import annotations

import hashlib
import hmac
import io
import json
import math
import os
import re
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import anyio
import qrcode
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from PIL import Image, UnidentifiedImageError

from app.photo_work import photo_admission, run_photo_work
from app.auth import get_admin_user
from app.selfit_assets import LocalAssetStore
from app.storage import ROOT_DIR
from app import selfit_xhs_share

router = APIRouter(tags=["selfit-mirror-photos"])
PHOTO_DIR = ROOT_DIR / "outputs" / "selfit_mirror_photos"
MAX_BYTES = 12 * 1024 * 1024
FILE_LINK_TTL = 600
PRIVATE_HEADERS = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "X-Content-Type-Options": "nosniff"}


def _store():
    # Personal keepsakes stay in a private, persistent server directory.
    return LocalAssetStore(PHOTO_DIR / "assets")


@contextmanager
def _database():
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(PHOTO_DIR / "photos.sqlite3", timeout=10)
    try:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("""CREATE TABLE IF NOT EXISTS photos (
            id TEXT PRIMARY KEY, secret_hash TEXT NOT NULL, digest TEXT NOT NULL,
            created REAL NOT NULL, expires REAL NOT NULL, settings TEXT NOT NULL,
            original_ext TEXT NOT NULL)""")
        with db:
            yield db
    finally:
        db.close()


def _identity(secret):
    if not re.fullmatch(r"[a-f0-9]{64}", secret or ""):
        raise HTTPException(400, "照片领取凭证无效，请重新拍摄。")
    digest = hashlib.sha256(secret.encode()).hexdigest()
    return "mp_" + digest[:32], digest


def _settings(raw):
    if len(raw) > 4096:
        raise HTTPException(400, "照片设置过长。")
    try:
        value = json.loads(raw)
    except (ValueError, TypeError):
        raise HTTPException(400, "照片设置无法读取。")
    if isinstance(value, dict) and value.get("template") == "woken-stamp":
        return _stamp_settings(value)
    if not isinstance(value, dict) or value.get("template") not in {"stamp", "postcard", "polaroid"}:
        raise HTTPException(400, "请选择照片模板。")
    stamp_year = value.get("stampYear")
    if value["template"] == "stamp" or "stampYear" in value:
        if not isinstance(stamp_year, str) or stamp_year not in {f"{year}-{year + 1}" for year in range(2016, 2026)}:
            raise HTTPException(400, "请选择周年邮票年份。")
    if value.get("effect") not in {"retro", "halftone", "print"} or value.get("palette") not in {"original", "wine", "blue", "purple", "redblack", "yellowblack"}:
        raise HTTPException(400, "照片效果设置不正确。")
    if not re.fullmatch(r"#[a-fA-F0-9]{6}", str(value.get("background", ""))):
        raise HTTPException(400, "照片底色设置不正确。")
    for key, low, high in (("intensity", 0, 100), ("zoom", 1, 2.5), ("x", -1, 1), ("y", -1, 1)):
        v = value.get(key)
        if isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) or not low <= v <= high:
            raise HTTPException(400, "照片调整设置不正确。")
    value = {k: value[k] for k in ("template", "effect", "palette", "background", "intensity", "zoom", "x", "y")}
    if stamp_year is not None:
        value["stampYear"] = stamp_year
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def _stamp_settings(value):
    if value.get("stampYear") not in [f"{y}-{y+1}" for y in range(2016, 2026)]:
        raise HTTPException(400, "请选择周年邮票年份。")
    if value.get("effect") not in ["faded", "fine-halftone", "xerox"] or value.get("palette") not in ["original", "red-white", "blue-white", "violet-white", "red-black", "yellow-black", "black-white", "custom"]:
        raise HTTPException(400, "照片效果设置不正确。")
    for key in ("background", "customInk"):
        if not re.fullmatch(r"#[a-fA-F0-9]{6}", str(value.get(key, ""))) and not (key == "background" and value.get(key) == "transparent"):
            raise HTTPException(400, "照片颜色设置不正确。")
    for key, low, high in (("intensity", 0, 100), ("zoom", 1, 2.4), ("x", -20, 20), ("y", -20, 20)):
        v = value.get(key)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not low <= v <= high:
            raise HTTPException(400, "照片调整设置不正确。")
    clean = {k: value[k] for k in ("template", "stampYear", "effect", "palette", "background", "customInk", "intensity", "zoom", "x", "y")}
    clean["version"] = "woken-v56"
    return json.dumps(clean, ensure_ascii=False, allow_nan=False)


def _check_image(raw, *, final=False, size=(1080, 1440)):
    try:
        with Image.open(io.BytesIO(raw)) as im:
            if im.width * im.height > 16_000_000 or getattr(im, "n_frames", 1) != 1:
                raise HTTPException(413, "请使用不超过 1600 万像素的静态照片。")
            fmt = im.format
            if fmt not in {"JPEG", "PNG", "WEBP"}:
                raise HTTPException(415, "请选择 JPG、PNG 或 WebP 照片。")
            if final and (fmt != "PNG" or im.size != size):
                raise HTTPException(422, "成片尺寸不正确，请返回重新完成照片。")
            im.verify()
        with Image.open(io.BytesIO(raw)) as im:
            im.load()
            if final:
                im.thumbnail((720, 960), Image.Resampling.LANCZOS)
                out = io.BytesIO()
                im.convert("RGBA" if "A" in im.getbands() else "RGB").save(out, "WEBP", quality=84)
                return out.getvalue()
        return {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}[fmt]
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise HTTPException(415, "照片无法读取，请重新拍摄或选择其他照片。")


def _save(original, final, settings, secret, scene=None):
    photo_id, secret_hash = _identity(secret)
    digest = hashlib.sha256(original + final + settings.encode() + (scene or b"")).hexdigest()
    # A retry after a lost response must return the same photo, not a duplicate.
    with _database() as db:
        previous = db.execute("SELECT * FROM photos WHERE id=?", (photo_id,)).fetchone()
        if previous:
            if previous["digest"] != digest:
                raise HTTPException(409, "照片已更新，请返回编辑后重新保存。")
            if previous["expires"] <= time.time():
                raise HTTPException(410, "领取凭证已过期，请返回编辑后重新保存。")
            return dict(previous)
    ext = _check_image(original)
    is_stamp = json.loads(settings).get("template") == "woken-stamp"
    size = (900, 1200) if is_stamp else (1080, 1440)
    # Current clients save only the stamp. Accept scene files from older clients
    # so an already open booth can still finish its pending upload.
    if scene and not is_stamp:
        raise HTTPException(422, "照片模板不支持展示图。")
    preview = _check_image(final, final=True, size=size)
    scene_preview = _check_image(scene, final=True, size=size) if scene else None
    now = time.time()
    ttl = max(300, min(604800, int(os.getenv("SELFIT_MIRROR_PHOTO_TTL_SECONDS", "86400"))))
    with _database() as db:
        db.execute("BEGIN IMMEDIATE")
        previous = db.execute("SELECT * FROM photos WHERE id=?", (photo_id,)).fetchone()
        if previous:
            if previous["digest"] != digest:
                raise HTTPException(409, "照片已更新，请重新保存。")
            if previous["expires"] <= time.time():
                raise HTTPException(410, "领取凭证已过期，请返回编辑后重新保存。")
            return dict(previous)
        store = _store()
        for name, data, content_type in (
            (f"original.{ext}", original, f"image/{'jpeg' if ext == 'jpg' else ext}"),
            ("print.png", final, "image/png"), ("preview.webp", preview, "image/webp"),
        ):
            store.save(f"mirror-photos/{photo_id}/{name}", data, content_type)
        if scene:
            store.save(f"mirror-photos/{photo_id}/scene.png", scene, "image/png")
            store.save(f"mirror-photos/{photo_id}/scene.webp", scene_preview, "image/webp")
        db.execute("INSERT INTO photos VALUES (?,?,?,?,?,?,?)", (photo_id, secret_hash, digest, now, now + ttl, settings, ext))
    return {"id": photo_id, "expires": now + ttl}


@router.post("/api/v1/selfit/mirror/photos", status_code=201)
async def save_photo(
    original: UploadFile = File(...), final: UploadFile = File(...),
    settings: str = Form(...), idempotency_key: str = Header(...),
    scene: UploadFile | None = File(default=None),
):
    _identity(idempotency_key)
    encoded_settings = _settings(settings)
    admission = photo_admission()
    try:
        admission.acquire_nowait()
    except anyio.WouldBlock:
        return JSONResponse({"error": {"code": "mirror.photo_busy", "message": "正在处理其他照片，请稍后重试。"}}, status_code=503, headers={**PRIVATE_HEADERS, "Retry-After": "3"})
    try:
        raw = await original.read(MAX_BYTES + 1)
        composed = await final.read(MAX_BYTES + 1)
        scene_bytes = await scene.read(MAX_BYTES + 1) if scene else None
        if not raw or not composed or scene_bytes == b"" or max(len(raw), len(composed), len(scene_bytes or b"")) > MAX_BYTES:
            raise HTTPException(413, "每张照片请控制在 12MB 以内。")
        record = await run_photo_work(_save, raw, composed, encoded_settings, idempotency_key, scene_bytes)
    finally:
        admission.release()
    return JSONResponse({"photoId": record["id"], "expiresAt": record["expires"] * 1000}, status_code=201, headers=PRIVATE_HEADERS)


def _authorized(photo_id, authorization):
    secret = authorization.removeprefix("Bearer ") if authorization else ""
    try:
        expected_id, _ = _identity(secret)
    except HTTPException:
        raise HTTPException(404, "照片不存在或领取链接不完整。")
    if photo_id != expected_id:
        raise HTTPException(404, "照片不存在或领取链接不完整。")
    with _database() as db:
        record = db.execute("SELECT * FROM photos WHERE id=?", (photo_id,)).fetchone()
    if not record:
        raise HTTPException(404, "照片不存在或领取链接不完整。")
    if record["expires"] <= time.time():
        raise HTTPException(410, "照片领取链接已过期，请在智能镜重新拍摄。")
    return record, secret


def _file_signature(record, name, expires, download):
    payload = f"mirror-file-v1:{record['id']}:{name}:{expires}:{int(download)}"
    return hmac.new(record["secret_hash"].encode(), payload.encode(), hashlib.sha256).hexdigest()


def _has_scene(record):
    return (json.loads(record["settings"]).get("template") == "woken-stamp"
            and bool(_store().local_path(f"mirror-photos/{record['id']}/scene.png")))


def _file_links(record, has_scene):
    # Native browser/WeChat downloads cannot supply the page's Bearer header.
    # Give each finished image a separate, short-lived capability, never the
    # primary 24-hour receipt secret or access to the uncomposited original.
    expires = int(min(record["expires"], time.time() + FILE_LINK_TTL))
    links = {"expiresAt": expires * 1000}
    for key, name in (("print", "print.png"), ("scene", "scene.png")):
        if key == "scene" and not has_scene:
            continue
        links[key] = {}
        for action, download in (("view", False), ("download", True)):
            signature = _file_signature(record, name, expires, download)
            links[key][action] = f"/api/v1/selfit/mirror/photos/{record['id']}/files/{name}?expires={expires}&download={int(download)}&signature={signature}"
    return links


@router.get("/api/v1/selfit/mirror/photos/{photo_id}/files/{name}")
def get_photo_file(photo_id: str, name: str, expires: int = 0, download: bool = False, signature: str = ""):
    if not re.fullmatch(r"mp_[a-f0-9]{32}", photo_id) or name not in {"print.png", "scene.png"} or not re.fullmatch(r"[a-f0-9]{64}", signature):
        raise HTTPException(404, "照片不存在或下载链接不完整。")
    record = admin_record(photo_id)
    if not record or not hmac.compare_digest(signature, _file_signature(record, name, expires, download)):
        raise HTTPException(404, "照片不存在或下载链接不完整。")
    if min(expires, record["expires"]) <= time.time():
        raise HTTPException(410, "下载链接已过期，请返回领取页重新点击保存。")
    is_stamp = json.loads(record["settings"]).get("template") == "woken-stamp"
    if name == "scene.png" and not _has_scene(record):
        raise HTTPException(404, "照片不存在。")
    path = _store().local_path(f"mirror-photos/{photo_id}/{name}")
    if not path:
        raise HTTPException(503, "照片暂时无法读取，请返回领取页重试。")
    filename = ("WOKEN-DAY-STAMP.png" if name == "print.png" else "WOKEN-DAY-MACHINE.png") if is_stamp else "selfit-photo.png"
    return FileResponse(path, media_type="image/png", filename=filename,
                        content_disposition_type="attachment" if download else "inline", headers=PRIVATE_HEADERS)


@router.get("/api/v1/selfit/mirror/photos/{photo_id}/{variant}")
def get_photo(photo_id: str, variant: str, request: Request, authorization: str = Header(default="")):
    record, secret = _authorized(photo_id, authorization)
    is_stamp = json.loads(record["settings"]).get("template") == "woken-stamp"
    if variant == "info":
        has_scene = _has_scene(record)
        return JSONResponse({"expiresAt": record["expires"] * 1000, "width": 900 if is_stamp else 1080, "height": 1200 if is_stamp else 1440, "hasScene": has_scene, "edition": "woken" if is_stamp else "selfit", "imageLinks": _file_links(record, has_scene), "xhsShareEnabled": is_stamp and selfit_xhs_share.configured()}, headers=PRIVATE_HEADERS)
    if variant == "xhs-share":
        if not is_stamp:
            raise HTTPException(404, "该照片暂不支持此分享方式，可以先保存照片。", headers=PRIVATE_HEADERS)
        # An explicit configured origin prevents Host-header injection into a
        # signed share. Only the composed print gets a short-lived public URL.
        base = os.getenv("SELFIT_PUBLIC_BASE_URL", "").strip().rstrip("/") or "https://selfit.com.cn"
        parsed = urlsplit(base)
        local_http = parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        if (parsed.scheme != "https" and not local_http) or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path:
            raise HTTPException(503, "分享地址暂未准备好，可以先保存照片。", headers=PRIVATE_HEADERS)
        if not _store().local_path(f"mirror-photos/{photo_id}/print.png"):
            raise HTTPException(503, "照片暂时无法读取，请重新加载后再分享。", headers=PRIVATE_HEADERS)
        links = _file_links(record, False)
        try:
            config = selfit_xhs_share.prepare_share(base + links["print"]["view"], base + "/selfit/photo/share", request.headers.get("user-agent", ""))
        except selfit_xhs_share.ShareUnavailable as exc:
            raise HTTPException(503, str(exc), headers=PRIVATE_HEADERS) from None
        return JSONResponse({**config, "expiresAt": min(config["expiresAt"], links["expiresAt"])}, headers=PRIVATE_HEADERS)
    if variant == "qr":
        base = os.getenv("SELFIT_PUBLIC_BASE_URL", "").strip().rstrip("/") or str(request.base_url).rstrip("/")
        # Generate the short-lived XHS share code on the phone, not at the kiosk.
        intent = "?intent=xhs" if is_stamp and request.query_params.get("intent") == "xhs" else ""
        url = f"{base}/selfit/photo{intent}#{photo_id}.{secret}"
        qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=6, border=4)
        qr.add_data(url)
        qr.make(fit=True)
        output = io.BytesIO()
        qr.make_image().save(output, format="PNG")
        return Response(output.getvalue(), media_type="image/png", headers=PRIVATE_HEADERS)
    if variant not in {"preview", "download"} and not (variant in {"scene-preview", "scene-download"} and _has_scene(record)):
        raise HTTPException(404, "照片不存在。")
    # Never redirect a private photo to an unprotected public object URL.
    name = {"preview": "preview.webp", "download": "print.png", "scene-preview": "scene.webp", "scene-download": "scene.png"}[variant]
    path = _store().local_path(f"mirror-photos/{photo_id}/{name}")
    if not path:
        raise HTTPException(503, "照片暂时无法读取，请稍后重试。")
    return FileResponse(path, media_type="image/webp" if name.endswith("webp") else "image/png", filename=f"selfit-{photo_id}-{name}" if variant.endswith("download") else None, headers=PRIVATE_HEADERS)


@router.get("/selfit/stamp", include_in_schema=False)
@router.get("/selfit/stamp/", include_in_schema=False)
def stamp_page():
    return FileResponse(Path(__file__).parent / "static/selfit/stamp/index.html", headers=PRIVATE_HEADERS)


@router.get("/selfit/photo", include_in_schema=False)
def phone_photo_page():
    return FileResponse(Path(__file__).parent / "static" / "selfit" / "mirror-photo.html", headers=PRIVATE_HEADERS)


@router.get("/selfit/photo/share", include_in_schema=False)
def phone_share_page():
    return FileResponse(Path(__file__).parent / "static" / "selfit" / "mirror-xhs-share.html", headers=PRIVATE_HEADERS)


def admin_record(photo_id):
    if not (PHOTO_DIR / "photos.sqlite3").exists():
        return None
    with _database() as db:
        row = db.execute("SELECT * FROM photos WHERE id=?", (photo_id,)).fetchone()
        return dict(row) if row else None


def admin_capture_rows():
    """Adapt keepsakes to the existing mirror-capture/manual-printing table."""
    if not (PHOTO_DIR / "photos.sqlite3").exists():
        return []
    with _database() as db:
        records = db.execute("SELECT id, created, expires, settings FROM photos ORDER BY created DESC").fetchall()
    rows = []
    for record in records:
        base = f"/admin/api/mirror-keepsakes/{record['id']}"
        def asset(variant, label):
            return {"label": label, "assetId": record['id'] + '-' + variant, "previewUrl": f"{base}/{variant}", "downloadUrl": f"{base}/{variant}?download=1"}
        rows.append({"handoffId": record['id'], "createdAt": datetime.fromtimestamp(record['created'], timezone.utc).isoformat(),
            "status": "keepsake", "phone": None, "sessionId": None,
            "original": asset("original", "拍摄原图"), "retouched": asset("print", "模板成片")})
        if _has_scene(record):
            rows[-1]["scene"] = asset("scene", "出片机展示图")
    return rows


@router.get("/admin/api/mirror-keepsakes/{photo_id}/{variant}")
def admin_photo(photo_id: str, variant: str, download: bool = False, admin: dict = Depends(get_admin_user)):
    record = admin_record(photo_id)
    if not record or variant not in {"original", "print", "scene"}:
        raise HTTPException(404, "没有找到这张镜子照片。")
    name = f"original.{record['original_ext']}" if variant == "original" else ("scene.png" if download else "scene.webp") if variant == "scene" else "print.png" if download else "preview.webp"
    path = _store().local_path(f"mirror-photos/{photo_id}/{name}")
    if not path:
        raise HTTPException(404, "没有找到这张镜子照片。")
    return FileResponse(path, filename=f"selfit-{photo_id}-{name}" if download else None, headers=PRIVATE_HEADERS)
