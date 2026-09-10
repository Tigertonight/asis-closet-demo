"""selfit 官网首页：公开访问，无需登录。

内容驱动：默认文案在 `app/static/site/content.json`（随 git 发布）；
服务器可用 `outputs/site/content.json` 覆盖（数据目录，改完刷新即生效，
无需重新部署）。改文案 / 增删板块 / 调整顺序都只动 JSON。

支持的板块类型：
- steps   标题 + 编号步骤列表
- types   标题 + 16 型人格卡片墙（卡片图自动取 /static/selfit/assets/personality/<EN>/hero.png）
- features 标题 + 特性卡片
- cta     结尾大按钮
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse

from app.storage import ROOT_DIR

DEFAULT_CONTENT_PATH = Path(__file__).resolve().parent / "static" / "site" / "content.json"
OVERRIDE_CONTENT_PATH = ROOT_DIR / "outputs" / "site" / "content.json"

router = APIRouter(tags=["site-home"])


def _esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def _safe_href(value: str) -> str:
    """只允许站内链接（/ 开头）与页内锚点（# 开头），防外链注入。"""

    text = str(value or "").strip()
    if text.startswith("/") or text.startswith("#"):
        return _esc(text)
    return "#"


def load_site_content() -> dict[str, Any]:
    path = OVERRIDE_CONTENT_PATH if OVERRIDE_CONTENT_PATH.exists() else DEFAULT_CONTENT_PATH
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    try:
        return json.loads(DEFAULT_CONTENT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _hero_image(code: str) -> str:
    lowered = str(code or "").strip().lower()
    asset = Path(__file__).resolve().parent / "static" / "selfit" / "assets" / "personality" / lowered / "hero.png"
    if lowered and asset.exists():
        return f"/static/selfit/assets/personality/{_esc(lowered)}/hero.png"
    return "/static/selfit/assets/personality/placeholder-card.svg"


def _section_steps(section: dict[str, Any]) -> str:
    items = section.get("items") or []
    cards = "".join(
        f'<li class="step"><span class="step-no">{index}</span>'
        f'<div class="step-body"><b>{_esc(item.get("title"))}</b><p>{_esc(item.get("text"))}</p></div></li>'
        for index, item in enumerate(items, start=1)
    )
    return f'<section id="{_esc(section.get("id") or "steps")}" class="section"><h2>{_esc(section.get("title"))}</h2><ol class="steps">{cards}</ol></section>'


def _section_types(section: dict[str, Any]) -> str:
    items = section.get("items") or []
    cards = "".join(
        f'<figure class="type-card"><img loading="lazy" src="{_hero_image(item.get("en"))}" alt="{_esc(item.get("name"))}" />'
        f'<figcaption><b>{_esc(item.get("name"))}</b><small>{_esc(item.get("en"))}</small></figcaption></figure>'
        for item in items
    )
    note = f'<p class="section-note">{_esc(section.get("text"))}</p>' if section.get("text") else ""
    return (
        f'<section id="{_esc(section.get("id") or "types")}" class="section section--types">'
        f"<h2>{_esc(section.get('title'))}</h2>{note}<div class=\"type-grid\">{cards}</div></section>"
    )


def _section_features(section: dict[str, Any]) -> str:
    items = section.get("items") or []
    cards = "".join(
        f'<article class="feature"><b>{_esc(item.get("title"))}</b><p>{_esc(item.get("text"))}</p></article>'
        for item in items
    )
    return f'<section id="{_esc(section.get("id") or "why")}" class="section"><h2>{_esc(section.get("title"))}</h2><div class="features">{cards}</div></section>'


def _section_cta(section: dict[str, Any]) -> str:
    button = section.get("button") or {}
    return (
        f'<section class="cta-band"><h2>{_esc(section.get("title"))}</h2>'
        f'<p>{_esc(section.get("text"))}</p>'
        f'<a class="btn btn--primary btn--lg" href="{_safe_href(button.get("href"))}">{_esc(button.get("label"))}</a></section>'
    )


_SECTION_RENDERERS = {
    "steps": _section_steps,
    "types": _section_types,
    "features": _section_features,
    "cta": _section_cta,
}


def render_site_html(content: dict[str, Any]) -> str:
    site = content.get("site") or {}
    hero = content.get("hero") or {}
    primary = hero.get("primaryCta") or {}
    secondary = hero.get("secondaryCta") or {}
    nav_links = "".join(
        f'<a href="{_safe_href(item.get("href"))}">{_esc(item.get("label"))}</a>'
        for item in (content.get("nav") or [])
    )
    # 普通板块走窄容器；cta 板块通栏（酒红底色要铺满屏幕宽）。
    inline_sections = []
    cta_sections = []
    for section in content.get("sections") or []:
        renderer = _SECTION_RENDERERS.get(str(section.get("type") or ""))
        if renderer is None:
            continue
        (cta_sections if section.get("type") == "cta" else inline_sections).append(renderer(section))
    sections_html = "".join(inline_sections)
    cta_html = "".join(cta_sections)
    footer = content.get("footer") or {}
    footer_links = "".join(
        f'<a href="{_safe_href(item.get("href"))}">{_esc(item.get("label"))}</a>'
        for item in (footer.get("links") or [])
    )
    name = site.get("name") or "selfit"
    tagline = site.get("tagline") or ""

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
  <title>{_esc(name)} · {_esc(tagline)} | 先认识自己，再决定怎么穿</title>
  <meta name="description" content="{_esc(hero.get("subtitle") or "1 分钟，找到真正衬你的风格")}" />
  <link rel="icon" type="image/svg+xml" href="/static/brand/favicon.svg" />
  <link rel="icon" type="image/png" sizes="32x32" href="/static/brand/favicon-32.png" />
  <link rel="apple-touch-icon" href="/static/brand/apple-touch-icon.png" />
  <style>
    :root {{
      --brand: #8a011b; --brand-pressed: #720015; --ink: #222; --muted: #666; --faint: #999;
      --line: #e7e7e7; --canvas: #fafafa; --card: #fff; --shadow: rgba(0, 0, 0, .06);
    }}
    * {{ box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}
    body {{ margin: 0; background: var(--canvas); color: var(--ink); font: 15px/1.75 -apple-system, BlinkMacSystemFont, "PingFang SC", "Segoe UI", sans-serif; -webkit-font-smoothing: antialiased; }}
    a {{ color: inherit; }}
    img {{ max-width: 100%; display: block; }}

    .topbar {{ position: sticky; top: 0; z-index: 40; display: flex; align-items: center; gap: 20px; padding: 14px 24px; background: rgba(255,255,255,.92); backdrop-filter: blur(8px); border-bottom: 1px solid var(--line); }}
    .wordmark {{ font-size: 18px; font-weight: 800; letter-spacing: .5px; color: var(--brand); text-decoration: none; }}
    .wordmark small {{ margin-left: 8px; color: var(--muted); font-weight: 500; font-size: 13px; }}
    .topnav {{ display: none; gap: 22px; margin-left: auto; }}
    .topnav a {{ color: var(--muted); text-decoration: none; font-size: 14px; }}
    .topnav a:hover {{ color: var(--brand); }}
    .topbar .btn {{ margin-left: auto; }}
    .topnav ~ .btn {{ margin-left: 0; }}

    .container {{ max-width: 1080px; margin: 0 auto; padding: 0 24px; }}

    .hero {{ padding: 56px 0 40px; }}
    .hero-inner {{ max-width: 640px; }}
    .hero .eyebrow {{ color: var(--brand); font-size: 13px; font-weight: 700; letter-spacing: 2px; margin: 0 0 12px; }}
    .hero h1 {{ margin: 0 0 16px; font-size: 34px; line-height: 1.3; letter-spacing: -.5px; text-wrap: balance; }}
    .hero .sub {{ margin: 0 0 28px; color: var(--muted); font-size: 16px; text-wrap: pretty; }}
    .hero-actions {{ display: flex; flex-wrap: wrap; gap: 12px; }}
    .hero-board {{ margin-top: 44px; border-radius: 20px; overflow: hidden; box-shadow: 0 18px 50px var(--shadow); background: #fff; }}

    .btn {{ display: inline-flex; align-items: center; justify-content: center; min-height: 48px; padding: 0 28px; border-radius: 999px; font-size: 15px; font-weight: 600; text-decoration: none; transition: background .16s ease, transform .16s ease; }}
    .btn--primary {{ background: var(--brand); color: #fff; }}
    .btn--primary:active {{ background: var(--brand-pressed); transform: scale(.985); }}
    .btn--ghost {{ border: 1px solid rgba(138,1,27,.28); background: #fff; color: var(--brand); }}
    .btn--ghost:hover {{ background: #fbf4f5; }}
    .btn--lg {{ min-height: 54px; padding: 0 36px; font-size: 16px; }}

    .section {{ padding: 52px 0 8px; }}
    .section h2 {{ margin: 0 0 8px; font-size: 24px; letter-spacing: -.3px; text-align: center; text-wrap: balance; }}
    .section-note {{ margin: 0 0 24px; color: var(--muted); text-align: center; font-size: 14px; }}

    .steps {{ list-style: none; margin: 28px 0 0; padding: 0; display: grid; gap: 14px; }}
    .step {{ display: flex; gap: 16px; align-items: flex-start; padding: 20px 22px; background: var(--card); border: 1px solid var(--line); border-radius: 18px; box-shadow: 0 4px 14px rgba(0,0,0,.03); }}
    .step-no {{ flex: 0 0 34px; height: 34px; display: grid; place-items: center; border-radius: 999px; background: #f6e7ea; color: var(--brand); font-weight: 800; font-size: 15px; }}
    .step-body b {{ display: block; font-size: 16px; margin-bottom: 4px; }}
    .step-body p {{ margin: 0; color: var(--muted); font-size: 14px; }}

    .type-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-top: 26px; }}
    .type-card {{ margin: 0; background: var(--card); border: 1px solid var(--line); border-radius: 16px; overflow: hidden; transition: transform .16s ease, box-shadow .16s ease; }}
    .type-card:hover {{ transform: translateY(-2px); box-shadow: 0 12px 28px rgba(0,0,0,.08); }}
    .type-card img {{ width: 100%; aspect-ratio: 1484 / 1072; object-fit: cover; background: #f2eded; }}
    .type-card figcaption {{ display: flex; align-items: baseline; justify-content: space-between; padding: 10px 14px; }}
    .type-card b {{ font-size: 14px; }}
    .type-card small {{ color: var(--faint); font-size: 11px; letter-spacing: 1px; }}

    .features {{ display: grid; gap: 14px; margin-top: 26px; }}
    .feature {{ padding: 22px 24px; background: var(--card); border: 1px solid var(--line); border-radius: 18px; }}
    .feature b {{ display: block; font-size: 16px; margin-bottom: 6px; }}
    .feature p {{ margin: 0; color: var(--muted); font-size: 14px; }}

    .cta-band {{ margin: 60px 0 0; padding: 56px 24px 64px; background: var(--brand); color: #fff; text-align: center; }}
    .cta-band h2 {{ margin: 0 0 10px; font-size: 26px; letter-spacing: -.3px; }}
    .cta-band p {{ margin: 0 0 26px; opacity: .82; }}
    .cta-band .btn--primary {{ background: #fff; color: var(--brand); }}
    .cta-band .btn--primary:active {{ background: #f6e7ea; }}

    footer {{ padding: 26px 0 34px; color: var(--faint); font-size: 13px; }}
    footer .container {{ display: flex; flex-wrap: wrap; gap: 8px 18px; align-items: center; justify-content: center; }}
    footer a {{ color: var(--muted); text-decoration: none; }}
    footer a:hover {{ color: var(--brand); }}

    @media (min-width: 720px) {{
      .topnav {{ display: flex; }}
      .hero {{ padding: 88px 0 56px; display: grid; grid-template-columns: minmax(0, 1.1fr) minmax(0, .9fr); gap: 48px; align-items: center; }}
      .hero-inner {{ max-width: none; }}
      .hero h1 {{ font-size: 44px; }}
      .hero .sub {{ font-size: 17px; }}
      .hero-board {{ margin-top: 0; }}
      .steps {{ grid-template-columns: repeat(3, 1fr); }}
      .type-grid {{ grid-template-columns: repeat(4, 1fr); }}
      .features {{ grid-template-columns: repeat(3, 1fr); }}
    }}
    @media (prefers-reduced-motion: reduce) {{
      html {{ scroll-behavior: auto; }}
      .type-card, .btn {{ transition: none; }}
    }}
  </style>
</head>
<body>
  <header class="topbar">
    <a class="wordmark" href="/">{_esc(name)}<small>{_esc(tagline)}</small></a>
    <nav class="topnav">{nav_links}</nav>
    <a class="btn btn--primary" href="{_safe_href(primary.get("href"))}">{_esc(primary.get("label") or "开始")}</a>
  </header>

  <main>
    <div class="hero container">
      <div class="hero-inner">
        <p class="eyebrow">{_esc(hero.get("eyebrow"))}</p>
        <h1>{_esc(hero.get("title"))}</h1>
        <p class="sub">{_esc(hero.get("subtitle"))}</p>
        <div class="hero-actions">
          <a class="btn btn--primary btn--lg" href="{_safe_href(primary.get("href"))}">{_esc(primary.get("label"))}</a>
          {f'<a class="btn btn--ghost btn--lg" href="{_safe_href(secondary.get("href"))}">{_esc(secondary.get("label"))}</a>' if secondary.get("label") else ""}
        </div>
      </div>
      <img class="hero-board" src="/static/selfit/assets/login-persona-board@2x.png" alt="selfit 风格人格展示" width="716" height="640" />
    </div>
    <div class="container">
      {sections_html}
    </div>
    {cta_html}
  </main>
  <footer>
    <div class="container">
      <span>{_esc(footer.get("text"))}</span>
      {footer_links}
    </div>
  </footer>
</body>
</html>"""


@router.get("/docs", include_in_schema=False, response_class=HTMLResponse)
def site_home_page() -> HTMLResponse:
    return HTMLResponse(render_site_html(load_site_content()), headers={"Cache-Control": "no-store"})


# 根路径历史上曾长期 308 永久重定向到 /selfit——访问过的浏览器已永久缓存该跳转，
# 服务端无法撤销。因此官网换到 /docs；根路径用 302（临时，不缓存）引到官网，
# 老访客的缓存 308 依旧直达测试页，新访客落到官网。
@router.get("/", include_in_schema=False)
def root_page() -> RedirectResponse:
    return RedirectResponse(url="/docs", status_code=302, headers={"Cache-Control": "no-store"})


@router.get("/home", include_in_schema=False)
def home_alias_page() -> RedirectResponse:
    return RedirectResponse(url="/docs", status_code=302, headers={"Cache-Control": "no-store"})
