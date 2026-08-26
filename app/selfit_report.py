"""selfit onboarding 报告内容生成的算法接口层。

报告渲染契约见 docs/SELFIT_REPORT_DATA_CONTRACT.md；任务生命周期见
docs/SELFIT_BACKEND_INTEGRATION.md 4.6 / 4.7 节；分型与推荐口径见
app/selfit_persona.py 与 app/selfit_recommend.py 模块注释。

算法接入说明
------------
接口层只依赖本模块暴露的稳定抽象，算法任务只需要：

1. 实现一个 `ReportBuilder`：`build(session) -> dict`，输入是 onboarding
   会话记录（含照片资产、手动信息、偏好轴、问卷答案），输出是报告数据契约
   定义的 dict。
2. 调用 `register_report_builder()` 注册（或直接替换 `default_report_builder`）。

约束：
- 输入 `session` 是内部 snake_case 会话记录，可用字段：
  `photos`（face/body 资产与状态）、`manual`（skin/faceShape/bodyShape）、
  `preferences`（axes/palette）、`vibe`（问卷答案）、`locale`。
- 输出 dict 的字段名与报告数据契约一致（camelCase，如 imageUrl）；
  未返回的顶层字段前端会使用 Figma 默认数据。
- 图片地址使用本站静态路径或完整 HTTPS URL。
- builder 抛异常会把报告任务标记为 failed（report.generation_failed），
  前端会引导用户返回问卷页重试。
"""

from __future__ import annotations

import os
from typing import Any, Callable

from app import selfit_persona, selfit_recommend
from app.selfit_persona import PERSONAS

# ---------------------------------------------------------------------------
# 报告展示配置（文案与色板：适合色为主 + 偏好色点缀）
# ---------------------------------------------------------------------------

# 每肤色适合色板（肤色×穿搭妆发映射「四、肤色×穿搭妆发映射」翻译为色值）。
SKIN_COLOR_SWATCHES: dict[str, list[tuple[str, str]]] = {
    "冷白肤": [("雾霭蓝", "#a8bcc4"), ("冷雾灰", "#c9cdd4"), ("薄荷绿", "#b7d4c3"), ("藏蓝", "#2f4a57"), ("银灰紫", "#c5c1d6")],
    "暖白肤": [("奶油白", "#f2e8d5"), ("燕麦色", "#d9c7a7"), ("浅驼色", "#c8a882"), ("蜜橘", "#e8a87c"), ("暖棕", "#8a5a3b")],
    "中性自然肤": [("米白", "#f5f0e8"), ("燕麦色", "#d9c7a7"), ("鼠尾草绿", "#9caf88"), ("雾霭蓝", "#a8bcc4"), ("陶土橘", "#b56b4e")],
    "暖黄肤": [("姜黄", "#d9a441"), ("焦糖", "#b07a45"), ("砖红", "#a35041"), ("橄榄绿", "#7a7a52"), ("深棕", "#5c4433")],
    "橄榄肤": [("灰绿", "#8a9a8b"), ("松柏绿", "#2f4a3e"), ("米灰", "#c8c6bd"), ("茄紫", "#6b4e71"), ("深藏蓝", "#26344a")],
    "小麦色": [("象牙白", "#f2ede4"), ("松石蓝", "#3e8e9e"), ("酒红", "#7b2d3b"), ("驼色", "#b08a5e"), ("曜石黑", "#1f1f1f")],
}

# 用户偏好色板 → 点缀色（大面积适合色 + 1~2 个偏好色点缀）。
PALETTE_ACCENTS: dict[str, tuple[str, str]] = {
    "mono": ("石墨黑", "#141414"),
    "earth": ("赤陶棕", "#8a4b2a"),
    "ocean": ("深海蓝", "#2f4a57"),
    "jewel": ("宝石红", "#7c2128"),
    "bright": ("霓虹粉", "#ff4d6d"),
    "pastel": ("粉雾", "#f3d3dc"),
}

# 体型建议文案（体型×穿搭结构映射翻译为用户语言）。
BODY_ADVICE = {
    "梨型": "视觉重心放上身，高腰线拉比例，下装保持利落纵向线条",
    "倒三角型": "视觉重心移到下半身，自然腰线平衡肩部量感",
    "沙漏型": "贴身合体剪裁放大腰臀比优势，突出自然腰线",
    "矩型": "用腰线与廓形制造曲线或保持利落直线条，两者都好看",
    "苹果型": "胸下腰线与纵向线条拉长身形，腹部保持舒适空间",
}

DEFAULT_ADVICE = [
    "先穿对适合色，再用偏好色小面积点缀",
    "围绕主人格建立核心衣橱，次人格风格用来做变化",
]

SOURCE_BLOCK = {
    "name": "小红书",
    "copy": "已为你筛选真实用户笔记",
    "avatars": {
        "imageUrl": "/static/selfit/assets/report-user-avatar-stack@4x.png",
        "alt": "3 位真实用户头像",
    },
}


def content_url(path: str) -> str:
    """把内容池相对路径解析为 CDN 完整 URL。

    报告 builder 中的图片字段（makeup/hair/outfits 的 imageUrl 等）建议返回
    内容池相对路径（如 "report/v1/makeup-01.webp"），经本函数转换：
    配置了 SELFIT_CONTENT_CDN_BASE_URL 时返回 CDN 完整地址，前端直连 CDN；
    未配置时原样返回（兼容本站静态路径或完整 URL）。
    """

    text = str(path or "")
    if not text or text.startswith(("http://", "https://", "/")):
        return text
    base = os.getenv("SELFIT_CONTENT_CDN_BASE_URL", "").rstrip("/")
    if not base:
        return text
    return f"{base}/{text.lstrip('/')}"


