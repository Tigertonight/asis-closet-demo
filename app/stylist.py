from __future__ import annotations

import asyncio
import html as html_lib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, AsyncIterator
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse

import httpx

from app.closet import (
    create_outfit,
    get_closet_item,
    import_link,
    list_closet_items,
    list_outfits,
    mock_tryon_from_outfit,
)
from app.tryon import extract_xhs_link


ROOT_DIR = Path(__file__).resolve().parents[1]
STYLIST_RUNTIME_DIR = ROOT_DIR / "asis-agent-runtime"
STYLIST_AGENT_ID = "asis-stylist"
STYLIST_SKILLS = [
    "travel-outfit",
    "interview-outfit",
    "wedding-guest-outfit",
    "ootd-breakdown",
    "color-match",
    "capsule-wardrobe",
    "xhs-trend-research",
]
STYLIST_TOOLS = [
    "asis_closet_search",
    "asis_get_item",
    "asis_compose_outfit",
    "asis_save_outfit",
    "asis_tryon_from_outfit",
    "asis_xhs_search",
    "asis_xhs_fetch_note",
    "asis_style_kb_search",
]
DEFAULT_STYLIST_MODEL = "openai/gpt-5.5"
STYLIST_MODEL_KEY_ENV_BY_PROVIDER = {
    "openai": ["OPENAI_API_KEY", "STYLIST_OPENCLAW_API_KEY"],
    "anthropic": ["ANTHROPIC_API_KEY"],
    "google": ["GOOGLE_API_KEY", "GEMINI_API_KEY"],
    "google-gemini-cli": ["GOOGLE_API_KEY", "GEMINI_API_KEY"],
    "google-vertex": ["GOOGLE_API_KEY", "GEMINI_API_KEY"],
    "openrouter": ["OPENROUTER_API_KEY"],
    "deepseek": ["DEEPSEEK_API_KEY"],
    "dashscope": ["DASHSCOPE_API_KEY"],
    "moonshot": ["MOONSHOT_API_KEY"],
    "minimax": ["MINIMAX_API_KEY"],
    "minimax-cn": ["MINIMAX_API_KEY"],
    "minimax-portal": ["MINIMAX_OAUTH_TOKEN", "MINIMAX_API_KEY"],
    "minimax-portal-cn": ["MINIMAX_OAUTH_TOKEN", "MINIMAX_API_KEY"],
}


def stylist_capabilities() -> dict[str, Any]:
    chat_url = _openclaw_chat_url()
    cli_enabled = _env_flag("STYLIST_ENABLE_OPENCLAW_CLI")
    cli_path = shutil.which(os.environ.get("STYLIST_OPENCLAW_CLI", "openclaw")) if cli_enabled else None
    demo_mode = _demo_mode()
    model_key = _stylist_model_key_report()
    xhs_mcp = _xhs_mcp_config()
    runtime_configured = bool(chat_url or cli_path or demo_mode)
    if demo_mode:
        status = "ready"
    elif not runtime_configured:
        status = "runtime_not_configured"
    elif not model_key["matching_key_present"]:
        status = "ai_unavailable"
    else:
        status = "ready"
    return {
        "status": status,
        "agent_id": os.environ.get("STYLIST_OPENCLAW_AGENT_ID", STYLIST_AGENT_ID),
        "runtime": {
            "mode": "demo" if demo_mode else "http" if chat_url else "cli" if cli_path else "unconfigured",
            "openclaw_chat_url_configured": bool(chat_url),
            "openclaw_cli_enabled": cli_enabled,
            "openclaw_cli_available": bool(cli_path),
            "runtime_dir": str(STYLIST_RUNTIME_DIR),
            "decoupled": True,
            "imports_openclaw_internal_code": False,
        },
        "model": {
            "model": model_key["model"],
            "provider": model_key["provider"],
            "key_present": model_key["any_key_present"],
            "key_matches_provider": model_key["matching_key_present"],
            "required_for_real_chat": not demo_mode,
            "accepted_env_keys": model_key["accepted_env_keys"],
        },
        "error_policy": {
            "model_key_missing": "ai_unavailable",
            "model_key_invalid": "ai_unavailable",
            "quota_exceeded": "ai_unavailable",
            "provider_unreachable": "ai_unavailable",
            "runtime_unavailable": "agent_runtime_unavailable",
            "demo_requires_explicit_flag": True,
        },
        "tools": STYLIST_TOOLS,
        "skills": STYLIST_SKILLS,
        "xiaohongshu": {
            "search": {
                "owner": "openclaw_sidecar",
                "fastapi_behavior": "provider_interface_only",
                "mcp_configured": bool(xhs_mcp["url"]),
                "mcp_url": xhs_mcp["url"],
                "mcp_mode": xhs_mcp["mode"],
                "allowed_tools": xhs_mcp["allowed_tools"],
                "blocked_write_tools": [
                    "publish_content",
                    "publish_with_video",
                    "like_feed",
                    "favorite_feed",
                    "post_comment_to_feed",
                    "reply_comment_in_feed",
                ],
                "recommended_provider": "xpzouying/xiaohongshu-mcp",
            },
        },
        "memory": {
            "owner": "openclaw_fork",
            "fastapi_behavior": "proxy_or_error",
        },
    }


