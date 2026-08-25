from __future__ import annotations

import json
from pathlib import Path

import pytest

import app.selfit_recommend as selfit_recommend
from app.selfit_recommend import (
    ContentPool,
    hair_static_key,
    makeup_static_key,
    persona_match_score,
    recommend_outfits,
    region_match_score,
    resolve_suit_profile,
    skin_color_score,
    body_structure_score,
    suit_score,
)


def _write_pool(tmp_path: Path, pool: dict) -> Path:
    path = tmp_path / "pool.json"
    path.write_text(json.dumps(pool, ensure_ascii=False), encoding="utf-8")
    selfit_recommend.reset_content_pool_cache()
    return path


def _outfit(**overrides):
    item = {
        "id": "of_1",
        "title": "测试穿搭",
        "description": "",
        "author": "作者",
        "badge": "精选",
        "imageUrl": "/static/x.jpg",
        "alt": "alt",
        "primary_persona": "MUTE",
        "secondary_personas": ["ICED"],
        "regional_style": "日系",
        "structure": {
            "visual_weight": "上半身",
            "waistline": "高腰",
            "tummy_space": "合体不贴",
            "line_direction": "纵向",
        },
        "color": {"temperature": "冷调", "lightness": "浅色", "saturation": "低饱和"},
    }
    item.update(overrides)
    return item


# ---------------------------------------------------------------------------
# SUITE 输入解析
# ---------------------------------------------------------------------------

def test_resolve_suit_profile_manual_overrides_photo() -> None:
    session = {
        "manual": {"skin": "暖白肤"},
        "photos": {
            "face": {"attributes": {"skin_tone": {"label": "冷白肤"}, "face_shape": {"label": "圆脸"}}},
            "body": {"attributes": {"body_shape": {"label": "梨型"}}},
        },
    }
    suit = resolve_suit_profile(session)
    assert suit == {"skin": "暖白肤", "face_shape": "圆脸", "body_shape": "梨型"}


def test_resolve_suit_profile_photo_fallback() -> None:
    session = {
        "manual": {},
        "photos": {
            "face": {"attributes": {"skin_tone": {"label": "橄榄肤"}, "face_shape": {"label": "方脸"}}},
            "body": {"attributes": {"body_shape": {"label": "矩型"}}},
        },
    }
    suit = resolve_suit_profile(session)
    assert suit == {"skin": "橄榄肤", "face_shape": "方脸", "body_shape": "矩型"}


def test_resolve_suit_profile_empty_session() -> None:
    assert resolve_suit_profile({}) == {"skin": None, "face_shape": None, "body_shape": None}


# ---------------------------------------------------------------------------
# 静态映射键
# ---------------------------------------------------------------------------

def test_makeup_static_key_fallbacks() -> None:
    assert makeup_static_key("冷白肤", "日系") == "冷白肤|日系"
    assert makeup_static_key("冷白肤", "轻亚") == "冷白肤|韩系"
    assert makeup_static_key(None, None) == "中性自然肤|韩系"


def test_hair_static_key_fallbacks() -> None:
    assert hair_static_key("暖黄肤", "菱形脸") == "暖黄肤|菱形脸"
    assert hair_static_key(None, None) == "中性自然肤|椭圆脸"


# ---------------------------------------------------------------------------
# 打分
# ---------------------------------------------------------------------------

def test_persona_match_score_tiers() -> None:
    outfit = _outfit(primary_persona="MUTE", secondary_personas=["ICED"])
    assert persona_match_score(outfit, "MUTE", "WABI") == 100  # 主=内容主
    assert persona_match_score(outfit, "ICED", "WABI") == 80   # 主命中内容次
    assert persona_match_score(outfit, "WABI", "MUTE") == 80   # 次=内容主
    assert persona_match_score(outfit, "WABI", "ICED") == 60   # 次命中内容次
    assert persona_match_score(outfit, "JADE", "HEIR") == 0


def test_region_match_score() -> None:
    outfit = _outfit(regional_style="日系")
    assert region_match_score(outfit, "日系", "无倾向", ()) == 100
    assert region_match_score(outfit, None, "日系", ()) == 70
    western = _outfit(regional_style="欧美系")
    assert region_match_score(western, "欧美系", "中式", ()) == 100
    assert region_match_score(outfit, "欧美系", "无倾向", ()) == 0
    assert region_match_score(_outfit(regional_style=None), "日系", "日系", ()) is None


