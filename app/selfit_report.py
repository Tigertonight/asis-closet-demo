"""selfit onboarding 报告内容生成的算法接口层。

报告渲染契约见 docs/SELFIT_REPORT_DATA_CONTRACT.md；任务生命周期见
docs/SELFIT_BACKEND_INTEGRATION.md 4.6 / 4.7 节；人格分型口径见
app/selfit_persona.py。报告内容固定读取前后端共用的人格默认模板，不再根据
肤色、脸型、体型、次人格或地域风格执行个性化选择与排序。

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

import copy
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from app import selfit_persona

PERSONALITY_TEMPLATE_PATH = (
    Path(__file__).resolve().parent
    / "static"
    / "selfit"
    / "data"
    / "personality-report-templates.v1.json"
)

ReportBuilder = Callable[[dict[str, Any]], dict[str, Any]]


@lru_cache(maxsize=1)
def _personality_template_catalog() -> dict[str, Any]:
    """读取与前端共用的人格默认模板，避免报告内容出现两套口径。"""

    payload = json.loads(PERSONALITY_TEMPLATE_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("types"), dict):
        raise ValueError("personality report template catalog is invalid")
    return payload


def _template_card(item: dict[str, Any]) -> dict[str, Any]:
    image = item.get("image") if isinstance(item.get("image"), dict) else {}
    return {
        "id": str(item.get("id") or ""),
        "name": str(item.get("name") or ""),
        "byline": str(item.get("byline") or ""),
        "sourceUrl": str(item.get("sourceUrl") or ""),
        "imageUrl": str(image.get("src") or ""),
        "alt": str(image.get("alt") or item.get("name") or ""),
    }


def default_personality_report(persona_code: str) -> dict[str, Any]:
    """把指定人格的默认模板转换为报告契约，不做个性化计算或内容排序。"""

    catalog = _personality_template_catalog()
    type_id = str(persona_code or "").lower()
    template = (catalog.get("types") or {}).get(type_id)
    if not isinstance(template, dict):
        raise ValueError(f"personality report template missing: {type_id}")

    metadata = template.get("metadata") if isinstance(template.get("metadata"), dict) else {}
    hero = template.get("hero") if isinstance(template.get("hero"), dict) else {}
    colors = template.get("colors") if isinstance(template.get("colors"), dict) else {}
    recommendations = (
        template.get("recommendations")
        if isinstance(template.get("recommendations"), dict)
        else {}
    )
    outfits = (
        recommendations.get("outfits")
        if isinstance(recommendations.get("outfits"), dict)
        else {}
    )
    conclusion = (
        template.get("conclusion")
        if isinstance(template.get("conclusion"), dict)
        else {}
    )
    render_rules = catalog.get("renderRules") if isinstance(catalog.get("renderRules"), dict) else {}
    color_rules = render_rules.get("colors") if isinstance(render_rules.get("colors"), dict) else {}
    color_limit = int(colors.get("renderLimit") or color_rules.get("limit") or 5)

    report = {
        "typeId": type_id,
        "templateVersion": str(catalog.get("templateVersion") or ""),
        "title": str(metadata.get("name") or ""),
        "eyebrow": str(metadata.get("code") or persona_code or ""),
        "traits": copy.deepcopy(template.get("keywords") or []),
        "summary": str(template.get("summary") or ""),
        "heroImage": copy.deepcopy(hero.get("image") or {}),
        "illustration": {},
        "colors": copy.deepcopy((colors.get("items") or [])[:color_limit]),
        "makeup": [_template_card(item) for item in recommendations.get("makeup") or []],
        "hair": [_template_card(item) for item in recommendations.get("hair") or []],
        "source": copy.deepcopy(outfits.get("source") or {}),
        "outfitSummary": str(outfits.get("summary") or ""),
        "outfits": [_template_card(item) for item in outfits.get("items") or []],
        "adviceIntro": str(conclusion.get("intro") or ""),
        "advice": copy.deepcopy(conclusion.get("points") or []),
    }
    return report


def _require_persona_inputs(session: dict[str, Any]) -> None:
    """分型核心输入全缺时让任务显式失败，而不是输出一份无意义报告。"""

    if not (session.get("preferences") or {}) and not (session.get("vibe") or {}):
        raise ValueError("report inputs missing: preferences and vibe are both empty")


def default_report_builder(session: dict[str, Any]) -> dict[str, Any]:
    """真实报告生成：只计算人格类型，内容完整使用该人格默认模板。"""

    _require_persona_inputs(session)

    vector = selfit_persona.build_user_vector(session)
    classification = selfit_persona.classify_persona(vector)
    return default_personality_report(classification["primary_persona"])


_builder: ReportBuilder = default_report_builder


def register_report_builder(builder: ReportBuilder) -> None:
    global _builder
    _builder = builder


def build_report(session: dict[str, Any]) -> dict[str, Any]:
    report = _builder(session)
    if not isinstance(report, dict):
        raise TypeError("report builder must return a dict")
    return report