async def run_stylist_chat(payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
    message = str(payload.get("message") or "").strip()
    if not message:
        return _failed("invalid_request", "请先告诉 AI 穿搭师你的场景或问题。", 400)

    request = _normalize_chat_payload(payload, message)
    await _attach_xhs_inspiration(request)
    if _demo_mode():
        return _demo_chat_response(request), 200

    chat_url = _openclaw_chat_url()
    if chat_url:
        if not _stylist_model_key_report()["matching_key_present"]:
            degraded = _degraded_inspiration_result_if_needed(
                {"status": "failed", "error": {"code": "ai_unavailable", "message": "AI 穿搭师暂时不可用，请检查模型配置。"}},
                request,
            )
            if degraded is not None:
                return degraded, 200
            return _failed("ai_unavailable", "AI 穿搭师暂时不可用，请检查模型配置。", 503)
        return await _post_openclaw_http(chat_url, request)

    if _env_flag("STYLIST_ENABLE_OPENCLAW_CLI"):
        if not _stylist_model_key_report()["matching_key_present"]:
            degraded = _degraded_inspiration_result_if_needed(
                {"status": "failed", "error": {"code": "ai_unavailable", "message": "AI 穿搭师暂时不可用，请检查模型配置。"}},
                request,
            )
            if degraded is not None:
                return degraded, 200
            return _failed("ai_unavailable", "AI 穿搭师暂时不可用，请检查模型配置。", 503)
        return await _run_openclaw_cli(request)

    degraded = _degraded_inspiration_result_if_needed(
        {"status": "failed", "error": {"code": "ai_unavailable", "message": "AI 穿搭师暂时不可用，请检查模型配置。"}},
        request,
    )
    if degraded is not None:
        return degraded, 200
    return _failed(
        "agent_runtime_unavailable",
        "OpenClaw 穿搭师运行时还没有配置，无法启动 AI 对话。",
        503,
        suggestion="请先启动 asis-agent-runtime，或配置 STYLIST_OPENCLAW_CHAT_URL。不要在正式模式下使用假回复。",
    )


async def stream_stylist_chat(payload: dict[str, Any]) -> AsyncIterator[str]:
    result, status = await run_stylist_chat(payload)
    event = "message" if status < 400 else "error"
    yield f"event: {event}\n"
    yield f"data: {json.dumps(result, ensure_ascii=False)}\n\n"


async def run_asis_tool(tool_name: str, payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
    try:
        if tool_name == "asis_closet_search":
            return _tool_closet_search(payload), 200
        if tool_name == "asis_get_item":
            item_id = str(payload.get("item_id") or "").strip()
            return {"status": "ok", "item": get_closet_item(item_id)}, 200
        if tool_name == "asis_compose_outfit":
            return _tool_compose_outfit(payload), 200
        if tool_name == "asis_save_outfit":
            return {"status": "ok", "outfit": create_outfit(payload)}, 200
        if tool_name == "asis_tryon_from_outfit":
            outfit_id = str(payload.get("outfit_id") or "").strip()
            return {"status": "ok", "tryon": mock_tryon_from_outfit(outfit_id)}, 200
        if tool_name == "asis_xhs_fetch_note":
            url = str(payload.get("url") or "").strip()
            return {"status": "ok", "note": await extract_xhs_link(url)}, 200
        if tool_name == "asis_xhs_search":
            return _tool_xhs_search(payload), 200
        if tool_name == "asis_style_kb_search":
            return _tool_style_kb_search(payload), 200
        if tool_name == "asis_import_link":
            url = str(payload.get("url") or "").strip()
            return {"status": "ok", "import_result": await import_link(url)}, 200
    except Exception as exc:
        return _failed("tool_failed", str(exc) or "工具调用失败。", 500)
    return _failed("unknown_tool", f"未知 asis 工具：{tool_name}", 404)


async def get_stylist_memory(user_id: str) -> tuple[dict[str, Any], int]:
    return await _proxy_memory("GET", user_id, None)


async def patch_stylist_memory(user_id: str, payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
    return await _proxy_memory("PATCH", user_id, payload)


async def delete_stylist_memory(user_id: str) -> tuple[dict[str, Any], int]:
    return await _proxy_memory("DELETE", user_id, None)


def _normalize_chat_payload(payload: dict[str, Any], message: str) -> dict[str, Any]:
    session_id = str(payload.get("session_id") or "default").strip() or "default"
    user_id = str(payload.get("user_id") or "local-user").strip() or "local-user"
    return {
        "agent_id": os.environ.get("STYLIST_OPENCLAW_AGENT_ID", STYLIST_AGENT_ID),
        "session_id": session_id,
        "session_key": f"asis:{user_id}:{session_id}",
        "user_id": user_id,
        "message": message,
        "context": payload.get("context") if isinstance(payload.get("context"), dict) else {},
        "required_output": "asis_stylist_recommendation_v1",
        "tool_base_url": os.environ.get("STYLIST_ASIS_TOOL_BASE_URL", "http://127.0.0.1:8002"),
    }


async def _post_openclaw_http(chat_url: str, request: dict[str, Any]) -> tuple[dict[str, Any], int]:
    async with httpx.AsyncClient(timeout=_openclaw_timeout_for_request(request)) as client:
        try:
            response = await client.post(chat_url, json=request)
        except httpx.HTTPError as exc:
            degraded = _degraded_inspiration_result_if_needed(
                {"status": "failed", "error": {"code": "ai_unavailable", "message": "OpenClaw 穿搭师服务暂时不可用。"}},
                request,
            )
            if degraded is not None:
                return degraded, 200
            return _failed(
                "agent_runtime_unavailable",
                "OpenClaw 穿搭师服务暂时不可用。",
                503,
                evidence={"transport": "http", "error_type": exc.__class__.__name__, "error": str(exc)},
            )
    try:
        data = response.json()
    except ValueError:
        data = {"raw_text": response.text}
    if response.status_code >= 400:
        code = _runtime_error_code(response.status_code, data)
        degraded = _degraded_inspiration_result_if_needed(
            {"status": "failed", "error": {"code": "ai_unavailable", "message": _runtime_error_message(code)}},
            request,
        )
        if degraded is not None:
            return degraded, 200
        return _failed(code, _runtime_error_message(code), _status_for_error_code(code), evidence={"transport": "http", "response": data})
    result = _normalize_agent_result(data, "openclaw_http", request)
    degraded = _degraded_inspiration_result_if_needed(result, request)
    if degraded is not None:
        return degraded, 200
    return result, _status_for_error_code(result.get("error", {}).get("code", "")) if result.get("status") == "failed" else 200


def _openclaw_timeout_for_request(request: dict[str, Any]) -> float:
    context = request.get("context") if isinstance(request.get("context"), dict) else {}
    if context.get("source") == "inspiration_tab":
        return float(os.environ.get("STYLIST_INSPIRATION_OPENCLAW_TIMEOUT", "12"))
    return float(os.environ.get("STYLIST_OPENCLAW_TIMEOUT", "45"))


async def _run_openclaw_cli(request: dict[str, Any]) -> tuple[dict[str, Any], int]:
    command = os.environ.get("STYLIST_OPENCLAW_CLI", "openclaw")
    cli_path = shutil.which(command)
    if cli_path is None:
        return _failed("agent_runtime_unavailable", "本机没有找到 openclaw 命令。", 503)

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False) as handle:
        handle.write(request["message"])
        message_path = handle.name
    cmd = [
        cli_path,
        "agent",
        "--agent",
        request["agent_id"],
        "--session-key",
        request["session_key"],
        "--message-file",
        message_path,
        "--json",
    ]
    try:
        proc = await asyncio.to_thread(
            subprocess.run,
            cmd,
            cwd=STYLIST_RUNTIME_DIR if STYLIST_RUNTIME_DIR.exists() else ROOT_DIR,
            capture_output=True,
            text=True,
            timeout=int(os.environ.get("STYLIST_OPENCLAW_TIMEOUT", "45")),
            check=False,
        )
    finally:
        Path(message_path).unlink(missing_ok=True)

    if proc.returncode != 0:
        code = _runtime_error_code(None, {"stderr": proc.stderr, "stdout": proc.stdout})
        return _failed(code, _runtime_error_message(code), _status_for_error_code(code), evidence={"transport": "cli", "stderr": proc.stderr[-1200:]})
    try:
        data = json.loads(proc.stdout)
    except ValueError:
        data = {"assistant_message": proc.stdout.strip()}
    result = _normalize_agent_result(data, "openclaw_cli", request)
    return result, _status_for_error_code(result.get("error", {}).get("code", "")) if result.get("status") == "failed" else 200


def _normalize_agent_result(data: dict[str, Any], transport: str, request: dict[str, Any] | None = None) -> dict[str, Any]:
    embedded = _extract_embedded_json_result(data)
    if embedded is not None:
        data = embedded
    if "status" in data and "assistant_message" in data:
        result = dict(data)
    elif data.get("status") == "failed" and isinstance(data.get("error"), dict):
        result = {
            "status": "failed",
            "mode": "error",
            "assistant_message": str(data["error"].get("message") or "AI 穿搭师暂时不可用。"),
            "error": data["error"],
            "recommended_items": [],
            "recommended_outfits": [],
            "rationale": [],
            "evidence_sources": [],
            "next_actions": [],
            "raw": data,
        }
    else:
        assistant_message = (
            data.get("assistant_message")
            or data.get("message")
            or data.get("text")
            or data.get("reply")
            or _extract_openclaw_payload_text(data)
            or ""
        )
        result = {
            "status": "ok",
            "mode": "openclaw",
            "assistant_message": assistant_message,
            "recommended_items": data.get("recommended_items", []),
            "recommended_outfits": data.get("recommended_outfits", []),
            "rationale": data.get("rationale", []),
            "evidence_sources": data.get("evidence_sources", []),
            "next_actions": data.get("next_actions", []),
            "raw": data,
        }
    result.setdefault("mode", "openclaw")
    result.setdefault("status", "ok")
    result.setdefault("recommended_items", [])
    result.setdefault("recommended_outfits", [])
    result.setdefault("rationale", [])
    result.setdefault("evidence_sources", [])
    result.setdefault("next_actions", [])
    _merge_xhs_artifacts(result, request)
    result["quality_checks"] = _stylist_quality_checks(result, request)
    result["runtime"] = {"transport": transport, "agent_id": os.environ.get("STYLIST_OPENCLAW_AGENT_ID", STYLIST_AGENT_ID)}
    return result


async def _attach_xhs_inspiration(request: dict[str, Any]) -> None:
    context = request.get("context") if isinstance(request.get("context"), dict) else {}
    if context.get("source") != "inspiration_tab" or not _should_invoke_xhs_skill(request):
        return
    message = _effective_user_message(request)
    try:
        artifacts = await asyncio.wait_for(_fetch_xhs_inspiration(message), timeout=float(os.environ.get("ASIS_XHS_TOTAL_TIMEOUT", "45")))
    except asyncio.TimeoutError:
        query = _xhs_query_from_message(message)
        artifacts = {
            "query": query,
            "notes": [],
            "tool_steps": [
                _xhs_tool_step("xhs", "调用小红书灵感 skill", "failed", "小红书推荐暂时超时，先给你可执行建议"),
                _xhs_tool_step("read", "读取笔记卡片", "failed", "这次没有拿到可用笔记卡片"),
                _xhs_tool_step("filter", "筛选相关性", "failed", "没有可筛选的笔记"),
                _xhs_tool_step("style", "整理穿搭建议", "done", "已改用通用穿搭逻辑"),
            ],
            "evidence_sources": [],
            "unavailable_reason": "xhs_timeout",
            "unavailable_detail": "小红书检索超时，暂时没有拿到可用笔记卡片",
        }
    context["xhs_query"] = artifacts["query"]
    context["xhs_notes"] = artifacts["notes"]
    context["xhs_tool_steps"] = artifacts["tool_steps"]
    context["xhs_evidence_sources"] = artifacts["evidence_sources"]
    context["xhs_unavailable_reason"] = artifacts.get("unavailable_reason")
    context["xhs_unavailable_detail"] = artifacts.get("unavailable_detail")
    request["context"] = context


async def _fetch_xhs_inspiration(message: str) -> dict[str, Any]:
    query = _xhs_query_from_message(message)
    strategy = _xhs_search_strategy_summary(message)
    steps = [
        _xhs_tool_step("xhs", "调用小红书灵感 skill", "running", f"{strategy}；首轮关键词：{query}"),
        _xhs_tool_step("read", "读取笔记卡片", "pending", "提取标题、封面、作者和互动数"),
        _xhs_tool_step("filter", "筛选相关性", "pending", "多轮检索后只保留和场景高度相关的穿搭笔记"),
        _xhs_tool_step("style", "整理穿搭建议", "pending", "把笔记信号转成可执行搭配"),
    ]
    base_url = _xhs_api_base_url()
    if not base_url:
        steps[0] = _xhs_tool_step("xhs", "调用小红书灵感 skill", "failed", f"{strategy}；小红书 API 还没有配置")
        return {
            "query": query,
            "notes": [],
            "tool_steps": steps,
            "evidence_sources": [],
            "unavailable_reason": "xhs_api_not_configured",
            "unavailable_detail": "小红书 API 还没有配置",
        }

    timeout = httpx.Timeout(float(os.environ.get("ASIS_XHS_TIMEOUT", "30")))
    search_timeout = float(os.environ.get("ASIS_XHS_SEARCH_TIMEOUT", "24"))
    async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client:
        login_status: dict[str, Any] | None = None
        try:
            login_response = await client.get("/api/v1/login/status", timeout=float(os.environ.get("ASIS_XHS_LOGIN_TIMEOUT", "8")))
            login_status = login_response.json() if login_response.headers.get("content-type", "").startswith("application/json") else None
        except (httpx.HTTPError, ValueError):
            login_status = None
        login_data = login_status.get("data") if isinstance(login_status, dict) else None
        if isinstance(login_data, dict) and login_data.get("is_logged_in") is False:
            unavailable_detail = _xhs_unavailable_detail(login_status, "小红书侧边服务未登录，请先扫码登录后重试")
            steps[0] = _xhs_tool_step("xhs", "调用小红书灵感 skill", "failed", f"{strategy}；{unavailable_detail}")
            steps[1] = _xhs_tool_step("read", "读取笔记卡片", "failed", "账号态未登录，没有读取笔记卡片")
            steps[2] = _xhs_tool_step("filter", "筛选相关性", "failed", "没有可筛选的笔记")
            steps[3] = _xhs_tool_step("style", "整理穿搭建议", "done", "已改用通用穿搭逻辑")
            artifacts = {
                "query": query,
                "notes": [],
                "tool_steps": steps,
                "evidence_sources": [],
                "unavailable_reason": "xhs_login_required",
                "unavailable_detail": unavailable_detail,
            }
            return await _attach_public_xhs_fallback(message, artifacts)
        notes, search_meta, search_error = await _search_xhs_notes_until_enough(client, message, search_timeout)
        source_label = "小红书搜索"
        if search_error and not search_meta:
            unavailable_detail = _xhs_unavailable_detail(login_status, search_error or "推荐/搜索请求失败")
            steps[0] = _xhs_tool_step("xhs", "调用小红书灵感 skill", "failed", f"{strategy}；{unavailable_detail}")
            steps[1] = _xhs_tool_step("read", "读取笔记卡片", "failed", "搜索未完成，没有读取到可靠笔记")
            steps[2] = _xhs_tool_step("filter", "筛选相关性", "failed", "搜索未完成，无法筛选可靠笔记")
            steps[3] = _xhs_tool_step("style", "整理穿搭建议", "done", "已改用通用穿搭逻辑")
            artifacts = {
                "query": query,
                "notes": [],
                "tool_steps": steps,
                "evidence_sources": [],
                "unavailable_reason": "xhs_search_failed",
                "unavailable_detail": unavailable_detail,
            }
            return await _attach_public_xhs_fallback(message, artifacts)
    if not notes:
        unavailable_detail = _xhs_unavailable_detail(login_status, "多轮检索后，没有拿到足够相关的可用穿搭笔记")
        steps[0] = _xhs_tool_step("xhs", "调用小红书灵感 skill", "failed", _xhs_search_step_detail(message, search_meta) if search_meta else f"{strategy}；{unavailable_detail}")
        steps[1] = _xhs_tool_step("read", "读取笔记卡片", "failed", "没有可展示的笔记卡片")
        steps[2] = _xhs_tool_step("filter", "筛选相关性", "failed", "多轮搜索结果不足，不把低相关笔记作为依据")
        artifacts = {
            "query": query,
            "notes": [],
            "tool_steps": steps,
            "evidence_sources": [],
            "unavailable_reason": "xhs_notes_empty",
            "unavailable_detail": unavailable_detail,
        }
        return await _attach_public_xhs_fallback(message, artifacts)

    steps = [
        _xhs_tool_step("xhs", "调用小红书灵感 skill", "done", _xhs_search_step_detail(message, search_meta)),
        _xhs_tool_step("read", "读取笔记卡片", "done", "已提取封面、标题、作者和互动数据"),
        _xhs_tool_step("filter", "筛选相关性", "done", _xhs_filter_step_detail(notes, message)),
        _xhs_tool_step("style", "整理穿搭建议", "done", "已作为回答依据"),
    ]
    used_queries = [item["query"] for item in search_meta if item.get("accepted_count")]
    evidence = [{"type": "xiaohongshu", "label": f"{source_label}：{' / '.join(used_queries[:3]) or query}", "count": len(notes)}]
    return {"query": query, "queries": search_meta, "notes": notes, "tool_steps": steps, "evidence_sources": evidence, "unavailable_reason": None, "unavailable_detail": None}


async def _search_xhs_notes_until_enough(client: httpx.AsyncClient, message: str, search_timeout: float) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str | None]:
    max_rounds = max(1, int(os.environ.get("ASIS_XHS_SEARCH_ROUNDS", "4")))
    max_candidates = max(12, int(os.environ.get("ASIS_XHS_MAX_CANDIDATES", "36")))
    queries = _xhs_query_candidates(message)[:max_rounds]
    all_notes: dict[str, dict[str, Any]] = {}
    search_meta: list[dict[str, Any]] = []
    last_error: str | None = None
    for query in queries:
        try:
            response = await asyncio.wait_for(client.get("/api/v1/feeds/search", params={"keyword": query}), timeout=search_timeout)
            payload = response.json()
            feeds = _extract_xhs_feeds(payload)
        except (asyncio.TimeoutError, httpx.HTTPError, ValueError) as exc:
            last_error = str(exc) or exc.__class__.__name__
            search_meta.append({"query": query, "raw_count": 0, "accepted_count": 0, "error": last_error})
            continue
        notes = _normalize_xhs_feeds(feeds, query, "小红书搜索", relevance_text=message, limit=max_candidates)
        for note in notes:
            note_id = str(note.get("note_id") or "")
            current = all_notes.get(note_id)
            if not current or float(note.get("relevance_score") or 0) > float(current.get("relevance_score") or 0):
                all_notes[note_id] = note
        ranked = _rank_xhs_notes_for_answer(list(all_notes.values()), message)
        search_meta.append({"query": query, "raw_count": len(feeds), "accepted_count": len(notes)})
        if _xhs_has_enough_answer_evidence(ranked, message):
            return ranked[:6], search_meta, None
    ranked = _rank_xhs_notes_for_answer(list(all_notes.values()), message)
    if _xhs_has_enough_answer_evidence(ranked, message):
        return ranked[:6], search_meta, None
    return [], search_meta, last_error


async def _attach_public_xhs_fallback(message: str, artifacts: dict[str, Any]) -> dict[str, Any]:
    if _env_flag("ASIS_XHS_DISABLE_PUBLIC_FALLBACK"):
        return artifacts
    query = str(artifacts.get("query") or _xhs_query_from_message(message))
    try:
        notes = await _fetch_public_xhs_references(message)
    except (asyncio.TimeoutError, httpx.HTTPError, ValueError):
        notes = []
    if not _xhs_has_enough_answer_evidence(notes, message):
        artifacts["tool_steps"] = [
            *[step for step in artifacts.get("tool_steps", []) if isinstance(step, dict)],
            _xhs_tool_step("public", "公开网页搜索补位", "failed", "没有找到足够相关的公开小红书链接"),
        ][:6]
        return artifacts
    artifacts["notes"] = notes
    artifacts["evidence_sources"] = [{"type": "public_web_search", "label": f"公开网页搜索：{query}", "count": len(notes)}]
    artifacts["tool_steps"] = [
        *[step for step in artifacts.get("tool_steps", []) if isinstance(step, dict)],
        _xhs_tool_step("public", "公开网页搜索补位", "done", f"找到 {len(notes)} 条公开小红书链接，仅作弱参考"),
    ][:6]
    artifacts["public_fallback_used"] = True
    return artifacts


async def _fetch_public_xhs_references(message: str) -> list[dict[str, Any]]:
    search_query = f"site:xiaohongshu.com/explore {_xhs_broad_query_from_message(message)}"
    search_url = os.environ.get("ASIS_XHS_PUBLIC_SEARCH_URL", "https://www.bing.com/search")
    timeout = float(os.environ.get("ASIS_XHS_PUBLIC_SEARCH_TIMEOUT", "4"))
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.6",
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout), headers=headers, follow_redirects=True) as client:
        response = await client.get(search_url, params={"q": search_query})
        response.raise_for_status()
    candidates = _extract_public_xhs_candidates(response.text)
    notes: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        note = _public_xhs_candidate_to_note(candidate, search_query)
        if not note or note["note_id"] in seen or not _is_xhs_fashion_note(note):
            continue
        score, reasons = _xhs_note_relevance(note, message)
        if score < _xhs_relevance_threshold(message):
            continue
        note["relevance_score"] = score
        note["relevance_reasons"] = reasons
        seen.add(note["note_id"])
        notes.append(note)
    notes.sort(key=lambda item: float(item.get("relevance_score") or 0), reverse=True)
    return notes[:4]


