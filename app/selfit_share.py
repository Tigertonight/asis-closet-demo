"""selfit 报告分享图的合成接口层。

契约见 docs/SELFIT_BACKEND_INTEGRATION.md 4.9 节：
`POST /api/v1/selfit/reports/{id}/share-assets`。

算法/设计接入说明
-----------------
接口层只依赖本模块暴露的稳定抽象，接入方只需要：

1. 实现一个 `ShareRenderer`：`render(report, slide_index, channel, image_format) -> bytes`，
   输入报告数据契约 dict、轮播页序号（0/1/2）、渠道展示值和图片格式，
   输出编码后的图片字节。
2. 调用 `register_share_renderer()` 注册（或直接替换 `default_share_renderer`）。

约束：
- `report` 是报告数据契约 dict（camelCase 字段，可能为空 dict，需容错默认值）。
- `slide_index` 只会是 0/1/2：0 对应标题+特质卡，1 对应色卡，2 对应推荐图卡。
- `channel` 是契约展示值：保存单张 | 发笔记 | 微信好友 | 朋友圈。
- renderer 抛异常会让接口返回 500 `share.render_failed`，请对缺失字段做容错。
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageDraw, ImageFont

SHARE_CHANNELS = frozenset({"保存单张", "发笔记", "微信好友", "朋友圈"})
SHARE_FORMATS = frozenset({"png"})
SHARE_SLIDE_COUNT = 3

CARD_WIDTH = 1080
CARD_HEIGHT = 1440
BACKGROUND_COLOR = "#fff5f0"
ACCENT_COLOR = "#ff4f86"
TEXT_PRIMARY = "#3a2d2d"
TEXT_SECONDARY = "#8a7676"

_FONT_CANDIDATES = (
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
)

ShareRenderer = Callable[[dict[str, Any], int, str, str], bytes]


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in _FONT_CANDIDATES:
        if Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _hex_to_rgb(value: str, fallback: tuple[int, int, int] = (200, 196, 135)) -> tuple[int, int, int]:
    text = str(value or "").strip().lstrip("#")
    if len(text) == 6:
        try:
            return tuple(int(text[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
        except ValueError:
            pass
    return fallback


def _draw_centered(draw: ImageDraw.ImageDraw, y: int, text: str, font: Any, color: str) -> int:
    box = draw.textbbox((0, 0), text, font=font)
    draw.text(((CARD_WIDTH - (box[2] - box[0])) / 2, y), text, font=font, fill=color)
    return y + (box[3] - box[1])


def default_share_renderer(report: dict[str, Any], slide_index: int, channel: str, image_format: str) -> bytes:
    """默认分享卡合成：温暖浅色底 + 标题/特质/色板，对齐报告数据契约的三张轮播卡。"""

    report = report or {}
    title = str(report.get("title") or "selfit 风格报告")
    traits = [str(item) for item in (report.get("traits") or [])][:3]
    colors = [item for item in (report.get("colors") or []) if isinstance(item, dict)][:5]

    image = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), BACKGROUND_COLOR)
    draw = ImageDraw.Draw(image)
    eyebrow_font = _load_font(40)
    title_font = _load_font(96)
    body_font = _load_font(48)

    _draw_centered(draw, 240, str(report.get("eyebrow") or "SELFIT REPORT"), eyebrow_font, ACCENT_COLOR)
    bottom = _draw_centered(draw, 340, title, title_font, TEXT_PRIMARY)

    if slide_index == 0 and traits:
        y = bottom + 120
        for trait in traits:
            _draw_centered(draw, y, f"· {trait} ·", body_font, TEXT_SECONDARY)
            y += 96
    elif slide_index == 1 and colors:
        swatch_size = 140
        gap = 40
        total = len(colors) * swatch_size + (len(colors) - 1) * gap
        x = (CARD_WIDTH - total) / 2
        y = bottom + 160
        for item in colors:
            draw.rounded_rectangle(
                (x, y, x + swatch_size, y + swatch_size),
                radius=28,
                fill=_hex_to_rgb(str(item.get("value") or "")),
            )
            x += swatch_size + gap
        names = " / ".join(str(item.get("name") or "") for item in colors if item.get("name"))
        if names:
            _draw_centered(draw, y + swatch_size + 80, names, body_font, TEXT_SECONDARY)
    elif slide_index == 2:
        _draw_centered(draw, bottom + 140, "穿搭与妆发灵感已生成", body_font, TEXT_SECONDARY)
        _draw_centered(draw, bottom + 260, "打开 selfit 查看完整报告", body_font, TEXT_SECONDARY)

    _draw_centered(draw, CARD_HEIGHT - 200, "selfit · 我的风格报告", eyebrow_font, ACCENT_COLOR)

    buffer = io.BytesIO()
    image.save(buffer, image_format.upper())
    return buffer.getvalue()


_renderer: ShareRenderer = default_share_renderer


def register_share_renderer(renderer: ShareRenderer) -> None:
    global _renderer
    _renderer = renderer


def render_share_image(report: dict[str, Any], slide_index: int, channel: str, image_format: str) -> bytes:
    return _renderer(report, slide_index, channel, image_format)