def test_body_structure_score_pear_shape() -> None:
    good = _outfit()
    bad = _outfit(structure={
        "visual_weight": "下半身", "waistline": "低腰",
        "tummy_space": "贴身", "line_direction": "横向",
    })
    missing = _outfit(structure={"waistline": "高腰"})
    assert body_structure_score(good, "梨型", None) == 100
    assert body_structure_score(bad, "梨型", None) == 20
    # 只有一个子项且命中：从分母剔除其余。
    assert body_structure_score(missing, "梨型", None) == 100


def test_body_structure_score_rectangle_branch() -> None:
    soft = _outfit(structure={
        "visual_weight": "上下均衡", "waistline": "高腰",
        "tummy_space": "合体不贴", "line_direction": "纵向",
    })
    clean = _outfit(structure={
        "visual_weight": "上下均衡", "waistline": "无腰线",
        "tummy_space": "宽松", "line_direction": "纵向",
    })
    assert body_structure_score(soft, "矩型", "soft_curve") == 100
    assert body_structure_score(soft, "矩型", "clean_line") < 100
    assert body_structure_score(clean, "矩型", "clean_line") == 100
    assert body_structure_score(clean, "矩型", "soft_curve") < 100


def test_skin_color_score() -> None:
    good = _outfit()
    bad = _outfit(color={"temperature": "暖调", "lightness": "深色", "saturation": "高饱和"})
    assert skin_color_score(good, "冷白肤") == 100
    assert skin_color_score(bad, "冷白肤") < 60
    # 中性自然肤不限明度/彩度：只算色温，冷暖均可（80）。
    assert skin_color_score(bad, "中性自然肤") == 80
    assert skin_color_score(_outfit(color={}), "冷白肤") is None
    assert skin_color_score(good, None) is None


def test_suit_score_persona_gate() -> None:
    # 人格不命中（0 分）时，即使地域/体型/色彩满分，人格地域栏也为 0。
    outfit = _outfit(regional_style="日系")
    kwargs = {
        "primary": "JADE", "secondary": None, "regional_style": "日系",
        "primary_region": "中式", "compatible_regions": ("日系",),
        "body_shape": "梨型", "rectangle_branch": None, "skin": "冷白肤",
    }
    assert persona_match_score(outfit, "JADE", None) == 0
    gated = suit_score(outfit, **kwargs)
    # 人格 0 分 → 人格地域栏 0；剩 50/50 权重给满分体型+色彩 → 恰好 50。
    assert gated == pytest.approx(50)

    hit = dict(kwargs, primary="MUTE")
    assert suit_score(outfit, **hit) == 100


def test_suit_score_missing_parts_renormalize() -> None:
    outfit = _outfit()
    base = {
        "primary": "MUTE", "secondary": None, "regional_style": "日系",
        "primary_region": "无倾向", "compatible_regions": ("日系", "韩系"),
        "rectangle_branch": None,
    }
    full = suit_score(outfit, **base, body_shape="梨型", skin="冷白肤")
    no_body = suit_score(outfit, **base, body_shape=None, skin="冷白肤")
    no_body_no_color = suit_score(outfit, **base, body_shape=None, skin=None)
    # 缺失栏剔除后权重归一化：全命中时应趋近满分。
    assert full == 100
    assert no_body == 100
    assert no_body_no_color == 100


# ---------------------------------------------------------------------------
# 降级链
# ---------------------------------------------------------------------------

def test_recommend_outfits_degradation_chain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pool_data = {
        "outfits": [
            _outfit(id=f"of_{i}", primary_persona="MUTE", title=f"MUTE {i}")
            for i in range(3)
        ] + [
            _outfit(id=f"ic_{i}", primary_persona="ICED", title=f"ICED {i}")
            for i in range(4)
        ] + [
            _outfit(id=f"jd_{i}", primary_persona="JADE", title=f"JADE {i}")
            for i in range(6)
        ],
    }
    path = _write_pool(tmp_path, pool_data)
    pool = ContentPool(path)

    common = {
        "regional_style": "日系",
        "primary_region": "无倾向", "compatible_regions": ("日系",),
        "body_shape": None, "rectangle_branch": None, "skin": None,
    }

    # 主池 3 条 < top10 → 并入次人格池 4 条 → 再并入全池补足。
    result = recommend_outfits(
        pool, primary="MUTE", secondary="ICED", top_n=10, **common,
    )
    assert len(result) == 10
    personas = [item["primary_persona"] for item in result]
    assert personas.count("MUTE") == 3
    assert personas.count("ICED") == 4
    assert personas.count("JADE") == 3

    # 池子总量不足 top_n：全部返回。
    tiny = ContentPool(_write_pool(tmp_path, {"outfits": pool_data["outfits"][:4]}))
    result = recommend_outfits(tiny, primary="MUTE", secondary=None, top_n=10, **common)
    assert len(result) == 4