def _extract_public_xhs_candidates(html_text: str) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    seen: set[str] = set()
    link_pattern = re.compile(r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.IGNORECASE | re.DOTALL)
    for href, raw_title in link_pattern.findall(html_text or ""):
        url = _clean_public_xhs_url(href)
        if not url or url in seen:
            continue
        title = _clean_public_search_title(raw_title)
        candidates.append({"url": url, "title": title})
        seen.add(url)
    for raw_url in re.findall(r"https?://(?:www\.)?xiaohongshu\.com/explore/[A-Za-z0-9]+(?:[^\s\"'<>]*)?", html_text or ""):
        url = _clean_public_xhs_url(raw_url)
        if url and url not in seen:
            candidates.append({"url": url, "title": ""})
            seen.add(url)
    return candidates[:12]


def _clean_public_xhs_url(raw_url: str) -> str:
    value = html_lib.unescape(str(raw_url or "")).strip()
    if not value:
        return ""
    parsed = urlparse(value)
    if "bing.com" in parsed.netloc and parsed.path.startswith("/ck/a"):
        params = parse_qs(parsed.query)
        value = unquote((params.get("u") or [""])[0])
    elif "duckduckgo.com" in parsed.netloc:
        params = parse_qs(parsed.query)
        value = unquote((params.get("uddg") or [""])[0])
    parsed = urlparse(value)
    if "xiaohongshu.com" not in parsed.netloc or "/explore/" not in parsed.path:
        return ""
    note_id = parsed.path.split("/explore/", 1)[1].split("/", 1)[0]
    if not note_id:
        return ""
    return f"https://www.xiaohongshu.com/explore/{quote(note_id)}"


