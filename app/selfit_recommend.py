"""selfit 报告推荐层：内容池 + 妆容/发型静态映射 + 穿搭 Suit 重排。

依据文档：
- 《Selfit 十六型：输入题目 → 分型与推荐 全链路工程规格》第四节（推荐算法）；
- 《Selfit 用户特征 × 穿搭妆发标签映射方案（通用）》（标注总表、体型×
  穿搭结构映射、肤色×穿搭妆发映射、推荐计算、缺失值处理）。

内容池
------
内容池是 JSON 清单（优先使用随应用发布的 bundled 数据，兼容
outputs/selfit_content_pool/pool.json，也可用 SELFIT_CONTENT_POOL_PATH 覆盖），图片走公开 CDN（builder 里 content_url
解析相对路径）。数据资产到位前由 scripts/seed_selfit_content_pool.py
生成 mock 条目跑通链路。条目 schema 见 seed 脚本头部注释。

推荐口径（V0 定版）
-------------------
- 妆容/发型：写死静态映射。妆容 = 肤色 × 地域风格（6×5=30 套），
  发型 = 肤色 × 脸型（6×5=30 套），与人格无关。
- 穿搭：先定人格取池 → Suit 重排取 top10。
  Suit = 人格与地域风格 50% + 体型结构 30% + 肤色色彩 20%；
  任何标签「不可判断」从分母剔除、权重按比例归一化；
  降级链：多标签命中 → 单标签命中 → 稳定随机补齐。
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.storage import ROOT_DIR
from app.selfit_content_quality import apply_curation, curation_stamp, recommendable

DEFAULT_CONTENT_POOL_PATH = ROOT_DIR / "outputs" / "selfit_content_pool" / "pool.json"
BUNDLED_CONTENT_POOL_PATH = ROOT_DIR / "app" / "static" / "selfit" / "data" / "content-pool.v1.json"
BUNDLED_CONTENT_POOL_V2_PATH = ROOT_DIR / "app" / "static" / "selfit" / "data" / "content-pool.v2.published.json"
BUNDLED_CONTENT_POOL_V2_INCREMENTAL_PATH = ROOT_DIR / "app" / "static" / "selfit" / "data" / "content-pool.v2.incremental.json"

# 穿搭重排权重（用户特征×穿搭妆发标签映射方案「六、推荐计算」）。
WEIGHT_PERSONA_REGION = 0.5
WEIGHT_BODY_STRUCTURE = 0.3
WEIGHT_SKIN_COLOR = 0.2

# 人格命中为前提下的地域调节系数（地域只加分不硬过滤）。
PERSONA_GATE_RATIO = 0.6

# 每次报告返回的穿搭条数上限（报告保底 ≥10 条，取 10）。
OUTFIT_TOP_N = 10

# 妆容/发型每套内容条数（「两种妆容图片，占满 UI」）。
STATIC_SET_SIZE = 2

# 报告展示的适合色数量（适合为主 + 1 个偏好色点缀）。
COLOR_SWATCH_SIZE = 5

# ---------------------------------------------------------------------------
# SUITE 输入解析（手动纠正优先，照片推断兜底）
# ---------------------------------------------------------------------------

SKIN_OPTIONS = ("冷白肤", "暖白肤", "中性自然肤", "暖黄肤", "橄榄肤", "小麦色")
FACE_SHAPE_OPTIONS = ("椭圆脸", "圆脸", "方脸", "心形脸", "菱形脸")
BODY_SHAPE_OPTIONS = ("梨型", "倒三角型", "沙漏型", "矩型", "苹果型")

# 肤色 →（skin_lightness, skin_undertone）派生表（映射方案「一、统一口径」）。
SKIN_DERIVED = {
    "冷白肤": ("白皙", "冷调"),
    "暖白肤": ("白皙", "暖调"),
    "中性自然肤": ("自然中等", "中性"),
    "暖黄肤": ("自然中等", "暖调"),
    "橄榄肤": ("自然中等", "橄榄调"),
    "小麦色": ("深肤", "未判断"),
}

# 妆容静态表的风格列（日/韩/欧美/中/法）；轻亚、无倾向、未答回退韩系
# （清透自然最普适；后续可配置）。
MAKEUP_REGIONAL_FALLBACK = "韩系"


def _photo_attribute(session: dict[str, Any], kind: str, name: str) -> str | None:
    photo = (session.get("photos") or {}).get(kind) or {}
    label = ((photo.get("attributes") or {}).get(name) or {}).get("label")
    return str(label) if label else None


def _first_valid(value: Any, options: tuple[str, ...]) -> str | None:
    if isinstance(value, str) and value in options:
        return value
    return None


def resolve_suit_profile(session: dict[str, Any]) -> dict[str, str | None]:
    """合并手动选择与照片推断：手动纠正优先（8/24 定版）。"""

    manual = session.get("manual") or {}
    skin = _first_valid(manual.get("skin"), SKIN_OPTIONS) \
        or _first_valid(_photo_attribute(session, "face", "skin_tone"), SKIN_OPTIONS)
    face_shape = _first_valid(manual.get("faceShape"), FACE_SHAPE_OPTIONS) \
        or _first_valid(_photo_attribute(session, "face", "face_shape"), FACE_SHAPE_OPTIONS)
    body_shape = _first_valid(manual.get("bodyShape"), BODY_SHAPE_OPTIONS) \
        or _first_valid(_photo_attribute(session, "body", "body_shape"), BODY_SHAPE_OPTIONS)
    return {"skin": skin, "face_shape": face_shape, "body_shape": body_shape}


def skin_derived(skin: str | None) -> tuple[str | None, str | None]:
    return SKIN_DERIVED.get(skin or "", (None, None))


# ---------------------------------------------------------------------------
# 内容池
# ---------------------------------------------------------------------------

STRUCTURE_KEYS = ("visual_weight", "waistline", "tummy_space", "line_direction")
COLOR_KEYS = ("temperature", "lightness", "saturation")


class ContentPool:
    """内容池清单读取（mtime 缓存，热替换 pool.json 即时生效）。"""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._mtime: float | None = None
        self._curation_mtime: int | None = None
        self._data: dict[str, Any] = {"outfits": [], "makeup": {}, "hair": {}}

    def _load(self) -> dict[str, Any]:
        try:
            mtime = self._path.stat().st_mtime
        except OSError:
            return self._data
        with self._lock:
            editorial_mtime = curation_stamp()
            if self._mtime == mtime and self._curation_mtime == editorial_mtime:
                return self._data
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return self._data
            if isinstance(data, dict):
                data.setdefault("outfits", [])
                data.setdefault("makeup", {})
                data.setdefault("hair", {})
                self._data = apply_curation(data) if data.get("schemaVersion") == "2.0" else data
                self._mtime = mtime
                self._curation_mtime = editorial_mtime
        return self._data

    @property
    def outfits(self) -> list[dict[str, Any]]:
        return [item for item in self.all_outfits if recommendable(item)]

    @property
    def all_outfits(self) -> list[dict[str, Any]]:
        """Includes editorial holds for saved-look/history resolution only."""
        items = self._load()["outfits"]
        return [item for item in items if isinstance(item, dict)]

    @property
    def garments(self) -> list[dict[str, Any]]:
        items = self._load().get("garments", [])
        return [item for item in items if isinstance(item, dict)]

    @property
    def metadata(self) -> dict[str, Any]:
        data = self._load()
        return {
            "schemaVersion": data.get("schemaVersion"),
            "contentVersion": data.get("contentVersion"),
            "status": data.get("status"),
            "releaseMode": data.get("releaseMode"),
            "publication": data.get("publication") or {},
            "curation": data.get("curation_summary") or {},
        }

    def static_set(self, section: str, key: str) -> list[dict[str, Any]]:
        items = self._load().get(section, {}).get(key, [])
        if not isinstance(items, list):
            return []
        return [item for item in items if isinstance(item, dict)][:STATIC_SET_SIZE]


_POOL_SINGLETONS: dict[str, ContentPool] = {}


def content_pool() -> ContentPool:
    configured = os.getenv("SELFIT_CONTENT_POOL_PATH", "").strip()
    version = os.getenv("SELFIT_CONTENT_POOL_VERSION", "auto").strip().lower()
    if configured:
        path = configured
    elif version == "v1":
        path = str(BUNDLED_CONTENT_POOL_PATH if BUNDLED_CONTENT_POOL_PATH.exists() else DEFAULT_CONTENT_POOL_PATH)
    elif version in {"auto", "v2", "v2-full"} and _published_v2_ready(BUNDLED_CONTENT_POOL_V2_PATH):
        path = str(BUNDLED_CONTENT_POOL_V2_PATH)
    elif version in {"auto", "v2", "incremental", "v2-incremental"} and _incremental_v2_ready(BUNDLED_CONTENT_POOL_V2_INCREMENTAL_PATH):
        path = str(BUNDLED_CONTENT_POOL_V2_INCREMENTAL_PATH)
    elif BUNDLED_CONTENT_POOL_PATH.exists():
        # 正式导入数据随应用发布；outputs 路径继续兼容 seed/mock 与旧环境。
        path = str(BUNDLED_CONTENT_POOL_PATH)
    else:
        path = str(DEFAULT_CONTENT_POOL_PATH)
    pool = _POOL_SINGLETONS.get(path)
    if pool is None:
        pool = ContentPool(Path(path))
        _POOL_SINGLETONS[path] = pool
    return pool


def _published_v2_ready(path: Path) -> bool:
    """Require useful curated coverage, not merely a raw 1,200-row manifest."""
    try:
        return _published_v2_ready_at(str(path), path.stat().st_mtime_ns, curation_stamp())
    except OSError:
        return False


@lru_cache(maxsize=8)
def _published_v2_ready_at(path: str, source_stamp: int, editorial_stamp: int) -> bool:

    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if data.get("schemaVersion") != "2.0" or data.get("status") != "published":
        return False
    data = apply_curation(data)
    garments = data.get("garments") or []
    outfits = [item for item in data.get("outfits") or [] if isinstance(item, dict) and recommendable(item)]
    if len(garments) < 600 or len(outfits) < 160:
        return False
    counts = Counter(item.get("primary_persona") for item in outfits if isinstance(item, dict))
    if any(counts[code] < 10 for code in ("MUTE", "ICED", "HEIR", "EASE", "MELT", "WABI", "FLOU", "NEON", "EDGE", "BOLT", "FILM", "JADE", "LOOP", "NOIR", "VOID", "OOPS")):
        return False
    return all((item.get("assets") or {}).get("rights_status") == "owned" for item in garments if isinstance(item, dict))


def _incremental_v2_ready(path: Path) -> bool:
    """Accept a reviewed V2 delta only when its manifest is internally complete."""

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if data.get("schemaVersion") != "2.0" or data.get("status") != "published" or data.get("releaseMode") != "incremental":
        return False
    publication = data.get("publication") or {}
    outfits = [item for item in data.get("outfits") or [] if isinstance(item, dict)]
    garments = [item for item in data.get("garments") or [] if isinstance(item, dict)]
    garment_by_id = {str(item.get("id") or ""): item for item in garments}
    outfit_by_id = {str(item.get("id") or ""): item for item in outfits}
    garment_ids = publication.get("incrementalGarmentIds") or []
    outfit_ids = publication.get("incrementalOutfitIds") or []
    if not garment_ids or not outfit_ids or len(garment_ids) != len(set(garment_ids)) or len(outfit_ids) != len(set(outfit_ids)):
        return False
    if publication.get("incrementalGarmentCount") != len(garment_ids) or publication.get("incrementalOutfitCount") != len(outfit_ids):
        return False
    if publication.get("baselineOutfitCount", 0) + len(outfit_ids) != len(outfits):
        return False
    if any(item_id not in garment_by_id for item_id in garment_ids) or any(item_id not in outfit_by_id for item_id in outfit_ids):
        return False
    for item_id in garment_ids:
        garment = garment_by_id[item_id]
        if (garment.get("assets") or {}).get("rights_status") != "owned":
            return False
        if (garment.get("production") or {}).get("qa_status") != "approved":
            return False
        if (garment.get("annotation") or {}).get("status") != "published":
            return False
        image_url = str((garment.get("assets") or {}).get("image_url") or "")
        if not image_url or not _bundled_asset_exists(image_url):
            return False
    published_garments = set(garment_ids)
    for item_id in outfit_ids:
        outfit = outfit_by_id[item_id]
        if (outfit.get("assets") or {}).get("rights_status") != "owned":
            return False
        if (outfit.get("annotation") or {}).get("status") != "published":
            return False
        image_url = str((outfit.get("assets") or {}).get("image_url") or "")
        if not image_url or not _bundled_asset_exists(image_url):
            return False
        if not set(outfit.get("garment_ids") or []).issubset(published_garments):
            return False
    return True


def _bundled_asset_exists(public_path: str) -> bool:
    if public_path.startswith("/static/"):
        return (ROOT_DIR / "app" / public_path.lstrip("/")).is_file()
    return Path(public_path).is_file()


def reset_content_pool_cache() -> None:
    _POOL_SINGLETONS.clear()


# ---------------------------------------------------------------------------
# 妆容 / 发型静态映射（V0 写死：肤色×风格 / 肤色×脸型）
# ---------------------------------------------------------------------------

MAKEUP_REGIONAL_KEYS = ("日系", "韩系", "欧美系", "中式", "法式")


def makeup_static_key(skin: str | None, regional_style: str | None) -> str:
    """妆容行键 = 肤色 × 地域风格；轻亚/无倾向/未答回退韩系。"""

    region = regional_style if regional_style in MAKEUP_REGIONAL_KEYS else MAKEUP_REGIONAL_FALLBACK
    skin_label = skin if skin in SKIN_OPTIONS else "中性自然肤"
    return f"{skin_label}|{region}"


def hair_static_key(skin: str | None, face_shape: str | None) -> str:
    """发型行键 = 肤色 × 脸型；缺省回退中性自然肤 × 椭圆脸。"""

    skin_label = skin if skin in SKIN_OPTIONS else "中性自然肤"
    face_label = face_shape if face_shape in FACE_SHAPE_OPTIONS else "椭圆脸"
    return f"{skin_label}|{face_label}"


def static_entries(pool: ContentPool, section: str, key: str) -> list[dict[str, Any]]:
    entries = []
    for item in pool.static_set(section, key):
        if item.get("imageUrl"):
            entries.append(item)
    return entries


# ---------------------------------------------------------------------------
# 体型 × 穿搭结构偏好（30% 部分）
# ---------------------------------------------------------------------------

# 命中得分：优先 100 / 可接受 70~90 / 未命中 20（不硬过滤）。
# 矩型按人格分叉（柔和曲线 vs 简约利落），由 selfit_persona.rectangle_body_branch 判定。
BODY_STRUCTURE_PREFERENCES: dict[str, dict[str, dict[str, float]]] = {
    "梨型": {
        "visual_weight": {"上半身": 100, "上下均衡": 70},
        "waistline": {"高腰": 100, "自然腰": 90},
        "tummy_space": {"合体不贴": 100},
        "line_direction": {"纵向": 100, "无明显": 80},
    },
    "倒三角型": {
        "visual_weight": {"下半身": 100, "上下均衡": 70},
        "waistline": {"自然腰": 100, "高腰": 90},
        "tummy_space": {"合体不贴": 100},
        "line_direction": {"纵向": 100, "无明显": 80},
    },
    "沙漏型": {
        "visual_weight": {"上下均衡": 100},
        "waistline": {"自然腰": 100, "高腰": 80},
        "tummy_space": {"贴身": 100, "合体不贴": 90},
        "line_direction": {"无明显": 100, "纵向": 80},
    },
    "矩型:soft_curve": {
        "visual_weight": {"上下均衡": 100},
        "waistline": {"高腰": 100, "自然腰": 90},
        "tummy_space": {"合体不贴": 100, "宽松": 60},
        "line_direction": {"纵向": 100, "无明显": 70},
    },
    "矩型:clean_line": {
        "visual_weight": {"上下均衡": 100},
        "waistline": {"无腰线": 100, "自然腰": 90, "高腰": 50},
        "tummy_space": {"宽松": 100, "合体不贴": 90},
        "line_direction": {"纵向": 100, "无明显": 70},
    },
    "苹果型": {
        "visual_weight": {"上下均衡": 100, "下半身": 90},
        "waistline": {"无腰线": 100, "胸下腰线": 100, "自然腰": 80},
        "tummy_space": {"合体不贴": 100, "宽松": 100},
        "line_direction": {"纵向": 100},
    },
}

STRUCTURE_MISS_SCORE = 20.0


def body_structure_key(body_shape: str | None, rectangle_branch: str | None) -> str | None:
    if body_shape == "矩型" and rectangle_branch:
        return f"矩型:{rectangle_branch}"
    return body_shape


def body_structure_score(outfit: dict[str, Any], body_shape: str | None,
                         rectangle_branch: str | None) -> float | None:
    """体型结构栏得分（0-100）；笔记结构标签缺失的子项从分母剔除。"""

    preferences = BODY_STRUCTURE_PREFERENCES.get(
        body_structure_key(body_shape, rectangle_branch) or ""
    )
    if preferences is None:
        return None
    structure = outfit.get("structure") or {}
    total = 0.0
    count = 0
    for key in STRUCTURE_KEYS:
        label = structure.get(key)
        if not label or label == "未判断":
            continue
        mapping = preferences.get(key) or {}
        total += mapping.get(str(label), STRUCTURE_MISS_SCORE)
        count += 1
    if count == 0:
        # 人工内容库已有直接体型标签时优先复用；结构四标签补齐后会自然走上面的细粒度评分。
        body_types = outfit.get("body_types") or []
        if isinstance(body_types, str):
            body_types = [item.strip() for item in body_types.split("|") if item.strip()]
        if body_shape and isinstance(body_types, list) and body_types:
            return 100.0 if body_shape in body_types else STRUCTURE_MISS_SCORE
        return None
    return total / count


# ---------------------------------------------------------------------------
# 肤色 × 穿搭配色偏好（20% 部分）
# ---------------------------------------------------------------------------

# 命中得分：适合 100 / 可接受 70~90 / 未命中 30；「不限」子项剔除（分母不含）。
SKIN_COLOR_PREFERENCES: dict[str, dict[str, dict[str, float]]] = {
    "冷白肤": {
        "temperature": {"冷调": 100, "中性": 90, "冷暖混合": 60},
        "lightness": {"浅色": 100, "中等": 90, "深色": 50},
        "saturation": {"低饱和": 100, "中饱和": 90, "无彩": 90, "高饱和": 40},
    },
    "暖白肤": {
        "temperature": {"暖调": 100, "中性": 90, "冷暖混合": 60},
        "lightness": {"浅色": 100, "中等": 90, "深色": 50},
        "saturation": {"低饱和": 100, "中饱和": 90, "无彩": 90, "高饱和": 40},
    },
    "中性自然肤": {
        "temperature": {"中性": 100, "冷暖混合": 100, "冷调": 80, "暖调": 80},
        "lightness": None,
        "saturation": None,
    },
    "暖黄肤": {
        "temperature": {"暖调": 100, "中性": 90, "冷暖混合": 60},
        "lightness": {"中等": 100, "深色": 90, "浅色": 60, "深浅对比": 90},
        "saturation": {"中饱和": 100, "低饱和": 80, "高饱和": 50},
    },
    "橄榄肤": {
        "temperature": {"中性": 100, "冷调": 90, "冷暖混合": 70, "暖调": 40},
        "lightness": {"中等": 100, "深色": 90, "浅色": 60},
        "saturation": {"低饱和": 100, "中饱和": 90, "无彩": 90, "高饱和": 40},
    },
    "小麦色": {
        "temperature": {"中性": 100, "冷调": 80, "暖调": 80, "冷暖混合": 70},
        "lightness": None,
        "saturation": {"中饱和": 100, "高饱和": 90, "低饱和": 70, "无彩": 80},
    },
}

COLOR_MISS_SCORE = 30.0


def skin_color_score(outfit: dict[str, Any], skin: str | None) -> float | None:
    """肤色色彩栏得分（0-100）；「不可判断」标签与「不限」子项从分母剔除。"""

    preferences = SKIN_COLOR_PREFERENCES.get(skin or "")
    if preferences is None:
        return None
    color = outfit.get("color") or {}
    total = 0.0
    count = 0
    for key in COLOR_KEYS:
        mapping = preferences.get(key)
        label = color.get(key)
        if mapping is None or not label or label == "未判断":
            continue
        total += mapping.get(str(label), COLOR_MISS_SCORE)
        count += 1
    if count == 0:
        return None
    return total / count


# ---------------------------------------------------------------------------
# 人格与地域栏（50% 部分）
# ---------------------------------------------------------------------------

def persona_match_score(outfit: dict[str, Any], primary: str, secondary: str | None) -> float:
    """人格匹配分：主=内容主 100 / 主命中内容次 80 / 次=内容主 80 / 次命中内容次 60。"""

    outfit_primary = str(outfit.get("primary_persona") or "")
    outfit_secondary = outfit.get("secondary_personas") or []
    if not isinstance(outfit_secondary, list):
        outfit_secondary = []
    scores = [0.0]
    if outfit_primary:
        if outfit_primary == primary:
            scores.append(100.0)
        elif secondary and outfit_primary == secondary:
            scores.append(80.0)
    if outfit_secondary:
        if primary in outfit_secondary:
            scores.append(80.0)
        if secondary and secondary in outfit_secondary:
            scores.append(60.0)
    return max(scores)


def region_match_score(outfit: dict[str, Any], regional_style: str | None,
                       primary_region: str, compatible_regions: tuple[str, ...]) -> float | None:
    """地域匹配分：命中笔记主地域 100 / 兼容 70 / 不匹配 0；笔记无地域标签剔除。"""

    outfit_regions = outfit.get("regional_styles") or outfit.get("regional_style")
    if isinstance(outfit_regions, str):
        outfit_regions = [item.strip() for item in outfit_regions.split("|") if item.strip()]
    if not isinstance(outfit_regions, list):
        outfit_regions = [str(outfit_regions)] if outfit_regions else []
    if not outfit_regions:
        return None
    if regional_style and regional_style in outfit_regions:
        return 100.0
    if primary_region in outfit_regions or any(item in compatible_regions for item in outfit_regions):
        return 70.0
    return 0.0


# ---------------------------------------------------------------------------
# Suit 重排与降级链
# ---------------------------------------------------------------------------

def suit_score(
    outfit: dict[str, Any],
    *,
    primary: str,
    secondary: str | None,
    regional_style: str | None,
    primary_region: str,
    compatible_regions: tuple[str, ...],
    body_shape: str | None,
    rectangle_branch: str | None,
    skin: str | None,
) -> float:
    """穿搭 Suit 适配分 = 人格与地域 50% + 体型结构 30% + 肤色色彩 20%。

    缺失栏位从分母剔除、权重按比例归一化；人格命中为前提（人格 0 分时
    人格地域栏为 0，靠降级链兜底）。
    """

    persona_score = persona_match_score(outfit, primary, secondary)
    region_score = region_match_score(outfit, regional_style, primary_region, compatible_regions)
    if region_score is None:
        persona_region = persona_score
    else:
        persona_region = persona_score * (PERSONA_GATE_RATIO + (1 - PERSONA_GATE_RATIO) * region_score / 100)

    parts: list[tuple[float, float]] = [(WEIGHT_PERSONA_REGION, persona_region)]
    body = body_structure_score(outfit, body_shape, rectangle_branch)
    if body is not None:
        parts.append((WEIGHT_BODY_STRUCTURE, body))
    color = skin_color_score(outfit, skin)
    if color is not None:
        parts.append((WEIGHT_SKIN_COLOR, color))

    weight_total = sum(weight for weight, _ in parts)
    if weight_total <= 0:
        return 0.0
    return sum(weight * score for weight, score in parts) / weight_total


def recommend_outfits(
    pool: ContentPool,
    *,
    primary: str,
    secondary: str | None,
    regional_style: str | None,
    primary_region: str,
    compatible_regions: tuple[str, ...],
    body_shape: str | None,
    rectangle_branch: str | None,
    skin: str | None,
    top_n: int = OUTFIT_TOP_N,
    scene: str | None = None,
    season: str | None = None,
    weather: str | None = None,
    visible_slots: tuple[str, ...] = (),
    recently_exposed_ids: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    """人格池 → Suit 重排 → top10。

    严格按工程规格降级：多标签命中 → 单标签命中 → 随机补齐。
    为避免用户重新打开报告时内容跳动，随机层使用人格与内容 ID
    生成稳定乱序键。
    """

    outfits = pool.outfits
    if not outfits:
        return []

    recent = set(recently_exposed_ids)

    def score(item: dict[str, Any]) -> float:
        value = suit_score(
            item,
            primary=primary,
            secondary=secondary,
            regional_style=regional_style,
            primary_region=primary_region,
            compatible_regions=compatible_regions,
            body_shape=body_shape,
            rectangle_branch=rectangle_branch,
            skin=skin,
        )
        if scene and scene in (item.get("scene_tags") or []):
            value += 8
        if season and (season in (item.get("season_tags") or []) or "四季" in (item.get("season_tags") or [])):
            value += 8
        if weather and weather in (item.get("weather_tags") or []):
            value += 5
        if str(item.get("id") or "") in recent:
            value -= 30
        return value

    def match_count(item: dict[str, Any]) -> int:
        """统计可判定且命中的人格/地域/体型/肤色标签类别数。"""

        matches = 0
        if persona_match_score(item, primary, secondary) > 0:
            matches += 1
        region = region_match_score(item, regional_style, primary_region, compatible_regions)
        if region is not None and region > 0:
            matches += 1
        body = body_structure_score(item, body_shape, rectangle_branch)
        if body is not None and body > STRUCTURE_MISS_SCORE:
            matches += 1
        color = skin_color_score(item, skin)
        if color is not None and color > COLOR_MISS_SCORE:
            matches += 1
        return matches

    def context_compatible(item: dict[str, Any]) -> bool:
        if scene and scene not in (item.get("scene_tags") or []):
            return False
        if season and season not in (item.get("season_tags") or []) and "四季" not in (item.get("season_tags") or []):
            return False
        if weather and weather not in (item.get("weather_tags") or []):
            return False
        if visible_slots and not set(visible_slots).intersection(item.get("visible_slots") or []):
            return False
        return True

    compatible = [item for item in outfits if context_compatible(item)]
    candidate_items = compatible + [item for item in outfits if item not in compatible]
    indexed = [(index, item, match_count(item)) for index, item in enumerate(candidate_items)]
    multi = [(index, item) for index, item, count in indexed if count >= 2]
    single = [(index, item) for index, item, count in indexed if count == 1]
    fallback = [(index, item) for index, item, count in indexed if count == 0]

    def ranked(items: list[tuple[int, dict[str, Any]]]) -> list[dict[str, Any]]:
        scored = [(score(item), index, item) for index, item in items]
        scored.sort(key=lambda triple: (-triple[0], triple[1]))
        return [item for _, _, item in scored]

    # 文档要求最后一层随机补齐；稳定哈希同时保证可复现与不依赖源数据顺序。
    fallback.sort(
        key=lambda pair: hashlib.sha256(
            f"{primary}|{secondary or ''}|{pair[1].get('id') or pair[0]}".encode("utf-8")
        ).digest()
    )
    ordered = ranked(multi) + ranked(single) + [item for _, item in fallback]
    selected: list[dict[str, Any]] = []
    main_item_counts: dict[str, int] = {}
    fingerprints: set[tuple[str, ...] | str] = set()
    for item in ordered:
        garment_ids = [str(value) for value in item.get("garment_ids") or []]
        slot_roles = item.get("slot_roles") or {}
        main_id = next((value for value in garment_ids if slot_roles.get(value) == "hero"), garment_ids[0] if garment_ids else "")
        # V2 recipes can be deduplicated by their actual item composition. Legacy
        # V1 cards often share one placeholder URL, so keep their stable IDs.
        fingerprint: tuple[str, ...] | str = tuple(sorted(garment_ids)) if garment_ids else str(item.get("id") or "")
        if fingerprint and fingerprint in fingerprints:
            continue
        if main_id and main_item_counts.get(main_id, 0) >= 2:
            continue
        reasons = list(item.get("recommendation_reasons") or [])
        if scene and scene in (item.get("scene_tags") or []):
            reasons.append(f"适合{scene}场景")
        if season and (season in (item.get("season_tags") or []) or "四季" in (item.get("season_tags") or [])):
            reasons.append(f"适合{season}季节")
        if visible_slots and set(visible_slots).intersection(item.get("visible_slots") or []):
            reasons.append("适配当前可见试穿部位")
        decorated = {**item, "recommendation_reasons": list(dict.fromkeys(reasons))}
        selected.append(decorated)
        fingerprints.add(fingerprint)
        if main_id:
            main_item_counts[main_id] = main_item_counts.get(main_id, 0) + 1
        if len(selected) >= top_n:
            break
    return selected
