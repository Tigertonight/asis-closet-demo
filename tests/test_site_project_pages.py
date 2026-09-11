"""独立验证官网导航与公开二级页，不启动试穿、AI 等无关服务。"""

from __future__ import annotations

import copy
import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import site_home
from app.ops import request_guard_middleware


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("SELFIT_ENV", "production")
    monkeypatch.setattr(site_home, "OVERRIDE_CONTENT_PATH", tmp_path / "absent.json")
    app = FastAPI(docs_url="/api-docs", redoc_url=None)
    app.middleware("http")(request_guard_middleware)
    app.include_router(site_home.router)
    with TestClient(app) as test_client:
        yield test_client


def test_home_retains_all_original_sections_without_module_navigation_cards(client):
    response = client.get("/docs")
    assert response.status_code == 200
    page = response.text
    topnav = re.search(r'<nav class="topnav"[^>]*>(.*?)</nav>', page, re.S).group(1)
    assert 'class="home-nav"' not in page
    assert 'aria-label="首页核心模块"' not in page
    assert 'href="/docs" aria-current="page"' in topnav
    for target in ("steps", "types", "why"):
        assert f'href="#{target}"' not in topnav
        assert f'id="{target}"' in page
    assert page.count('<figure class="type-card">') == 16
    assert "先看看 16 种风格" in page
    assert 'width="2808" height="3208"' in page
    for section in site_home.load_site_content()["sections"]:
        assert site_home._SECTION_RENDERERS[section["type"]](section) in page


@pytest.mark.parametrize("slug", ["styling", "technology", "research", "practice"])
def test_project_pages_are_public_directly_addressable_and_have_working_navigation(client, slug):
    response = client.get(f"/docs/{slug}", follow_redirects=False)
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert response.headers["cache-control"] == "no-store"
    page = response.text
    assert f'href="/docs/{slug}" aria-current="page"' in page
    topnav = re.search(r'<nav class="topnav"[^>]*>(.*?)</nav>', page, re.S).group(1)
    assert topnav.count('aria-current="page"') == 1
    assert "返回首页" in page
    assert 'class="hero-board"' not in page
    assert 'class="home-nav"' not in page
    assert '<figure class="type-card">' not in page
    assert "本页内容" not in page
    assert 'aria-label="本页目录"' not in page
    assert 'href="#chapter-' not in page
    source = next(item for item in site_home.load_project_pages() if item["slug"] == slug)
    for index, chapter in enumerate(source["chapters"], start=1):
        assert f'<h2 id="chapter-title-{index}">{site_home._esc(chapter["title"])}</h2>' in page
    for href in re.findall(r'href="(/docs[^"]*)"', page):
        assert client.get(href).status_code == 200


def test_unknown_project_page_does_not_fall_back_to_home(client):
    assert client.get("/docs/missing-page").status_code == 404
    assert client.get("/docs/project-pages.json").status_code == 404


def test_existing_home_content_override_keeps_new_routes_and_navigation(client, monkeypatch):
    override = {"hero": {"title": "自定义首页"}, "nav": [{"label": "我的介绍", "href": "#intro"}], "sections": []}
    monkeypatch.setattr(site_home, "load_site_content", lambda: override)
    home = client.get("/docs").text
    detail = client.get("/docs/styling").text
    assert "自定义首页" in home
    assert 'href="#intro"' not in home
    assert 'href="/docs/styling"' in home
    assert "穿搭知识体系" in detail
    assert 'href="#intro"' not in detail


def test_project_text_is_escaped():
    page = copy.deepcopy(site_home.load_project_pages()[0])
    attack = '<img src=x onerror="alert(1)">'
    page["title"] = attack
    page["chapters"][0]["cards"][0]["text"] = attack
    page["chapters"][0]["note"] = attack
    rendered = site_home.render_site_html({}, page)
    assert attack not in rendered
    assert rendered.count("&lt;img src=x onerror=&quot;alert(1)&quot;&gt;") == 3