def _clean_public_search_title(raw_title: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw_title or "")
    text = html_lib.unescape(text)
    text = " ".join(text.split())
    return text[:80]


def _public_xhs_candidate_to_note(candidate: dict[str, str], query: str) -> dict[str, Any] | None:
    url = candidate.get("url", "")
    note_id = urlparse(url).path.split("/explore/", 1)[-1].split("/", 1)[0]
    title = str(candidate.get("title") or "公开小红书笔记").strip()
    if not note_id:
        return None
    return {
        "note_id": note_id,
        "title": title[:80],
        "desc": "",
        "author_name": "公开网页搜索",
        "author_avatar": "",
        "cover_url": "",
        "cover_source_url": "",
        "liked_count": "",
        "collected_count": "",
        "comment_count": "",
        "source_label": "公开网页搜索",
        "query": query,
        "url": url,
        "is_public_fallback": True,
    }


def _xhs_tool_step(step_id: str, title: str, status: str, detail: str) -> dict[str, str]:
    return {"id": step_id, "title": title, "status": status, "detail": detail}


def _effective_user_message(request: dict[str, Any]) -> str:
    current = str(request.get("message") or "").strip()
    context = request.get("context") if isinstance(request.get("context"), dict) else {}
    conversation = context.get("conversation") if isinstance(context.get("conversation"), list) else []
    user_turns: list[str] = []
    for item in conversation[-6:]:
        if not isinstance(item, dict) or item.get("role") != "user":
            continue
        content = str(item.get("content") or "").strip()
        if content and content not in user_turns:
            user_turns.append(content)
    if current and current not in user_turns:
        user_turns.append(current)
    return "；".join(user_turns[-3:]) or current


def _should_invoke_xhs_skill(request: dict[str, Any]) -> bool:
    context = request.get("context") if isinstance(request.get("context"), dict) else {}
    requested = context.get("requested_skills") if isinstance(context.get("requested_skills"), list) else []
    if "xhs-trend-research" in {str(skill) for skill in requested}:
        return True
    message = _effective_user_message(request)
    if _message_explicitly_disables_xhs(message):
        return False
    if _message_matches_xhs_intent(message):
        return True
    if context.get("xiaohongshu_preferred") is False:
        return False
    return False


def _message_explicitly_disables_xhs(message: str) -> bool:
    normalized = str(message or "").lower()
    return any(token in normalized for token in ["不用小红书", "不要小红书", "别用小红书", "不看小红书", "只看衣橱", "只用衣橱", "只用我的衣橱", "不要外部参考", "不用外部参考"])


def _message_matches_xhs_intent(message: str) -> bool:
    normalized = message.lower()
    xhs_terms = ["小红书", "红书", "xhs", "rednote", "笔记", "同款", "平替", "趋势", "流行", "博主", "种草", "参考", "灵感"]
    fashion_terms = [
        "穿搭",
        "搭配",
        "怎么穿",
        "穿什么",
        "怎么配",
        "ootd",
        "outfit",
        "look",
        "style",
        "衣服",
        "上衣",
        "下装",
        "裤",
        "裙",
        "鞋",
        "包",
        "外套",
        "大衣",
        "衬衫",
        "针织",
        "卫衣",
        "西装",
        "连衣裙",
        "半身裙",
        "通勤",
        "上班",
        "面试",
        "约会",
        "聚餐",
        "看展",
        "旅行",
        "上课",
        "校园",
        "拍照",
        "对镜",
        "挡脸",
        "场景拍",
        "显瘦",
        "显高",
        "显白",
        "配色",
        "色彩",
        "风格",
        "氛围感",
        "松弛",
        "韩系",
        "法式",
        "日系",
        "美式",
    ]
    return any(token in normalized for token in [*xhs_terms, *fashion_terms])


def _xhs_query_from_message(message: str) -> str:
    cleaned = " ".join(str(message or "").replace("\n", " ").split())
    if not cleaned:
        return "通勤 穿搭"
    seeds: list[str] = []
    if "周五" in cleaned:
        seeds.append("周五")
    if "看展" in cleaned or "展" in cleaned:
        seeds.append("看展")
    if "聚餐" in cleaned or "饭局" in cleaned:
        seeds.append("聚餐")
    if any(token in cleaned for token in ["上班", "工作", "通勤"]):
        seeds.append("通勤")
    if any(token in cleaned for token in ["客户", "会面", "会议", "商务", "正式", "稳"]):
        seeds.append("客户会面")
    if "面试" in cleaned:
        seeds.append("面试")
    if any(token in cleaned for token in ["约会", "见面"]):
        seeds.append("约会")
    if any(token in cleaned for token in ["上课", "校园", "学生"]):
        seeds.append("校园")
    if any(token in cleaned for token in ["旅行", "旅游", "出游"]):
        seeds.append("旅行")
    if any(token in cleaned for token in ["拍照", "对镜", "挡脸", "场景拍"]):
        seeds.append("拍照")
    if "下雨" in cleaned or "雨" in cleaned:
        seeds.append("雨天")
    if "显瘦" in cleaned:
        seeds.append("显瘦")
    if "显高" in cleaned:
        seeds.append("显高")
    if "显白" in cleaned:
        seeds.append("显白")
    if "上海" in cleaned:
        seeds.append("上海")
    style_keywords = ["韩系", "法式", "日系", "美式", "松弛", "平替", "小个子", "梨形", "通勤风", "学院风"]
    seeds.extend([token for token in style_keywords if token in cleaned])
    seeds.append("穿搭")
    return " ".join(dict.fromkeys(seeds))[:80]


def _xhs_broad_query_from_message(message: str) -> str:
    cleaned = str(message or "")
    seeds = ["穿搭"]
    if any(token in cleaned for token in ["聚餐", "饭局", "下班"]):
        seeds.append("聚餐")
    if any(token in cleaned for token in ["上班", "通勤", "工作", "周五"]):
        seeds.append("通勤")
    if any(token in cleaned for token in ["客户", "会面", "会议", "商务", "正式", "稳"]):
        seeds.append("客户会面")
    if any(token in cleaned for token in ["看展", "展"]):
        seeds.append("看展")
    if "面试" in cleaned:
        seeds.append("面试")
    if "约会" in cleaned:
        seeds.append("约会")
    if any(token in cleaned for token in ["上课", "校园", "学生"]):
        seeds.append("校园")
    if any(token in cleaned for token in ["旅行", "旅游", "出游"]):
        seeds.append("旅行")
    if any(token in cleaned for token in ["拍照", "对镜", "挡脸", "场景拍"]):
        seeds.append("拍照")
    if any(token in cleaned for token in ["雨", "下雨", "小雨"]):
        seeds.append("雨天")
    if len(seeds) == 1:
        seeds.extend(["通勤", "ootd"])
    return " ".join(dict.fromkeys(seeds))


def _xhs_query_candidates(message: str) -> list[str]:
    cleaned = " ".join(str(message or "").replace("\n", " ").split())
    primary = _xhs_query_from_message(cleaned)
    broad = _xhs_broad_query_from_message(cleaned)
    candidates = [primary, broad]
    scenario_terms: list[str] = []
    if any(token in cleaned for token in ["客户", "会面", "会议", "商务", "正式", "稳"]):
        scenario_terms.extend(["客户会面 通勤 穿搭", "商务通勤 穿搭", "职场正式 不老气 穿搭"])
    if "面试" in cleaned:
        scenario_terms.extend(["面试 通勤 穿搭", "正式 不老气 穿搭"])
    if any(token in cleaned for token in ["聚餐", "饭局", "下班"]):
        scenario_terms.extend(["通勤转聚餐 穿搭", "下班聚餐 穿搭"])
    if any(token in cleaned for token in ["约会", "见面"]):
        scenario_terms.extend(["约会 显气质 穿搭", "温柔 约会 穿搭"])
    if any(token in cleaned for token in ["雨", "下雨", "小雨"]):
        scenario_terms.extend(["雨天 通勤 穿搭", "雨天 防滑 穿搭"])
    if any(token in cleaned for token in ["看展", "美术馆", "拍照", "对镜", "挡脸"]):
        scenario_terms.extend(["拍照 出片 穿搭", "看展 拍照 穿搭"])
    candidates.extend(scenario_terms)
    candidates.append("通勤 ootd 穿搭")
    return [query for query in dict.fromkeys(query.strip() for query in candidates) if query]