ReportBuilder = Callable[[dict[str, Any]], dict[str, Any]]


def _require_persona_inputs(session: dict[str, Any]) -> None:
    """分型核心输入全缺时让任务显式失败，而不是输出一份无意义报告。"""

    if not (session.get("preferences") or {}) and not (session.get("vibe") or {}):
        raise ValueError("report inputs missing: preferences and vibe are both empty")


def _colors_block(skin: str | None, palette: Any) -> list[dict[str, str]]:
    swatches = list(SKIN_COLOR_SWATCHES.get(skin or "", SKIN_COLOR_SWATCHES["中性自然肤"]))
    accent = PALETTE_ACCENTS.get(str(palette)) if palette else None
    if accent is not None:
        # 报告固定展示 5 个槽位：4 个肤色适合色 + 1 个用户偏好点缀色。
        swatches = swatches[:4] + [accent]
    return [{"name": name, "value": value} for name, value in swatches[:5]]


def _advice_block(body_shape: str | None, palette: Any, skin: str | None,
                  persona: Any, vector: dict[str, Any]) -> list[str]:
    advice: list[str] = []
    if body_shape and body_shape in BODY_ADVICE:
        advice.append(BODY_ADVICE[body_shape])
    if body_shape == "矩型":
        branch = selfit_persona.rectangle_body_branch(vector)
        if branch == "soft_curve":
            advice.append("你的风格偏柔和，矩型身材适合高腰收腰剪裁，自然营造曲线")
        else:
            advice.append("你的风格偏利落，矩型身材适合直筒宽松剪裁，弱化腰线更高级")
    if palette and skin and str(palette) in PALETTE_ACCENTS:
        advice.append("大面积穿适合色，再用偏好色做 1~2 处点缀")
    if not advice:
        advice = list(DEFAULT_ADVICE)
    advice.append(f"你的核心风格是「{persona.signature}」，优先围绕它建立穿搭主线")
    return advice[:3]


def default_report_builder(session: dict[str, Any]) -> dict[str, Any]:
    """真实报告生成：分型 → 静态映射 + 穿搭重排 → 契约数据。"""

    _require_persona_inputs(session)

    vector = selfit_persona.build_user_vector(session)
    classification = selfit_persona.classify_persona(vector)
    persona = PERSONAS[classification["primary_persona"]]
    secondary = classification["secondary_persona"]

    suit = selfit_recommend.resolve_suit_profile(session)
    rectangle_branch = selfit_persona.rectangle_body_branch(vector)
    pool = selfit_recommend.content_pool()

    makeup_key = selfit_recommend.makeup_static_key(suit["skin"], vector["regional_style"])
    hair_key = selfit_recommend.hair_static_key(suit["skin"], suit["face_shape"])

    outfits = selfit_recommend.recommend_outfits(
        pool,
        primary=persona.code,
        secondary=secondary,
        regional_style=vector["regional_style"],
        primary_region=persona.primary_region,
        compatible_regions=persona.compatible_regions,
        body_shape=suit["body_shape"],
        rectangle_branch=rectangle_branch,
        skin=suit["skin"],
    )

    makeup = [
        {
            "name": str(item.get("name") or "妆容参考"),
            "byline": str(item.get("byline") or ""),
            "imageUrl": content_url(str(item.get("imageUrl") or "")),
            "alt": str(item.get("alt") or item.get("name") or "妆容参考"),
        }
        for item in selfit_recommend.static_entries(pool, "makeup", makeup_key)
    ]
    hair = [
        {
            "name": str(item.get("name") or "发型参考"),
            "byline": str(item.get("byline") or ""),
            "imageUrl": content_url(str(item.get("imageUrl") or "")),
            "alt": str(item.get("alt") or item.get("name") or "发型参考"),
        }
        for item in selfit_recommend.static_entries(pool, "hair", hair_key)
    ]
    outfit_cards = [
        {
            "badge": str(item.get("badge") or "精选"),
            "title": str(item.get("title") or "穿搭参考"),
            "description": str(item.get("description") or ""),
            "imageUrl": content_url(str(item.get("imageUrl") or "")),
            "alt": str(item.get("alt") or item.get("title") or "穿搭参考"),
            "author": str(item.get("author") or ""),
            "sourceUrl": str(item.get("sourceUrl") or ""),
        }
        for item in outfits
    ]

    report: dict[str, Any] = {
        # 前端以 typeId 加载完整人格兜底模板；SUIT 只覆盖本次真实算出的非空字段。
        "typeId": persona.code.lower(),
        "templateVersion": "2026.08.assets-v1",
        "eyebrow": persona.code,
        "title": persona.name,
        "traits": list(persona.traits),
        "colors": _colors_block(suit["skin"], (session.get("preferences") or {}).get("palette")),
        "advice": _advice_block(suit["body_shape"], (session.get("preferences") or {}).get("palette"),
                                suit["skin"], persona, vector),
    }
    # 空数组不能覆盖 TYPE 模板。拿到真实 SUIT 数据后才覆盖对应版块。
    if makeup:
        report["makeup"] = makeup
    if hair:
        report["hair"] = hair
    if outfit_cards:
        report["source"] = dict(SOURCE_BLOCK)
        report["outfits"] = outfit_cards
    return report


_builder: ReportBuilder = default_report_builder


def register_report_builder(builder: ReportBuilder) -> None:
    global _builder
    _builder = builder


def build_report(session: dict[str, Any]) -> dict[str, Any]:
    report = _builder(session)
    if not isinstance(report, dict):
        raise TypeError("report builder must return a dict")
    return report
