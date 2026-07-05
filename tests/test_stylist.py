from __future__ import annotations

import io
import itertools
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
        "OPENCLAW_ASIS_CHAT_URL",
        "STYLIST_ENABLE_OPENCLAW_CLI",
        "STYLIST_OPENCLAW_MEMORY_URL",
        "STYLIST_OPENCLAW_MODEL",
        "ASIS_XHS_MCP_URL",
        "ASIS_XHS_API_URL",
        "ASIS_XHS_MCP_MODE",
        "ASIS_XHS_ALLOWED_TOOLS",
        "STYLIST_XHS_SEARCH_URL",
        "STYLIST_XHS_MCP_URL",
        "STYLIST_XHS_API_URL",
        "STYLIST_XHS_MCP_MODE",
        "STYLIST_XHS_ALLOWED_TOOLS",
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


def test_stylist_chat_legacy_session_id_still_works(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_closet(monkeypatch, tmp_path)
    _clear_stylist_env(monkeypatch)
    monkeypatch.setenv("STYLIST_DEMO_MODE", "1")
    client = _auth_client()

    response = client.post("/stylist/chat", json={"session_id": "asis-inspiration", "message": "小雨通勤怎么穿"})

    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "asis-inspiration"
    detail = client.get("/stylist/sessions/asis-inspiration").json()
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
    assert data["assistant_message"] == "灵感暂时不可用，请稍后再试。"


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
            "session_id": "asis-inspiration",
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
    assert result["assistant_message"] == "AI 穿搭师暂时不可用，请检查模型配置。"


def test_stylist_degrades_inspiration_tool_failure_without_xhs_claim() -> None:
    result = stylist._degraded_inspiration_result_if_needed(
        {
            "status": "failed",
            "error": {"code": "ai_unavailable", "message": "AI 穿搭师暂时不可用，请检查模型配置。"},
        },
        {
            "message": "延续刚才看展场景，如果下雨并且我想显瘦，鞋包怎么调整？",
            "context": {
                "source": "inspiration_tab",
                "xiaohongshu_preferred": True,
                "conversation": [
                    {"role": "user", "content": "周末上海看展怎么穿？"},
                    {"role": "assistant", "content": "走松弛通勤感。"},
                    {"role": "user", "content": "下雨怎么调整？"},
                ],
            },
        },
    )

    assert result is not None
    assert result["status"] == "ok"
    assert result["mode"] == "degraded_openclaw"
    assert result["quality_checks"]["used_xiaohongshu_recommendations"] is False
    assert result["quality_checks"]["continued_conversation"] is True
    assert result["evidence_sources"] == []
    assert "已经调用小红书灵感 skill" in result["assistant_message"]
    assert "不给你硬塞低相关笔记" in result["assistant_message"]
    assert any(action["type"] == "retry_xhs" for action in result["next_actions"])


def test_stylist_degraded_inspiration_uses_real_xhs_notes_when_available() -> None:
    xhs_notes = [
        {
            "note_id": "note-1",
            "title": "上海看展松弛通勤穿搭",
            "author_name": "穿搭薯",
            "cover_url": "https://example.com/cover.jpg",
            "liked_count": "123",
            "collected_count": "45",
            "source_label": "小红书搜索",
        }
    ]
    result = stylist._degraded_inspiration_result_if_needed(
        {
            "status": "failed",
            "error": {"code": "ai_unavailable", "message": "AI 穿搭师暂时不可用，请检查模型配置。"},
        },
        {
            "message": "周末上海看展怎么穿？",
            "context": {
                "source": "inspiration_tab",
                "xiaohongshu_preferred": True,
                "xhs_notes": xhs_notes,
                "xhs_tool_steps": [{"id": "search", "title": "搜索小红书灵感", "status": "done", "detail": "小红书搜索 · 1 张笔记卡片"}],
                "xhs_evidence_sources": [{"type": "xiaohongshu", "label": "小红书搜索：上海看展", "count": 1}],
                "conversation": [],
            },
        },
    )

    assert result is not None
    assert result["xhs_notes"] == xhs_notes
    assert result["quality_checks"]["used_xiaohongshu_recommendations"] is True
    assert result["evidence_sources"][0]["type"] == "xiaohongshu"
    assert "上海看展松弛通勤穿搭" in result["assistant_message"]


def test_stylist_degraded_followup_handles_rain_without_high_heels() -> None:
    xhs_notes = [
        {
            "note_id": "note-rain-1",
            "title": "雨天通勤乐福鞋穿搭",
            "author_name": "穿搭薯",
            "cover_url": "https://example.com/rain.jpg",
            "liked_count": "321",
            "collected_count": "88",
            "source_label": "小红书搜索",
        }
    ]
    result = stylist._degraded_inspiration_result_if_needed(
        {
            "status": "failed",
            "error": {"code": "ai_unavailable", "message": "AI 穿搭师暂时不可用，请检查模型配置。"},
        },
        {
            "message": "如果下雨，而且不想穿高跟，怎么调整？继续参考刚才的场景",
            "context": {
                "source": "inspiration_tab",
                "xiaohongshu_preferred": True,
                "xhs_notes": xhs_notes,
                "xhs_tool_steps": [{"id": "search", "title": "搜索小红书灵感", "status": "done", "detail": "小红书搜索 · 1 张笔记卡片"}],
                "xhs_evidence_sources": [{"type": "xiaohongshu", "label": "小红书搜索：周五 聚餐 通勤 雨天 穿搭", "count": 1}],
                "conversation": [
                    {"role": "user", "content": "周五上班接聚餐：帮我推荐穿搭，要有小红书笔记参考"},
                    {"role": "assistant", "content": "可以走白天得体、晚上有一点亮点的路线。"},
                    {"role": "user", "content": "如果下雨，而且不想穿高跟，怎么调整？继续参考刚才的场景"},
                ],
            },
        },
    )

    assert result is not None
    assert result["quality_checks"]["continued_conversation"] is True
    assert result["quality_checks"]["used_xiaohongshu_recommendations"] is True
    assert "不想穿高跟" in result["assistant_message"]
    assert "光面乐福鞋" in result["assistant_message"]
    assert "防滑" in result["assistant_message"]
    assert "雨天通勤乐福鞋穿搭" in result["assistant_message"]


def test_stylist_degraded_inspiration_explains_xhs_login_failure() -> None:
    result = stylist._degraded_inspiration_result_if_needed(
        {
            "status": "failed",
            "error": {"code": "ai_unavailable", "message": "AI 穿搭师暂时不可用，请检查模型配置。"},
        },
        {
            "message": "周五上班接聚餐：帮我推荐穿搭，要有小红书笔记参考",
            "context": {
                "source": "inspiration_tab",
                "xiaohongshu_preferred": True,
                "requested_skills": ["xhs-trend-research"],
                "xhs_notes": [],
                "xhs_unavailable_reason": "xhs_search_failed",
                "xhs_unavailable_detail": "小红书侧边服务未登录，请先扫码登录后重试",
                "conversation": [],
            },
        },
    )

    assert result is not None
    assert "已经调用小红书灵感 skill" in result["assistant_message"]
    assert "账号态未登录" in result["assistant_message"]
    assert "没有实时索引到" not in result["assistant_message"]
    assert result["quality_checks"]["used_xiaohongshu_recommendations"] is False


def test_stylist_degraded_inspiration_explains_public_fallback_failure() -> None:
    result = stylist._degraded_inspiration_result_if_needed(
        {
            "status": "failed",
            "error": {"code": "ai_unavailable", "message": "AI 穿搭师暂时不可用，请检查模型配置。"},
        },
        {
            "message": "周五上班接聚餐：帮我推荐穿搭，要有小红书笔记参考",
            "context": {
                "source": "inspiration_tab",
                "xiaohongshu_preferred": True,
                "requested_skills": ["xhs-trend-research"],
                "xhs_notes": [],
                "xhs_unavailable_reason": "xhs_login_required",
                "xhs_unavailable_detail": "小红书侧边服务未登录，请先扫码登录后重试",
                "xhs_tool_steps": [{"id": "public", "title": "公开网页搜索补位", "status": "failed", "detail": "没有找到可引用的公开小红书链接"}],
                "conversation": [],
            },
        },
    )

    assert result is not None
    assert "公开网页搜索也没有找到可引用的小红书链接" in result["assistant_message"]
    assert result["quality_checks"]["used_xiaohongshu_recommendations"] is False


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


def test_stylist_degraded_inspiration_marks_public_xhs_fallback() -> None:
    public_notes = [
        {
            "note_id": "abc123",
            "title": "周五通勤下班聚餐穿搭",
            "author_name": "公开网页搜索",
            "source_label": "公开网页搜索",
            "url": "https://www.xiaohongshu.com/explore/abc123",
            "is_public_fallback": True,
        }
    ]
    result = stylist._degraded_inspiration_result_if_needed(
        {
            "status": "failed",
            "error": {"code": "ai_unavailable", "message": "AI 穿搭师暂时不可用，请检查模型配置。"},
        },
        {
            "message": "周五上班接聚餐：帮我推荐穿搭，要有小红书笔记参考",
            "context": {
                "source": "inspiration_tab",
                "xiaohongshu_preferred": True,
                "requested_skills": ["xhs-trend-research"],
                "xhs_notes": public_notes,
                "xhs_evidence_sources": [{"type": "public_web_search", "label": "公开网页搜索：通勤 聚餐", "count": 1}],
                "xhs_unavailable_reason": "xhs_login_required",
                "xhs_unavailable_detail": "小红书侧边服务未登录，请先扫码登录后重试",
                "conversation": [],
            },
        },
    )

    assert result is not None
    assert "公开网页搜索补到 1 条小红书公开链接" in result["assistant_message"]
    assert "不当作原生推荐流" in result["assistant_message"]
    assert result["quality_checks"]["used_xiaohongshu_recommendations"] is False
    assert result["quality_checks"]["used_public_xhs_fallback"] is True
    assert result["xhs_notes"] == public_notes


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


def test_stylist_xhs_query_candidates_include_scene_specific_loops() -> None:
    queries = stylist._xhs_query_candidates("客户会面要稳：帮我推荐穿搭")

    assert queries[0] == "客户会面 穿搭"
    assert "商务通勤 穿搭" in queries
    assert "职场正式 不老气 穿搭" in queries


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


def test_stylist_invokes_xhs_skill_only_on_intent() -> None:
    assert stylist._should_invoke_xhs_skill(
        {
            "message": "胶囊衣橱：帮我推荐穿搭",
            "context": {"source": "inspiration_tab", "xiaohongshu_preferred": False, "requested_skills": ["capsule-wardrobe"]},
        }
    ) is True
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
    assert "asis_closet_search" in data["tools"]
    assert data["xiaohongshu"]["search"]["owner"] == "openclaw_sidecar"
    assert data["xiaohongshu"]["search"]["mcp_configured"] is False


def test_stylist_capabilities_exposes_xhs_mcp_sidecar(monkeypatch) -> None:
    _clear_stylist_env(monkeypatch)
    monkeypatch.setenv("ASIS_XHS_MCP_URL", "http://127.0.0.1:18060/mcp")
    monkeypatch.setenv("ASIS_XHS_ALLOWED_TOOLS", "search_feeds,get_feed_detail")
    client = _auth_client()

    data = client.get("/stylist/capabilities").json()

    search = data["xiaohongshu"]["search"]
    assert search["mcp_configured"] is True
    assert search["mcp_url"] == "http://127.0.0.1:18060/mcp"
    assert search["allowed_tools"] == ["search_feeds", "get_feed_detail"]
    assert "publish_content" in search["blocked_write_tools"]


def test_stylist_capabilities_reports_ai_unavailable_when_runtime_has_no_model_key(monkeypatch) -> None:
    _clear_stylist_env(monkeypatch)
    monkeypatch.setenv("STYLIST_OPENCLAW_CHAT_URL", "http://127.0.0.1:18789/api/asis/chat")
    client = _auth_client()

    data = client.get("/stylist/capabilities").json()

    assert data["status"] == "ai_unavailable"
    assert data["model"]["key_present"] is False


def test_stylist_chat_fails_fast_when_runtime_has_no_model_key(monkeypatch) -> None:
    _clear_stylist_env(monkeypatch)
    monkeypatch.setenv("STYLIST_OPENCLAW_CHAT_URL", "http://127.0.0.1:18789/api/asis/chat")
    client = _auth_client()

    response = client.post("/stylist/chat", json={"message": "通勤怎么穿"})

    assert response.status_code == 503
    data = response.json()
    assert data["error"]["code"] == "ai_unavailable"


def test_stylist_capabilities_require_key_matching_model_provider(monkeypatch) -> None:
    _clear_stylist_env(monkeypatch)
    monkeypatch.setenv("STYLIST_OPENCLAW_CHAT_URL", "http://127.0.0.1:18789/api/asis/chat")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    client = _auth_client()

    data = client.get("/stylist/capabilities").json()

    assert data["status"] == "ai_unavailable"
    assert data["model"]["provider"] == "openai"
    assert data["model"]["key_present"] is True
    assert data["model"]["key_matches_provider"] is False


def test_stylist_capabilities_accept_matching_google_model_key(monkeypatch) -> None:
    _clear_stylist_env(monkeypatch)
    monkeypatch.setenv("STYLIST_OPENCLAW_CHAT_URL", "http://127.0.0.1:18789/api/asis/chat")
    monkeypatch.setenv("STYLIST_OPENCLAW_MODEL", "google/gemini-2.5-flash")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    client = _auth_client()

    data = client.get("/stylist/capabilities").json()

    assert data["status"] == "ready"
    assert data["model"]["provider"] == "google"
    assert data["model"]["key_matches_provider"] is True


def test_stylist_capabilities_accept_matching_minimax_key(monkeypatch) -> None:
    _clear_stylist_env(monkeypatch)
    monkeypatch.setenv("STYLIST_OPENCLAW_CHAT_URL", "http://127.0.0.1:18789/api/asis/chat")
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
    monkeypatch.setenv("STYLIST_OPENCLAW_CHAT_URL", "http://127.0.0.1:18789/api/asis/chat")
    monkeypatch.setenv("STYLIST_OPENCLAW_MODEL", "minimax-portal/MiniMax-M3")
    monkeypatch.setenv("MINIMAX_OAUTH_TOKEN", "test-token")
    client = _auth_client()

    data = client.get("/stylist/capabilities").json()

    assert data["status"] == "ready"
    assert data["model"]["provider"] == "minimax-portal"
    assert "MINIMAX_OAUTH_TOKEN" in data["model"]["accepted_env_keys"]
    assert data["model"]["key_matches_provider"] is True


def test_asis_tool_closet_search_reads_fastapi_closet(monkeypatch, tmp_path: Path) -> None:
    _clear_stylist_env(monkeypatch)
    _use_tmp_closet(monkeypatch, tmp_path)
    client = _auth_client()
    created = client.post(
        "/closet/import/upload",
        files=[("images", ("top.png", _png_bytes(_synthetic_top_image()), "image/png"))],
    ).json()["items"][0]

    response = client.post("/stylist/tools/asis_closet_search", json={"category": "top"})

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["items"][0]["item_id"] == created["item_id"]


def test_asis_xhs_search_reports_mcp_sidecar(monkeypatch) -> None:
    _clear_stylist_env(monkeypatch)
    monkeypatch.setenv("ASIS_XHS_MCP_URL", "http://127.0.0.1:18060/mcp")
    client = _auth_client()

    response = client.post("/stylist/tools/asis_xhs_search", json={"query": "夏天通勤穿搭"})

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