def _xhs_search_strategy_summary(message: str) -> str:
    profile = _xhs_relevance_profile(message)
    scenes = list(profile["scene_groups"].keys())
    styles = profile["style_tokens"]
    parts: list[str] = []
    if scenes:
        parts.append(f"从问题中提取场景：{'、'.join(scenes[:3])}")
    if styles:
        parts.append(f"约束：{'、'.join(styles[:3])}")
    if not parts:
        parts.append("识别为泛穿搭灵感需求")
    return "；".join(parts)


def _xhs_search_step_detail(message: str, search_meta: list[dict[str, Any]]) -> str:
    strategy = _xhs_search_strategy_summary(message)
    used_queries = [str(item.get("query") or "").strip() for item in search_meta if item.get("query")]
    raw_count = sum(int(item.get("raw_count") or 0) for item in search_meta)
    query_preview = " / ".join(used_queries[:3])
    if len(used_queries) > 3:
        query_preview = f"{query_preview} 等 {len(used_queries)} 组"
    return f"{strategy}；搜索：{query_preview or '默认穿搭'}；共 {raw_count} 张候选卡片"


def _xhs_filter_step_detail(notes: list[dict[str, Any]], message: str) -> str:
    profile = _xhs_relevance_profile(message)
    scenes = list(profile["scene_groups"].keys())
    top_reasons: list[str] = []
    for note in notes:
        for reason in note.get("relevance_reasons") or []:
            if reason not in top_reasons:
                top_reasons.append(str(reason))
    reason_text = "、".join(top_reasons[:4])
    if scenes:
        return f"保留 {len(notes)} 张高相关笔记，要求命中 {'、'.join(scenes[:3])}；依据：{reason_text or '场景相关'}"
    return f"保留 {len(notes)} 张穿搭相关笔记；依据：{reason_text or '穿搭相关'}"


def _xhs_api_base_url() -> str | None:
    explicit = os.environ.get("ASIS_XHS_API_URL") or os.environ.get("STYLIST_XHS_API_URL") or os.environ.get("STYLIST_XHS_SEARCH_URL")
    if explicit and explicit.strip():
        return explicit.strip().rstrip("/")
    mcp_url = _xhs_mcp_config().get("url")
    if isinstance(mcp_url, str) and mcp_url.strip():
        return mcp_url.strip().removesuffix("/mcp").rstrip("/")
    return None


def _xhs_unavailable_detail(login_status: dict[str, Any] | None, fallback: str) -> str:
    data = login_status.get("data") if isinstance(login_status, dict) else None
    if isinstance(data, dict) and data.get("is_logged_in") is False:
        return "小红书侧边服务未登录，请先扫码登录后重试"
    return fallback


def _xhs_user_facing_unavailable_detail(context: dict[str, Any]) -> str:
    detail = str(context.get("xhs_unavailable_detail") or "").strip()
    reason = str(context.get("xhs_unavailable_reason") or "").strip()
    if "未登录" in detail:
        return "当前小红书账号态未登录，暂时拿不到笔记卡片"
    if "超时" in detail or reason == "xhs_timeout":
        return "小红书检索超时，暂时没有拿到稳定结果"
    if "没有通过场景相关性过滤" in detail or reason == "xhs_notes_empty":
        return "检索结果没有通过场景相关性过滤"
    if "没有配置" in detail or reason == "xhs_api_not_configured":
        return "小红书检索服务还没有配置好"
    if detail:
        return detail.rstrip("。；;")
    return "这次没有拿到可用笔记卡片"


def _xhs_public_fallback_failed(context: dict[str, Any]) -> bool:
    steps = context.get("xhs_tool_steps") if isinstance(context.get("xhs_tool_steps"), list) else []
    return any(isinstance(step, dict) and step.get("id") == "public" and step.get("status") == "failed" for step in steps)


