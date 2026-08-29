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
import re
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from PIL import Image, ImageDraw, ImageFont
import qrcode

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

PUBLIC_REPORT_FIELDS = frozenset({
    "typeId", "templateVersion", "title", "eyebrow", "traits", "summary",
    "heroImage", "illustration", "colors", "makeup", "hair", "source",
    "outfitSummary", "outfits", "adviceIntro", "advice", "personalization",
})
PUBLIC_CARD_FIELDS = frozenset({"id", "name", "byline", "sourceUrl", "imageUrl", "alt"})
PUBLIC_IMAGE_FIELDS = frozenset({"src", "alt", "width", "height", "placeholder"})


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


def _safe_public_url(value: Any) -> str:
    text = str(value or "").strip()
    if text.startswith("/static/"):
        return text
    parsed = urlparse(text)
    return text if parsed.scheme == "https" and parsed.netloc else ""


def _clean_text(value: Any, limit: int = 1200) -> str:
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(value or ""))[:limit]


def _sanitize_image(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    cleaned = {key: value.get(key) for key in PUBLIC_IMAGE_FIELDS if key in value}
    cleaned["src"] = _safe_public_url(cleaned.get("src"))
    cleaned["alt"] = _clean_text(cleaned.get("alt"), 240)
    return {key: item for key, item in cleaned.items() if item not in (None, "")}


def _sanitize_card(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    card = {key: value.get(key) for key in PUBLIC_CARD_FIELDS if key in value}
    card["id"] = _clean_text(card.get("id"), 120)
    card["name"] = _clean_text(card.get("name"), 240)
    card["byline"] = _clean_text(card.get("byline"), 240)
    card["alt"] = _clean_text(card.get("alt"), 240)
    card["sourceUrl"] = _safe_public_url(card.get("sourceUrl"))
    card["imageUrl"] = _safe_public_url(card.get("imageUrl"))
    return {key: item for key, item in card.items() if item not in (None, "")}


def sanitize_public_report(report: dict[str, Any]) -> dict[str, Any]:
    """生成可持链接公开的报告快照，严格限定为报告展示字段。"""

    source = report if isinstance(report, dict) else {}
    public: dict[str, Any] = {}
    for key in PUBLIC_REPORT_FIELDS:
        if key not in source:
            continue
        value = source[key]
        if key in {"typeId", "templateVersion", "title", "eyebrow", "summary", "outfitSummary", "adviceIntro"}:
            public[key] = _clean_text(value)
        elif key in {"traits", "advice"}:
            public[key] = [_clean_text(item, 500) for item in (value or []) if isinstance(item, (str, int, float))][:12]
        elif key == "colors":
            public[key] = [
                {
                    "id": _clean_text(item.get("id"), 120),
                    "name": _clean_text(item.get("name"), 120),
                    "value": _clean_text(item.get("value"), 24),
                }
                for item in (value or []) if isinstance(item, dict)
            ][:8]
        elif key in {"makeup", "hair", "outfits"}:
            public[key] = [_sanitize_card(item) for item in (value or []) if isinstance(item, dict)][:8]
        elif key in {"heroImage", "illustration"}:
            public[key] = _sanitize_image(value)
        elif key == "source" and isinstance(value, dict):
            avatars = value.get("avatars") if isinstance(value.get("avatars"), dict) else {}
            public[key] = {
                "name": _clean_text(value.get("name"), 120),
                "copy": _clean_text(value.get("copy"), 240),
                "avatars": {
                    "imageUrl": _safe_public_url(avatars.get("imageUrl")),
                    "alt": _clean_text(avatars.get("alt"), 240),
                },
            }
        elif key == "personalization" and isinstance(value, dict):
            public[key] = {
                item_key: _clean_text(item_value) if not isinstance(item_value, list)
                else [_clean_text(item, 500) for item in item_value[:12]]
                for item_key, item_value in value.items()
                if item_key in {"summary", "outfitSummary", "adviceIntro", "advice"}
            }
    return public


def _load_optional_image(path: Path) -> Image.Image | None:
    try:
        if path.exists():
            return Image.open(path).convert("RGBA")
    except OSError:
        pass
    return None


def _qr_image(share_url: str, box_size: int) -> Image.Image:
    qr = qrcode.QRCode(version=None, box_size=box_size, border=4)
    qr.add_data(share_url)
    qr.make(fit=True)
    return qr.make_image(fill_color="#3a0010", back_color="white").convert("RGB")


def render_public_share_qr(share_url: str) -> bytes:
    qr_image = _qr_image(share_url, box_size=8)
    canvas = Image.new("RGB", (400, 400), "white")
    canvas.paste(qr_image, ((400 - qr_image.width) // 2, (400 - qr_image.height) // 2))
    buffer = io.BytesIO()
    canvas.save(buffer, "PNG", optimize=True)
    return buffer.getvalue()


def render_public_share_cover(report: dict[str, Any], share_url: str) -> bytes:
    """生成适合社交链接卡的 600×600 方形封面，不包含用户原图。"""

    size = 600
    image = Image.new("RGB", (size, size), "#8a011b")
    draw = ImageDraw.Draw(image)
    title_font = _load_font(54)
    eyebrow_font = _load_font(24)
    body_font = _load_font(24)
    small_font = _load_font(18)
    title = _clean_text(report.get("title") or "selfit 风格报告", 22)
    eyebrow = _clean_text(report.get("eyebrow") or "SELFIT REPORT", 28).upper()
    traits = [_clean_text(item, 12) for item in (report.get("traits") or [])[:3]]

    draw.text((48, 46), "SELFIT REPORT", font=eyebrow_font, fill="#f3cad4")
    draw.text((48, 92), title, font=title_font, fill="#ffffff")
    if eyebrow:
        draw.text((50, 162), eyebrow, font=body_font, fill="#f3cad4")

    type_id = re.sub(r"[^a-z0-9_-]", "", str(report.get("typeId") or "").lower())
    asset_root = Path(__file__).resolve().parent / "static" / "selfit" / "assets"
    ornament = _load_optional_image(asset_root / "personality" / type_id / "share-ornament.webp") if type_id else None
    if ornament is not None:
        ornament.thumbnail((330, 235), Image.Resampling.LANCZOS)
        image.paste(ornament, (48 + (330 - ornament.width) // 2, 210 + (235 - ornament.height) // 2), ornament)

    if traits:
        draw.text((48, 475), " · ".join(traits), font=body_font, fill="#ffffff")
    draw.text((48, 526), "selfit · 先认识自己，再决定怎么穿", font=small_font, fill="#f3cad4")

    qr_image = _qr_image(share_url, box_size=3)
    image.paste(qr_image, (size - qr_image.width - 48, size - qr_image.height - 48))

    buffer = io.BytesIO()
    image.save(buffer, "PNG", optimize=True)
    return buffer.getvalue()
