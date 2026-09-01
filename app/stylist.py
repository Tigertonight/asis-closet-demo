from __future__ import annotations

import asyncio
import html as html_lib
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
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
    recommend_outfits,
)
from app.tryon import extract_xhs_link


LOGGER = logging.getLogger("selfit.stylist")
if not LOGGER.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
    LOGGER.addHandler(_handler)
LOGGER.setLevel(logging.INFO)
LOGGER.propagate = False
ROOT_DIR = Path(__file__).resolve().parents[1]
STYLIST_RUNTIME_DIR = ROOT_DIR / "selfit-agent-runtime"
STYLIST_AGENT_ID = "selfit-stylist"
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
    "selfit_closet_search",
    "selfit_get_item",
    "selfit_compose_outfit",
    "selfit_save_outfit",
    "selfit_tryon_from_outfit",
    "selfit_xhs_search",
    "selfit_xhs_fetch_note",
    "selfit_style_kb_search",
]
DEFAULT_STYLIST_MODEL = "openai/gpt-5.5"
STYLIST_FRIENDLY_ERROR_MESSAGE = "暂时灵感耗尽，正在努力充能～"
CONTEXT_ITEM_LIMIT = 24
CONTEXT_ITEMS_PER_SLOT = 4
CONTEXT_OUTFIT_LIMIT = 8
CONTEXT_OUTFITS_PER_SCENE = 3
CLOSET_ONLY_ITEM_LIMIT = 14
CLOSET_ONLY_OUTFIT_LIMIT = 5
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
    started_at = time.perf_counter()
    message = str(payload.get("message") or "").strip()
    if not message:
        return _failed("invalid_request", "请先告诉 AI 穿搭师你的场景或问题。", 400)

    request = _normalize_chat_payload(payload, message)
    _attach_closet_context(request)
    LOGGER.info(
        "stylist_chat_start session=%s source=%s xhs_pref=%s closet_only=%s message=%s",
        request.get("session_id"),
        request.get("context", {}).get("source"),
        request.get("context", {}).get("xiaohongshu_preferred"),
        request.get("context", {}).get("closet_only"),
        message[:80],
    )
    await _attach_xhs_inspiration(request)
    if _demo_mode():
        result = _demo_chat_response(request)
        LOGGER.info("stylist_chat_done session=%s mode=demo status=200 elapsed=%.2fs", request.get("session_id"), time.perf_counter() - started_at)
        return result, 200

    if _should_use_light_closet_ai(request):
        light_result = await _run_light_closet_ai(request)
        if light_result is not None:
            LOGGER.info("stylist_chat_done session=%s mode=light_closet_ai status=200 elapsed=%.2fs", request.get("session_id"), time.perf_counter() - started_at)
            return light_result, 200

    chat_url = _openclaw_chat_url()
    if chat_url:
        if not _stylist_model_key_report()["matching_key_present"]:
            return _failed("ai_unavailable", "AI 穿搭师暂时不可用，请检查模型配置。", 503)
        result, status = await _post_openclaw_http(chat_url, request)
        LOGGER.info(
            "stylist_chat_done session=%s mode=%s status=%s elapsed=%.2fs",
            request.get("session_id"),
            result.get("mode"),
            status,
            time.perf_counter() - started_at,
        )
        return result, status

    if _env_flag("STYLIST_ENABLE_OPENCLAW_CLI"):
        if not _stylist_model_key_report()["matching_key_present"]:
            return _failed("ai_unavailable", "AI 穿搭师暂时不可用，请检查模型配置。", 503)
        result, status = await _run_openclaw_cli(request)
        LOGGER.info("stylist_chat_done session=%s mode=%s status=%s elapsed=%.2fs", request.get("session_id"), result.get("mode"), status, time.perf_counter() - started_at)
        return result, status

    result = _failed(
        "agent_runtime_unavailable",
        "OpenClaw 穿搭师运行时还没有配置，无法启动 AI 对话。",
        503,
        suggestion="请先启动 selfit-agent-runtime，或配置 STYLIST_OPENCLAW_CHAT_URL。不要在正式模式下使用假回复。",
    )
    LOGGER.info("stylist_chat_done session=%s mode=unavailable status=503 elapsed=%.2fs", request.get("session_id"), time.perf_counter() - started_at)
    return result


async def stream_stylist_chat(payload: dict[str, Any]) -> AsyncIterator[str]:
    result, status = await run_stylist_chat(payload)
    event = "message" if status < 400 else "error"
    yield f"event: {event}\n"
    yield f"data: {json.dumps(result, ensure_ascii=False)}\n\n"


async def run_selfit_tool(tool_name: str, payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
    try:
        if tool_name == "selfit_closet_search":
            return _tool_closet_search(payload), 200
        if tool_name == "selfit_get_item":
            item_id = str(payload.get("item_id") or "").strip()
            return {"status": "ok", "item": get_closet_item(item_id)}, 200
        if tool_name == "selfit_compose_outfit":
            return _tool_compose_outfit(payload), 200
        if tool_name == "selfit_save_outfit":
            return {"status": "ok", "outfit": create_outfit(payload)}, 200
        if tool_name == "selfit_tryon_from_outfit":
            outfit_id = str(payload.get("outfit_id") or "").strip()
            return {"status": "ok", "tryon": mock_tryon_from_outfit(outfit_id)}, 200
        if tool_name == "selfit_xhs_fetch_note":
            url = str(payload.get("url") or "").strip()
            return {"status": "ok", "note": await extract_xhs_link(url)}, 200
        if tool_name == "selfit_xhs_search":
            return _tool_xhs_search(payload), 200
        if tool_name == "selfit_style_kb_search":
            return _tool_style_kb_search(payload), 200
        if tool_name == "selfit_import_link":
            url = str(payload.get("url") or "").strip()
            return {"status": "ok", "import_result": await import_link(url)}, 200
    except Exception as exc:
        return _failed("tool_failed", str(exc) or "工具调用失败。", 500)
    return _failed("unknown_tool", f"未知 selfit 工具：{tool_name}", 404)


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
        "session_key": f"selfit:{user_id}:{session_id}",
        "user_id": user_id,
        "message": message,
        "context": payload.get("context") if isinstance(payload.get("context"), dict) else {},
        "required_output": "selfit_stylist_recommendation_v1",
        "tool_base_url": os.environ.get("STYLIST_SELFIT_TOOL_BASE_URL", "http://127.0.0.1:8002"),
    }


def _attach_closet_context(request: dict[str, Any]) -> None:
    context = request.get("context") if isinstance(request.get("context"), dict) else {}
    message = str(request.get("message") or context.get("current_query") or "").strip()
    try:
        items = list_closet_items().get("items", [])
    except Exception:
        items = []
    try:
        outfits = list_outfits().get("outfits", [])
    except Exception:
        outfits = []
    context["item_count"] = len(items)
    context["outfit_count"] = len(outfits)
    closet_only = _message_explicitly_disables_xhs(message) or context.get("xiaohongshu_preferred") is False
    item_limit = CLOSET_ONLY_ITEM_LIMIT if closet_only else CONTEXT_ITEM_LIMIT
    outfit_limit = CLOSET_ONLY_OUTFIT_LIMIT if closet_only else CONTEXT_OUTFIT_LIMIT
    ranked_items = _rank_context_items(items, message)
    selected_items = _balanced_context_items(ranked_items, limit=item_limit, per_slot=CONTEXT_ITEMS_PER_SLOT)
    ranked_outfits = _rank_context_outfits(outfits, message)[:outfit_limit]
    context["closet_only"] = closet_only
    context["closet_items"] = [_summarize_closet_item(item) for item in selected_items]
    context["closet_item_groups"] = _closet_item_groups(selected_items)
    context["closet_outfits"] = [_summarize_closet_outfit(outfit) for outfit in ranked_outfits]
    context["closet_outfit_groups"] = _closet_outfit_groups(ranked_outfits)
    request["context"] = context


def _rank_context_items(items: list[dict[str, Any]], message: str) -> list[dict[str, Any]]:
    terms = _context_terms(message)

    def score(item: dict[str, Any]) -> tuple[int, float, str]:
        text = _closet_item_search_text(item)
        overlap = sum(1 for term in terms if term and term in text)
        favorite = 3 if item.get("favorite") else 0
        usable = 2 if str(item.get("quality", {}).get("status") or "") in {"usable", "pass", "ok"} else 0
        quality = float(item.get("quality", {}).get("score") or 0)
        return (overlap + favorite + usable, quality, str(item.get("updated_at") or ""))

    return sorted([item for item in items if isinstance(item, dict) and not item.get("deleted")], key=score, reverse=True)


