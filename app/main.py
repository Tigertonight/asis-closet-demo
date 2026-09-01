from __future__ import annotations

import hashlib
import html as html_lib
import json
import mimetypes
import os
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import httpx
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.auth import (
    current_token_from_request,
    get_current_user,
    get_optional_user,
    resolve_token,
    revoke_token,
    start_phone_login,
    verify_phone_login,
    verify_phone_direct_login,
    verify_invite_login,
    client_ip_from_request,
)
from app.ops import deployment_guard_report, env_flag, request_guard_middleware
from app.analyzer import (
    analyze_contract,
    explain_fixture_case,
    analyze_fixture_case,
    analyze_image_bytes,
    cached_self_test_results as read_cached_self_test,
    fixture_cases,
    mvp_algorithm_contract,
    mvp_algorithm_markdown,
    mvp_handoff_markdown,
    mvp_open_source_markdown,
    mvp_pilot_guide_markdown,
    mvp_policy_rules,
    mvp_seasonal_evaluation,
    mvp_scenario_matrix,
    mvp_status_summary,
    render_demo_page,
    render_mvp_status_page,
    render_self_test_page,
    self_test_results as run_self_test,
)
from app.closet import (
    CLOSET_OUTPUT_DIR,
    closet_capabilities,
    create_import_upload_job,
    create_outfit,
    delete_closet_item,
    delete_outfit,
    delete_tryon_record,
    get_closet_item,
    get_import_job,
    get_outfit,
    get_user_preferences,
    import_link as import_closet_link,
    import_uploads as import_closet_uploads,
    list_closet_items,
    list_outfits,
    list_tryon_records,
    mock_tryon_from_outfit,
    recommend_outfits,
    record_selfit_tryon_result,
    render_closet_demo_page,
    render_selfit_demo_page,
    reprocess_closet_item,
    retry_import_job,
    update_closet_item,
    update_outfit,
    update_user_preferences,
)
from app.tryon import (
    TRYON_MODEL_FIXTURE_DIR,
    TRYON_OUTPUT_DIR,
    analyze_garment_upload,
    complete_codex_bridge_job_upload,
    create_outfit_tryon_job,
    extract_xhs_link,
    get_outfit_tryon_job,
    get_codex_bridge_job,
    list_codex_bridge_jobs,
    next_codex_bridge_job,
    render_tryon_demo_page,
    retry_outfit_tryon_job,
    run_try_on_from_outfit_upload,
    run_try_on_from_outfit_plan_upload,
    run_try_on_from_inspiration_upload,
    run_try_on_upload,
    tryon_capabilities,
)
from app.stylist import (
    delete_stylist_memory,
    get_stylist_memory,
    patch_stylist_memory,
    run_stylist_chat,
    run_selfit_tool,
    stream_stylist_chat,
    stylist_capabilities,
)
from app.stylist_sessions import (
    append_stylist_message,
    create_stylist_session,
    delete_stylist_session,
    ensure_stylist_session,
    get_stylist_session,
    list_stylist_sessions,
    recent_conversation,
    update_stylist_session,
)
from app import selfit_onboarding, selfit_share
from app.selfit_onboarding import router as selfit_onboarding_router
from app.selfit_mirror_handoff import router as selfit_mirror_handoff_router
from app.selfit_analytics import admin_router as selfit_admin_router, router as selfit_analytics_router
from app.selfit_admin_submissions import router as selfit_admin_submissions_router
from app.qa_onboarding import QA_PHOTO_DIR, router as qa_onboarding_router
from app.storage import hydrate_user_from_demo_data, storage_context, user_storage
from scripts.generate_qa_artifacts import generate_qa_artifacts
from scripts.check_runtime_readiness import readiness as runtime_readiness


load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True)

app = FastAPI(title="selfit", version="0.2.0")
app.middleware("http")(request_guard_middleware)
app.include_router(selfit_onboarding_router)
app.include_router(selfit_mirror_handoff_router)
app.include_router(selfit_analytics_router)
app.include_router(selfit_admin_router)
app.include_router(selfit_admin_submissions_router)
app.include_router(qa_onboarding_router)
SELFIT_INDEX_PATH = Path(__file__).resolve().parent / "static" / "selfit" / "index.html"
ADMIN_INDEX_PATH = Path(__file__).resolve().parent / "static" / "admin" / "index.html"
FAVICON_PATH = Path(__file__).resolve().parent / "static" / "brand" / "favicon.ico"
SELFIT_MIRROR_INDEX_PATH = Path(__file__).resolve().parent / "static" / "selfit" / "mirror.html"
REPORT_BUILDER_INDEX_PATH = Path(__file__).resolve().parent / "static" / "report-builder" / "index.html"
TRYON_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
XHS_IMAGE_CACHE_DIR = Path("outputs/xhs_images")
XHS_IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
for _mounted_dir in (Path("tests/fixtures/images"), Path("tests/results"), Path("outputs/demo_assets")):
    _mounted_dir.mkdir(parents=True, exist_ok=True)
app.mount("/fixture-images", StaticFiles(directory="tests/fixtures/images"), name="fixture-images")
app.mount("/qa-artifacts", StaticFiles(directory="tests/results"), name="qa-artifacts")
app.mount("/demo-assets", StaticFiles(directory="outputs/demo_assets"), name="demo-assets")


class CachedStaticFiles(StaticFiles):
    """静态资源长缓存：报告页大图曾因无缓存头反复全量下载（内测反馈 hero 图 10s）。

    图片/字体引用统一带 ?v= 版本参数（模板更新时升 v 强制刷新），
    因此可以放心 immutable 一年；HTML 不走这个挂载。
    """

    def file_response(self, *args: Any, **kwargs: Any) -> Response:
        response = super().file_response(*args, **kwargs)
        response.headers.setdefault("Cache-Control", "public, max-age=31536000, immutable")
        return response