def _extract_xhs_feeds(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if isinstance(data, dict) and isinstance(data.get("feeds"), list):
        return [feed for feed in data["feeds"] if isinstance(feed, dict)]
    if isinstance(data, list):
        return [feed for feed in data if isinstance(feed, dict)]
    if isinstance(payload.get("feeds"), list):
        return [feed for feed in payload["feeds"] if isinstance(feed, dict)]
    return []


def _normalize_xhs_feeds(feeds: list[dict[str, Any]], query: str, source_label: str, relevance_text: str | None = None, limit: int = 6) -> list[dict[str, Any]]:
    notes: list[dict[str, Any]] = []
    seen: set[str] = set()
    for feed in feeds:
        note = _normalize_xhs_feed(feed, query, source_label)
        if not note or note["note_id"] in seen or not _is_xhs_fashion_note(note):
            continue
        score, reasons = _xhs_note_relevance(note, relevance_text or query)
        if score < _xhs_relevance_threshold(relevance_text or query):
            continue
        note["relevance_score"] = score
        note["relevance_reasons"] = reasons
        seen.add(note["note_id"])
        notes.append(note)
    notes.sort(key=lambda item: float(item.get("relevance_score") or 0), reverse=True)
    return notes[:limit]


def _is_xhs_fashion_note(note: dict[str, Any]) -> bool:
    title = str(note.get("title") or "").lower()
    author = str(note.get("author_name") or "").lower()
    text = f"{title} {author}"
    positive_keywords = [
        "穿搭",
        "ootd",
        "look",
        "通勤",
        "职场",
        "商务",
        "客户",
        "会面",
        "会议",
        "正式",
        "上班",
        "聚餐",
        "约会",
        "显瘦",
        "韩系",
        "法式",
        "日系",
        "松弛",
        "搭配",
        "西装",
        "衬衫",
        "针织",
        "半裙",
        "裙",
        "裤",
        "牛仔",
        "外套",
        "上衣",
        "鞋",
        "包",
        "乐福",
        "短靴",
        "slingback",
        "衣",
    ]
    negative_keywords = ["宝宝", "喂养", "咖啡", "医生", "英语", "说唱", "彩妆", "卷发", "美甲", "育儿", "睡衣"]
    if any(keyword in text for keyword in negative_keywords):
        return False
    return any(keyword in text for keyword in positive_keywords)


def _xhs_relevance_threshold(message: str) -> float:
    profile = _xhs_relevance_profile(message)
    return 2.3 if profile["scene_tokens"] else 1.2


def _rank_xhs_notes_for_answer(notes: list[dict[str, Any]], message: str) -> list[dict[str, Any]]:
    profile = _xhs_relevance_profile(message)
    threshold = _xhs_relevance_threshold(message)
    ranked = [
        note
        for note in notes
        if float(note.get("relevance_score") or 0) >= threshold and _xhs_note_has_scene_evidence(note, profile)
    ]
    ranked.sort(key=lambda item: float(item.get("relevance_score") or 0), reverse=True)
    return ranked


def _xhs_has_enough_answer_evidence(notes: list[dict[str, Any]], message: str) -> bool:
    profile = _xhs_relevance_profile(message)
    if not notes:
        return False
    if not profile["scene_tokens"]:
        return len(notes) >= int(os.environ.get("ASIS_XHS_MIN_GENERIC_NOTES", "3"))
    min_notes = int(os.environ.get("ASIS_XHS_MIN_SCENE_NOTES", "4"))
    threshold = _xhs_relevance_threshold(message)
    strong_notes = [note for note in notes if float(note.get("relevance_score") or 0) >= threshold + 0.5]
    scene_matched = [note for note in notes if _xhs_note_has_scene_evidence(note, profile)]
    return len(notes) >= min_notes and len(strong_notes) >= max(2, min_notes // 2) and len(scene_matched) >= min_notes


def _xhs_note_has_scene_evidence(note: dict[str, Any], profile: dict[str, Any]) -> bool:
    if not profile["scene_tokens"]:
        return True
    text = _xhs_note_text(note)
    return any(_contains_any(text, tokens) for tokens in profile["scene_groups"].values())


def _xhs_note_relevance(note: dict[str, Any], message: str) -> tuple[float, list[str]]:
    profile = _xhs_relevance_profile(message)
    text = _xhs_note_text(note)
    score = 0.0
    reasons: list[str] = []
    if _contains_any(text, profile["fashion_tokens"]):
        score += 1.2
        reasons.append("穿搭")
    for group, tokens in profile["scene_groups"].items():
        matched = [token for token in tokens if token and token.lower() in text]
        if matched:
            score += 1.15
            score += min(0.9, max(0, len(set(matched)) - 1) * 0.3)
            reasons.append(group)
    for token in profile["style_tokens"]:
        if token and token in text:
            score += 0.45
            reasons.append(token)
    for token in profile["negative_tokens"]:
        if token and token in text:
            score -= 2.5
            reasons.append(f"排除:{token}")
    # A generic outfit note is acceptable only when the user did not provide a strong scene.
    if not profile["scene_tokens"] and _contains_any(text, profile["fashion_tokens"]):
        score += 0.4
    return round(score, 2), reasons[:6]


def _xhs_relevance_profile(message: str) -> dict[str, Any]:
    text = str(message or "").lower()
    scene_groups: dict[str, list[str]] = {}
    if any(token in text for token in ["聚餐", "饭局", "约饭", "下班"]):
        scene_groups["聚餐"] = ["聚餐", "饭局", "约饭", "约会", "晚餐", "下班", "小酌", "约会"]
    if any(token in text for token in ["约会", "见面", "date"]):
        scene_groups["约会"] = ["约会", "date", "见面", "晚餐", "电影", "咖啡约"]
    if any(token in text for token in ["上班", "通勤", "工作", "职场", "会议", "面试"]):
        scene_groups["通勤"] = ["通勤", "上班", "职场", "工作", "办公室", "会议", "面试", "班味"]
    if any(token in text for token in ["客户", "会面", "商务", "正式", "稳"]):
        scene_groups["客户会面"] = ["客户", "会面", "商务", "正式", "稳重", "得体", "职场", "会议", "通勤"]
    if any(token in text for token in ["看展", "展", "美术馆", "拍照"]):
        scene_groups["看展"] = ["看展", "展览", "美术馆", "博物馆", "拍照", "出片"]
    if any(token in text for token in ["生日", "派对", "party"]):
        scene_groups["派对"] = ["生日", "派对", "party", "聚会", "宴会"]
    if any(token in text for token in ["社团", "校园", "学生"]):
        scene_groups["校园"] = ["社团", "校园", "学生", "学院", "拍照"]
    if any(token in text for token in ["雨", "下雨", "小雨", "防水"]):
        scene_groups["雨天"] = ["雨天", "下雨", "小雨", "防水", "防滑", "雨靴"]
    if any(token in text for token in ["演唱会", "音乐节"]):
        scene_groups["演出"] = ["演唱会", "音乐节", "live", "出片", "蹦迪"]
    style_tokens = [
        token
        for token in ["显瘦", "显白", "松弛", "韩系", "法式", "日系", "甜辣", "预算", "平替", "小个子", "微胖", "梨形", "通勤感"]
        if token in text
    ]
    return {
        "fashion_tokens": ["穿搭", "搭配", "ootd", "look", "西装", "衬衫", "针织", "半裙", "裤", "裙", "牛仔", "外套", "乐福", "短靴", "鞋", "包"],
        "scene_groups": scene_groups,
        "scene_tokens": [token for tokens in scene_groups.values() for token in tokens],
        "style_tokens": style_tokens,
        "negative_tokens": ["宝宝", "喂养", "咖啡", "医生", "英语", "说唱", "彩妆", "卷发", "美甲", "育儿", "睡衣", "家常菜", "旅行攻略"],
    }


def _xhs_note_text(note: dict[str, Any]) -> str:
    parts = [
        note.get("title"),
        note.get("author_name"),
        note.get("desc"),
        note.get("source_label"),
    ]
    return " ".join(str(part or "") for part in parts).lower()


def _contains_any(text: str, tokens: list[str]) -> bool:
    return any(token.lower() in text for token in tokens if token)


def _normalize_xhs_feed(feed: dict[str, Any], query: str = "", source_label: str = "小红书推荐") -> dict[str, Any] | None:
    note_card = feed.get("noteCard") if isinstance(feed.get("noteCard"), dict) else {}
    note_id = str(feed.get("id") or note_card.get("noteId") or "").strip()
    title = str(note_card.get("displayTitle") or note_card.get("title") or feed.get("title") or "").strip()
    if not note_id or not title:
        return None
    user = note_card.get("user") if isinstance(note_card.get("user"), dict) else {}
    interact = note_card.get("interactInfo") if isinstance(note_card.get("interactInfo"), dict) else {}
    cover = note_card.get("cover") if isinstance(note_card.get("cover"), dict) else {}
    cover_source_url = _xhs_cover_url(cover)
    if not cover_source_url:
        return None
    cover_url = _xhs_image_proxy_url(cover_source_url)
    xsec_token = str(feed.get("xsecToken") or feed.get("xsec_token") or "").strip()
    url = f"https://www.xiaohongshu.com/explore/{quote(note_id)}"
    if xsec_token:
        url = f"{url}?{urlencode({'xsec_token': xsec_token, 'xsec_source': 'pc_feed'})}"
    return {
        "note_id": note_id,
        "title": title[:80],
        "desc": str(note_card.get("desc") or note_card.get("description") or feed.get("desc") or "").strip()[:180],
        "author_name": str(user.get("nickname") or user.get("nickName") or "小红书用户").strip(),
        "author_avatar": str(user.get("avatar") or "").strip(),
        "cover_url": cover_url,
        "cover_source_url": cover_source_url,
        "liked_count": _xhs_count(interact.get("likedCount")),
        "collected_count": _xhs_count(interact.get("collectedCount")),
        "comment_count": _xhs_count(interact.get("commentCount")),
        "source_label": source_label,
        "query": query,
        "url": url,
    }


def _xhs_cover_url(cover: dict[str, Any]) -> str:
    for key in ["urlDefault", "url", "urlPre"]:
        value = str(cover.get(key) or "").strip()
        if value:
            return value
    info_list = cover.get("infoList")
    if isinstance(info_list, list):
        for item in info_list:
            if isinstance(item, dict) and item.get("url"):
                return str(item["url"]).strip()
    return ""


def _xhs_image_proxy_url(url: str) -> str:
    clean_url = str(url or "").strip()
    if not clean_url:
        return ""
    if "xhscdn.com" not in clean_url:
        return clean_url
    return f"/xhs-image?{urlencode({'url': clean_url})}"


def _xhs_count(value: Any) -> str:
    text = str(value or "").strip()
    return text if text and text != "0" else ""


def _merge_xhs_artifacts(result: dict[str, Any], request: dict[str, Any] | None) -> None:
    context = request.get("context") if isinstance(request, dict) and isinstance(request.get("context"), dict) else {}
    notes = context.get("xhs_notes") if isinstance(context.get("xhs_notes"), list) else []
    tool_steps = context.get("xhs_tool_steps") if isinstance(context.get("xhs_tool_steps"), list) else []
    evidence = context.get("xhs_evidence_sources") if isinstance(context.get("xhs_evidence_sources"), list) else []
    if notes:
        result["xhs_notes"] = notes
    elif context.get("source") == "inspiration_tab" and context.get("xiaohongshu_preferred"):
        result.pop("xhs_notes", None)
        current = result.get("evidence_sources") if isinstance(result.get("evidence_sources"), list) else []
        result["evidence_sources"] = [
            source
            for source in current
            if not (isinstance(source, dict) and ("xiaohongshu" in json.dumps(source, ensure_ascii=False).lower() or "小红书" in json.dumps(source, ensure_ascii=False)))
        ]
    if tool_steps:
        result["tool_steps"] = tool_steps
    if evidence:
        current = result.get("evidence_sources") if isinstance(result.get("evidence_sources"), list) else []
        existing = json.dumps(current, ensure_ascii=False)
        result["evidence_sources"] = [*current, *[source for source in evidence if json.dumps(source, ensure_ascii=False) not in existing]]


def _extract_embedded_json_result(data: dict[str, Any]) -> dict[str, Any] | None:
    text = (
        data.get("assistant_message")
        or data.get("message")
        or data.get("text")
        or data.get("reply")
        or _extract_openclaw_payload_text(data)
        or ""
    )
    text = str(text).strip()
    if not text:
        return None
    candidates = [text]
    if text.startswith("```"):
        stripped = text.strip("`").strip()
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
        candidates.insert(0, stripped)
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidates.append(text[start : end + 1])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(parsed, dict) and parsed.get("status") in {"ok", "failed"}:
            return parsed
    return None


def _degraded_inspiration_result_if_needed(result: dict[str, Any], request: dict[str, Any]) -> dict[str, Any] | None:
    context = request.get("context") if isinstance(request.get("context"), dict) else {}
    if context.get("source") != "inspiration_tab" or result.get("status") != "failed":
        return None
    error = result.get("error") if isinstance(result.get("error"), dict) else {}
    if error.get("code") != "ai_unavailable":
        return None
    message = _effective_user_message(request).strip()
    if not message:
        return None
    conversation = context.get("conversation") if isinstance(context.get("conversation"), list) else []
    rainy = any(token in message for token in ["雨", "下雨", "小雨", "防水"])
    slim = any(token in message for token in ["显瘦", "修身", "比例"])
    no_high_heels = any(token in message for token in ["不想穿高跟", "不穿高跟", "不要高跟", "不想高跟", "平底", "低跟", "乐福鞋"])
    exhibition = any(token in message for token in ["看展", "展", "美术馆"])
    commute_dinner = any(token in message for token in ["聚餐", "饭局", "下班", "接聚餐"]) and any(token in message for token in ["上班", "通勤", "周五", "工作"])
    xhs_notes = context.get("xhs_notes") if isinstance(context.get("xhs_notes"), list) else []
    note_titles = [str(note.get("title") or "").strip() for note in xhs_notes if isinstance(note, dict) and note.get("title")]
    xhs_requested = _should_invoke_xhs_skill(request)
    public_fallback_used = any(isinstance(note, dict) and note.get("is_public_fallback") for note in xhs_notes)
    if xhs_notes and public_fallback_used:
        xhs_failure = _xhs_user_facing_unavailable_detail(context)
        xhs_note = f"我已经调用小红书灵感 skill，但{xhs_failure}；同时用公开网页搜索补到 {len(xhs_notes)} 条小红书公开链接，只作为弱参考，不当作原生推荐流。"
    elif xhs_notes:
        xhs_note = f"我先参考到 {len(xhs_notes)} 张小红书笔记卡片，重点看标题、封面和互动热度，再给你一版可执行建议。"
    elif xhs_requested:
        xhs_failure = _xhs_user_facing_unavailable_detail(context)
        public_fallback_note = "，公开网页搜索也没有找到可引用的小红书链接" if _xhs_public_fallback_failed(context) else ""
        xhs_note = f"我已经调用小红书灵感 skill，但{xhs_failure}{public_fallback_note}；这版先不给你硬塞低相关笔记，改用通用穿搭逻辑给一版可执行建议。"
    else:
        xhs_note = "我先按你这次的场景和衣橱目标，给你一版可直接执行的搭配建议。"
    if rainy and no_high_heels:
        assistant = (
            f"{xhs_note}\n\n延续周五上班接聚餐的场景，雨天又不想穿高跟，核心是“防滑、利落、晚上不显随便”："
            "鞋子优先光面乐福鞋、厚底德训鞋、短筒切尔西靴或防水短靴，鞋头选微尖或窄圆头，避开帆布、麂皮和太厚重的雨靴。"
            "下装用九分直筒西裤、微喇裤或过膝直筒裙，露出一点脚踝或靴筒边缘，会比拖地裤更清爽也不容易溅湿。"
            "上身保持垂感衬衫、薄针织或短西装，外面加一件防泼水风衣/短外套；颜色可以用黑、米白、灰、酒红做组合。"
            "聚餐前只要把通勤托特换成小肩包，再补耳环和口红，就能从上班切到晚间。"
        )
        rationale = [
            "雨天不穿高跟时，鞋底防滑和鞋面易清洁比高度更重要。",
            "九分直筒、微喇和短靴能保持腿部线条，避免雨天裤脚拖沓。",
            "小肩包、耳环和口红负责聚餐氛围，不需要靠高跟鞋撑场。",
        ]
    elif rainy and slim:
        assistant = (
            f"{xhs_note}\n\n延续刚才的场景，下雨又想显瘦，重点放在鞋包和线条：鞋子选光面皮、厚底乐福鞋或微尖头短靴，避开帆布和麂皮；"
            "鞋裤尽量同色，比如黑裤配黑乐福、燕麦裤配米色鞋，腿部线条会更顺。包选有结构的中号腋下包或短肩带托特，包底落在腰线上方，"
            "不要垂到胯部，这样不会横向截断比例。颜色控制在三种以内，雨伞也选透明、米白或浅卡其，会比黑伞更轻。"
        )
        rationale = [
            "雨天优先光面、防泼水材质，减少脏污和变形风险。",
            "鞋裤同色和短肩带包能减少视觉截断，更容易显高显瘦。",
            "结构感包型比软塌大包更利落，适合看展和通勤之间的场景。",
        ]
    elif exhibition:
        assistant = (
            f"{xhs_note}\n\n上海周末看展可以走“松弛通勤感”：上身选宽松白衬衫、薄针织或浅色短外套，下身配直筒卡其裤、米白阔腿裤或深色微喇裤；"
            "鞋子用乐福鞋、德训鞋或干净小白鞋，保证走路舒服；包选奶油色托特、浅棕腋下包或小号邮差包。整体用米白、燕麦、浅卡其、雾蓝这类低饱和颜色，"
            "再用细项链或丝巾做一点精致感。展厅冷气强，可以带一件薄外套。"
        )
        rationale = [
            "低饱和浅色和有结构的宽松版型更接近松弛通勤感。",
            "看展需要长时间走动，鞋子和包要先保证舒适与轻便。",
            "薄外套能处理上海湿热与展厅冷气的温差。",
        ]
    elif commute_dinner:
        assistant = (
            f"{xhs_note}\n\n周五上班接聚餐，建议走“白天得体、晚上有一点亮点”的路线：上身选垂感衬衫、薄针织或合身小西装，"
            "下身配直筒西裤、微喇裤或开衩半裙；颜色用黑、米白、燕麦、酒红或深牛仔做底，避免太休闲的卫衣和运动裤。"
            "鞋子选乐福鞋、低跟 slingback 或干净短靴，白天不累、晚上也不塌。包可以从通勤大包换成小肩包，"
            "再加耳环、细项链或一支更有气色的口红，聚餐感就出来了。"
        )
        rationale = [
            "通勤转聚餐的关键是保留办公室得体度，同时用鞋包和配饰做夜晚氛围。",
            "直筒或微喇下装能兼顾久坐、通勤和显腿直。",
            "小包、低跟鞋和金属配饰比大面积露肤更稳，也更适合下班直接赴约。",
        ]
    else:
        assistant = (
            f"{xhs_note}\n\n我建议先用一件有结构的基础上装确定风格，再配直筒或阔腿下装，鞋包保持同色系。"
            "如果想更通勤，就用衬衫、西装马甲、乐福鞋；如果想更松弛，就换成薄针织、德训鞋和软托特。"
        )
        rationale = [
            "先确定上装和下装主轴，整体更容易稳定。",
            "鞋包同色系能减少杂乱感，让搭配更完整。",
        ]
    return {
        "status": "ok",
        "mode": "degraded_openclaw",
        "assistant_message": assistant + (f"\n\n这次参考的笔记关键词包括：{'、'.join(note_titles[:3])}。" if note_titles else ""),
        "recommended_items": [],
        "recommended_outfits": [],
        "rationale": rationale,
        "evidence_sources": context.get("xhs_evidence_sources") if xhs_notes else [],
        "xhs_notes": xhs_notes,
        "tool_steps": context.get("xhs_tool_steps") if isinstance(context.get("xhs_tool_steps"), list) else [],
        "next_actions": [
            {"type": "open_closet", "label": "去衣橱选择单品"},
            *([{"type": "retry_xhs", "label": "稍后重试小红书灵感"}] if xhs_requested else []),
        ],
        "quality_checks": {
            "used_xiaohongshu_recommendations": bool(xhs_notes and not public_fallback_used),
            "used_public_xhs_fallback": bool(public_fallback_used),
            "xiaohongshu_preferred": bool(context.get("xiaohongshu_preferred")),
            "continued_conversation": len(conversation) >= 2,
        },
        "degraded_reason": "stylist_tools_unavailable",
    }


def _stylist_quality_checks(result: dict[str, Any], request: dict[str, Any] | None) -> dict[str, bool]:
    context = request.get("context") if isinstance(request, dict) and isinstance(request.get("context"), dict) else {}
    sources = result.get("evidence_sources") if isinstance(result.get("evidence_sources"), list) else []
    used_xhs = any(
        isinstance(source, dict)
        and str(source.get("type") or source.get("label") or "").lower() in {"xhs", "xiaohongshu", "小红书", "小红书推荐"}
        for source in sources
    )
    if not used_xhs:
        source_text = json.dumps(sources, ensure_ascii=False).lower()
        used_xhs = ("xiaohongshu" in source_text or "小红书" in source_text) and "public_web_search" not in source_text
    if not used_xhs and isinstance(result.get("xhs_notes"), list) and result["xhs_notes"]:
        used_xhs = not any(isinstance(note, dict) and note.get("is_public_fallback") for note in result["xhs_notes"])
    conversation = context.get("conversation") if isinstance(context, dict) else None
    return {
        "used_xiaohongshu_recommendations": bool(used_xhs),
        "used_public_xhs_fallback": bool(
            isinstance(result.get("xhs_notes"), list)
            and any(isinstance(note, dict) and note.get("is_public_fallback") for note in result["xhs_notes"])
        ),
        "xiaohongshu_preferred": bool(context.get("xiaohongshu_preferred")) if isinstance(context, dict) else False,
        "continued_conversation": bool(isinstance(conversation, list) and len(conversation) >= 2),
    }


def _extract_openclaw_payload_text(data: dict[str, Any]) -> str:
    payloads = data.get("payloads")
    if isinstance(payloads, list):
        texts = [str(payload.get("text") or "").strip() for payload in payloads if isinstance(payload, dict)]
        joined = "\n\n".join(text for text in texts if text)
        if joined:
            return joined
    meta = data.get("meta")
    if isinstance(meta, dict):
        return str(meta.get("finalAssistantVisibleText") or meta.get("finalAssistantRawText") or "").strip()
    return ""


def _demo_chat_response(request: dict[str, Any]) -> dict[str, Any]:
    outfits = list_outfits().get("outfits", [])[:2]
    items = list_closet_items().get("items", [])[:6]
    return {
        "status": "ok",
        "mode": "demo",
        "assistant_message": "我先基于你当前衣橱给一版演示推荐。正式模式会调用独立 OpenClaw 穿搭师运行时。",
        "recommended_items": items,
        "recommended_outfits": outfits,
        "rationale": [
            "优先选择衣橱里已有的可用单品。",
            "正式运行时会结合记忆、技能、内部知识库和小红书检索做解释。",
        ],
        "evidence_sources": [{"type": "closet", "label": "本地衣橱", "count": len(items)}],
        "next_actions": [
            {"type": "save_outfit", "label": "保存套装"},
            {"type": "tryon", "label": "去试穿"},
            {"type": "configure_openclaw", "label": "连接正式穿搭师"},
        ],
        "quality_checks": _stylist_quality_checks({"evidence_sources": [{"type": "closet", "label": "本地衣橱", "count": len(items)}]}, request),
        "session_id": request["session_id"],
        "user_id": request["user_id"],
        "runtime": {"transport": "demo", "agent_id": request["agent_id"]},
    }


def _tool_closet_search(payload: dict[str, Any]) -> dict[str, Any]:
    category = str(payload.get("category") or "").strip() or None
    query = str(payload.get("query") or payload.get("scene") or "").strip().lower()
    items = list_closet_items(category if category != "all" else None).get("items", [])
    if query:
        items = [
            item
            for item in items
            if query in json.dumps(
                {
                    "category": item.get("category"),
                    "category_label": item.get("category_label"),
                    "attributes": item.get("attributes", {}),
                    "note": item.get("note", ""),
                },
                ensure_ascii=False,
            ).lower()
        ] or items
    limit = max(1, min(24, int(payload.get("limit") or 12)))
    return {"status": "ok", "total": len(items), "items": items[:limit]}


def _tool_compose_outfit(payload: dict[str, Any]) -> dict[str, Any]:
    item_ids = payload.get("item_ids")
    if isinstance(item_ids, list) and item_ids:
        items = [get_closet_item(str(item_id)) for item_id in item_ids[:8]]
    else:
        items = _pick_basic_outfit_items(list_closet_items().get("items", []))
    return {
        "status": "ok",
        "draft": {
            "title": str(payload.get("title") or payload.get("scene") or "AI 推荐搭配")[:48],
            "item_ids": [item["item_id"] for item in items],
            "items": items,
            "scene_tags": [str(payload.get("scene"))] if payload.get("scene") else [],
        },
    }


def _pick_basic_outfit_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    used: set[str] = set()
    for category in ["top", "dress", "bottom", "skirt", "shoes", "bag", "accessory"]:
        if category in used:
            continue
        if category == "skirt" and "bottom" in used:
            continue
        if category in {"top", "bottom", "skirt"} and "dress" in used:
            continue
        match = next((item for item in items if item.get("category") == category and item.get("item_id") not in {x.get("item_id") for x in selected}), None)
        if match:
            selected.append(match)
            used.add(category)
    return selected[:5]


def _tool_xhs_search(payload: dict[str, Any]) -> dict[str, Any]:
    mcp = _xhs_mcp_config()
    if mcp["url"]:
        return {
            "status": "mcp_sidecar_configured",
            "message": "小红书搜索已配置为 OpenClaw 侧通过 MCP sidecar 调用；FastAPI 只保留工具边界和结构化结果约定。",
            "query": payload.get("query") or payload.get("scene"),
            "mcp_url": mcp["url"],
            "mcp_mode": mcp["mode"],
            "allowed_tools": mcp["allowed_tools"],
            "notes": [],
        }
    provider_url = os.environ.get("STYLIST_XHS_SEARCH_URL")
    if not provider_url:
        return {
            "status": "not_configured",
            "message": "小红书搜索 MCP sidecar 尚未配置，当前只能读取公开链接。",
            "query": payload.get("query") or payload.get("scene"),
            "notes": [],
        }
    return {
        "status": "provider_required",
        "message": "请由 OpenClaw fork 的搜索插件调用 STYLIST_XHS_SEARCH_URL。",
        "provider_url": provider_url,
    }


def _tool_style_kb_search(payload: dict[str, Any]) -> dict[str, Any]:
    query = str(payload.get("query") or payload.get("scene") or "").strip()
    rules = [
        {"id": "balance-main-axis", "title": "主轴搭配", "content": "一套搭配先确定上衣/连衣装与下装，再放鞋包配饰，避免同品类重复。"},
        {"id": "low-noise-color", "title": "低噪色彩", "content": "通勤、面试和正式场景优先选择低饱和、清爽干净的色彩组合。"},
        {"id": "scene-first", "title": "场景优先", "content": "推荐解释先回答场景需求，再解释颜色、比例、材质和舒适度。"},
    ]
    return {"status": "ok", "query": query, "results": rules}


async def _proxy_memory(method: str, user_id: str, payload: dict[str, Any] | None) -> tuple[dict[str, Any], int]:
    memory_url = os.environ.get("STYLIST_OPENCLAW_MEMORY_URL")
    if _demo_mode():
        return {"status": "ok", "mode": "demo", "user_id": user_id, "memory": []}, 200
    if not memory_url:
        return _failed(
            "agent_runtime_unavailable",
            "用户记忆由独立 OpenClaw runtime 管理，但当前没有配置记忆服务。",
            503,
            suggestion="请配置 STYLIST_OPENCLAW_MEMORY_URL，或启动 asis-agent-runtime。",
        )
    async with httpx.AsyncClient(timeout=20) as client:
        url = f"{memory_url.rstrip('/')}/{user_id}"
        try:
            response = await client.request(method, url, json=payload if payload is not None else None)
        except httpx.HTTPError as exc:
            return _failed("agent_runtime_unavailable", "OpenClaw 记忆服务暂时不可用。", 503, evidence={"error": str(exc)})
    try:
        data = response.json()
    except ValueError:
        data = {"raw_text": response.text}
    if response.status_code >= 400:
        return _failed(_runtime_error_code(response.status_code, data), _runtime_error_message(_runtime_error_code(response.status_code, data)), response.status_code)
    return data, 200


def _runtime_error_code(status_code: int | None, data: dict[str, Any]) -> str:
    text = json.dumps(data, ensure_ascii=False).lower()
    if status_code in {401, 402, 403, 429}:
        return "ai_unavailable"
    if any(token in text for token in ["api key", "apikey", "unauthorized", "invalid key", "quota", "credit", "billing", "model not found", "provider"]):
        return "ai_unavailable"
    return "agent_runtime_unavailable"


def _runtime_error_message(code: str) -> str:
    if code == "ai_unavailable":
        return "AI 穿搭师暂时不可用，请检查模型配置。"
    return "OpenClaw 穿搭师运行时暂时不可用。"


def _status_for_error_code(code: str) -> int:
    return 503 if code in {"ai_unavailable", "agent_runtime_unavailable"} else 400


def _failed(code: str, message: str, status_code: int, suggestion: str | None = None, evidence: dict[str, Any] | None = None) -> tuple[dict[str, Any], int]:
    return {
        "status": "failed",
        "mode": "error",
        "error": {
            "code": code,
            "message": message,
            "suggestion": suggestion or message,
        },
        "assistant_message": message,
        "recommended_items": [],
        "recommended_outfits": [],
        "rationale": [],
        "evidence_sources": [],
        "next_actions": [],
        "evidence": evidence or {},
    }, status_code


def _openclaw_chat_url() -> str | None:
    value = os.environ.get("STYLIST_OPENCLAW_CHAT_URL") or os.environ.get("OPENCLAW_ASIS_CHAT_URL")
    return value.strip() if value and value.strip() else None


def _stylist_model_key_names() -> list[str]:
    names: list[str] = []
    for values in STYLIST_MODEL_KEY_ENV_BY_PROVIDER.values():
        names.extend(values)
    return sorted(set(names))


def _stylist_model_ref() -> str:
    return os.environ.get("STYLIST_OPENCLAW_MODEL", "").strip() or DEFAULT_STYLIST_MODEL


def _stylist_model_provider(model_ref: str | None = None) -> str:
    ref = (model_ref or _stylist_model_ref()).strip().lower()
    return ref.split("/", 1)[0] if "/" in ref else "openai"


def _stylist_model_key_report() -> dict[str, Any]:
    model = _stylist_model_ref()
    provider = _stylist_model_provider(model)
    accepted_keys = STYLIST_MODEL_KEY_ENV_BY_PROVIDER.get(provider, [])
    any_key_present = any(os.environ.get(key, "").strip() for key in _stylist_model_key_names())
    matching_key_present = any(os.environ.get(key, "").strip() for key in accepted_keys)
    return {
        "model": model,
        "provider": provider,
        "accepted_env_keys": accepted_keys,
        "any_key_present": any_key_present,
        "matching_key_present": matching_key_present,
    }


def _xhs_mcp_config() -> dict[str, Any]:
    url = os.environ.get("ASIS_XHS_MCP_URL") or os.environ.get("STYLIST_XHS_MCP_URL")
    mode = os.environ.get("ASIS_XHS_MCP_MODE") or os.environ.get("STYLIST_XHS_MCP_MODE") or "streamable-http"
    raw_tools = os.environ.get("ASIS_XHS_ALLOWED_TOOLS") or os.environ.get("STYLIST_XHS_ALLOWED_TOOLS") or ""
    allowed_tools = [tool.strip() for tool in raw_tools.split(",") if tool.strip()] or ["check_login_status", "search_feeds", "get_feed_detail", "list_feeds"]
    return {
        "url": url.strip() if url and url.strip() else None,
        "mode": mode.strip() if mode and mode.strip() else "streamable-http",
        "allowed_tools": allowed_tools,
    }


def _demo_mode() -> bool:
    return _env_flag("STYLIST_DEMO_MODE")


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}