def _balanced_context_items(items: list[dict[str, Any]], limit: int, per_slot: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    slot_counts: dict[str, int] = {}
    for item in items:
        item_id = str(item.get("item_id") or "")
        slot = _closet_item_group_key(item)
        if item_id in selected_ids or slot_counts.get(slot, 0) >= per_slot:
            continue
        selected.append(item)
        selected_ids.add(item_id)
        slot_counts[slot] = slot_counts.get(slot, 0) + 1
        if len(selected) >= limit:
            return selected
    for item in items:
        item_id = str(item.get("item_id") or "")
        if item_id in selected_ids:
            continue
        selected.append(item)
        selected_ids.add(item_id)
        if len(selected) >= limit:
            break
    return selected


def _closet_item_group_key(item: dict[str, Any]) -> str:
    return str(item.get("slot") or item.get("category") or item.get("subcategory") or "other").strip() or "other"


def _closet_item_groups(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        key = _closet_item_group_key(item)
        groups.setdefault(key, [])
        if len(groups[key]) >= CONTEXT_ITEMS_PER_SLOT:
            continue
        groups[key].append(_summarize_closet_group_item(item))
    return groups


def _closet_outfit_groups(outfits: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for outfit in outfits:
        scene_tags = [str(tag) for tag in outfit.get("scene_tags") or [] if str(tag).strip()] or ["通用"]
        summary = _summarize_closet_group_outfit(outfit)
        for tag in scene_tags[:4]:
            groups.setdefault(tag, [])
            if len(groups[tag]) < CONTEXT_OUTFITS_PER_SCENE:
                groups[tag].append(summary)
    return groups


def _rank_context_outfits(outfits: list[dict[str, Any]], message: str) -> list[dict[str, Any]]:
    terms = _context_terms(message)

    def score(outfit: dict[str, Any]) -> tuple[int, int, str]:
        text = " ".join(
            str(value or "")
            for value in [
                outfit.get("title"),
                " ".join(str(tag) for tag in outfit.get("scene_tags") or []),
                " ".join(str(item.get("category_label") or "") for item in outfit.get("items") or [] if isinstance(item, dict)),
            ]
        )
        overlap = sum(1 for term in terms if term and term in text)
        favorite_count = int(outfit.get("favorite_count") or 0)
        return (overlap, favorite_count, str(outfit.get("updated_at") or ""))

    return sorted([outfit for outfit in outfits if isinstance(outfit, dict) and not outfit.get("deleted")], key=score, reverse=True)


def _context_terms(message: str) -> list[str]:
    text = str(message or "")
    terms = [term for term in re.split(r"[\s,，。:：；;、]+", text) if term]
    seeds = [
        "生日", "派对", "约会", "聚会", "演唱会", "音乐节", "通勤", "面试", "看展", "旅行", "婚礼",
        "显白", "显瘦", "出片", "温柔", "甜酷", "辣妹", "正式", "休闲", "雨", "小红书",
    ]
    terms.extend(seed for seed in seeds if seed in text)
    return list(dict.fromkeys(terms))


def _closet_item_search_text(item: dict[str, Any]) -> str:
    attributes = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
    values: list[str] = [
        str(item.get("item_id") or ""),
        str(item.get("category") or ""),
        str(item.get("category_label") or ""),
        str(item.get("subcategory") or ""),
        str(item.get("slot") or ""),
    ]
    for value in attributes.values():
        if isinstance(value, list):
            values.extend(str(next_value) for next_value in value)
        else:
            values.append(str(value or ""))
    return " ".join(values)


def _summarize_closet_item(item: dict[str, Any]) -> dict[str, Any]:
    attributes = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
    slot = item.get("slot") or item.get("category")
    subcategory = item.get("subcategory") or attributes.get("subcategory") or ""
    style_tags = attributes.get("style_tags") or []
    type_tags = [item.get("category"), slot, subcategory, *style_tags]
    return {
        "item_id": item.get("item_id"),
        "category": item.get("category"),
        "subcategory": subcategory,
        "slot": slot,
        "label": item.get("category_label"),
        "colors": attributes.get("colors") or [],
        "material": attributes.get("material") or [],
        "fit": attributes.get("fit") or "",
        "pattern": attributes.get("pattern") or "",
        "style_tags": style_tags,
        "type_tags": [str(tag) for tag in type_tags if tag],
        "favorite": bool(item.get("favorite")),
        "quality_status": (item.get("quality") or {}).get("status"),
        "preview_path": (item.get("assets") or {}).get("preview_path"),
    }


def _summarize_closet_group_item(item: dict[str, Any]) -> dict[str, Any]:
    summary = _summarize_closet_item(item)
    return {
        "item_id": summary["item_id"],
        "category": summary["category"],
        "subcategory": summary["subcategory"],
        "slot": summary["slot"],
        "label": summary["label"],
        "colors": summary["colors"][:4] if isinstance(summary["colors"], list) else [],
        "style_tags": summary["style_tags"][:6] if isinstance(summary["style_tags"], list) else [],
        "type_tags": summary["type_tags"][:8] if isinstance(summary["type_tags"], list) else [],
        "quality_status": summary["quality_status"],
    }


def _summarize_closet_outfit(outfit: dict[str, Any]) -> dict[str, Any]:
    return {
        "outfit_id": outfit.get("outfit_id"),
        "title": outfit.get("title"),
        "scene_tags": outfit.get("scene_tags") or [],
        "favorite_count": outfit.get("favorite_count") or 0,
        "item_ids": outfit.get("item_ids") or [],
        "items": [
            {
                "item_id": item.get("item_id"),
                "category": item.get("category"),
                "label": item.get("category_label"),
            }
            for item in (outfit.get("items") or [])[:6]
            if isinstance(item, dict)
        ],
        "cover_path": outfit.get("layout_snapshot_path") or outfit.get("cover_path"),
    }


def _summarize_closet_group_outfit(outfit: dict[str, Any]) -> dict[str, Any]:
    return {
        "outfit_id": outfit.get("outfit_id"),
        "title": outfit.get("title"),
        "scene_tags": outfit.get("scene_tags") or [],
        "favorite_count": outfit.get("favorite_count") or 0,
        "item_ids": outfit.get("item_ids") or [],
    }


async def _post_openclaw_http(chat_url: str, request: dict[str, Any]) -> tuple[dict[str, Any], int]:
    started_at = time.perf_counter()
    context = request.get("context") if isinstance(request.get("context"), dict) else {}
    LOGGER.info(
        "openclaw_http_start session=%s url=%s timeout=%ss xhs_notes=%s",
        request.get("session_id"),
        chat_url,
        _openclaw_timeout_for_request(request),
        len(context.get("xhs_notes", [])) if isinstance(context.get("xhs_notes"), list) else 0,
    )
    async with httpx.AsyncClient(timeout=_openclaw_timeout_for_request(request)) as client:
        try:
            response = await client.post(chat_url, json=request)
        except httpx.HTTPError as exc:
            LOGGER.warning(
                "openclaw_http_error session=%s error_type=%s elapsed=%.2fs",
                request.get("session_id"),
                exc.__class__.__name__,
                time.perf_counter() - started_at,
            )
            if isinstance(exc, httpx.TimeoutException):
                return _failed(
                    "agent_timeout",
                    "AI 穿搭师生成时间过长，请稍后重试。",
                    504,
                    evidence={"transport": "http", "error_type": exc.__class__.__name__, "error": str(exc)},
                )
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
        LOGGER.warning(
            "openclaw_http_failed session=%s http_status=%s code=%s elapsed=%.2fs",
            request.get("session_id"),
            response.status_code,
            code,
            time.perf_counter() - started_at,
        )
        return _failed(code, _runtime_error_message(code), _status_for_error_code(code), evidence={"transport": "http", "response": data})
    result = _normalize_agent_result(data, "openclaw_http", request)
    LOGGER.info(
        "openclaw_http_done session=%s result_status=%s elapsed=%.2fs",
        request.get("session_id"),
        result.get("status"),
        time.perf_counter() - started_at,
    )
    return result, _status_for_error_code(result.get("error", {}).get("code", "")) if result.get("status") == "failed" else 200


def _openclaw_timeout_for_request(request: dict[str, Any]) -> float:
    context = request.get("context") if isinstance(request.get("context"), dict) else {}
    if context.get("source") == "inspiration_tab":
        return float(os.environ.get("STYLIST_INSPIRATION_OPENCLAW_TIMEOUT", "240"))
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
        friendly_message = _friendly_stylist_error_message(str(data["error"].get("code") or ""))
        result = {
            "status": "failed",
            "mode": "error",
            "assistant_message": friendly_message,
            "error": {
                **data["error"],
                "message": friendly_message,
                "technical_message": str(data["error"].get("message") or ""),
            },
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
    result["assistant_message"] = _sanitize_assistant_message(result.get("assistant_message") or "")
    _merge_xhs_artifacts(result, request)
    result["quality_checks"] = _stylist_quality_checks(result, request)
    result["runtime"] = {"transport": transport, "agent_id": os.environ.get("STYLIST_OPENCLAW_AGENT_ID", STYLIST_AGENT_ID)}
    return result


def _should_use_light_closet_ai(request: dict[str, Any]) -> bool:
    if not _env_flag("SELFIT_ENABLE_LIGHT_CLOSET_AI"):
        return False
    context = request.get("context") if isinstance(request.get("context"), dict) else {}
    if not context.get("closet_only"):
        return False
    model_ref = _stylist_model_ref()
    provider = _stylist_model_provider(model_ref)
    if provider not in {"minimax", "minimax-portal", "minimax-cn", "minimax-portal-cn"}:
        return False
    return bool(_minimax_stylist_key(provider))


async def _run_light_closet_ai(request: dict[str, Any]) -> dict[str, Any] | None:
    context = request.get("context") if isinstance(request.get("context"), dict) else {}
    provider = _stylist_model_provider(_stylist_model_ref())
    key = _minimax_stylist_key(provider)
    if not key:
        return None
    endpoint = _minimax_anthropic_messages_url(provider)
    prompt = _light_closet_ai_prompt(request)
    payload = {
        "model": _minimax_model_id(_stylist_model_ref()),
        "max_tokens": int(os.environ.get("SELFIT_LIGHT_CLOSET_MAX_TOKENS", "900")),
        "system": (
            "你是 selfit 的轻量衣橱穿搭师。只根据用户衣橱证据回答。"
            "不要使用小红书、外部趋势或不存在的单品。只输出合法 JSON。"
        ),
        "messages": [{"role": "user", "content": prompt}],
    }
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01",
    }
    try:
        async with httpx.AsyncClient(timeout=float(os.environ.get("SELFIT_LIGHT_CLOSET_TIMEOUT", "18"))) as client:
            response = await client.post(endpoint, json=payload, headers=headers)
            if response.status_code >= 400:
                return None
            data = response.json()
    except (httpx.HTTPError, ValueError):
        return None
    text = _anthropic_message_text(data)
    parsed = _parse_json_object(text)
    if not parsed:
        parsed = {
            "status": "ok",
            "mode": "light_closet_ai",
            "assistant_message": text,
            "recommended_items": [],
            "recommended_outfits": [],
            "rationale": [],
            "evidence_sources": [],
            "next_actions": [],
        }
    parsed.setdefault("status", "ok")
    parsed.setdefault("mode", "light_closet_ai")
    result = _normalize_agent_result(parsed, "light_closet_ai", request)
    result["mode"] = "light_closet_ai"
    return result


def _light_closet_ai_prompt(request: dict[str, Any]) -> str:
    context = request.get("context") if isinstance(request.get("context"), dict) else {}
    data = {
        "user_message": request.get("message") or "",
        "closet_items": context.get("closet_items", [])[:16] if isinstance(context.get("closet_items"), list) else [],
        "closet_outfits": context.get("closet_outfits", [])[:6] if isinstance(context.get("closet_outfits"), list) else [],
        "closet_item_groups": _trim_context_groups(context.get("closet_item_groups"), 6, 2),
        "closet_outfit_groups": _trim_context_groups(context.get("closet_outfit_groups"), 5, 2),
        "style_persona": _request_style_persona(request),
    }
    return (
        "根据以下衣橱数据回答用户。要求：\n"
        "1. assistant_message 用中文，最多 5 个短要点，给 1 套首选和最多 1 套备选。\n"
        "2. assistant_message 不要出现 item_id/outfit_id/raw id/JSON/字段名。\n"
        "3. recommended_items/recommended_outfits 可以填写真实 id；没有真实证据就留空。\n"
        "4. 如果 style_persona 存在，必须根据其关键词、推荐色和穿搭原则选择证据，不能只取列表前几件。\n"
        "5. 不要提小红书或外部参考。\n"
        "6. 返回 JSON：status, mode, assistant_message, recommended_items, recommended_outfits, rationale, evidence_sources, next_actions, quality_checks。\n"
        f"衣橱上下文：{json.dumps(data, ensure_ascii=False)}"
    )


def _trim_context_groups(value: Any, group_limit: int, item_limit: int) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    groups: dict[str, Any] = {}
    for index, (key, group_value) in enumerate(value.items()):
        if index >= group_limit:
            break
        groups[str(key)] = group_value[:item_limit] if isinstance(group_value, list) else group_value
    return groups


def _trim_context_for_fast_style_answer(context: dict[str, Any]) -> None:
    if isinstance(context.get("closet_items"), list):
        context["closet_items"] = context["closet_items"][:CLOSET_ONLY_ITEM_LIMIT]
    if isinstance(context.get("closet_outfits"), list):
        context["closet_outfits"] = context["closet_outfits"][:CLOSET_ONLY_OUTFIT_LIMIT]
    context["closet_item_groups"] = _trim_context_groups(context.get("closet_item_groups"), 5, 2)
    context["closet_outfit_groups"] = _trim_context_groups(context.get("closet_outfit_groups"), 4, 2)


def _minimax_stylist_key(provider: str) -> str | None:
    if provider in {"minimax-portal", "minimax-portal-cn"}:
        return (os.environ.get("MINIMAX_OAUTH_TOKEN") or os.environ.get("MINIMAX_API_KEY") or "").strip() or None
    return (os.environ.get("MINIMAX_API_KEY") or os.environ.get("MINIMAX_OAUTH_TOKEN") or "").strip() or None


def _minimax_anthropic_messages_url(provider: str) -> str:
    host = "https://api.minimax.io" if provider in {"minimax", "minimax-cn"} else "https://api.minimaxi.com"
    return os.environ.get("SELFIT_LIGHT_CLOSET_MODEL_URL", f"{host}/anthropic/v1/messages")


def _minimax_model_id(model_ref: str) -> str:
    return (model_ref.rsplit("/", 1)[-1] if model_ref else "MiniMax-M3").strip() or "MiniMax-M3"


def _anthropic_message_text(data: dict[str, Any]) -> str:
    content = data.get("content") if isinstance(data, dict) else None
    if not isinstance(content, list):
        return ""
    parts = [str(item.get("text") or "") for item in content if isinstance(item, dict) and item.get("type") == "text"]
    return "\n".join(part for part in parts if part).strip()


def _sanitize_assistant_message(text: str) -> str:
    value = str(text or "")
    value = re.sub(r"\s*[（(]\s*(?:w|item|outfit)_[A-Za-z0-9_:-]+(?:\s*[,，、][^）)]{0,18})?\s*[）)]", "", value)
    value = re.sub(r"\b(?:w|item|outfit)_[A-Za-z0-9_:-]+\b", "这套已保存搭配", value)
    value = re.sub(r"[ \t]{2,}", " ", value)
    return value.strip()


async def _attach_xhs_inspiration(request: dict[str, Any]) -> None:
    context = request.get("context") if isinstance(request.get("context"), dict) else {}
    should_invoke = _should_invoke_xhs_skill(request)
    if context.get("source") != "inspiration_tab" or not should_invoke:
        LOGGER.info(
            "xhs_skip session=%s source=%s should_invoke=%s",
            request.get("session_id"),
            context.get("source"),
            should_invoke,
        )
        return
    started_at = time.perf_counter()
    message = _effective_user_message(request)
    LOGGER.info("xhs_start session=%s message=%s", request.get("session_id"), message[:120])
    try:
        artifacts = await asyncio.wait_for(_fetch_xhs_inspiration(message), timeout=float(os.environ.get("SELFIT_XHS_TOTAL_TIMEOUT", "10")))
    except asyncio.TimeoutError:
        query = _xhs_query_from_message(message)
        artifacts = {
            "query": query,
            "notes": [],
            "tool_steps": [
                _xhs_tool_step("xhs", "找小红书参考", "failed", "小红书推荐暂时超时"),
                _xhs_tool_step("read", "读取参考卡片", "failed", "这次没有拿到可用笔记卡片"),
                _xhs_tool_step("filter", "过滤不相关内容", "failed", "没有可筛选的笔记"),
                _xhs_tool_step("agent", "交给 AI 穿搭师", "pending", "由 AI 根据当前问题和已有上下文回答"),
            ],
            "evidence_sources": [],
            "unavailable_reason": "xhs_timeout",
            "unavailable_detail": "小红书检索超时，暂时没有拿到可用笔记卡片",
        }
        LOGGER.warning(
            "xhs_timeout session=%s query=%s elapsed=%.2fs",
            request.get("session_id"),
            query,
            time.perf_counter() - started_at,
        )
    notes = artifacts.get("notes") if isinstance(artifacts.get("notes"), list) else []
    aligned_notes = _scene_aligned_xhs_notes(notes, message) if notes else []
    context["xhs_query"] = artifacts["query"]
    context["xhs_notes"] = aligned_notes
    context["xhs_tool_steps"] = artifacts["tool_steps"]
    context["xhs_evidence_sources"] = (
        [{"type": "xiaohongshu", "label": artifacts["evidence_sources"][0]["label"], "count": len(aligned_notes)}]
        if aligned_notes and isinstance(artifacts.get("evidence_sources"), list) and artifacts["evidence_sources"]
        else []
    )
    context["xhs_unavailable_reason"] = artifacts.get("unavailable_reason")
    context["xhs_unavailable_detail"] = artifacts.get("unavailable_detail")
    if not aligned_notes:
        _trim_context_for_fast_style_answer(context)
    request["context"] = context
    LOGGER.info(
        "xhs_done session=%s query=%s notes=%s aligned_notes=%s reason=%s elapsed=%.2fs",
        request.get("session_id"),
        artifacts.get("query"),
        len(notes),
        len(aligned_notes),
        artifacts.get("unavailable_reason"),
        time.perf_counter() - started_at,
    )


async def _fetch_xhs_inspiration(message: str) -> dict[str, Any]:
    plan = await _xhs_search_plan(message)
    query = plan["queries"][0]
    strategy = _xhs_search_strategy_summary(message, plan)
    steps = [
        _xhs_tool_step("xhs", "找小红书参考", "running", f"{strategy}；首轮关键词：{query}"),
        _xhs_tool_step("read", "读取参考卡片", "pending", "提取标题、封面、作者和互动数"),
        _xhs_tool_step("filter", "过滤不相关内容", "pending", "多轮检索后只保留和场景高度相关的穿搭笔记"),
        _xhs_tool_step("agent", "交给 AI 穿搭师", "pending", "把参考信号交给 AI 生成回答"),
    ]
    base_url = _xhs_api_base_url()
    if not base_url:
        steps[0] = _xhs_tool_step("xhs", "找小红书参考", "failed", f"{strategy}；小红书 API 还没有配置")
        return {
            "query": query,
            "notes": [],
            "tool_steps": steps,
            "evidence_sources": [],
            "unavailable_reason": "xhs_api_not_configured",
            "unavailable_detail": "小红书 API 还没有配置",
        }

    timeout = httpx.Timeout(float(os.environ.get("SELFIT_XHS_TIMEOUT", "9")))
    search_timeout = float(os.environ.get("SELFIT_XHS_SEARCH_TIMEOUT", "6"))
    async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client:
        login_status: dict[str, Any] | None = None
        try:
            login_response = await client.get("/api/v1/login/status", timeout=float(os.environ.get("SELFIT_XHS_LOGIN_TIMEOUT", "4")))
            login_status = login_response.json() if login_response.headers.get("content-type", "").startswith("application/json") else None
        except (httpx.HTTPError, ValueError):
            login_status = None
        login_data = login_status.get("data") if isinstance(login_status, dict) else None
        if isinstance(login_data, dict) and login_data.get("is_logged_in") is False:
            unavailable_detail = _xhs_unavailable_detail(login_status, "小红书侧边服务未登录，请先扫码登录后重试")
            steps[0] = _xhs_tool_step("xhs", "找小红书参考", "failed", f"{strategy}；{unavailable_detail}")
            steps[1] = _xhs_tool_step("read", "读取参考卡片", "failed", "账号态未登录，没有读取参考卡片")
            steps[2] = _xhs_tool_step("filter", "过滤不相关内容", "failed", "没有可筛选的笔记")
            steps[3] = _xhs_tool_step("agent", "交给 AI 穿搭师", "pending", "由 AI 根据当前问题和已有上下文回答")
            artifacts = {
                "query": query,
                "notes": [],
                "tool_steps": steps,
                "evidence_sources": [],
                "unavailable_reason": "xhs_login_required",
                "unavailable_detail": unavailable_detail,
            }
            return await _attach_public_xhs_fallback(message, artifacts)
        notes, search_meta, search_error = await _search_xhs_notes_until_enough(client, message, search_timeout, plan)
        if notes:
            detail_timeout = float(os.environ.get("SELFIT_XHS_DETAIL_TOTAL_TIMEOUT", "3"))
            detail_timed_out = False
            try:
                notes = await asyncio.wait_for(_enrich_xhs_notes_with_details(client, notes), timeout=detail_timeout)
            except asyncio.TimeoutError:
                detail_timed_out = True
        source_label = "小红书搜索"
        if search_error and not search_meta:
            unavailable_detail = _xhs_unavailable_detail(login_status, search_error or "推荐/搜索请求失败")
            steps[0] = _xhs_tool_step("xhs", "找小红书参考", "failed", f"{strategy}；{unavailable_detail}")
            steps[1] = _xhs_tool_step("read", "读取参考卡片", "failed", "搜索未完成，没有读取到可靠笔记")
            steps[2] = _xhs_tool_step("filter", "过滤不相关内容", "failed", "搜索未完成，无法筛选可靠笔记")
            steps[3] = _xhs_tool_step("agent", "交给 AI 穿搭师", "pending", "由 AI 根据当前问题和已有上下文回答")
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
        steps[0] = _xhs_tool_step("xhs", "找小红书参考", "failed", _xhs_search_step_detail(message, search_meta, plan) if search_meta else f"{strategy}；{unavailable_detail}")
        steps[1] = _xhs_tool_step("read", "读取参考卡片", "failed", "没有可展示的笔记卡片")
        steps[2] = _xhs_tool_step("filter", "过滤不相关内容", "failed", "多轮搜索结果不足，不把低相关笔记作为依据")
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
        _xhs_tool_step("xhs", "找小红书参考", "done", _xhs_search_step_detail(message, search_meta, plan)),
        _xhs_tool_step("read", "读取参考卡片", "done", "已提取封面、标题、作者和互动数据；正文详情较慢时不阻塞推荐" if locals().get("detail_timed_out") else "已提取封面、标题、作者和互动数据"),
        _xhs_tool_step("filter", "过滤不相关内容", "done", _xhs_filter_step_detail(notes, message)),
        _xhs_tool_step("agent", "交给 AI 穿搭师", "done", "已作为 AI 回答上下文"),
    ]
    used_queries = [item["query"] for item in search_meta if item.get("accepted_count")]
    evidence = [{"type": "xiaohongshu", "label": f"{source_label}：{' / '.join(used_queries[:3]) or query}", "count": len(notes)}]
    return {"query": query, "queries": search_meta, "notes": notes, "tool_steps": steps, "evidence_sources": evidence, "unavailable_reason": None, "unavailable_detail": None}


async def _search_xhs_notes_until_enough(
    client: httpx.AsyncClient, message: str, search_timeout: float, plan: dict[str, Any] | None = None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str | None]:
    max_rounds = max(1, int(os.environ.get("SELFIT_XHS_SEARCH_ROUNDS", "2")))
    max_candidates = max(8, int(os.environ.get("SELFIT_XHS_MAX_CANDIDATES", "24")))
    search_plan = plan or _fallback_xhs_search_plan(message)
    queries = [str(query or "").strip() for query in search_plan.get("queries", []) if str(query or "").strip()][:max_rounds]
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
    if ranked:
        return ranked[:6], search_meta, None
    return [], search_meta, last_error


async def _attach_public_xhs_fallback(message: str, artifacts: dict[str, Any]) -> dict[str, Any]:
    if not _env_flag("SELFIT_XHS_ENABLE_PUBLIC_FALLBACK"):
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
    search_url = os.environ.get("SELFIT_XHS_PUBLIC_SEARCH_URL", "https://www.bing.com/search")
    timeout = float(os.environ.get("SELFIT_XHS_PUBLIC_SEARCH_TIMEOUT", "4"))
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
    if not _message_needs_conversation_context(current):
        return current
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
    return "；".join(user_turns[-2:]) or current


def _message_needs_conversation_context(message: str) -> bool:
    text = str(message or "").strip()
    if not text:
        return False
    explicit_followup_markers = ["继续", "刚才", "上一", "前面", "这个", "那", "它", "这套", "那套", "还有", "另外"]
    if any(marker in text for marker in explicit_followup_markers):
        return True
    if _message_has_primary_scene(text):
        return False
    followup_markers = [
        "如果", "换成", "调整", "改成", "还是", "下雨", "不想", "不要", "显瘦", "显白",
    ]
    if any(marker in text for marker in followup_markers):
        return True
    return len(text) <= 12 and any(token in text for token in ["呢", "吗", "怎么", "可以"])


def _message_has_primary_scene(message: str) -> bool:
    text = str(message or "")
    scenes = [
        "上班", "通勤", "面试", "客户", "汇报", "会议", "约会", "聚餐", "看展", "旅行", "上课", "校园",
        "生日", "派对", "演唱会", "音乐节", "婚礼", "宴会", "运动", "户外", "居家", "返校",
    ]
    return any(scene in text for scene in scenes)


def _should_invoke_xhs_skill(request: dict[str, Any]) -> bool:
    context = request.get("context") if isinstance(request.get("context"), dict) else {}
    requested = context.get("requested_skills") if isinstance(context.get("requested_skills"), list) else []
    message = str(request.get("message") or context.get("current_query") or "").strip()
    if _message_explicitly_disables_xhs(message):
        return False
    if "xhs-trend-research" in {str(skill) for skill in requested}:
        return True
    if context.get("xiaohongshu_preferred") is False:
        return False
    if _message_matches_xhs_intent(message):
        return True
    return False


def _message_explicitly_disables_xhs(message: str) -> bool:
    normalized = str(message or "").lower()
    return any(token in normalized for token in ["不用小红书", "不要小红书", "别用小红书", "不看小红书", "只看衣橱", "只用衣橱", "只用我的衣橱", "不要外部参考", "不用外部参考"])


def _message_matches_xhs_intent(message: str) -> bool:
    normalized = message.lower()
    xhs_terms = ["小红书", "红书", "xhs", "rednote", "笔记", "同款", "平替", "趋势", "流行", "博主", "种草", "参考", "灵感"]
    if any(token in normalized for token in xhs_terms):
        return True
    outfit_terms = [
        "穿", "搭", "上班", "通勤", "面试", "客户", "会议", "约会", "聚餐", "看展", "旅行", "上课", "校园",
        "生日", "派对", "party", "演唱会", "音乐节", "婚礼", "宴会", "运动", "户外", "居家",
        "鞋", "包", "帽", "裙", "裤", "衬衫", "针织", "西装", "外套", "配饰",
        "显瘦", "显白", "出片", "拍照", "ootd", "氛围感", "风格", "颜色", "身材", "体型",
        "雨", "冷", "热", "降温", "升温", "天气", "防水", "防滑",
    ]
    return any(token in normalized for token in outfit_terms)


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
    if any(token in cleaned for token in ["生日", "派对", "party", "Party"]):
        seeds.append("生日派对")
    if any(token in cleaned for token in ["婚礼", "宴会", "年会"]):
        seeds.append("宴会")
    if any(token in cleaned for token in ["演唱会", "音乐节", "live", "Live", "蹦迪"]):
        seeds.append("演唱会")
    if any(token in cleaned for token in ["拍照", "对镜", "挡脸", "场景拍"]):
        seeds.append("拍照")
    if "出片" in cleaned:
        seeds.append("出片")
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
    budget_match = re.search(r"(?:预算)?\s*(\d{2,5})\s*(?:以内|内|以下|元)?", cleaned)
    if "预算" in cleaned and budget_match:
        seeds.append(f"预算{budget_match.group(1)}")
    style_keywords = ["韩系", "法式", "日系", "美式", "松弛", "平替", "小个子", "梨形", "通勤风", "学院风", "甜辣", "辣妹", "摇滚"]
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
    if any(token in cleaned for token in ["生日", "派对", "party", "Party"]):
        seeds.append("生日派对")
    if any(token in cleaned for token in ["婚礼", "宴会", "年会"]):
        seeds.append("宴会")
    if any(token in cleaned for token in ["演唱会", "音乐节", "live", "Live", "蹦迪"]):
        seeds.append("演唱会")
    if any(token in cleaned for token in ["拍照", "对镜", "挡脸", "场景拍"]):
        seeds.append("拍照")
    if "出片" in cleaned:
        seeds.append("出片")
    budget_match = re.search(r"(?:预算)?\s*(\d{2,5})\s*(?:以内|内|以下|元)?", cleaned)
    if "预算" in cleaned and budget_match:
        seeds.append(f"预算{budget_match.group(1)}")
    if any(token in cleaned for token in ["雨", "下雨", "小雨"]):
        seeds.append("雨天")
    if len(seeds) == 1:
        seeds.extend(["通勤", "ootd"])
    return " ".join(dict.fromkeys(seeds))


def _xhs_query_candidates(message: str) -> list[str]:
    return [str(query) for query in _fallback_xhs_search_plan(message)["queries"]]


async def _xhs_search_plan(message: str) -> dict[str, Any]:
    fallback = _fallback_xhs_search_plan(message)
    ai_plan = await _ai_xhs_search_plan(message)
    if not ai_plan:
        return fallback
    queries = _sanitize_xhs_queries(ai_plan.get("queries"), fallback["queries"], message)
    if not queries:
        return fallback
    plan = {**fallback, **{key: value for key, value in ai_plan.items() if value not in (None, "", [])}}
    plan["queries"] = queries
    plan["planner"] = "ai"
    return plan


async def _ai_xhs_search_plan(message: str) -> dict[str, Any] | None:
    if _env_flag("SELFIT_XHS_DISABLE_AI_PLANNER"):
        return None
    base_url = _openai_compatible_base_url()
    api_key = _openai_compatible_api_key(base_url)
    if not base_url or not api_key:
        return None
    prompt = (
        "你是小红书穿搭搜索规划器。只返回 JSON，不要解释。\n"
        "目标：根据当前用户问题和必要的历史上下文，决定是否需要小红书检索，并生成 0-4 条完整、具体、互补的中文搜索词。\n"
        "规则：\n"
        "1. 搜索词必须围绕最后一轮用户真实需求；如果最后一轮是追问，才合并历史场景。\n"
        "2. 不要把 query 拆成孤立关键词分别搜索；每条 query 都要能独立表达场景、目标和关键约束。\n"
        "3. 保留预算、天气、出片、显白、显瘦、正式度、地点、对象等约束。\n"
        "4. 如果问题不需要外部灵感，返回 {\"queries\": []}。\n"
        "JSON 字段：queries, intent, scenario, goals, constraints, negative_signals。\n"
        f"用户问题：{message}"
    )
    payload = {
        "model": os.environ.get("SELFIT_XHS_PLANNER_MODEL") or "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "你只输出合法 JSON。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 420,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=float(os.environ.get("SELFIT_XHS_AI_PLANNER_TIMEOUT", "5"))) as client:
            response = await client.post(f"{base_url.rstrip('/')}/chat/completions", json=payload, headers=headers)
            if response.status_code >= 400:
                return None
            data = response.json()
    except (httpx.HTTPError, ValueError):
        return None
    content = ""
    try:
        content = str(data["choices"][0]["message"]["content"] or "")
    except (KeyError, IndexError, TypeError):
        return None
    parsed = _parse_json_object(content)
    return parsed if isinstance(parsed, dict) else None


def _fallback_xhs_search_plan(message: str) -> dict[str, Any]:
    cleaned = _normalize_search_text(message)
    facets = _extract_xhs_search_facets(cleaned)
    base = _compact_xhs_search_query(cleaned)
    canonical = _xhs_query_from_message(cleaned)
    primary_parts = [base]
    if "穿搭" not in base and not any(token in base.lower() for token in ["ootd", "look"]):
        primary_parts.append("穿搭")
    primary = _clean_xhs_search_query(" ".join(primary_parts))
    scenario = " ".join(facets["scenario"][:2])
    goals = " ".join(facets["goals"][:3])
    constraints = " ".join(facets["constraints"][:3])
    styles = " ".join(facets["styles"][:2])
    candidates = [
        primary,
        canonical,
        _clean_xhs_search_query(" ".join(part for part in [scenario, goals, constraints, "穿搭"] if part)),
        _clean_xhs_search_query(" ".join(part for part in [scenario, styles, goals, "ootd 穿搭"] if part)),
        _xhs_broad_query_from_message(cleaned),
    ]
    queries = _sanitize_xhs_queries(candidates, [_xhs_query_from_message(cleaned)], cleaned)
    return {
        "planner": "fallback",
        "intent": "fashion_inspiration",
        "scenario": facets["scenario"],
        "goals": facets["goals"],
        "constraints": facets["constraints"],
        "styles": facets["styles"],
        "negative_signals": facets["negative_signals"],
        "queries": queries,
    }


def _normalize_search_text(message: str) -> str:
    text = " ".join(str(message or "").replace("\n", " ").split())
    text = re.sub(r"(帮我|请|推荐|建议|看看小红书上怎么说|看小红书上怎么说|小红书|红书|笔记参考|参考)", " ", text)
    text = _strip_negative_scene_phrases(text)
    return " ".join(text.split()).strip(" ：:，,。.?？")


def _strip_negative_scene_phrases(text: str) -> str:
    value = str(text or "")
    scene_words = "演唱会|音乐节|派对|生日|面试|通勤|约会|男装|男生|女装|女生|婚礼|宴会|旅行|看展"
    return re.sub(rf"(?:不要|不用|不看|不想|别用|别|不是|非)[\u4e00-\u9fffA-Za-z0-9]{{0,10}}(?:{scene_words})[\u4e00-\u9fffA-Za-z0-9]{{0,8}}", " ", value)


def _compact_xhs_search_query(text: str) -> str:
    cleaned = re.sub(r"(怎么穿|穿什么|怎么搭|如何搭|可以吗|是什么关系|关系是什么)", " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ：:，,。.?？")
    return cleaned[:42] or _xhs_query_from_message(text)


def _clean_xhs_search_query(query: str) -> str:
    value = " ".join(str(query or "").replace("：", " ").replace("，", " ").replace(",", " ").split())
    return value[:80]


def _sanitize_xhs_queries(raw_queries: Any, fallback: list[str], message: str = "") -> list[str]:
    values = raw_queries if isinstance(raw_queries, list) else []
    queries: list[str] = []
    for item in values:
        query = _clean_xhs_search_query(str(item or ""))
        if len(query) < 2:
            continue
        if _xhs_query_too_generic(query, message):
            continue
        if query not in queries:
            queries.append(query)
    if not queries:
        queries = [_clean_xhs_search_query(query) for query in fallback if _clean_xhs_search_query(query)]
    return _apply_xhs_gender_guard(list(dict.fromkeys(queries))[:4], message)


def _xhs_query_too_generic(query: str, message: str) -> bool:
    value = _clean_xhs_search_query(query).lower()
    generic = {"穿搭", "ootd", "ootd 穿搭", "女生穿搭", "女装穿搭", "穿搭 女生穿搭"}
    if value not in generic:
        return False
    return _message_has_primary_scene(message) or any(token in str(message or "") for token in ["显白", "显瘦", "出片", "预算"])


def _apply_xhs_gender_guard(queries: list[str], message: str) -> list[str]:
    profile = _xhs_gender_profile(message)
    guarded: list[str] = []
    for query in queries:
        value = _clean_xhs_search_query(query)
        if not value:
            continue
        if profile["target"] == "female" and not _contains_any(value.lower(), profile["female_tokens"]):
            value = _clean_xhs_search_query(f"{value} 女生穿搭")
        elif profile["target"] == "male" and not _contains_any(value.lower(), profile["male_tokens"]):
            value = _clean_xhs_search_query(f"{value} 男生穿搭")
        if value not in guarded:
            guarded.append(value)
    return guarded[:4]


def _extract_xhs_search_facets(text: str) -> dict[str, list[str]]:
    value = str(text or "")
    fashion_stop = {
        "穿搭",
        "搭配",
        "推荐",
        "帮我",
        "怎么穿",
        "怎么搭",
        "参考",
        "小红书",
        "红书",
        "笔记",
        "目前",
        "这个",
        "关系",
    }
    scenario: list[str] = []
    goals: list[str] = []
    constraints: list[str] = []
    styles: list[str] = []
    negative_signals: list[str] = []
    for match in re.finditer(r"预算\s*\d{2,5}\s*(?:以内|内|以下|元)?|\d{2,5}\s*(?:以内|内|以下|元)", value):
        constraints.append("".join(match.group(0).split()))
    for token in re.split(r"[\s：:，,。.!！?？、/]+", value):
        token = token.strip()
        if not token or token in fashion_stop:
            continue
        if len(token) > 14:
            for sub in re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,8}", token):
                if sub not in fashion_stop:
                    scenario.append(sub)
            continue
        if any(key in token for key in ["显白", "显瘦", "显高", "出片", "拍照", "氛围", "气质", "松弛", "稳", "年轻"]):
            goals.append(token)
        elif any(key in token for key in ["预算", "以内", "下雨", "小雨", "雨天", "防水", "不想", "不要", "低跟", "平底"]):
            constraints.append(token)
        elif any(key in token for key in ["韩系", "法式", "日系", "美式", "甜辣", "辣妹", "学院", "通勤风", "摇滚", "温柔"]):
            styles.append(token)
        elif any(key in token for key in ["宝宝", "喂养", "家常菜", "美甲", "卷发", "彩妆"]):
            negative_signals.append(token)
        else:
            scenario.append(token)
    return {
        "scenario": list(dict.fromkeys(scenario))[:4],
        "goals": list(dict.fromkeys(goals))[:4],
        "constraints": list(dict.fromkeys(constraints))[:4],
        "styles": list(dict.fromkeys(styles))[:4],
        "negative_signals": list(dict.fromkeys(negative_signals))[:4],
    }


def _openai_compatible_base_url() -> str | None:
    value = (
        os.environ.get("SELFIT_XHS_PLANNER_BASE_URL")
        or os.environ.get("STYLIST_OPENAI_BASE_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or os.environ.get("OPENAI_API_BASE")
        or os.environ.get("LOCAL_OPENAI_BASE_URL")
    )
    if value and value.strip():
        return value.rstrip("/")
    if os.environ.get("SELFIT_XHS_PLANNER_API_KEY") or os.environ.get("OPENAI_API_KEY"):
        return "https://api.openai.com/v1"
    return None


def _openai_compatible_api_key(base_url: str | None) -> str | None:
    key = os.environ.get("SELFIT_XHS_PLANNER_API_KEY") or os.environ.get("OPENAI_API_KEY") or os.environ.get("STYLIST_OPENCLAW_API_KEY")
    if key and key.strip():
        return key.strip()
    return "local-codex-proxy" if base_url else None


def _parse_json_object(text: str) -> dict[str, Any] | None:
    value = str(text or "").strip()
    if value.startswith("```"):
        value = value.strip("`").strip()
        if value.lower().startswith("json"):
            value = value[4:].strip()
    start = value.find("{")
    end = value.rfind("}")
    if start >= 0 and end > start:
        value = value[start : end + 1]
    try:
        parsed = json.loads(value)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _xhs_search_strategy_summary(message: str, plan: dict[str, Any] | None = None) -> str:
    search_plan = plan or _fallback_xhs_search_plan(message)
    profile = _xhs_relevance_profile(message)
    scenes = list(profile["scene_groups"].keys()) or [str(item) for item in search_plan.get("scenario", []) if str(item)]
    styles = [str(item) for item in [*profile["style_tokens"], *search_plan.get("goals", []), *search_plan.get("constraints", [])] if str(item)]
    parts: list[str] = []
    if scenes:
        parts.append(f"从问题中提取场景：{'、'.join(scenes[:3])}")
    if styles:
        parts.append(f"约束：{'、'.join(styles[:3])}")
    if not parts:
        parts.append("识别为泛穿搭灵感需求")
    if search_plan.get("planner") == "ai":
        parts.append("AI 已生成搜索计划")
    return "；".join(parts)


def _xhs_search_step_detail(message: str, search_meta: list[dict[str, Any]], plan: dict[str, Any] | None = None) -> str:
    strategy = _xhs_search_strategy_summary(message, plan)
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
    explicit = os.environ.get("SELFIT_XHS_API_URL") or os.environ.get("STYLIST_XHS_API_URL") or os.environ.get("STYLIST_XHS_SEARCH_URL")
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
    negative_keywords = ["宝宝", "喂养", "咖啡", "医生", "英语", "彩妆", "卷发", "美甲", "育儿", "睡衣"]
    if any(keyword in text for keyword in negative_keywords):
        return False
    return any(keyword in text for keyword in positive_keywords)


def _xhs_relevance_threshold(message: str) -> float:
    profile = _xhs_relevance_profile(message)
    return 2.3 if profile["scene_tokens"] else 1.2


def _rank_xhs_notes_for_answer(notes: list[dict[str, Any]], message: str) -> list[dict[str, Any]]:
    ranked = _scene_aligned_xhs_notes(notes, message)
    ranked.sort(key=lambda item: float(item.get("relevance_score") or 0), reverse=True)
    return ranked


def _xhs_has_enough_answer_evidence(notes: list[dict[str, Any]], message: str) -> bool:
    profile = _xhs_relevance_profile(message)
    if not notes:
        return False
    if not profile["scene_tokens"]:
        return len(notes) >= int(os.environ.get("SELFIT_XHS_MIN_GENERIC_NOTES", "3"))
    min_notes = int(os.environ.get("SELFIT_XHS_MIN_SCENE_NOTES", "4"))
    threshold = _xhs_relevance_threshold(message)
    scene_matched = [note for note in notes if _xhs_note_has_scene_evidence(note, profile)]
    scored_scene_notes = [note for note in scene_matched if float(note.get("relevance_score") or 0) >= threshold]
    return len(scored_scene_notes) >= min_notes


def _xhs_note_has_scene_evidence(note: dict[str, Any], profile: dict[str, Any]) -> bool:
    if not profile["scene_tokens"]:
        return True
    text = _xhs_note_text(note)
    return any(_contains_any(text, tokens) for tokens in profile["scene_groups"].values())


def _scene_aligned_xhs_notes(notes: list[dict[str, Any]], message: str) -> list[dict[str, Any]]:
    profile = _xhs_relevance_profile(message)
    threshold = _xhs_relevance_threshold(message)
    aligned: list[dict[str, Any]] = []
    for note in notes:
        if not isinstance(note, dict):
            continue
        score = float(note.get("relevance_score") or 0)
        if not score:
            score, reasons = _xhs_note_relevance(note, message)
            note = {**note, "relevance_score": score, "relevance_reasons": reasons}
        if score >= threshold and _xhs_note_has_scene_evidence(note, profile):
            aligned.append(note)
    return aligned


def _scene_relevant_note_titles(message: str, notes: list[dict[str, Any]]) -> list[str]:
    return [
        str(note.get("title") or "").strip()
        for note in _scene_aligned_xhs_notes(notes, message)
        if isinstance(note, dict) and str(note.get("title") or "").strip()
    ]


def _xhs_note_relevance(note: dict[str, Any], message: str) -> tuple[float, list[str]]:
    profile = _xhs_relevance_profile(message)
    text = _xhs_note_text(note)
    score = 0.0
    reasons: list[str] = []
    if _xhs_note_gender_conflicts(text, profile):
        score -= 4.0
        reasons.append("排除:性别不符")
    elif _contains_any(text, profile["gender_positive_tokens"]):
        score += 0.45
        reasons.append(profile["target_gender"])
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
    gender = _xhs_gender_profile(text)
    scene_groups: dict[str, list[str]] = {}
    if _contains_positive_scene(text, ["聚餐", "饭局", "约饭", "下班"]):
        scene_groups["聚餐"] = ["聚餐", "饭局", "约饭", "约会", "晚餐", "下班", "小酌", "约会"]
    if _contains_positive_scene(text, ["约会", "见面", "date"]):
        scene_groups["约会"] = ["约会", "date", "见面", "晚餐", "电影", "咖啡约"]
    interview_scene = _contains_positive_scene(text, ["面试", "offer", "求职"])
    if interview_scene:
        scene_groups["面试"] = ["面试", "面试穿搭", "求职", "offer", "职场", "正式", "得体", "西装", "衬衫"]
    elif _contains_positive_scene(text, ["上班", "通勤", "工作", "职场", "会议"]):
        scene_groups["通勤"] = ["通勤", "上班", "职场", "工作", "办公室", "会议", "面试", "班味"]
    if _contains_positive_scene(text, ["客户", "会面", "商务", "正式", "稳"]):
        scene_groups["客户会面"] = ["客户", "会面", "商务", "正式", "稳重", "得体", "职场", "会议", "通勤"]
    if _contains_positive_scene(text, ["看展", "展", "美术馆", "拍照"]):
        scene_groups["看展"] = ["看展", "展览", "美术馆", "博物馆", "拍照", "出片"]
    if _contains_positive_scene(text, ["生日", "派对", "party"]):
        scene_groups["派对"] = ["生日", "派对", "party", "聚会", "宴会"]
    if _contains_positive_scene(text, ["社团", "校园", "学生"]):
        scene_groups["校园"] = ["社团", "校园", "学生", "学院", "拍照"]
    if _contains_positive_scene(text, ["雨", "下雨", "小雨", "防水"]):
        scene_groups["雨天"] = ["雨天", "下雨", "小雨", "防水", "防滑", "雨靴"]
    if _contains_positive_scene(text, ["演唱会", "音乐节"]):
        scene_groups["演出"] = ["演唱会", "音乐节", "live", "出片", "蹦迪"]
    style_tokens = [
        token
        for token in ["显瘦", "显白", "松弛", "韩系", "法式", "日系", "甜辣", "预算", "平替", "小个子", "微胖", "梨形", "通勤感"]
        if token in text
    ]
    return {
        "target_gender": gender["target"],
        "gender_positive_tokens": gender["positive_tokens"],
        "gender_negative_tokens": gender["negative_tokens"],
        "fashion_tokens": ["穿搭", "搭配", "ootd", "look", "西装", "衬衫", "针织", "半裙", "裤", "裙", "牛仔", "外套", "乐福", "短靴", "鞋", "包"],
        "scene_groups": scene_groups,
        "scene_tokens": [token for tokens in scene_groups.values() for token in tokens],
        "style_tokens": style_tokens,
        "negative_tokens": [
            "宝宝", "喂养", "咖啡", "医生", "英语", "彩妆", "卷发", "美甲", "育儿", "睡衣", "家常菜", "旅行攻略",
            *(["演唱会", "音乐节", "派对", "party", "生日", "拍照", "出片", "ootd", "蹦迪"] if interview_scene else []),
        ],
    }


def _xhs_gender_profile(message: str) -> dict[str, Any]:
    text = str(message or "").lower()
    male_tokens = ["男生", "男士", "男装", "男款", "男性", "男模", "男友", "男朋友", "boyfriend", "menswear", "men's", "men "]
    female_tokens = ["女生", "女装", "女款", "女性", "女人", "女士", "姐妹", "小姐姐", "girl", "girls", "women", "women's", "女"]
    target = "male" if _contains_any(text, male_tokens) and not _contains_any(text, female_tokens) else "female"
    return {
        "target": target,
        "male_tokens": male_tokens,
        "female_tokens": female_tokens,
        "positive_tokens": male_tokens if target == "male" else female_tokens,
        "negative_tokens": female_tokens if target == "male" else male_tokens,
    }


def _contains_positive_scene(text: str, tokens: list[str]) -> bool:
    value = str(text or "").lower()
    for token in tokens:
        token_value = str(token or "").lower()
        if not token_value:
            continue
        start = 0
        while True:
            index = value.find(token_value, start)
            if index < 0:
                break
            prefix = value[max(0, index - 8):index]
            if not re.search(r"(不要|不用|不看|不想|别用|别|不是|非)\s*$", prefix):
                return True
            start = index + len(token_value)
    return False


def _xhs_note_gender_conflicts(text: str, profile: dict[str, Any]) -> bool:
    return _contains_any(text, profile.get("gender_negative_tokens") or profile.get("negative_tokens") or [])


def _xhs_note_text(note: dict[str, Any]) -> str:
    parts = [
        note.get("title"),
        note.get("author_name"),
        note.get("desc"),
        note.get("detail_summary"),
        note.get("detail_text"),
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
        "xsec_token": xsec_token,
    }


async def _enrich_xhs_notes_with_details(client: httpx.AsyncClient, notes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not notes or _env_flag("SELFIT_XHS_DISABLE_DETAIL_FETCH"):
        return notes
    limit = max(0, min(len(notes), int(os.environ.get("SELFIT_XHS_DETAIL_LIMIT", "1"))))
    if limit <= 0:
        return notes
    headers = await _xhs_mcp_session_headers(client)
    if not headers:
        return notes
    semaphore = asyncio.Semaphore(max(1, int(os.environ.get("SELFIT_XHS_DETAIL_CONCURRENCY", "2"))))

    async def enrich_one(note: dict[str, Any]) -> dict[str, Any]:
        async with semaphore:
            return await _enrich_xhs_note_with_detail(client, note, headers)

    detail_notes = await asyncio.gather(*(enrich_one(note) for note in notes[:limit]), return_exceptions=True)
    enriched: list[dict[str, Any]] = []
    for original, maybe_note in zip(notes[:limit], detail_notes):
        enriched.append(maybe_note if isinstance(maybe_note, dict) else original)
    enriched.extend(notes[limit:])
    return enriched


async def _xhs_mcp_session_headers(client: httpx.AsyncClient) -> dict[str, str] | None:
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "selfit-stylist", "version": "0.1"},
        },
    }
    try:
        response = await client.post("/mcp", json=payload, headers=headers, timeout=float(os.environ.get("SELFIT_XHS_MCP_INIT_TIMEOUT", "4")))
        session_id = response.headers.get("mcp-session-id") or response.headers.get("Mcp-Session-Id")
        if not session_id:
            return None
        session_headers = {**headers, "Mcp-Session-Id": session_id}
        await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
            headers=session_headers,
            timeout=float(os.environ.get("SELFIT_XHS_MCP_INIT_TIMEOUT", "4")),
        )
        return session_headers
    except (httpx.HTTPError, ValueError):
        return None