app.mount("/static", CachedStaticFiles(directory="app/static"), name="static")
app.mount("/tryon-outputs", StaticFiles(directory="outputs/tryon"), name="tryon-outputs")
app.mount("/tryon-models", StaticFiles(directory=TRYON_MODEL_FIXTURE_DIR), name="tryon-models")
CLOSET_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/closet-outputs", StaticFiles(directory="outputs/closet"), name="closet-outputs")
QA_PHOTO_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/qa-photos", StaticFiles(directory=str(QA_PHOTO_DIR)), name="qa-photos")


def _is_allowed_xhs_image_url(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.hostname or ""
    return parsed.scheme in {"http", "https"} and (host == "xhscdn.com" or host.endswith(".xhscdn.com"))


def _xhs_image_cache_key(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]


def _xhs_image_cache_meta_path(cache_key: str) -> Path:
    return XHS_IMAGE_CACHE_DIR / f"{cache_key}.json"


def _xhs_image_cache_file_path(cache_key: str, media_type: str = "image/jpeg") -> Path:
    extension = mimetypes.guess_extension(media_type.split(";")[0].strip()) or ".jpg"
    if extension == ".jpe":
        extension = ".jpg"
    return XHS_IMAGE_CACHE_DIR / f"{cache_key}{extension}"


def _cached_xhs_image_response(source_url: str) -> FileResponse | None:
    cache_key = _xhs_image_cache_key(source_url)
    meta_path = _xhs_image_cache_meta_path(cache_key)
    if not meta_path.exists():
        return None
    try:
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    media_type = str(metadata.get("media_type") or "image/jpeg")
    image_path = XHS_IMAGE_CACHE_DIR / str(metadata.get("filename") or _xhs_image_cache_file_path(cache_key, media_type).name)
    if not image_path.exists() or not image_path.is_file():
        return None
    return FileResponse(
        image_path,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


def _write_xhs_image_cache(source_url: str, content: bytes, media_type: str) -> FileResponse:
    cache_key = _xhs_image_cache_key(source_url)
    image_path = _xhs_image_cache_file_path(cache_key, media_type)
    tmp_path = image_path.with_suffix(f"{image_path.suffix}.tmp")
    tmp_path.write_bytes(content)
    tmp_path.replace(image_path)
    metadata = {
        "source_url": source_url,
        "filename": image_path.name,
        "media_type": media_type,
    }
    meta_tmp = _xhs_image_cache_meta_path(cache_key).with_suffix(".json.tmp")
    meta_tmp.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    meta_tmp.replace(_xhs_image_cache_meta_path(cache_key))
    return FileResponse(
        image_path,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@app.get("/xhs-image")
async def proxy_xhs_image(url: str) -> Response:
    source_url = unquote(str(url or "").strip())
    if not _is_allowed_xhs_image_url(source_url):
        return PlainTextResponse("unsupported image url", status_code=400)
    cached = _cached_xhs_image_response(source_url)
    if cached is not None:
        return cached
    headers = {
        "User-Agent": "Mozilla/5.0 AppleWebKit/537.36 Chrome/126 Safari/537.36",
        "Referer": "https://www.xiaohongshu.com/",
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    }
    try:
        async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
            upstream = await client.get(source_url, headers=headers)
    except httpx.HTTPError:
        return PlainTextResponse("image unavailable", status_code=502)
    content_type = upstream.headers.get("content-type", "")
    if upstream.status_code >= 400 or not content_type.startswith("image/"):
        return PlainTextResponse("image unavailable", status_code=502)
    if len(upstream.content) > 12 * 1024 * 1024:
        return PlainTextResponse("image too large", status_code=502)
    media_type = content_type.split(";")[0]
    return _write_xhs_image_cache(source_url, upstream.content, media_type)


def _friendly_error(code: str, message: str, suggestion: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "failed",
            "detail": message,
            "error": {
                "code": code,
                "message": message,
                "suggestion": suggestion,
            },
            "decision": {
                "retake_required": True,
                "blocking_errors": [
                    {
                        "stage": "input_quality",
                        "code": code,
                        "message": message,
                        "suggestion": suggestion,
                    }
                ],
                "warnings": [],
                "user_message": suggestion,
            },
        },
    )


def _upload_error_for_detail(detail: str, status_code: int) -> tuple[str, str, str]:
    if "图片为空" in detail:
        return "upload.empty", "没有收到照片，请重新选择一张图片后再试。", "请选择一张清晰的单人自拍，JPG、PNG 或 WebP 都可以。"
    if "超过 12MB" in detail:
        return "upload.too_large", "图片太大了，暂时无法上传。", "请换一张 12MB 以内的原图或稍微压缩后再试。"
    if "无法识别图片格式" in detail:
        return "upload.unrecognized_image", "无法识别这张图片。", "请上传 JPG、PNG 或 WebP 格式的清晰照片，不要上传文档、动图或损坏图片。"
    if "仅支持" in detail:
        return "upload.unsupported_format", "暂时不支持这个图片格式。", "请换成 JPG、PNG 或 WebP 图片后再试。"
    return "request.failed", detail or "这次请求没有完成。", "请重新上传一张清晰的单人自拍再试。"


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    if request.url.path in {"/analyze", "/demo/analyze"}:
        return _friendly_error(
            "upload.image_missing",
            "没有收到照片。",
            "请点击上传按钮，选择一张 JPG、PNG 或 WebP 格式的清晰单人自拍后再试。",
            422,
        )
    return _friendly_error("request.invalid", "提交的信息不完整。", "请检查页面内容后再试。", 422)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else "这次请求没有完成。"
    if request.url.path.startswith("/auth"):
        code = f"auth.http_{int(exc.status_code)}"
        return _friendly_error(code, detail, detail, int(exc.status_code))
    code, message, suggestion = _upload_error_for_detail(detail, int(exc.status_code))
    return _friendly_error(code, message, suggestion, int(exc.status_code))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "release": _release_fingerprint()}


def _release_fingerprint() -> str:
    """部署版本指纹：git 提交 + 人格算法版本。

    事故防护：并行部署/镜像覆盖导致代码回滚时，这个指纹会立刻暴露
    「线上跑的不是你以为的版本」。git 信息不可用时降级为文件 mtime。
    """

    parts = []
    try:
        import subprocess

        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5, cwd=Path(__file__).resolve().parent.parent,
        ).stdout.strip()
        if commit:
            parts.append(f"git:{commit}")
    except Exception:
        pass
    try:
        from app.selfit_persona import ALGORITHM_VERSION

        parts.append(f"persona:{ALGORITHM_VERSION}")
    except Exception:
        pass
    if not parts:
        parts.append(f"main.py:{Path(__file__).stat().st_mtime:.0f}")
    return " ".join(parts)


