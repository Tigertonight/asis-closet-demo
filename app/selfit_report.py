"""selfit onboarding 报告内容生成的算法接口层。

报告渲染契约见 docs/SELFIT_REPORT_DATA_CONTRACT.md；任务生命周期见
docs/SELFIT_BACKEND_INTEGRATION.md 4.6 / 4.7 节。

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


def default_report_builder(session: dict[str, Any]) -> dict[str, Any]:
    """默认占位实现：返回空报告，前端渲染 Figma 默认内容。

    算法接入前用于跑通联调链路；接入时替换为真实风格计算。
    """

    return {}


_builder: ReportBuilder = default_report_builder


def register_report_builder(builder: ReportBuilder) -> None:
    global _builder
    _builder = builder


def build_report(session: dict[str, Any]) -> dict[str, Any]:
    report = _builder(session)
    if not isinstance(report, dict):
        raise TypeError("report builder must return a dict")
    return report
