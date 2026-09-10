"""官网首页（/ 与 /home）的渲染测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.site_home as site_home
from app.main import app


def test_site_home_is_public_and_renders_default_content() -> None:
    client = TestClient(app)

    for path in ("/", "/home"):
        response = client.get(path)

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        # 默认文案来自 git 内置 content.json
        assert "1 分钟，找到真正衬你的风格" in response.text
        assert "免费测我的风格" in response.text
        assert "16 种风格人格" in response.text
        # 主 CTA 指向测试入口
        assert 'href="/selfit"' in response.text
        # 16 型卡片：卡片墙包含全部人格名
        for name in ("静音时髦", "造梦浪漫", "东方玉骨", "搭配事故"):
            assert name in response.text
        # 未知板块类型被安全跳过
        assert "type=\"steps\"" not in response.text  # 渲染后的 HTML 不应泄漏 JSON 类型名


def test_site_home_content_override_takes_precedence(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
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

    response = client.get("/")

    assert response.status_code == 200
    assert "这是覆盖后的标题" in response.text
    assert "覆盖页脚" in response.text
    assert "1 分钟" not in response.text


def test_site_home_escapes_user_content_and_blocks_external_links(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
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

    response = client.get("/")

    assert response.status_code == 200
    # 文案被转义，不能注入 HTML
    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;" in response.text
    # 外链 href 被替换为安全占位
    assert "https://evil.example.com" not in response.text