@app.get("/health/dependencies")
def health_dependencies() -> dict[str, Any]:
    report = runtime_readiness()
    return {
        "status": report["status"],
        "ready": report["ready"],
        "endpoints": report["endpoints"],
        "deployment": deployment_guard_report(),
        "missing_actions": report["missing_actions"],
    }


@app.post("/auth/phone/start")
async def auth_phone_start(request: Request) -> dict[str, Any]:
    payload = await request.json()
    return start_phone_login(str(payload.get("phone") or ""))


@app.post("/auth/phone/verify")
async def auth_phone_verify(request: Request) -> dict[str, Any]:
    payload = await request.json()
    return verify_phone_login(str(payload.get("phone") or ""), str(payload.get("code") or ""))


@app.post("/auth/phone/direct")
async def auth_phone_direct(request: Request) -> dict[str, Any]:
    payload = await request.json()
    return verify_phone_direct_login(str(payload.get("phone") or ""), client_ip_from_request(request))


@app.post("/auth/invite/verify")
async def auth_invite_verify(request: Request) -> dict[str, Any]:
    payload = await request.json()
    return verify_invite_login(str(payload.get("invite_code") or ""), client_ip_from_request(request))


@app.get("/auth/me")
async def auth_me(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    return {"status": "ok", "user": current_user}


@app.post("/auth/logout")
async def auth_logout(request: Request, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    token = current_token_from_request(request)
    if token:
        return revoke_token(token)
    return {"status": "logged_out", "user_id": current_user["user_id"]}


@app.get("/user-assets/{kind}/{asset_path:path}")
async def user_asset(
    kind: str,
    asset_path: str,
    access_token: str | None = None,
    current_user: dict[str, Any] | None = Depends(get_optional_user),
) -> FileResponse:
    if kind not in {"closet", "tryon"}:
        raise StarletteHTTPException(status_code=404, detail="没有找到这个资源")
    user = current_user or (resolve_token(access_token) if access_token else None)
    if user is None:
        raise StarletteHTTPException(status_code=401, detail="请先登录")
    with user_storage(user["user_id"]):
        ctx = storage_context()
        base_dir = ctx.closet_output_dir if kind == "closet" else ctx.tryon_output_dir
        target = (base_dir / asset_path).resolve()
        try:
            target.relative_to(base_dir.resolve())
        except ValueError as exc:
            raise StarletteHTTPException(status_code=404, detail="没有找到这个资源") from exc
        if not target.exists() or not target.is_file():
            # 早期账号可能已经有 demo 清单，但只创建了上层目录，导致后续
            # hydration 跳过目录内部图片。请求时补齐缺失文件，让老账号刷新即恢复。
            hydrate_user_from_demo_data(str(user["user_id"]))
        if not target.exists() or not target.is_file():
            raise StarletteHTTPException(status_code=404, detail="没有找到这个资源")
        return FileResponse(target)


@app.post("/analyze")
async def analyze(image: UploadFile = File(...)) -> dict[str, Any]:
    raw = await image.read()
    return analyze_image_bytes(raw, image.filename)


@app.post("/demo/analyze")
async def demo_analyze(image: UploadFile = File(...)) -> dict[str, Any]:
    raw = await image.read()
    return analyze_image_bytes(raw, image.filename, allow_demo_fallback=True)


@app.get("/analyze/contract")
def analyze_api_contract() -> dict[str, Any]:
    return analyze_contract()


@app.get("/self-test/results")
def self_test_results() -> dict[str, Any]:
    return run_self_test()


@app.get("/self-test/cached-results")
def cached_self_test_results() -> dict[str, Any]:
    return read_cached_self_test()


@app.get("/mvp/status")
def mvp_status() -> dict[str, Any]:
    return mvp_status_summary()


@app.get("/mvp", response_class=HTMLResponse)
def mvp_page() -> HTMLResponse:
    return HTMLResponse(render_mvp_status_page())


@app.get("/mvp/rules")
def mvp_rules() -> dict[str, Any]:
    return mvp_policy_rules()


@app.get("/mvp/handoff", response_class=PlainTextResponse)
def mvp_handoff() -> PlainTextResponse:
    return PlainTextResponse(mvp_handoff_markdown(), media_type="text/markdown; charset=utf-8")


@app.head("/mvp/handoff")
def mvp_handoff_head() -> PlainTextResponse:
    return PlainTextResponse("", media_type="text/markdown; charset=utf-8")


@app.get("/mvp/pilot-guide", response_class=PlainTextResponse)
def mvp_pilot_guide() -> PlainTextResponse:
    return PlainTextResponse(mvp_pilot_guide_markdown(), media_type="text/markdown; charset=utf-8")


@app.head("/mvp/pilot-guide")
def mvp_pilot_guide_head() -> PlainTextResponse:
    return PlainTextResponse("", media_type="text/markdown; charset=utf-8")


@app.get("/mvp/algorithm", response_class=PlainTextResponse)
def mvp_algorithm() -> PlainTextResponse:
    return PlainTextResponse(mvp_algorithm_markdown(), media_type="text/markdown; charset=utf-8")


@app.get("/mvp/algorithm/contract")
def mvp_algorithm_contract_endpoint() -> dict[str, Any]:
    return mvp_algorithm_contract()


@app.get("/mvp/open-source-tech", response_class=PlainTextResponse)
def mvp_open_source_tech() -> PlainTextResponse:
    return PlainTextResponse(mvp_open_source_markdown(), media_type="text/markdown; charset=utf-8")


@app.head("/mvp/open-source-tech")
def mvp_open_source_tech_head() -> PlainTextResponse:
    return PlainTextResponse("", media_type="text/markdown; charset=utf-8")


@app.get("/mvp/seasonal-evaluation")
def mvp_seasonal_evaluation_endpoint() -> dict[str, Any]:
    return mvp_seasonal_evaluation()


@app.get("/mvp/scenario-matrix")
def mvp_scenario_matrix_endpoint() -> dict[str, Any]:
    return mvp_scenario_matrix()


@app.head("/mvp/algorithm")
def mvp_algorithm_head() -> PlainTextResponse:
    return PlainTextResponse("", media_type="text/markdown; charset=utf-8")


@app.post("/qa/regenerate-artifacts")
def regenerate_qa_artifacts() -> dict[str, Any]:
    return generate_qa_artifacts()


@app.get("/fixtures")
def fixtures() -> dict[str, Any]:
    cases = [
        {
            "id": case["id"],
            "name": case["name"],
            "group": case.get("group"),
            "image": case["image"],
            "expected_status": case["expected_status"],
        }
        for case in fixture_cases()
    ]
    return {"total": len(cases), "cases": cases}


@app.get("/fixtures/{case_id}/analyze")
def analyze_fixture(case_id: str) -> dict[str, Any]:
    return analyze_fixture_case(case_id)


@app.get("/fixtures/{case_id}/explain")
def explain_fixture(case_id: str) -> dict[str, Any]:
    return explain_fixture_case(case_id)


@app.get("/self-test", response_class=HTMLResponse)
@app.get("/qa", response_class=HTMLResponse)
def self_test_page() -> HTMLResponse:
    return HTMLResponse(render_self_test_page())


@app.get("/demo", response_class=HTMLResponse)
def demo_page() -> HTMLResponse:
    return HTMLResponse(
        render_demo_page(),
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


@app.post("/try-on/analyze-garment")
async def analyze_garment(image: UploadFile = File(...), current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    with user_storage(current_user["user_id"]):
        return await analyze_garment_upload(image)


@app.post("/try-on")
async def try_on(
    person_image: UploadFile = File(...),
    garment_image: UploadFile | None = File(None),
    closet_item_id: str | None = Form(None),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    with user_storage(current_user["user_id"]):
        return await run_try_on_upload(person_image, garment_image, closet_item_id)


@app.post("/closet/import/upload")
async def closet_import_upload(images: list[UploadFile] = File(...), current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    with user_storage(current_user["user_id"]):
        return await import_closet_uploads(images)


@app.post("/closet/import/jobs")
async def closet_import_job_create(images: list[UploadFile] = File(...), current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    with user_storage(current_user["user_id"]):
        return await create_import_upload_job(images, current_user["user_id"])


@app.get("/closet/import/jobs/{job_id}")
def closet_import_job(job_id: str, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    with user_storage(current_user["user_id"]):
        return get_import_job(job_id)


@app.post("/closet/import/jobs/{job_id}/retry")
def closet_import_job_retry(job_id: str, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    with user_storage(current_user["user_id"]):
        return retry_import_job(job_id, current_user["user_id"])


@app.post("/closet/import/link")
async def closet_import_link(url: str = Form(...), current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    with user_storage(current_user["user_id"]):
        return await import_closet_link(url)


@app.get("/closet/preferences")
def closet_preferences(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    with user_storage(current_user["user_id"]):
        return get_user_preferences()


@app.patch("/closet/preferences")
async def closet_preferences_update(request: Request, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    with user_storage(current_user["user_id"]):
        return update_user_preferences(await request.json())


@app.get("/closet/items")
def closet_items(category: str | None = None, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    with user_storage(current_user["user_id"]):
        return list_closet_items(category)


@app.get("/closet/items/{item_id}")
def closet_item(item_id: str, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    with user_storage(current_user["user_id"]):
        return get_closet_item(item_id)


@app.patch("/closet/items/{item_id}")
async def closet_item_update(item_id: str, request: Request, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    with user_storage(current_user["user_id"]):
        return update_closet_item(item_id, await request.json())


@app.post("/closet/items/{item_id}/reprocess")
def closet_item_reprocess(item_id: str, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    with user_storage(current_user["user_id"]):
        return reprocess_closet_item(item_id)


@app.delete("/closet/items/{item_id}")
def closet_item_delete(item_id: str, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    with user_storage(current_user["user_id"]):
        return delete_closet_item(item_id)


@app.get("/closet/capabilities")
def closet_capability_status(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    with user_storage(current_user["user_id"]):
        return closet_capabilities()


@app.get("/closet/outfits")
def closet_outfits(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    with user_storage(current_user["user_id"]):
        return list_outfits()


@app.post("/closet/recommendations/outfits")
async def closet_outfit_recommendations(request: Request, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    with user_storage(current_user["user_id"]):
        return recommend_outfits(await request.json())


@app.post("/closet/outfits")
async def closet_outfit_create(request: Request, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    with user_storage(current_user["user_id"]):
        return create_outfit(await request.json())


@app.get("/closet/outfits/{outfit_id}")
def closet_outfit(outfit_id: str, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    with user_storage(current_user["user_id"]):
        return get_outfit(outfit_id)


@app.patch("/closet/outfits/{outfit_id}")
async def closet_outfit_update(outfit_id: str, request: Request, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    with user_storage(current_user["user_id"]):
        return update_outfit(outfit_id, await request.json())


@app.delete("/closet/outfits/{outfit_id}")
def closet_outfit_delete(outfit_id: str, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    with user_storage(current_user["user_id"]):
        return delete_outfit(outfit_id)


@app.get("/closet/tryon-records")
def closet_tryon_records(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    with user_storage(current_user["user_id"]):
        return list_tryon_records()


@app.delete("/closet/tryon-records/{record_id}")
def closet_tryon_record_delete(record_id: str, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    with user_storage(current_user["user_id"]):
        return delete_tryon_record(record_id)


@app.get("/closet/demo", response_class=HTMLResponse)
def closet_demo_page() -> HTMLResponse:
    return HTMLResponse(render_closet_demo_page())


def _selfit_index_html(
    *,
    config_overrides: dict[str, Any] | None = None,
    social_meta: dict[str, str] | None = None,
) -> str:
    """服务端注入运行配置：正式环境不再依赖 ?apiMode=live 查询参数。"""

    html_text = SELFIT_INDEX_PATH.read_text(encoding="utf-8")
    config = {
        "apiMode": os.getenv("SELFIT_ONBOARDING_API_MODE", "live"),
        "apiBase": "/api/v1/selfit",
        "authMode": os.getenv("SELFIT_AUTH_FRONTEND_MODE") or os.getenv("SELFIT_ONBOARDING_API_MODE", "live"),
        "authBase": "/auth",
        "timeoutMs": 15000,
        # 邀请码登录仅内部测试用，默认对用户隐藏（SELFIT_SHOW_INVITE_LOGIN=1 打开）。
        "showInviteLogin": env_flag("SELFIT_SHOW_INVITE_LOGIN", False),
    }
    config.update(config_overrides or {})
    tag = "<script>window.__SELFIT_CONFIG__ = " + json.dumps(config, ensure_ascii=False) + ";</script>"
    marker = '<script src="/static/selfit/selfit-api.js'
    if marker in html_text:
        html_text = html_text.replace(marker, tag + marker, 1)
    if social_meta:
        title = html_lib.escape(social_meta.get("title") or "selfit 风格报告", quote=True)
        description = html_lib.escape(social_meta.get("description") or "打开查看 selfit 风格报告", quote=True)
        image_url = html_lib.escape(social_meta.get("image") or "", quote=True)
        page_url = html_lib.escape(social_meta.get("url") or "", quote=True)
        robots = html_lib.escape(social_meta.get("robots") or "noindex,nofollow,noarchive", quote=True)
        preload_image = html_lib.escape(social_meta.get("preload_image") or "", quote=True)
        html_text = html_text.replace(
            "<title>selfit · 先认识自己，再决定怎么穿</title>",
            f"<title>{title}</title>",
            1,
        )
        preload_tag = (
            f'<link rel="preload" as="image" href="{preload_image}" fetchpriority="high" />'
            if preload_image else ""
        )
        meta_tags = preload_tag + (
            f'<meta name="description" content="{description}" />'
            f'<meta name="robots" content="{robots}" />'
            '<meta property="og:type" content="website" />'
            '<meta property="og:site_name" content="selfit" />'
            f'<meta property="og:title" content="{title}" />'
            f'<meta property="og:description" content="{description}" />'
            f'<meta property="og:image" content="{image_url}" />'
            f'<meta property="og:image:secure_url" content="{image_url}" />'
            '<meta property="og:image:type" content="image/png" />'
            '<meta property="og:image:width" content="600" />'
            '<meta property="og:image:height" content="600" />'
            f'<meta property="og:url" content="{page_url}" />'
            '<meta name="twitter:card" content="summary" />'
            f'<meta name="twitter:image" content="{image_url}" />'
        )
        html_text = html_text.replace("<head>", "<head>" + meta_tags, 1)
    return html_text


@app.get("/", include_in_schema=False)
def root_page() -> RedirectResponse:
    return RedirectResponse(url="/selfit", status_code=308)


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> FileResponse:
    return FileResponse(FAVICON_PATH, media_type="image/x-icon")


@app.get("/selfit", response_class=HTMLResponse)
@app.get("/selfit/", response_class=HTMLResponse)
@app.get("/selfit/demo", response_class=HTMLResponse)
def selfit_onboarding_page(request: Request) -> HTMLResponse:
    origin = os.getenv("SELFIT_PUBLIC_BASE_URL", "").strip().rstrip("/") or str(request.base_url).rstrip("/")
    return HTMLResponse(
        _selfit_index_html(
            social_meta={
                "title": "selfit · 适我",
                "description": "1 分钟，找到真正衬你的颜色与穿搭风格",
                "image": f"{origin}/selfit/share-logo.png",
                "url": f"{origin}/selfit",
                "robots": "index,follow",
            },
        ),
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


@app.get("/selfit/share-logo.png", response_model=None, include_in_schema=False)
def selfit_share_logo() -> Response:
    return Response(
        content=selfit_share.render_brand_share_logo(),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.get("/selfit/qr.png", response_model=None, include_in_schema=False)
def selfit_entry_qr(request: Request) -> Response:
    origin = os.getenv("SELFIT_PUBLIC_BASE_URL", "").strip().rstrip("/") or str(request.base_url).rstrip("/")
    return Response(
        content=selfit_share.render_public_share_qr(f"{origin}/selfit"),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.get("/s/{token}/cover.png", response_model=None, include_in_schema=False)
def public_report_share_cover(token: str) -> Response:
    return selfit_onboarding.public_share_cover_response(token)


@app.get("/s/{token}/qr.png", response_model=None, include_in_schema=False)
def public_report_share_qr(token: str) -> Response:
    return selfit_onboarding.public_share_qr_response(token)


@app.get("/s/{token}", response_class=HTMLResponse, include_in_schema=False)
def public_report_share_page(token: str, request: Request) -> HTMLResponse:
    record, status = selfit_onboarding.get_public_share_record(token)
    origin = (os.getenv("SELFIT_PUBLIC_BASE_URL", "").strip().rstrip("/") or str(request.base_url).rstrip("/"))
    page_url = f"{origin}/s/{token}"
    active = record is not None and status == "active"
    title = f"Ta的 selfit 风格报告 · {record.get('title')}" if active else "selfit · 分享的风格报告"
    description = str(record.get("description") or "打开查看Ta分享的风格报告") if active else "这份报告已停止分享"
    hero_image = ((record or {}).get("report_snapshot") or {}).get("heroImage") or {}
    hero_source = str(hero_image.get("src") or "")
    is_bundled_hero = "/static/selfit/assets/personality/" in hero_source and "/hero.webp" in hero_source
    mobile_hero_source = hero_source.replace("/hero.webp", "/hero-mobile.webp", 1) if is_bundled_hero else hero_source
    if active and not mobile_hero_source:
        type_id = str(((record or {}).get("report_snapshot") or {}).get("typeId") or "").lower()
        if type_id.isascii() and type_id.isalnum():
            mobile_asset = Path(__file__).resolve().parent / "static" / "selfit" / "assets" / "personality" / type_id / "hero-mobile.webp"
            if mobile_asset.is_file():
                mobile_hero_source = f"/static/selfit/assets/personality/{type_id}/hero-mobile.webp?v=20260829-mobile-v1"
    html_text = _selfit_index_html(
        config_overrides={"publicShareToken": token},
        social_meta={
            "title": title,
            "description": description,
            "image": f"{page_url}/cover.png" if active else "",
            "url": page_url,
            "preload_image": mobile_hero_source if active else "",
        },
    )
    return HTMLResponse(
        html_text,
        status_code=200 if active else (410 if status in {"expired", "revoked"} else 404),
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Referrer-Policy": "no-referrer",
            "X-Robots-Tag": "noindex, nofollow, noarchive",
        },
    )


@app.get("/admin", response_class=FileResponse, include_in_schema=False)
@app.get("/admin/", response_class=FileResponse, include_in_schema=False)
def selfit_admin_page() -> FileResponse:
    """管理后台（内部工具）：页面可加载，全部数据走需要管理员 token 的 /admin/api/*。"""

    return FileResponse(
        ADMIN_INDEX_PATH,
        media_type="text/html",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


@app.get("/report-builder", response_class=FileResponse, include_in_schema=False)
@app.get("/report-builder/", response_class=FileResponse, include_in_schema=False)
def report_builder_page() -> FileResponse:
    return FileResponse(REPORT_BUILDER_INDEX_PATH, media_type="text/html")


@app.get("/ori/demo", include_in_schema=False)
def legacy_ori_demo_page() -> RedirectResponse:
    return RedirectResponse(url="/selfit/demo", status_code=308)


@app.get("/selfit/mirror", response_class=FileResponse)
@app.get("/selfit/mirror/", response_class=FileResponse)
def selfit_mirror_page() -> FileResponse:
    return FileResponse(
        SELFIT_MIRROR_INDEX_PATH,
        media_type="text/html",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


@app.get("/wearwow/demo", response_class=HTMLResponse)
def wearwow_demo_compat_page() -> HTMLResponse:
    return HTMLResponse(render_selfit_demo_page())


@app.get("/ori/runtime-readiness", include_in_schema=False)
@app.get("/selfit/runtime-readiness")
def selfit_runtime_readiness() -> dict[str, Any]:
    return runtime_readiness()


@app.post("/ori/try-on/from-outfit", include_in_schema=False)
@app.post("/selfit/try-on/from-outfit")
async def selfit_try_on_from_outfit(
    person_image: UploadFile = File(...),
    outfit_id: str = Form(...),
    photo_mode: str | None = Form(None),
    scene_label: str | None = Form(None),
    force_regenerate: bool = Form(False),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    with user_storage(current_user["user_id"]):
        result = await run_try_on_from_outfit_upload(person_image, outfit_id, photo_mode, scene_label, force_regenerate)
        result["selfit_mode"] = "product_tryon"
        record = record_selfit_tryon_result(outfit_id, result)
        if record:
            result["record"] = record
        return result


@app.post("/selfit/try-on/jobs")
async def selfit_try_on_job_create(
    person_image: UploadFile = File(...),
    outfit_id: str = Form(...),
    photo_mode: str | None = Form(None),
    scene_label: str | None = Form(None),
    force_regenerate: bool = Form(False),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    with user_storage(current_user["user_id"]):
        return create_outfit_tryon_job(
            await person_image.read(),
            person_image.filename,
            outfit_id,
            photo_mode,
            scene_label,
            current_user["user_id"],
            force_regenerate,
        )


@app.get("/selfit/try-on/jobs/{job_id}")
def selfit_try_on_job(job_id: str, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    with user_storage(current_user["user_id"]):
        return get_outfit_tryon_job(job_id)


@app.post("/selfit/try-on/jobs/{job_id}/retry")
def selfit_try_on_job_retry(job_id: str, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    with user_storage(current_user["user_id"]):
        return retry_outfit_tryon_job(job_id, current_user["user_id"])


@app.get("/stylist/capabilities")
def stylist_capability_status(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    with user_storage(current_user["user_id"]):
        return stylist_capabilities()


@app.get("/stylist/sessions")
def stylist_sessions(include_archived: bool = False, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    with user_storage(current_user["user_id"]):
        return list_stylist_sessions(include_archived)


@app.post("/stylist/sessions")
async def stylist_session_create(request: Request, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    with user_storage(current_user["user_id"]):
        return create_stylist_session(payload)


@app.get("/stylist/sessions/{session_id}")
def stylist_session_detail(session_id: str, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    with user_storage(current_user["user_id"]):
        return get_stylist_session(session_id)


@app.patch("/stylist/sessions/{session_id}")
async def stylist_session_update(session_id: str, request: Request, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    with user_storage(current_user["user_id"]):
        return update_stylist_session(session_id, await request.json())


@app.delete("/stylist/sessions/{session_id}")
def stylist_session_delete(session_id: str, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    with user_storage(current_user["user_id"]):
        return delete_stylist_session(session_id)


def _compact_text(value: Any, limit: int = 180) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit]


def _stylist_conversation_context(conversation: list[dict[str, Any]], current_query: str) -> dict[str, Any]:
    user_queries = [
        _compact_text(item.get("content"), 140)
        for item in conversation
        if isinstance(item, dict) and item.get("role") == "user" and str(item.get("content") or "").strip()
    ]
    if current_query and (not user_queries or user_queries[-1] != current_query):
        user_queries.append(_compact_text(current_query, 140))

    previous_assistant = next(
        (
            item
            for item in reversed(conversation)
            if isinstance(item, dict) and item.get("role") == "assistant" and str(item.get("content") or "").strip()
        ),
        None,
    )
    previous_sources: list[dict[str, Any]] = []
    if isinstance(previous_assistant, dict) and isinstance(previous_assistant.get("metadata"), dict):
        metadata = previous_assistant["metadata"]
        notes = metadata.get("xhs_notes") if isinstance(metadata.get("xhs_notes"), list) else []
        sources = metadata.get("evidence_sources") if isinstance(metadata.get("evidence_sources"), list) else []
        previous_sources = [
            {"title": _compact_text(note.get("title"), 48), "source": note.get("source_label") or "小红书"}
            for note in notes[:4]
            if isinstance(note, dict) and note.get("title")
        ]
        previous_sources.extend([source for source in sources[:2] if isinstance(source, dict)])

    return {
        "current_query": current_query,
        "recent_user_queries": user_queries[-5:],
        "previous_query": user_queries[-2] if len(user_queries) >= 2 else "",
        "previous_assistant_summary": _compact_text(previous_assistant.get("content") if isinstance(previous_assistant, dict) else "", 220),
        "previous_xhs_sources": previous_sources[:6],
        "conversation_turn_count": len(conversation),
        "must_answer_current_query": True,
    }


@app.post("/stylist/chat")
async def stylist_chat(request: Request, current_user: dict[str, Any] = Depends(get_current_user)) -> JSONResponse:
    try:
        payload = await request.json()
        payload["user_id"] = current_user["user_id"]
        with user_storage(current_user["user_id"]):
            session = ensure_stylist_session(payload.get("session_id") or "selfit-inspiration", {"metadata": {"source": "selfit_inspiration"}})
            payload["session_id"] = session["session_id"]
            context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
            stored_conversation = recent_conversation(session["session_id"], 8)
            incoming_conversation = context.get("conversation") if isinstance(context.get("conversation"), list) else []
            context["conversation"] = (stored_conversation or incoming_conversation)[-8:]
            user_message = str(payload.get("message") or "").strip()
            context["conversation_context"] = _stylist_conversation_context(context["conversation"], user_message)
            context["current_query"] = user_message
            context["recent_user_queries"] = context["conversation_context"]["recent_user_queries"]
            payload["context"] = context
            if user_message:
                append_stylist_message(session["session_id"], "user", user_message, {"source": "selfit_inspiration"})
            result, status_code = await run_stylist_chat(payload)
            assistant_message = str(result.get("assistant_message") or result.get("error", {}).get("message") or "").strip()
            if assistant_message:
                metadata = {
                    "status": result.get("status"),
                    "mode": result.get("mode"),
                    "tool_steps": result.get("tool_steps") if isinstance(result.get("tool_steps"), list) else [],
                    "xhs_notes": result.get("xhs_notes") if isinstance(result.get("xhs_notes"), list) else [],
                    "evidence_sources": result.get("evidence_sources") if isinstance(result.get("evidence_sources"), list) else [],
                    "rationale": result.get("rationale") if isinstance(result.get("rationale"), list) else [],
                }
                append_stylist_message(session["session_id"], "assistant", assistant_message, metadata)
                if status_code < 400 and result.get("status") != "failed":
                    update_stylist_session(session["session_id"], {"metadata": {"unread_completion": True}})
            result["session_id"] = session["session_id"]
            if isinstance(result.get("session_title"), str) and result["session_title"].strip():
                update_stylist_session(session["session_id"], {"title": result["session_title"].strip()})
        return JSONResponse(status_code=status_code, content=result)
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={
                "status": "failed",
                "mode": "error",
                "assistant_message": "暂时灵感耗尽，正在努力充能～",
                "error": {
                    "code": "stylist_internal_error",
                    "message": "暂时灵感耗尽，正在努力充能～",
                    "technical_message": "灵感服务暂时不可用。",
                },
                "recommended_items": [],
                "recommended_outfits": [],
                "rationale": [],
                "evidence_sources": [],
                "next_actions": [{"type": "open_closet", "label": "去衣橱选择"}],
                "debug": {"error_type": exc.__class__.__name__},
            },
        )


@app.get("/stylist/chat/stream")
async def stylist_chat_stream(message: str, session_id: str = "default", current_user: dict[str, Any] = Depends(get_current_user)) -> StreamingResponse:
    payload = {"message": message, "session_id": session_id, "user_id": current_user["user_id"]}
    with user_storage(current_user["user_id"]):
        return StreamingResponse(stream_stylist_chat(payload), media_type="text/event-stream")


@app.post("/stylist/tools/{tool_name}")
async def stylist_tool(tool_name: str, request: Request, current_user: dict[str, Any] = Depends(get_current_user)) -> JSONResponse:
    payload = await request.json()
    payload["user_id"] = current_user["user_id"]
    with user_storage(current_user["user_id"]):
        result, status_code = await run_selfit_tool(tool_name, payload)
    return JSONResponse(status_code=status_code, content=result)


@app.get("/stylist/memory")
async def stylist_memory(current_user: dict[str, Any] = Depends(get_current_user)) -> JSONResponse:
    with user_storage(current_user["user_id"]):
        result, status_code = await get_stylist_memory(current_user["user_id"])
    return JSONResponse(status_code=status_code, content=result)


@app.patch("/stylist/memory")
async def stylist_memory_update(request: Request, current_user: dict[str, Any] = Depends(get_current_user)) -> JSONResponse:
    with user_storage(current_user["user_id"]):
        result, status_code = await patch_stylist_memory(current_user["user_id"], await request.json())
    return JSONResponse(status_code=status_code, content=result)


@app.delete("/stylist/memory")
async def stylist_memory_delete(current_user: dict[str, Any] = Depends(get_current_user)) -> JSONResponse:
    with user_storage(current_user["user_id"]):
        result, status_code = await delete_stylist_memory(current_user["user_id"])
    return JSONResponse(status_code=status_code, content=result)


@app.post("/try-on/from-inspiration")
async def try_on_from_inspiration(
    person_image: UploadFile = File(...),
    inspiration_image: UploadFile = File(...),
    style_brief: str | None = Form(None),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    with user_storage(current_user["user_id"]):
        return await run_try_on_from_inspiration_upload(person_image, inspiration_image, style_brief)


@app.post("/try-on/from-outfit")
async def try_on_from_outfit(
    person_image: UploadFile = File(...),
    outfit_id: str = Form(...),
    photo_mode: str | None = Form(None),
    scene_label: str | None = Form(None),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    with user_storage(current_user["user_id"]):
        return await run_try_on_from_outfit_upload(person_image, outfit_id, photo_mode, scene_label)


@app.post("/try-on/from-outfit-plan")
async def try_on_from_outfit_plan(
    person_image: UploadFile = File(...),
    style_reference_image: UploadFile = File(...),
    item_images: list[UploadFile] = File(...),
    outfit_plan: str | None = Form(None),
    photo_mode: str | None = Form(None),
    scene_label: str | None = Form(None),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    with user_storage(current_user["user_id"]):
        return await run_try_on_from_outfit_plan_upload(
            person_image,
            style_reference_image,
            item_images,
            outfit_plan,
            photo_mode,
            scene_label,
        )


@app.post("/try-on/mock-from-outfit")
def try_on_mock_from_outfit(outfit_id: str = Form(...), current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    with user_storage(current_user["user_id"]):
        return mock_tryon_from_outfit(outfit_id)


@app.post("/try-on/extract-xhs")
async def extract_xhs(url: str = Form(...), current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    with user_storage(current_user["user_id"]):
        return await extract_xhs_link(url)


@app.post("/try-on/extract-inspiration")
async def extract_inspiration(url: str = Form(...), current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    with user_storage(current_user["user_id"]):
        return await extract_xhs_link(url)


@app.get("/try-on/capabilities")
def try_on_capabilities(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    with user_storage(current_user["user_id"]):
        return tryon_capabilities()


@app.get("/try-on/codex-bridge/jobs")
def codex_bridge_jobs(status: str | None = None, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    with user_storage(current_user["user_id"]):
        return list_codex_bridge_jobs(status)


@app.get("/try-on/codex-bridge/jobs/next")
def codex_bridge_next_job(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    with user_storage(current_user["user_id"]):
        return next_codex_bridge_job()


@app.get("/try-on/codex-bridge/jobs/{job_id}")
def codex_bridge_job(job_id: str, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    with user_storage(current_user["user_id"]):
        return get_codex_bridge_job(job_id)


@app.post("/try-on/codex-bridge/jobs/{job_id}/complete")
async def codex_bridge_complete_job(
    job_id: str,
    result_image: UploadFile | None = File(None),
    result_path: str | None = Form(None),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    with user_storage(current_user["user_id"]):
        return await complete_codex_bridge_job_upload(job_id, result_image, result_path)


@app.get("/try-on/demo", response_class=HTMLResponse)
def try_on_demo_page() -> HTMLResponse:
    return HTMLResponse(render_tryon_demo_page())