async def _enrich_xhs_note_with_detail(client: httpx.AsyncClient, note: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    feed_id = str(note.get("note_id") or "").strip()
    xsec_token = str(note.get("xsec_token") or "").strip()
    if not feed_id or not xsec_token:
        return note
    payload = {
        "jsonrpc": "2.0",
        "id": feed_id[:12],
        "method": "tools/call",
        "params": {
            "name": "get_feed_detail",
            "arguments": {"feed_id": feed_id, "xsec_token": xsec_token, "load_all_comments": False},
        },
    }
    try:
        response = await client.post("/mcp", json=payload, headers=headers, timeout=float(os.environ.get("SELFIT_XHS_DETAIL_TIMEOUT", "3")))
        data = response.json()
    except (httpx.HTTPError, ValueError):
        return note
    detail_note = _extract_xhs_detail_note(data)
    if not detail_note:
        return note
    enriched = dict(note)
    title = str(detail_note.get("title") or "").strip()
    desc = _clean_xhs_detail_text(detail_note.get("desc") or "")
    if title:
        enriched["title"] = title[:80]
    if desc:
        enriched["detail_text"] = desc[:900]
        enriched["desc"] = desc[:520]
        enriched["detail_summary"] = _xhs_note_detail_summary(desc)
    image_list = detail_note.get("imageList") if isinstance(detail_note.get("imageList"), list) else []
    image_urls = [_xhs_cover_url(item) for item in image_list if isinstance(item, dict)]
    image_urls = [url for url in image_urls if url]
    if image_urls:
        enriched["image_urls"] = [_xhs_image_proxy_url(url) for url in image_urls[:6]]
        enriched["cover_source_url"] = image_urls[0]
        enriched["cover_url"] = _xhs_image_proxy_url(image_urls[0])
    return enriched


def _extract_xhs_detail_note(data: Any) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None
    result = data.get("result") if isinstance(data.get("result"), dict) else {}
    content = result.get("content") if isinstance(result.get("content"), list) else []
    for item in content:
        if not isinstance(item, dict) or item.get("type") != "text":
            continue
        try:
            parsed = json.loads(str(item.get("text") or ""))
        except json.JSONDecodeError:
            continue
        payload = parsed.get("data") if isinstance(parsed, dict) else None
        note = payload.get("note") if isinstance(payload, dict) and isinstance(payload.get("note"), dict) else None
        if note:
            return note
    return None


def _clean_xhs_detail_text(value: Any) -> str:
    text = str(value or "")
    text = re.sub(r"#([^#\\[]+?)\\[话题\\]#", r"#\1", text)
    text = re.sub(r"@[\\w\\-\u4e00-\u9fff·&]+", "", text)
    text = re.sub(r"[\\t\\r]+", " ", text)
    return " ".join(line.strip() for line in text.splitlines() if line.strip())


def _xhs_note_detail_summary(desc: str) -> str:
    text = _clean_xhs_detail_text(desc)
    text = re.sub(r"#[^#\\s]+", "", text)
    return " ".join(text.split())[:180]


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
    persona = _request_style_persona(request)
    outfits = recommend_outfits({"persona": persona, "limit": 2, "rotate_by": 2}).get("outfits", [])
    all_items = list_closet_items().get("items", [])
    recommended_item_ids = [
        str(item.get("item_id") or "")
        for outfit in outfits
        for item in outfit.get("items", [])
        if item.get("item_id")
    ]
    ranked_items = []
    for item_id in [*recommended_item_ids, *(str(item.get("item_id") or "") for item in all_items)]:
        item = next((candidate for candidate in all_items if candidate.get("item_id") == item_id), None)
        if item and not any(existing.get("item_id") == item_id for existing in ranked_items):
            ranked_items.append(item)
    items = ranked_items[:6]
    persona_name = persona.get("metadata", {}).get("name") or "你的风格"
    return {
        "status": "ok",
        "mode": "demo",
        "assistant_message": f"我先按照{persona_name}的关键词和推荐色，从你当前衣橱里排了一版。",
        "recommended_items": items,
        "recommended_outfits": outfits,
        "rationale": [
            f"优先匹配{persona_name}的风格特征与推荐色。",
            "同时优先保留主服装、鞋包结构更完整的穿搭。",
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


def _request_style_persona(request: dict[str, Any]) -> dict[str, Any]:
    context = request.get("context") if isinstance(request.get("context"), dict) else {}
    profile = context.get("mock_profile") if isinstance(context.get("mock_profile"), dict) else {}
    raw = profile.get("style_persona") if isinstance(profile.get("style_persona"), dict) else {}
    colors = raw.get("colors") if isinstance(raw.get("colors"), list) else []
    return {
        "typeId": raw.get("type_id") or raw.get("typeId"),
        "metadata": {"name": raw.get("name"), "code": raw.get("code")},
        "keywords": raw.get("keywords") if isinstance(raw.get("keywords"), list) else [],
        "summary": raw.get("summary") or "",
        "colors": {"items": colors},
        "recommendations": raw.get("recommendations") if isinstance(raw.get("recommendations"), dict) else {},
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
            suggestion="请配置 STYLIST_OPENCLAW_MEMORY_URL，或启动 selfit-agent-runtime。",
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
    return _friendly_stylist_error_message(code)


def _friendly_stylist_error_message(code: str | None = None) -> str:
    if code == "agent_timeout":
        return "灵感加载有点慢，正在努力充能～"
    return STYLIST_FRIENDLY_ERROR_MESSAGE


def _status_for_error_code(code: str) -> int:
    return 503 if code in {"ai_unavailable", "agent_runtime_unavailable"} else 400


def _failed(code: str, message: str, status_code: int, suggestion: str | None = None, evidence: dict[str, Any] | None = None) -> tuple[dict[str, Any], int]:
    friendly_message = _friendly_stylist_error_message(code)
    return {
        "status": "failed",
        "mode": "error",
        "error": {
            "code": code,
            "message": friendly_message,
            "suggestion": friendly_message,
            "technical_message": message,
            "technical_suggestion": suggestion or message,
        },
        "assistant_message": friendly_message,
        "recommended_items": [],
        "recommended_outfits": [],
        "rationale": [],
        "evidence_sources": [],
        "next_actions": [],
        "evidence": evidence or {},
    }, status_code


def _openclaw_chat_url() -> str | None:
    value = os.environ.get("STYLIST_OPENCLAW_CHAT_URL") or os.environ.get("OPENCLAW_SELFIT_CHAT_URL")
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
    url = os.environ.get("SELFIT_XHS_MCP_URL") or os.environ.get("STYLIST_XHS_MCP_URL")
    mode = os.environ.get("SELFIT_XHS_MCP_MODE") or os.environ.get("STYLIST_XHS_MCP_MODE") or "streamable-http"
    raw_tools = os.environ.get("SELFIT_XHS_ALLOWED_TOOLS") or os.environ.get("STYLIST_XHS_ALLOWED_TOOLS") or ""
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
