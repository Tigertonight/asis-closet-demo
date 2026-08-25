"""生成 selfit 报告内容池 mock 数据与占位图。

内容池是报告推荐用的公开静态资源清单（app/selfit_recommend.py 加载）。
数据资产到位前用本脚本生成 mock 条目跑通全链路：

- outfits：16 型人格 × 4 条（带人格/地域/结构/色彩全标签，标签从人格
  中心点语义采样，保证 Suit 重排有区分度）；
- makeup：肤色 6 × 地域 5 = 30 套（每套 2 张，V0 写死映射）；
- hair：肤色 6 × 脸型 5 = 30 套（每套 2 张，V0 写死映射）。

占位图写入 app/static/selfit/assets/content_pool/（本站静态路径，
本地验收无 404）；真实资产到位后用 scripts/upload_content_pool.py
上传公开桶并把 pool.json 里的 imageUrl 换成 CDN 相对路径
（report/v1/...），配 SELFIT_CONTENT_CDN_BASE_URL 生效。

用法：
    python scripts/seed_selfit_content_pool.py [--force]
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from colorsys import hsv_to_rgb
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.selfit_persona import DIMENSIONS, PERSONAS  # noqa: E402
from app.selfit_recommend import (  # noqa: E402
    BODY_SHAPE_OPTIONS,
    FACE_SHAPE_OPTIONS,
    MAKEUP_REGIONAL_KEYS,
    SKIN_OPTIONS,
)

OUTPUT_POOL_PATH = ROOT / "outputs" / "selfit_content_pool" / "pool.json"
IMAGE_DIR = ROOT / "app" / "static" / "selfit" / "assets" / "content_pool"
STATIC_BASE = "/static/selfit/assets/content_pool"

OUTFIT_PER_PERSONA = 4

VISUAL_WEIGHTS = ("上半身", "下半身", "上下均衡")
WAISTLINES = ("无腰线", "低腰", "自然腰", "高腰", "胸下腰线")
TUMMY_SPACES = ("贴身", "合体不贴", "宽松")
LINE_DIRECTIONS = ("横向", "无明显", "纵向")
COLOR_TEMPERATURES = ("冷调", "暖调", "中性", "冷暖混合")
COLOR_LIGHTNESS = ("浅色", "中等", "深色", "深浅对比")
COLOR_SATURATIONS = ("无彩", "低饱和", "中饱和", "高饱和")

AUTHORS = ("索贝", "板牙", "阿岚", "豆豆", "水野", "林一", "Kiko", "小满")
BADGES = ("精选", "活动", "热门", "灵感")

_TITLES = {
    "MUTE": ("静音色系通勤", "极简廓形大衣", "低饱和同色系", "利落直线叠穿"),
    "ICED": ("冷感冰面穿搭", "清冷淡彩通勤", "冷调极简套装", "冰蓝层次感"),
    "HEIR": ("老钱风针织", "经典格纹套装", "低调质感叠穿", "驼色系老钱"),
    "EASE": ("松弛法式衬衫", "慵懒针织开衫", "松弛牛仔通勤", "暖调慵懒风"),
    "MELT": ("甜感奶油穿搭", "温柔蝴蝶结", "甜妹奶咖色", "软糯毛绒感"),
    "WABI": ("侘寂自然色", "手作亚麻套装", "自然褶皱感", "朴素棉麻穿搭"),
    "FLOU": ("浪漫纱裙", "法式碎花连衣裙", "梦幻蕾丝叠穿", "造梦层次纱"),
    "NEON": ("高饱和撞色", "先锋荧光穿搭", "吸睛撞色套装", "大胆色彩实验"),
    "EDGE": ("甜辣短上衣", "轻亚辣妹穿搭", "冷感皮质混搭", "Y2K 甜辣风"),
    "BOLT": ("复古千金套装", "戏剧感泡泡袖", "缎面复古穿搭", "华丽复古裙装"),
    "FILM": ("胶片感牛仔", "复古棕调穿搭", "暖调老钱电影感", "胶片风叠穿"),
    "JADE": ("新中式盘扣", "东方玉色穿搭", "中式立领套装", "水墨感中式"),
    "LOOP": ("多场景百搭套装", "一衣多穿模板", "高完成度通勤", "反复搭配王"),
    "NOIR": ("全黑层次穿搭", "暗黑极简套装", "黑色皮质风", "深色肃杀风"),
    "VOID": ("随性混搭风", "慵懒松弛穿搭", "无风格公式穿搭", "反差混搭"),
    "OOPS": ("大胆混搭实验", "冲突感叠穿", "先锋解构穿搭", "反套路搭配"),
}

_DESCRIPTIONS = {
    "MUTE": "低饱和同色系与利落直线剪裁，安静但有力量。",
    "ICED": "冷调淡彩与精修细节，清透干净的冰面质感。",
    "HEIR": "经典单品与低调质感，时间越久越耐看。",
    "EASE": "松弛剪裁配暖调基础色，毫不费力的讲究。",
    "MELT": "奶油甜色与柔和廓形，治愈感拉满。",
    "WABI": "自然材质与朴素色系，接受不完美的安静美。",
    "FLOU": "纱、蕾丝与浪漫装饰，把日常穿成梦。",
    "NEON": "高饱和撞色与先锋单品，走到哪都是焦点。",
    "EDGE": "冷调甜辣与强轮廓，甜与酷的对撞。",
    "BOLT": "戏剧化装饰与复古缎面，人人都是主角。",
    "FILM": "暖调复古色与生活感单品，像一帧老电影。",
    "JADE": "东方结构与传统色，克制而挺拔的骨相美。",
    "LOOP": "高完成度的百搭模板，怎么搭都不出错。",
    "NOIR": "全黑层次与利落剪裁，深色里的高级感。",
    "VOID": "打破公式的随性混搭，舒服比正确重要。",
    "OOPS": "主动制造冲突的实验性搭配，意外地好看。",
}


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in (
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
    ):
        if Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _persona_palette(code: str) -> tuple[int, int, int]:
    """从人格中心点推导占位图主色（HSV → RGB）。"""

    persona = PERSONAS[code]
    saturation = persona.center["saturation"] / 100.0
    temperature = persona.center["temperature"]
    if temperature < 40:
        hue = 215  # 冷调：蓝
    elif temperature > 60:
        hue = 25   # 暖调：橙
    else:
        hue = 90   # 中性：灰绿
    hsv_s = 0.15 + saturation * 0.55
    hsv_v = 0.55 + (1 - saturation) * 0.25
    r, g, b = hsv_to_rgb(hue / 360.0, hsv_s, hsv_v)
    return int(r * 255), int(g * 255), int(b * 255)


def _render_placeholder(path: Path, size: tuple[int, int], background: tuple[int, int, int],
                        eyebrow: str, title: str) -> None:
    width, height = size
    image = Image.new("RGB", size, background)
    draw = ImageDraw.Draw(image)
    dark = tuple(max(0, channel - 70) for channel in background)
    draw.rectangle([0, 0, width, 12], fill=dark)
    draw.rectangle([0, height - 12, width, height], fill=dark)
    draw.ellipse([width - 180, height - 260, width + 60, height - 20], outline=dark, width=6)

    eyebrow_font = _font(34)
    title_font = _font(52)
    draw.text((40, height // 2 - 80), eyebrow, fill=dark, font=eyebrow_font)
    draw.text((40, height // 2 - 10), title, fill=dark, font=title_font)
    draw.text((40, height // 2 + 70), "Selfit mock 素材 · 待替换", fill=dark, font=_font(24))

    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="JPEG", quality=88)


def _sample_outfit_labels(rng: random.Random, code: str, index: int) -> dict[str, dict[str, str]]:
    """按人格中心点语义采样结构/色彩标签；留一部分随机值制造排序区分度。"""

    persona = PERSONAS[code]

    def near(value: int, options: tuple[str, ...], buckets: int) -> str:
        bucket = min(buckets - 1, max(0, int(value / (100 / buckets))))
        return options[bucket]

    if index % 4 == 3:
        # 每 4 条留 1 条完全随机，保证重排有区分度。
        return {
            "structure": {
                "visual_weight": rng.choice(VISUAL_WEIGHTS),
                "waistline": rng.choice(WAISTLINES),
                "tummy_space": rng.choice(TUMMY_SPACES),
                "line_direction": rng.choice(LINE_DIRECTIONS),
            },
            "color": {
                "temperature": rng.choice(COLOR_TEMPERATURES),
                "lightness": rng.choice(COLOR_LIGHTNESS),
                "saturation": rng.choice(COLOR_SATURATIONS),
            },
        }

    silhouette = persona.center["silhouette"]
    return {
        "structure": {
            "visual_weight": "上下均衡" if 40 <= silhouette <= 60 else (
                "上半身" if silhouette < 40 else "下半身"
            ),
            "waistline": near(persona.center["completion"], WAISTLINES, 5),
            "tummy_space": "宽松" if silhouette >= 60 else ("贴身" if silhouette <= 25 else "合体不贴"),
            "line_direction": "纵向" if persona.center["complexity"] <= 40 else rng.choice(("无明显", "横向")),
        },
        "color": {
            "temperature": near(persona.center["temperature"], COLOR_TEMPERATURES, 4),
            "lightness": near(100 - persona.center["saturation"], COLOR_LIGHTNESS, 4),
            "saturation": near(persona.center["saturation"], COLOR_SATURATIONS, 4),
        },
    }


def build_outfits(rng: random.Random) -> list[dict[str, str | list[str] | dict[str, dict[str, str]]]]:
    outfits: list[dict[str, str | list[str] | dict[str, dict[str, str]]]] = []
    for code, persona in PERSONAS.items():
        regions = [persona.primary_region, *persona.compatible_regions]
        regions = [item for item in regions if item != "无倾向"] or ["日系", "韩系", "欧美系", "中式", "法式"]
        titles = _TITLES[code]
        for index in range(OUTFIT_PER_PERSONA):
            title = f"{titles[index]} · {index + 1:02d}"
            image_name = f"outfit-{code.lower()}-{index + 1:02d}.jpg"
            _render_placeholder(
                IMAGE_DIR / image_name,
                (640, 800),
                _persona_palette(code),
                code,
                persona.name,
            )
            secondary = rng.sample(sorted(set(PERSONAS) - {code}), k=1)
            outfits.append(
                {
                    "id": f"outfit_{code.lower()}_{index + 1:02d}",
                    "title": title,
                    "description": _DESCRIPTIONS[code],
                    "author": rng.choice(AUTHORS),
                    "badge": rng.choice(BADGES),
                    "imageUrl": f"{STATIC_BASE}/{image_name}",
                    "alt": f"{persona.name}穿搭参考",
                    "primary_persona": code,
                    "secondary_personas": secondary,
                    "regional_style": rng.choice(regions),
                    **_sample_outfit_labels(rng, code, index),
                }
            )
    return outfits


def build_static_sets(rng: random.Random) -> tuple[dict[str, list[dict[str, str]]], dict[str, list[dict[str, str]]]]:
    makeup: dict[str, list[dict[str, str]]] = {}
    hair: dict[str, list[dict[str, str]]] = {}

    region_names = {"日系": "日系", "韩系": "韩系", "欧美系": "欧美", "中式": "中式", "法式": "法式"}
    for skin in SKIN_OPTIONS:
        for region in MAKEUP_REGIONAL_KEYS:
            key = f"{skin}|{region}"
            entries = []
            for slot in (1, 2):
                image_name = f"makeup-{skin}-{region}-{slot:02d}.jpg"
                name = f"{region_names[region]}感{'清透' if slot == 1 else '进阶'}妆"
                _render_placeholder(
                    IMAGE_DIR / image_name,
                    (600, 750),
                    (246, 226, 226) if slot == 1 else (238, 210, 214),
                    f"{region} · {skin}",
                    name,
                )
                entries.append(
                    {
                        "name": name,
                        "byline": f"@{rng.choice(AUTHORS)}",
                        "imageUrl": f"{STATIC_BASE}/{image_name}",
                        "alt": f"{skin}{region_names[region]}风妆容参考",
                    }
                )
            makeup[key] = entries

    face_names = {"椭圆脸": "椭圆脸", "圆脸": "圆脸", "方脸": "方脸", "心形脸": "心形脸", "菱形脸": "菱形脸"}
    for skin in SKIN_OPTIONS:
        for face in FACE_SHAPE_OPTIONS:
            key = f"{skin}|{face}"
            entries = []
            for slot in (1, 2):
                image_name = f"hair-{skin}-{face}-{slot:02d}.jpg"
                name = f"{face_names[face]}修饰{'层次' if slot == 1 else '长发'}"
                _render_placeholder(
                    IMAGE_DIR / image_name,
                    (600, 750),
                    (232, 224, 214) if slot == 1 else (222, 212, 202),
                    f"{face} · {skin}",
                    name,
                )
                entries.append(
                    {
                        "name": name,
                        "byline": f"@{rng.choice(AUTHORS)}",
                        "imageUrl": f"{STATIC_BASE}/{image_name}",
                        "alt": f"{skin}{face_names[face]}发型参考",
                    }
                )
            hair[key] = entries
    return makeup, hair


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="已存在时仍覆盖生成")
    args = parser.parse_args()

    if OUTPUT_POOL_PATH.exists() and not args.force:
        print(f"[skip] 内容池已存在: {OUTPUT_POOL_PATH}（--force 覆盖）")
        return 0

    rng = random.Random(20260825)
    outfits = build_outfits(rng)
    makeup, hair = build_static_sets(rng)

    OUTPUT_POOL_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_POOL_PATH.write_text(
        json.dumps({"outfits": outfits, "makeup": makeup, "hair": hair}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[ok] 内容池: {OUTPUT_POOL_PATH}")
    print(f"[ok] 穿搭 {len(outfits)} 条（{len(PERSONAS)} 型 × {OUTFIT_PER_PERSONA}）")
    print(f"[ok] 妆容 {len(makeup)} 套 / 发型 {len(hair)} 套")
    print(f"[ok] 占位图: {IMAGE_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
