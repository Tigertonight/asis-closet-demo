from __future__ import annotations

import asyncio
import io
import itertools
import json
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

import app.closet as closet
import app.auth as auth
import app.main as main_module
import app.storage as storage
import app.stylist as stylist
from app.main import app


_phone_counter = itertools.count(2000)


def _auth_client(phone: str | None = None) -> TestClient:
    phone = phone or f"+8613900{next(_phone_counter):06d}"
    client = TestClient(app)
    start = client.post("/auth/phone/start", json={"phone": phone}).json()
    token = client.post("/auth/phone/verify", json={"phone": phone, "code": start["dev_code"]}).json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def _png_bytes(image: Image.Image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, "PNG")
    return buf.getvalue()


def _synthetic_top_image() -> Image.Image:
    image = Image.new("RGB", (720, 900), "#fffafa")
    pixels = image.load()
    for y in range(170, 770):
        width = 210 + int((y - 170) * 0.14)
        left = 360 - width // 2
        right = 360 + width // 2
        for x in range(max(0, left), min(720, right)):
            pixels[x, y] = (220, 60, 105)
    return image


def _use_tmp_closet(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(storage, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(auth, "AUTH_DIR", tmp_path / "outputs" / "auth")
    monkeypatch.setattr(auth, "AUTH_STORE_PATH", tmp_path / "outputs" / "auth" / "auth_store.json")
    monkeypatch.setattr(closet, "CLOSET_OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(closet, "CLOSET_SOURCE_DIR", tmp_path / "sources")
    monkeypatch.setattr(closet, "CLOSET_ITEM_DIR", tmp_path / "items")
    monkeypatch.setattr(closet, "CLOSET_MANIFEST_PATH", tmp_path / "closet_manifest.json")
    monkeypatch.setattr(closet, "OUTFIT_DIR", tmp_path / "outfits")
    monkeypatch.setattr(closet, "OUTFIT_MANIFEST_PATH", tmp_path / "outfits_manifest.json")
    monkeypatch.setattr(closet, "TRYON_RECORD_DIR", tmp_path / "tryon_records")
    monkeypatch.setattr(closet, "TRYON_RECORDS_MANIFEST_PATH", tmp_path / "tryon_records_manifest.json")


def _clear_stylist_env(monkeypatch) -> None:
    for key in [
        "STYLIST_DEMO_MODE",
        "STYLIST_OPENCLAW_CHAT_URL",
        "OPENCLAW_SELFIT_CHAT_URL",
        "STYLIST_ENABLE_OPENCLAW_CLI",
        "STYLIST_OPENCLAW_MEMORY_URL",
        "STYLIST_OPENCLAW_MODEL",
        "SELFIT_XHS_MCP_URL",
        "SELFIT_XHS_API_URL",
        "SELFIT_XHS_MCP_MODE",
        "SELFIT_XHS_ALLOWED_TOOLS",
        "STYLIST_XHS_SEARCH_URL",
        "STYLIST_XHS_MCP_URL",
        "STYLIST_XHS_API_URL",
        "STYLIST_XHS_MCP_MODE",
        "STYLIST_XHS_ALLOWED_TOOLS",
        "SELFIT_ENABLE_LIGHT_CLOSET_AI",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
        "OPENROUTER_API_KEY",
        "DEEPSEEK_API_KEY",
        "DASHSCOPE_API_KEY",
        "MOONSHOT_API_KEY",
        "STYLIST_OPENCLAW_API_KEY",
        "MINIMAX_API_KEY",
        "MINIMAX_OAUTH_TOKEN",
    ]:
        monkeypatch.delenv(key, raising=False)


def test_stylist_chat_fails_closed_without_runtime(monkeypatch) -> None:
    _clear_stylist_env(monkeypatch)
    client = _auth_client()

    response = client.post("/stylist/chat", json={"message": "明天面试怎么穿"})

    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "failed"
    assert data["error"]["code"] == "agent_runtime_unavailable"
    assert data["recommended_outfits"] == []
    assert "我会这样搭" not in data["assistant_message"]
    assert data.get("mode") != "degraded_openclaw"


def test_stylist_inspiration_fails_closed_when_ai_key_missing(monkeypatch) -> None:
    _clear_stylist_env(monkeypatch)
    monkeypatch.setenv("STYLIST_OPENCLAW_CHAT_URL", "http://127.0.0.1:18789/api/selfit/chat")

    result, status = asyncio.run(
        stylist.run_stylist_chat(
            {
                "message": "生日派对怎么穿",
                "context": {"source": "inspiration_tab", "xiaohongshu_preferred": True},
            }
        )
    )

    assert status == 503
    assert result["status"] == "failed"
    assert result["error"]["code"] == "ai_unavailable"
    assert result.get("mode") != "degraded_openclaw"
    assert "我会这样搭" not in result["assistant_message"]
    assert "生日主角" not in result["assistant_message"]


def test_stylist_attaches_real_closet_context_for_agent(monkeypatch) -> None:
    monkeypatch.setattr(
        stylist,
        "list_closet_items",
        lambda category=None: {
            "items": [
                {
                    "item_id": "party_dress",
                    "category": "dress",
                    "category_label": "香槟色缎面连衣裙",
                    "slot": "dress",
                    "attributes": {"colors": ["香槟"], "material": ["satin"], "style_tags": ["生日", "派对", "温柔"]},
                    "quality": {"status": "usable", "score": 0.95},
                    "assets": {"preview_path": "/items/party_dress/preview.png"},
                }
            ]
        },
    )
    monkeypatch.setattr(
        stylist,
        "list_outfits",
        lambda: {
            "outfits": [
                {
                    "outfit_id": "birthday_outfit",
                    "title": "生日派对香槟裙",
                    "scene_tags": ["生日", "派对"],
                    "favorite_count": 12,
                    "item_ids": ["party_dress"],
                    "items": [{"item_id": "party_dress", "category": "dress", "category_label": "香槟色缎面连衣裙"}],
                    "layout_snapshot_path": "/outfits/birthday_outfit/flatlay.png",
                }
            ]
        },
    )
    request = {"message": "生日派对怎么穿", "context": {"source": "inspiration_tab"}}

    stylist._attach_closet_context(request)

    assert request["context"]["item_count"] == 1
    assert request["context"]["outfit_count"] == 1
    assert request["context"]["closet_items"][0]["item_id"] == "party_dress"
    assert request["context"]["closet_item_groups"]["dress"][0]["item_id"] == "party_dress"
    assert request["context"]["closet_outfits"][0]["outfit_id"] == "birthday_outfit"
    assert request["context"]["closet_outfit_groups"]["生日"][0]["outfit_id"] == "birthday_outfit"


def test_stylist_balances_closet_context_across_item_types(monkeypatch) -> None:
    crowded_tops = [
        {
            "item_id": f"top_{index}",
            "category": "top",
            "category_label": f"上衣 {index}",
            "slot": "top",
            "attributes": {"style_tags": ["通勤"]},
            "quality": {"status": "usable", "score": 0.9},
        }
        for index in range(20)
    ]
    other_items = [
        {
            "item_id": "black_skirt",
            "category": "skirt",
            "category_label": "黑色半裙",
            "slot": "skirt",
            "attributes": {"style_tags": ["通勤", "面试"]},
            "quality": {"status": "usable", "score": 0.9},
        },
        {
            "item_id": "loafers",
            "category": "shoes",
            "category_label": "黑色乐福鞋",
            "slot": "shoes",
            "attributes": {"style_tags": ["通勤", "面试"]},
            "quality": {"status": "usable", "score": 0.9},
        },
        {
            "item_id": "tote",
            "category": "bag",
            "category_label": "通勤托特包",
            "slot": "bag",
            "attributes": {"style_tags": ["通勤"]},
            "quality": {"status": "usable", "score": 0.9},
        },
    ]
    monkeypatch.setattr(stylist, "list_closet_items", lambda category=None: {"items": [*crowded_tops, *other_items]})
    monkeypatch.setattr(stylist, "list_outfits", lambda: {"outfits": []})
    request = {"message": "明天面试怎么穿", "context": {"source": "inspiration_tab"}}

    stylist._attach_closet_context(request)

    groups = request["context"]["closet_item_groups"]
    assert "top" in groups
    assert "skirt" in groups
    assert "shoes" in groups
    assert "bag" in groups
    assert len(groups["top"]) <= stylist.CONTEXT_ITEMS_PER_SLOT


def test_stylist_closet_only_context_is_smaller(monkeypatch) -> None:
    monkeypatch.setattr(
        stylist,
        "list_closet_items",
        lambda category=None: {
            "items": [
                {
                    "item_id": f"item_{index}",
                    "category": "top" if index < 30 else "shoes",
                    "category_label": f"单品 {index}",
                    "slot": "top" if index < 30 else "shoes",
                    "attributes": {"style_tags": ["通勤"]},
                    "quality": {"status": "usable", "score": 0.9},
                }
                for index in range(40)
            ]
        },
    )
    monkeypatch.setattr(stylist, "list_outfits", lambda: {"outfits": []})
    request = {"message": "只看我的衣橱，明天客户汇报怎么穿，不用小红书", "context": {"source": "inspiration_tab"}}

    stylist._attach_closet_context(request)

    assert request["context"]["closet_only"] is True
    assert len(request["context"]["closet_items"]) <= stylist.CLOSET_ONLY_ITEM_LIMIT


def test_stylist_sessions_crud_is_user_scoped(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    client_a = _auth_client("+8613900001001")
    client_b = _auth_client("+8613900001002")

    created = client_a.post("/stylist/sessions", json={"title": "周五聚餐"}).json()
    assert created["title"] == "周五聚餐"
    assert client_a.get("/stylist/sessions").json()["total"] == 1
    assert client_b.get("/stylist/sessions").json()["total"] == 0

    patched = client_a.patch(f"/stylist/sessions/{created['session_id']}", json={"title": "周五通勤聚餐"}).json()
    assert patched["title"] == "周五通勤聚餐"

    deleted = client_a.delete(f"/stylist/sessions/{created['session_id']}")
    assert deleted.status_code == 200
    assert client_a.get("/stylist/sessions").json()["total"] == 0
    assert client_a.get("/stylist/sessions?include_archived=true").json()["total"] == 1


def test_stylist_chat_persists_messages_per_session(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    _clear_stylist_env(monkeypatch)
    monkeypatch.setenv("STYLIST_DEMO_MODE", "1")
    client = _auth_client()
    session_a = client.post("/stylist/sessions", json={"title": "面试"}).json()
    session_b = client.post("/stylist/sessions", json={"title": "旅行"}).json()

    first = client.post("/stylist/chat", json={"session_id": session_a["session_id"], "message": "明天面试怎么穿"})
    second = client.post("/stylist/chat", json={"session_id": session_b["session_id"], "message": "海边旅行怎么穿"})

    assert first.status_code == 200
    assert second.status_code == 200
    detail_a = client.get(f"/stylist/sessions/{session_a['session_id']}").json()
    detail_b = client.get(f"/stylist/sessions/{session_b['session_id']}").json()
    listed = client.get("/stylist/sessions").json()["sessions"]
    listed_a = next(item for item in listed if item["session_id"] == session_a["session_id"])
    assert listed_a["metadata"]["unread_completion"] is True
    cleared = client.patch(f"/stylist/sessions/{session_a['session_id']}", json={"metadata": {"unread_completion": False}}).json()
    assert cleared["metadata"]["unread_completion"] is False
    assert [message["role"] for message in detail_a["messages"]] == ["user", "assistant"]
    assert "明天面试" in detail_a["messages"][0]["content"]
    assert "海边旅行" not in " ".join(message["content"] for message in detail_a["messages"])
    assert "海边旅行" in detail_b["messages"][0]["content"]


def test_stylist_chat_enriches_context_for_followup(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    _clear_stylist_env(monkeypatch)
    captured: list[dict] = []

    async def fake_chat(payload):
        captured.append(payload)
        return {
            "status": "ok",
            "mode": "test",
            "assistant_message": "可以走通勤转聚餐，先保留得体度。",
            "recommended_items": [],
            "recommended_outfits": [],
            "rationale": [],
            "evidence_sources": [],
            "next_actions": [],
        }, 200

    monkeypatch.setattr(main_module, "run_stylist_chat", fake_chat)
    client = _auth_client()
    session = client.post("/stylist/sessions", json={"title": "周五聚餐"}).json()

    first = client.post("/stylist/chat", json={"session_id": session["session_id"], "message": "周五上班接聚餐怎么穿？"})
    second = client.post("/stylist/chat", json={"session_id": session["session_id"], "message": "那如果下雨，不想穿高跟呢？"})

    assert first.status_code == 200
    assert second.status_code == 200
    context = captured[-1]["context"]
    assert context["current_query"] == "那如果下雨，不想穿高跟呢？"
    assert context["recent_user_queries"][-2:] == ["周五上班接聚餐怎么穿？", "那如果下雨，不想穿高跟呢？"]
    assert context["conversation_context"]["previous_query"] == "周五上班接聚餐怎么穿？"
    assert "通勤转聚餐" in context["conversation_context"]["previous_assistant_summary"]
    assert context["conversation_context"]["must_answer_current_query"] is True


def test_stylist_chat_legacy_session_id_still_works(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    _clear_stylist_env(monkeypatch)
    monkeypatch.setenv("STYLIST_DEMO_MODE", "1")
    client = _auth_client()

    response = client.post("/stylist/chat", json={"session_id": "selfit-inspiration", "message": "小雨通勤怎么穿"})

    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "selfit-inspiration"
    detail = client.get("/stylist/sessions/selfit-inspiration").json()
    assert detail["message_count"] == 2


def test_stylist_chat_internal_error_stays_json(monkeypatch) -> None:
    _clear_stylist_env(monkeypatch)

    async def broken_chat(payload):
        raise RuntimeError("boom")

    monkeypatch.setattr(main_module, "run_stylist_chat", broken_chat)
    client = _auth_client()

    response = client.post("/stylist/chat", json={"message": "周五上班接聚餐怎么穿？"})

    assert response.status_code == 500
    data = response.json()
    assert data["status"] == "failed"
    assert data["error"]["code"] == "stylist_internal_error"
    assert data["assistant_message"] == "暂时灵感耗尽，正在努力充能～"


def test_stylist_demo_mode_is_explicit(monkeypatch, tmp_path: Path) -> None:
    _clear_stylist_env(monkeypatch)
    monkeypatch.setenv("STYLIST_DEMO_MODE", "1")
    _use_tmp_closet(monkeypatch, tmp_path)
    client = _auth_client()
    client.post(
        "/closet/import/upload",
        files=[("images", ("top.png", _png_bytes(_synthetic_top_image()), "image/png"))],
    )

    response = client.post("/stylist/chat", json={"message": "旅行计划帮我搭一套"})

    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "demo"
    assert data["status"] == "ok"
    assert data["recommended_items"]


def test_stylist_demo_quality_checks_track_inspiration_context(monkeypatch, tmp_path: Path) -> None:
    _clear_stylist_env(monkeypatch)
    monkeypatch.setenv("STYLIST_DEMO_MODE", "1")
    _use_tmp_closet(monkeypatch, tmp_path)
    client = _auth_client()
    client.post(
        "/closet/import/upload",
        files=[("images", ("top.png", _png_bytes(_synthetic_top_image()), "image/png"))],
    )

    response = client.post(
        "/stylist/chat",
        json={
            "message": "延续刚才看展场景，下雨怎么调整？",
            "session_id": "selfit-inspiration",
            "context": {
                "source": "inspiration_tab",
                "xiaohongshu_preferred": True,
                "conversation": [
                    {"role": "user", "content": "周末看展怎么穿？"},
                    {"role": "assistant", "content": "可以走松弛通勤感。"},
                    {"role": "user", "content": "下雨怎么调整？"},
                ],
            },
        },
    )

    assert response.status_code == 200
    checks = response.json()["quality_checks"]
    assert checks["xiaohongshu_preferred"] is True
    assert checks["continued_conversation"] is True
    assert checks["used_xiaohongshu_recommendations"] is False


def test_stylist_normalizes_fenced_json_failure() -> None:
    result = stylist._normalize_agent_result(
        {
            "assistant_message": '```json\n{"status":"failed","error":{"code":"ai_unavailable","message":"AI 穿搭师暂时不可用，请检查模型配置。"}}\n```'
        },
        "openclaw_http",
        {"context": {"source": "inspiration_tab", "xiaohongshu_preferred": True, "conversation": []}},
    )

    assert result["status"] == "failed"
    assert result["error"]["code"] == "ai_unavailable"
    assert result["assistant_message"] == "暂时灵感耗尽，正在努力充能～"
    assert result["error"]["technical_message"] == "AI 穿搭师暂时不可用，请检查模型配置。"


def test_stylist_sanitizes_internal_ids_from_user_copy() -> None:
    result = stylist._normalize_agent_result(
        {
            "status": "ok",
            "assistant_message": "首选生日聚会珊瑚粉(w_outfit_date_04,你衣橱里已有保存)，也可以换 w_top_coral_blouse。",
        },
        "test",
        {"context": {}},
    )

    assert "w_outfit" not in result["assistant_message"]
    assert "w_top" not in result["assistant_message"]
    assert "生日聚会珊瑚粉" in result["assistant_message"]


def test_stylist_public_xhs_candidate_parser_filters_relevance() -> None:
    html = """
    <a href="https://www.xiaohongshu.com/explore/abc123?xsec_token=t">周五通勤下班聚餐穿搭</a>
    <a href="https://www.xiaohongshu.com/explore/baby123">宝宝喂养经验</a>
    """
    candidates = stylist._extract_public_xhs_candidates(html)
    notes = []
    for candidate in candidates:
        note = stylist._public_xhs_candidate_to_note(candidate, "site:xiaohongshu.com/explore 穿搭 聚餐 通勤")
        if note:
            score, reasons = stylist._xhs_note_relevance(note, "周五上班接聚餐：帮我推荐穿搭，要有小红书笔记参考")
            if stylist._is_xhs_fashion_note(note) and score >= stylist._xhs_relevance_threshold("周五上班接聚餐"):
                note["relevance_score"] = score
                note["relevance_reasons"] = reasons
                notes.append(note)

    assert [note["note_id"] for note in notes] == ["abc123"]
    assert notes[0]["source_label"] == "公开网页搜索"
    assert notes[0]["is_public_fallback"] is True


def test_stylist_normalizes_xhs_feed_card() -> None:
    note = stylist._normalize_xhs_feed(
        {
            "id": "abc123",
            "xsecToken": "token-value",
            "noteCard": {
                "displayTitle": "雨天通勤显瘦穿搭",
                "user": {"nickname": "搭配研究所", "avatar": "https://example.com/avatar.jpg"},
                "interactInfo": {"likedCount": "1200", "collectedCount": "88", "commentCount": "12"},
                "cover": {"urlDefault": "https://example.com/cover.jpg"},
            },
        },
        "雨天通勤",
        "小红书搜索",
    )

    assert note is not None
    assert note["note_id"] == "abc123"
    assert note["title"] == "雨天通勤显瘦穿搭"
    assert note["author_name"] == "搭配研究所"
    assert note["cover_url"] == "https://example.com/cover.jpg"
    assert note["liked_count"] == "1200"
    assert note["url"].startswith("https://www.xiaohongshu.com/explore/abc123")
    assert note["xsec_token"] == "token-value"


def test_stylist_extracts_xhs_detail_note_text() -> None:
    data = {
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "data": {
                                "note": {
                                    "title": "约会战袍穿搭",
                                    "desc": "温柔浪漫裙装，适合约会显白。#约会穿搭指南[话题]#",
                                    "imageList": [{"urlDefault": "https://example.com/detail.jpg"}],
                                }
                            }
                        },
                        ensure_ascii=False,
                    ),
                }
            ]
        }
    }

    note = stylist._extract_xhs_detail_note(data)

    assert note is not None
    assert note["title"] == "约会战袍穿搭"
    assert "约会显白" in stylist._clean_xhs_detail_text(note["desc"])


def test_stylist_scene_filter_preserves_xhs_note_body() -> None:
    notes = [
        {
            "note_id": "interview001",
            "title": "明天面试穿搭模板",
            "desc": "求职面试、职场汇报都适合的白衬衫和黑西裤。",
            "detail_summary": "面试穿搭要正式得体，白衬衫配黑西裤。",
            "detail_text": "求职面试当天建议白衬衫、黑西裤、低跟鞋，整体正式但不要老气。",
        },
        {
            "note_id": "concert001",
            "title": "演唱会出片穿搭",
            "desc": "演唱会拍照出片，亮色上衣和短裙。",
            "detail_summary": "演唱会要亮色、露肤和出片。",
            "detail_text": "适合演唱会现场的人群亮点搭配。",
        },
    ]

    aligned = stylist._scene_aligned_xhs_notes(notes, "明天面试应该穿什么")

    assert [note["note_id"] for note in aligned] == ["interview001"]
    assert "求职面试当天" in aligned[0]["detail_text"]
    assert "白衬衫配黑西裤" in aligned[0]["detail_summary"]


def test_stylist_proxies_xhs_cover_image() -> None:
    source_url = "http://sns-webpic-qc.xhscdn.com/path/to/cover!nc_n_webp_mw_1"
    note = stylist._normalize_xhs_feed(
        {
            "id": "abc123",
            "noteCard": {
                "displayTitle": "通勤穿搭",
                "cover": {"urlDefault": source_url},
            },
        }
    )

    assert note is not None
    assert note["cover_source_url"] == source_url
    assert note["cover_url"].startswith("/xhs-image?url=")
    assert "sns-webpic-qc.xhscdn.com" in note["cover_url"]


def test_stylist_skips_xhs_feed_without_cover() -> None:
    note = stylist._normalize_xhs_feed(
        {
            "id": "abc123",
            "noteCard": {
                "displayTitle": "通勤穿搭",
                "cover": {},
            },
        }
    )

    assert note is None


def test_stylist_filters_non_fashion_xhs_notes() -> None:
    notes = stylist._normalize_xhs_feeds(
        [
            {
                "id": "baby001",
                "noteCard": {
                    "displayTitle": "宝宝喂养看这里",
                    "cover": {"urlDefault": "https://example.com/baby.jpg"},
                },
            },
            {
                "id": "sleep001",
                "noteCard": {
                    "displayTitle": "迪士尼睡衣米奇晚安服务",
                    "cover": {"urlDefault": "https://example.com/sleep.jpg"},
                },
            },
            {
                "id": "look001",
                "noteCard": {
                    "displayTitle": "周五通勤接聚餐穿搭",
                    "cover": {"urlDefault": "https://example.com/look.jpg"},
                },
            },
        ],
        "周五通勤聚餐穿搭",
        "小红书搜索",
    )

    assert [note["note_id"] for note in notes] == ["look001"]


def test_stylist_filters_low_relevance_generic_fashion_notes() -> None:
    notes = stylist._normalize_xhs_feeds(
        [
            {
                "id": "generic001",
                "noteCard": {
                    "displayTitle": "美式甜辣正肩短袖穿搭",
                    "cover": {"urlDefault": "https://example.com/generic.jpg"},
                },
            },
            {
                "id": "commute001",
                "noteCard": {
                    "displayTitle": "周五通勤下班聚餐穿搭",
                    "cover": {"urlDefault": "https://example.com/commute.jpg"},
                },
            },
        ],
        "周五上班接聚餐穿搭",
        "小红书搜索",
        relevance_text="周五上班接聚餐：帮我推荐穿搭",
    )

    assert [note["note_id"] for note in notes] == ["commute001"]
    assert notes[0]["relevance_score"] >= 2.3


def test_stylist_requires_scene_evidence_for_customer_meeting() -> None:
    notes = stylist._normalize_xhs_feeds(
        [
            {
                "id": "couple001",
                "noteCard": {
                    "displayTitle": "交出你们两张最反差的ootd",
                    "cover": {"urlDefault": "https://example.com/couple.jpg"},
                },
            },
            {
                "id": "client001",
                "noteCard": {
                    "displayTitle": "客户会面要稳的职场通勤穿搭",
                    "cover": {"urlDefault": "https://example.com/client.jpg"},
                },
            },
            {
                "id": "business001",
                "noteCard": {
                    "displayTitle": "商务会议正式不老气穿搭",
                    "cover": {"urlDefault": "https://example.com/business.jpg"},
                },
            },
            {
                "id": "office001",
                "noteCard": {
                    "displayTitle": "职场会面得体通勤look",
                    "cover": {"urlDefault": "https://example.com/office.jpg"},
                },
            },
            {
                "id": "formal001",
                "noteCard": {
                    "displayTitle": "正式场合西装衬衫搭配",
                    "cover": {"urlDefault": "https://example.com/formal.jpg"},
                },
            },
        ],
        "客户会面 穿搭",
        "小红书搜索",
        relevance_text="客户会面要稳：帮我推荐穿搭",
        limit=12,
    )

    ranked = stylist._rank_xhs_notes_for_answer(notes, "客户会面要稳：帮我推荐穿搭")
    assert "couple001" not in [note["note_id"] for note in ranked]
    assert stylist._xhs_has_enough_answer_evidence(ranked, "客户会面要稳：帮我推荐穿搭") is True


def test_stylist_accepts_scene_matched_date_outfit_notes_without_exact_style_word() -> None:
    feeds = [
        {
            "id": "date001",
            "noteCard": {
                "displayTitle": "一般人不告诉你的约会战袍穿搭店铺",
                "cover": {"urlDefault": "https://example.com/date1.jpg"},
            },
        },
        {
            "id": "date002",
            "noteCard": {
                "displayTitle": "温柔浪漫约会裙子店铺",
                "cover": {"urlDefault": "https://example.com/date2.jpg"},
            },
        },
        {
            "id": "date003",
            "noteCard": {
                "displayTitle": "男生约会穿搭锐评",
                "cover": {"urlDefault": "https://example.com/date3.jpg"},
            },
        },
        {
            "id": "date004",
            "noteCard": {
                "displayTitle": "520约会穿搭求建议",
                "cover": {"urlDefault": "https://example.com/date4.jpg"},
            },
        },
        {
            "id": "date005",
            "noteCard": {
                "displayTitle": "女生约会显白氛围感穿搭",
                "cover": {"urlDefault": "https://example.com/date5.jpg"},
            },
        },
    ]
    notes = stylist._normalize_xhs_feeds(
        feeds,
        "约会 显白 穿搭",
        "小红书搜索",
        relevance_text="周末约会显白搭：帮我推荐穿搭",
        limit=12,
    )

    ranked = stylist._rank_xhs_notes_for_answer(notes, "周末约会显白搭：帮我推荐穿搭")
    assert [note["note_id"] for note in ranked] == ["date005", "date001", "date002", "date004"]
    assert stylist._xhs_has_enough_answer_evidence(ranked, "周末约会显白搭：帮我推荐穿搭") is True


def test_stylist_filters_menswear_cards_for_default_female_context() -> None:
    notes = stylist._normalize_xhs_feeds(
        [
            {
                "id": "mens001",
                "noteCard": {
                    "displayTitle": "男装通勤衬衫西裤穿搭",
                    "cover": {"urlDefault": "https://example.com/mens.jpg"},
                },
            },
            {
                "id": "women001",
                "noteCard": {
                    "displayTitle": "女生面试通勤衬衫西裤穿搭",
                    "cover": {"urlDefault": "https://example.com/women.jpg"},
                },
            },
        ],
        "面试 穿搭 女生穿搭",
        "小红书搜索",
        relevance_text="明天面试应该穿什么",
        limit=12,
    )

    assert [note["note_id"] for note in notes] == ["women001"]


def test_stylist_xhs_query_candidates_include_scene_specific_loops() -> None:
    queries = stylist._xhs_query_candidates("客户会面要稳：帮我推荐穿搭")

    assert any(query == "客户会面 穿搭 女生穿搭" for query in queries)
    assert any("客户会面" in query for query in queries)
    assert all("女生穿搭" in query for query in queries)
    assert all("通勤 ootd" not in query for query in queries)


def test_stylist_xhs_query_candidates_preserve_concert_budget_constraints() -> None:
    queries = stylist._xhs_query_candidates("演唱会出片穿搭，预算500以内")

    assert queries[0] == "演唱会出片穿搭 预算500以内 女生穿搭"
    assert "演唱会 出片 预算500 穿搭 女生穿搭" in queries
    assert any("演唱会" in query and "预算500" in query for query in queries)
    assert any("出片" in query for query in queries)
    assert all("女生穿搭" in query for query in queries)
    assert all("通勤 ootd" not in query for query in queries)


def test_stylist_negative_scene_phrases_do_not_become_positive_scene() -> None:
    profile = stylist._xhs_relevance_profile("明天面试应该穿什么，要女生通勤感，不要演唱会出片")
    queries = stylist._xhs_query_candidates("明天面试应该穿什么，要女生通勤感，不要演唱会出片")

    assert "面试" in profile["scene_groups"]
    assert "演出" not in profile["scene_groups"]
    assert all("演唱会" not in query and "出片" not in query for query in queries)


def test_stylist_returns_partial_ranked_xhs_notes_when_not_enough_for_full_threshold(monkeypatch) -> None:
    async def fake_get(*args, **kwargs):
        class Response:
            def json(self):
                return {
                    "data": {
                        "feeds": [
                            {
                                "id": "date_partial_1",
                                "noteCard": {
                                    "displayTitle": "女生约会显白温柔穿搭",
                                    "cover": {"urlDefault": "https://example.com/date.jpg"},
                                },
                            }
                        ]
                    }
                }

        return Response()

    class Client:
        async def get(self, *args, **kwargs):
            return await fake_get(*args, **kwargs)

    notes, meta, error = asyncio.run(
        stylist._search_xhs_notes_until_enough(
            Client(),
            "周末约会显白搭：帮我推荐穿搭",
            1,
            {"queries": ["约会 显白 穿搭 女生穿搭"]},
        )
    )

    assert error is None
    assert meta[0]["raw_count"] == 1
    assert [note["note_id"] for note in notes] == ["date_partial_1"]


def test_stylist_ai_search_plan_can_override_fallback_queries(monkeypatch) -> None:
    async def fake_ai_plan(message: str) -> dict:
        return {
            "queries": ["演唱会 预算500 出片穿搭", "音乐节 平价 出片穿搭"],
            "scenario": ["演唱会"],
            "goals": ["出片"],
            "constraints": ["预算500以内"],
        }

    monkeypatch.setattr(stylist, "_ai_xhs_search_plan", fake_ai_plan)

    plan = __import__("asyncio").run(stylist._xhs_search_plan("演唱会出片穿搭，预算500以内"))

    assert plan["planner"] == "ai"
    assert plan["queries"][:2] == ["演唱会 预算500 出片穿搭 女生穿搭", "音乐节 平价 出片穿搭 女生穿搭"]
    assert plan["constraints"] == ["预算500以内"]


def test_stylist_xhs_tool_steps_explain_search_strategy() -> None:
    meta = [
        {"query": "客户会面 穿搭", "raw_count": 8, "accepted_count": 2},
        {"query": "商务通勤 穿搭", "raw_count": 9, "accepted_count": 2},
        {"query": "职场正式 不老气 穿搭", "raw_count": 7, "accepted_count": 1},
    ]
    detail = stylist._xhs_search_step_detail("客户会面要稳：帮我推荐穿搭", meta)

    assert "从问题中提取场景：客户会面" in detail
    assert "客户会面 穿搭 / 商务通勤 穿搭" in detail
    assert "24 张候选卡片" in detail


def test_stylist_xhs_query_keeps_fashion_intent() -> None:
    query = stylist._xhs_query_from_message("周五上班接聚餐：帮我推荐穿搭，要有小红书笔记参考")

    assert "穿搭" in query
    assert "聚餐" in query
    assert "通勤" in query


def test_stylist_xhs_query_keeps_party_scene_and_rejects_generic_planner_terms() -> None:
    query = stylist._xhs_query_from_message("生日派对怎么穿：帮我参考小红书推荐一套")
    sanitized = stylist._sanitize_xhs_queries(["穿搭"], [query], "生日派对怎么穿：帮我参考小红书推荐一套")

    assert "生日派对" in query
    assert sanitized
    assert all(item != "穿搭 女生穿搭" for item in sanitized)
    assert any("生日派对" in item for item in sanitized)


def test_stylist_effective_message_uses_single_session_history() -> None:
    message = stylist._effective_user_message(
        {
            "message": "那下雨显瘦呢？",
            "context": {
                "conversation": [
                    {"role": "user", "content": "周五上班接聚餐：帮我推荐穿搭"},
                    {"role": "assistant", "content": "可以走通勤转聚餐。"},
                    {"role": "user", "content": "那下雨显瘦呢？"},
                ]
            },
        }
    )

    assert "周五上班接聚餐" in message
    assert "下雨显瘦" in message


def test_stylist_effective_message_does_not_mix_independent_scene_history() -> None:
    message = stylist._effective_user_message(
        {
            "message": "生日派对怎么穿：帮我参考小红书推荐一套",
            "context": {
                "conversation": [
                    {"role": "user", "content": "演唱会出片穿搭，预算500以内"},
                    {"role": "assistant", "content": "可以把亮点放在上半身。"},
                    {"role": "user", "content": "生日派对怎么穿：帮我参考小红书推荐一套"},
                ]
            },
        }
    )

    assert message == "生日派对怎么穿：帮我参考小红书推荐一套"
    assert "演唱会" not in message
    assert "预算500" not in message


def test_stylist_xhs_intent_uses_current_query_not_history() -> None:
    assert stylist._should_invoke_xhs_skill(
        {
            "message": "目前的这个和社团的关系是什么",
            "context": {
                "source": "inspiration_tab",
                "requested_skills": [],
                "conversation": [
                    {"role": "user", "content": "社团拍照 OOTD：帮我推荐穿搭"},
                    {"role": "assistant", "content": "可以走学院风。"},
                    {"role": "user", "content": "看看小红书上怎么说"},
                ],
            },
        }
    ) is False
    assert stylist._should_invoke_xhs_skill(
        {
            "message": "看看小红书上怎么说",
            "context": {
                "source": "inspiration_tab",
                "requested_skills": [],
                "conversation": [
                    {"role": "user", "content": "社团拍照 OOTD：帮我推荐穿搭"},
                    {"role": "assistant", "content": "可以走学院风。"},
                ],
            },
        }
    ) is True


def test_stylist_invokes_xhs_skill_only_on_intent() -> None:
    assert stylist._should_invoke_xhs_skill(
        {
            "message": "胶囊衣橱：帮我推荐穿搭",
            "context": {"source": "inspiration_tab", "xiaohongshu_preferred": False, "requested_skills": ["capsule-wardrobe"]},
        }
    ) is False
    assert stylist._should_invoke_xhs_skill(
        {
            "message": "只看衣橱，不用小红书，帮我用现有单品搭一套",
            "context": {"source": "inspiration_tab", "xiaohongshu_preferred": False, "requested_skills": ["capsule-wardrobe"]},
        }
    ) is False
    assert stylist._should_invoke_xhs_skill(
        {
            "message": "胶囊衣橱：帮我推荐穿搭，要有小红书笔记参考",
            "context": {"source": "inspiration_tab", "xiaohongshu_preferred": True, "requested_skills": ["capsule-wardrobe", "xhs-trend-research"]},
        }
    ) is True
    assert stylist._should_invoke_xhs_skill(
        {
            "message": "明天面试怎么穿，要正式但别太老气",
            "context": {"source": "inspiration_tab", "requested_skills": []},
        }
    ) is True
    assert stylist._should_invoke_xhs_skill(
        {
            "message": "雨天约会拍照想显瘦一点",
            "context": {"source": "inspiration_tab", "requested_skills": []},
        }
    ) is True
    assert stylist._should_invoke_xhs_skill(
        {
            "message": "周末约会显白搭：帮我推荐穿搭",
            "context": {"source": "inspiration_tab", "requested_skills": []},
        }
    ) is True
    assert stylist._should_invoke_xhs_skill(
        {
            "message": "帮我查一下今天几点了",
            "context": {"source": "inspiration_tab", "requested_skills": []},
        }
    ) is False


def test_stylist_removes_xhs_evidence_when_relevance_filter_empty() -> None:
    result = {
        "status": "ok",
        "assistant_message": "参考小红书后建议这样穿。",
        "evidence_sources": [{"type": "xiaohongshu", "label": "小红书搜索：通勤", "count": 3}, {"type": "closet", "label": "本地衣橱"}],
        "xhs_notes": [{"note_id": "bad"}],
    }
    request = {"context": {"source": "inspiration_tab", "xiaohongshu_preferred": True, "xhs_notes": [], "xhs_tool_steps": []}}

    stylist._merge_xhs_artifacts(result, request)

    assert "xhs_notes" not in result
    assert result["evidence_sources"] == [{"type": "closet", "label": "本地衣橱"}]


def test_openclaw_bridge_passes_xhs_note_body_to_model_context() -> None:
    bridge = Path(__file__).resolve().parents[1] / "selfit-agent-runtime" / "scripts" / "selfit-openclaw-bridge.mjs"
    text = bridge.read_text(encoding="utf-8")

    assert "detail_summary" in text
    assert "detail_text" in text
    assert "Use xhs_notes.detail_summary/detail_text as Xiaohongshu note body evidence" in text


def test_openclaw_bridge_passes_closet_context_to_model() -> None:
    bridge = Path(__file__).resolve().parents[1] / "selfit-agent-runtime" / "scripts" / "selfit-openclaw-bridge.mjs"
    text = bridge.read_text(encoding="utf-8")

    assert "closet_items" in text
    assert "closet_item_groups" in text
    assert "closet_outfits" in text
    assert "closet_outfit_groups" in text
    assert "Use saved outfits by their scene tags" not in text
    assert "Use closet_outfits by scene_tags first" in text
    assert "If no suitable closet_outfits or closet_items match" in text
    assert "Default target audience is women's styling" in text
    assert "do not mention internal field names" in text


def test_stylist_light_closet_ai_is_opt_in(monkeypatch) -> None:
    _clear_stylist_env(monkeypatch)
    monkeypatch.setenv("STYLIST_OPENCLAW_MODEL", "minimax/MiniMax-M3")
    monkeypatch.setenv("MINIMAX_API_KEY", "test-key")
    request = {"context": {"closet_only": True}}

    assert stylist._should_use_light_closet_ai(request) is False

    monkeypatch.setenv("SELFIT_ENABLE_LIGHT_CLOSET_AI", "1")
    assert stylist._should_use_light_closet_ai(request) is True


def test_stylist_default_female_profile_rejects_menswear_notes() -> None:
    profile = stylist._xhs_gender_profile("生日派对怎么穿")

    assert profile["target"] == "female"
    assert stylist._xhs_note_gender_conflicts("男装通勤穿搭 男生西装推荐", profile) is True


def test_stylist_agent_rules_default_to_womenswear() -> None:
    agent = Path(__file__).resolve().parents[1] / "selfit-agent-runtime" / "agents" / "selfit-stylist" / "agent.md"
    text = agent.read_text(encoding="utf-8")

    assert "Default to women's styling" in text
    assert "Do not use male/menswear Xiaohongshu notes" in text
    assert "If no suitable saved outfit or closet item matches" in text
    assert "still answer the latest user question" in text


def test_stylist_capabilities_exposes_decoupled_runtime(monkeypatch) -> None:
    _clear_stylist_env(monkeypatch)
    client = _auth_client()

    data = client.get("/stylist/capabilities").json()

    assert data["status"] == "runtime_not_configured"
    assert data["runtime"]["decoupled"] is True
    assert data["runtime"]["imports_openclaw_internal_code"] is False
    assert data["model"]["key_present"] is False
    assert data["model"]["key_matches_provider"] is False
    assert data["model"]["provider"] == "openai"
    assert data["error_policy"]["model_key_invalid"] == "ai_unavailable"
    assert "selfit_closet_search" in data["tools"]
    assert data["xiaohongshu"]["search"]["owner"] == "openclaw_sidecar"
    assert data["xiaohongshu"]["search"]["mcp_configured"] is False


def test_stylist_capabilities_exposes_xhs_mcp_sidecar(monkeypatch) -> None:
    _clear_stylist_env(monkeypatch)
    monkeypatch.setenv("SELFIT_XHS_MCP_URL", "http://127.0.0.1:18060/mcp")
    monkeypatch.setenv("SELFIT_XHS_ALLOWED_TOOLS", "search_feeds,get_feed_detail")
    client = _auth_client()

    data = client.get("/stylist/capabilities").json()

    search = data["xiaohongshu"]["search"]
    assert search["mcp_configured"] is True
    assert search["mcp_url"] == "http://127.0.0.1:18060/mcp"
    assert search["allowed_tools"] == ["search_feeds", "get_feed_detail"]
    assert "publish_content" in search["blocked_write_tools"]


def test_stylist_capabilities_reports_ai_unavailable_when_runtime_has_no_model_key(monkeypatch) -> None:
    _clear_stylist_env(monkeypatch)
    monkeypatch.setenv("STYLIST_OPENCLAW_CHAT_URL", "http://127.0.0.1:18789/api/selfit/chat")
    client = _auth_client()

    data = client.get("/stylist/capabilities").json()

    assert data["status"] == "ai_unavailable"
    assert data["model"]["key_present"] is False


def test_stylist_chat_fails_fast_when_runtime_has_no_model_key(monkeypatch) -> None:
    _clear_stylist_env(monkeypatch)
    monkeypatch.setenv("STYLIST_OPENCLAW_CHAT_URL", "http://127.0.0.1:18789/api/selfit/chat")
    client = _auth_client()

    response = client.post("/stylist/chat", json={"message": "通勤怎么穿"})

    assert response.status_code == 503
    data = response.json()
    assert data["error"]["code"] == "ai_unavailable"


def test_stylist_capabilities_require_key_matching_model_provider(monkeypatch) -> None:
    _clear_stylist_env(monkeypatch)
    monkeypatch.setenv("STYLIST_OPENCLAW_CHAT_URL", "http://127.0.0.1:18789/api/selfit/chat")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    client = _auth_client()

    data = client.get("/stylist/capabilities").json()

    assert data["status"] == "ai_unavailable"
    assert data["model"]["provider"] == "openai"
    assert data["model"]["key_present"] is True
    assert data["model"]["key_matches_provider"] is False


def test_stylist_capabilities_accept_matching_google_model_key(monkeypatch) -> None:
    _clear_stylist_env(monkeypatch)
    monkeypatch.setenv("STYLIST_OPENCLAW_CHAT_URL", "http://127.0.0.1:18789/api/selfit/chat")
    monkeypatch.setenv("STYLIST_OPENCLAW_MODEL", "google/gemini-2.5-flash")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    client = _auth_client()

    data = client.get("/stylist/capabilities").json()

    assert data["status"] == "ready"
    assert data["model"]["provider"] == "google"
    assert data["model"]["key_matches_provider"] is True


def test_stylist_capabilities_accept_matching_minimax_key(monkeypatch) -> None:
    _clear_stylist_env(monkeypatch)
    monkeypatch.setenv("STYLIST_OPENCLAW_CHAT_URL", "http://127.0.0.1:18789/api/selfit/chat")
    monkeypatch.setenv("STYLIST_OPENCLAW_MODEL", "minimax/MiniMax-M3")
    monkeypatch.setenv("MINIMAX_API_KEY", "test-key")
    client = _auth_client()

    data = client.get("/stylist/capabilities").json()

    assert data["status"] == "ready"
    assert data["model"]["provider"] == "minimax"
    assert data["model"]["accepted_env_keys"] == ["MINIMAX_API_KEY"]
    assert data["model"]["key_matches_provider"] is True


def test_stylist_capabilities_accept_matching_minimax_portal_token(monkeypatch) -> None:
    _clear_stylist_env(monkeypatch)
    monkeypatch.setenv("STYLIST_OPENCLAW_CHAT_URL", "http://127.0.0.1:18789/api/selfit/chat")
    monkeypatch.setenv("STYLIST_OPENCLAW_MODEL", "minimax-portal/MiniMax-M3")
    monkeypatch.setenv("MINIMAX_OAUTH_TOKEN", "test-token")
    client = _auth_client()

    data = client.get("/stylist/capabilities").json()

    assert data["status"] == "ready"
    assert data["model"]["provider"] == "minimax-portal"
    assert "MINIMAX_OAUTH_TOKEN" in data["model"]["accepted_env_keys"]
    assert data["model"]["key_matches_provider"] is True


def test_selfit_tool_closet_search_reads_fastapi_closet(monkeypatch, tmp_path: Path) -> None:
    _clear_stylist_env(monkeypatch)
    _use_tmp_closet(monkeypatch, tmp_path)
    client = _auth_client()
    created = client.post(
        "/closet/import/upload",
        files=[("images", ("top.png", _png_bytes(_synthetic_top_image()), "image/png"))],
    ).json()["items"][0]

    response = client.post("/stylist/tools/selfit_closet_search", json={"category": "top"})

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["items"][0]["item_id"] == created["item_id"]


def test_selfit_xhs_search_reports_mcp_sidecar(monkeypatch) -> None:
    _clear_stylist_env(monkeypatch)
    monkeypatch.setenv("SELFIT_XHS_MCP_URL", "http://127.0.0.1:18060/mcp")
    client = _auth_client()

    response = client.post("/stylist/tools/selfit_xhs_search", json={"query": "夏天通勤穿搭"})

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "mcp_sidecar_configured"
    assert data["mcp_mode"] == "streamable-http"
    assert "search_feeds" in data["allowed_tools"]


def test_stylist_memory_is_owned_by_runtime(monkeypatch) -> None:
    _clear_stylist_env(monkeypatch)
    client = _auth_client()

    response = client.get("/stylist/memory?user_id=u1")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "agent_runtime_unavailable"
