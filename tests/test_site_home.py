"""官网入口测试：/ 302 引流到 App，/docs、/home 渲染官网。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.site_home as site_home
from app.main import app


def test_root_redirects_to_app_with_temporary_redirect() -> None:
    """裸域名 302（临时、不缓存）到 App；绝不用 308，避免再次被浏览器永久缓存。"""

    client = TestClient(app)

    response = client.get("/", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "/selfit"
    assert "no-store" in response.headers.get("cache-control", "")


@pytest.mark.parametrize("path", ["/docs", "/home"])
def test_site_page_is_public_and_renders_default_content(path: str) -> None:
    client = TestClient(app)

    response = client.get(path, follow_redirects=False)

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "location" not in response.headers
    assert "no-store" in response.headers.get("cache-control", "")
    # 默认文案来自 git 内置 content.json
    assert "1 分钟，找到真正衬你的风格" in response.text
    assert "免费测我的风格" in response.text
    assert "16 种风格人格" in response.text
    # 主 CTA 指向测试入口
    assert 'href="/selfit"' in response.text
    # 16 型卡片：卡片墙包含全部人格名
    for name in ("静音时髦", "造梦浪漫", "东方玉骨", "搭配事故"):
        assert name in response.text


@pytest.mark.parametrize(
    ("path", "script"),
    [("/selfit", "selfit-api.js"), ("/selfit/try-on", "studio.js")],
)
def test_app_entries_remain_separate_from_site(path: str, script: str) -> None:
    client = TestClient(app)
    response = client.get(path, follow_redirects=False)
    assert response.status_code == 200
    assert script in response.text
    assert "先认识自己，再决定怎么穿</title>" not in response.text


def test_fastapi_docs_moved_off_docs_path() -> None:
    """/docs 不再是 Swagger；API 文档挪到 /api-docs。"""

    client = TestClient(app)

    docs = client.get("/docs")
    assert "swagger" not in docs.text.lower()

    api_docs = client.get("/api-docs")
    assert api_docs.status_code == 200
    assert "swagger" in api_docs.text.lower()


@pytest.mark.parametrize("path", ["/docs", "/home"])
def test_site_content_override_takes_precedence(path: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    override = tmp_path / "site" / "content.json"
    override.parent.mkdir(parents=True)
    override.write_text(
        json.dumps(
            {
                "site": {"name": "selfit", "tagline": "适我"},
                "hero": {
                    "eyebrow": "测试覆盖",
                    "title": "这是覆盖后的标题",
                    "subtitle": "服务器 outputs 覆盖文案",
                    "primaryCta": {"label": "去测试", "href": "/selfit"},
                    "secondaryCta": {"label": "", "href": ""},
                },
                "sections": [],
                "footer": {"text": "覆盖页脚", "links": []},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(site_home, "OVERRIDE_CONTENT_PATH", override)
    client = TestClient(app)

    response = client.get(path, follow_redirects=False)

    assert response.status_code == 200
    assert "这是覆盖后的标题" in response.text
    assert "覆盖页脚" in response.text
    assert "1 分钟" not in response.text


@pytest.mark.parametrize("path", ["/docs", "/home"])
def test_site_escapes_user_content_and_blocks_external_links(path: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    override = tmp_path / "site" / "content.json"
    override.parent.mkdir(parents=True)
    override.write_text(
        json.dumps(
            {
                "site": {"name": "selfit", "tagline": "适我"},
                "hero": {
                    "eyebrow": "<script>alert(1)</script>",
                    "title": "标题<b>加粗</b>",
                    "subtitle": "",
                    "primaryCta": {"label": "外链", "href": "https://evil.example.com"},
                    "secondaryCta": {"label": "", "href": ""},
                },
                "sections": [],
                "footer": {"text": "", "links": []},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(site_home, "OVERRIDE_CONTENT_PATH", override)
    client = TestClient(app)

    response = client.get(path, follow_redirects=False)

    assert response.status_code == 200
    # 文案被转义，不能注入 HTML
    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;" in response.text
    # 外链 href 被替换为安全占位
    assert "https://evil.example.com" not in response.text
