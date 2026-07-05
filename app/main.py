from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import httpx
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, Response, StreamingResponse
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
)
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
    create_outfit,
    delete_closet_item,
    delete_outfit,
    delete_tryon_record,
    get_closet_item,
    get_outfit,
    get_user_preferences,
    import_link as import_closet_link,
    import_uploads as import_closet_uploads,
    list_closet_items,
    list_outfits,
    list_tryon_records,
    mock_tryon_from_outfit,
    record_asis_tryon_result,
    render_closet_demo_page,
    render_asis_demo_page,
    reprocess_closet_item,
    update_closet_item,
    update_outfit,
    update_user_preferences,
)
from app.tryon import (
    TRYON_MODEL_FIXTURE_DIR,
    TRYON_OUTPUT_DIR,
    analyze_garment_upload,
    complete_codex_bridge_job_upload,
    extract_xhs_link,
    get_codex_bridge_job,
    list_codex_bridge_jobs,
    next_codex_bridge_job,
    render_tryon_demo_page,
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
    run_asis_tool,
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
from app.storage import storage_context, user_storage
from scripts.generate_qa_artifacts import generate_qa_artifacts
from scripts.check_runtime_readiness import readiness as runtime_readiness


load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True)

app = FastAPI(title="Color Test MVP POC", version="0.2.0")
TRYON_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/fixture-images", StaticFiles(directory="tests/fixtures/images"), name="fixture-images")
app.mount("/qa-artifacts", StaticFiles(directory="tests/results"), name="qa-artifacts")
app.mount("/demo-assets", StaticFiles(directory="outputs/demo_assets"), name="demo-assets")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.mount("/tryon-outputs", StaticFiles(directory="outputs/tryon"), name="tryon-outputs")
app.mount("/tryon-models", StaticFiles(directory=TRYON_MODEL_FIXTURE_DIR), name="tryon-models")
CLOSET_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/closet-outputs", StaticFiles(directory="outputs/closet"), name="closet-outputs")


def _is_allowed_xhs_image_url(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.hostname or ""
    return parsed.scheme in {"http", "https"} and (host == "xhscdn.com" or host.endswith(".xhscdn.com"))


@app.get("/xhs-image")
async def proxy_xhs_image(url: str) -> Response:
    source_url = unquote(str(url or "").strip())
    if not _is_allowed_xhs_image_url(source_url):
        return PlainTextResponse("unsupported image url", status_code=400)
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
    return Response(
        content=upstream.content,
        media_type=content_type.split(";")[0],
        headers={"Cache-Control": "public, max-age=86400"},
    )


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
    code, message, suggestion = _upload_error_for_detail(detail, int(exc.status_code))
    return _friendly_error(code, message, suggestion, int(exc.status_code))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/auth/phone/start")
async def auth_phone_start(request: Request) -> dict[str, Any]:
    payload = await request.json()
    return start_phone_login(str(payload.get("phone") or ""))


@app.post("/auth/phone/verify")
async def auth_phone_verify(request: Request) -> dict[str, Any]:
    payload = await request.json()
    return verify_phone_login(str(payload.get("phone") or ""), str(payload.get("code") or ""))


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


@app.get("/asis/demo", response_class=HTMLResponse)
def asis_demo_page() -> HTMLResponse:
    return HTMLResponse(render_asis_demo_page())


@app.get("/wearwow/demo", response_class=HTMLResponse)
def wearwow_demo_compat_page() -> HTMLResponse:
    return HTMLResponse(render_asis_demo_page())


@app.get("/asis/runtime-readiness")
def asis_runtime_readiness() -> dict[str, Any]:
    return runtime_readiness()


@app.post("/asis/try-on/from-outfit")
async def asis_try_on_from_outfit(
    person_image: UploadFile = File(...),
    outfit_id: str = Form(...),
    photo_mode: str | None = Form(None),
    scene_label: str | None = Form(None),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    with user_storage(current_user["user_id"]):
        result = await run_try_on_from_outfit_upload(person_image, outfit_id, photo_mode, scene_label)
        result["asis_mode"] = "product_tryon"
        record = record_asis_tryon_result(outfit_id, result)
        if record:
            result["record"] = record
        return result


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


@app.post("/stylist/chat")
async def stylist_chat(request: Request, current_user: dict[str, Any] = Depends(get_current_user)) -> JSONResponse:
    try:
        payload = await request.json()
        payload["user_id"] = current_user["user_id"]
        with user_storage(current_user["user_id"]):
            session = ensure_stylist_session(payload.get("session_id") or "asis-inspiration", {"metadata": {"source": "asis_inspiration"}})
            payload["session_id"] = session["session_id"]
            context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
            stored_conversation = recent_conversation(session["session_id"], 8)
            incoming_conversation = context.get("conversation") if isinstance(context.get("conversation"), list) else []
            context["conversation"] = (stored_conversation or incoming_conversation)[-8:]
            payload["context"] = context
            user_message = str(payload.get("message") or "").strip()
            if user_message:
                append_stylist_message(session["session_id"], "user", user_message, {"source": "asis_inspiration"})
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
                "assistant_message": "灵感暂时不可用，请稍后再试。",
                "error": {"code": "stylist_internal_error", "message": "灵感服务暂时不可用。"},
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
        result, status_code = await run_asis_tool(tool_name, payload)
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