def test_recommend_outfits_ranks_by_suit(tmp_path: Path) -> None:
    pool_data = {
        "outfits": [
            _outfit(id="best", primary_persona="MUTE", regional_style="日系"),
            _outfit(
                id="worst",
                primary_persona="MUTE",
                regional_style="欧美系",
                structure={"visual_weight": "下半身", "waistline": "低腰", "tummy_space": "贴身", "line_direction": "横向"},
                color={"temperature": "暖调", "lightness": "深色", "saturation": "高饱和"},
            ),
        ],
    }
    path = _write_pool(tmp_path, pool_data)
    pool = ContentPool(path)
    result = recommend_outfits(
        pool,
        primary="MUTE", secondary=None, regional_style="日系",
        primary_region="无倾向", compatible_regions=("日系", "韩系"),
        body_shape="梨型", rectangle_branch=None, skin="冷白肤",
        top_n=2,
    )
    assert [item["id"] for item in result] == ["best", "worst"]


def test_content_pool_hot_reload(tmp_path: Path) -> None:
    path = _write_pool(tmp_path, {"outfits": [_outfit(id="a")]})
    pool = ContentPool(path)
    assert len(pool.outfits) == 1
    _write_pool(tmp_path, {"outfits": [_outfit(id="a"), _outfit(id="b")]})
    assert len(pool.outfits) == 2
    selfit_recommend.reset_content_pool_cache()


# ---------------------------------------------------------------------------
# 报告 builder 端到端（走 mock 内容池）
# ---------------------------------------------------------------------------

def test_default_report_builder_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app import selfit_report

    pool_data = {
        "outfits": [
            _outfit(id=f"mute_{i}", primary_persona="MUTE", secondary_personas=[])
            for i in range(12)
        ],
        "makeup": {"冷白肤|日系": [
            {"name": "日系清透妆", "byline": "@作者", "imageUrl": "report/v1/makeup-a.webp", "alt": "alt"},
            {"name": "日系进阶妆", "byline": "@作者", "imageUrl": "report/v1/makeup-b.webp", "alt": "alt"},
        ]},
        "hair": {"冷白肤|椭圆脸": [
            {"name": "层次长发", "byline": "@作者", "imageUrl": "report/v1/hair-a.webp", "alt": "alt"},
            {"name": "修饰中发", "byline": "@作者", "imageUrl": "report/v1/hair-b.webp", "alt": "alt"},
        ]},
    }
    _write_pool(tmp_path, pool_data)
    monkeypatch.setenv("SELFIT_CONTENT_POOL_PATH", str(tmp_path / "pool.json"))
    selfit_recommend.reset_content_pool_cache()

    session = {
        "preferences": {"axes": {"shape": 25, "energy": 10, "trend": 40}, "palette": "mono"},
        "vibe": {"occasion": "C", "wardrobe": "A", "expression": "A"},
        "manual": {"skin": "冷白肤", "faceShape": "椭圆脸", "bodyShape": "梨型"},
        "photos": {},
    }
    report = selfit_report.build_report(session)

    assert report["eyebrow"] == "MUTE"
    assert report["title"] == "静音时髦"
    assert report["traits"] == ["硬朗利落", "极简克制", "低饱和"]
    assert report["colors"][0]["name"] == "雾霭蓝"
    assert report["colors"][-1]["value"] == "#141414"  # mono 偏好点缀
    assert len(report["makeup"]) == 2
    assert report["makeup"][0]["imageUrl"].endswith("makeup-a.webp")
    assert len(report["hair"]) == 2
    assert len(report["outfits"]) == 10
    assert all(item["author"] for item in report["outfits"])
    assert 1 <= len(report["advice"]) <= 3
    selfit_recommend.reset_content_pool_cache()


def test_default_report_builder_fails_without_inputs() -> None:
    from app import selfit_report

    with pytest.raises(ValueError):
        selfit_report.build_report({"preferences": {}, "vibe": {}})
