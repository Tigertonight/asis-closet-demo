from __future__ import annotations

from app.selfit_persona import (
    DIMENSIONS,
    PERSONAS,
    build_user_vector,
    classify_persona,
    derive_regional_style,
    persona_makeup_styles,
    rectangle_body_branch,
)


def _session(**overrides):
    session = {
        "preferences": {
            "axes": {"shape": 50, "energy": 50, "trend": 50},
            "palette": "mono",
        },
        "vibe": {"occasion": "B", "wardrobe": "A", "expression": "A"},
    }
    session.update(overrides)
    return session


def test_shape_axis_is_inverted_for_silhouette() -> None:
    # 前端 shape 0=硬朗、100=柔和；算法廓形 0=柔和、100=硬朗。
    vector = build_user_vector(_session(preferences={
        "axes": {"shape": 0, "energy": 80, "trend": 20},
        "palette": "earth",
    }))
    assert vector["silhouette"] == 100
    assert vector["complexity"] == 80
    assert vector["time_orientation"] == 20


def test_palette_signals_mapping() -> None:
    vector = build_user_vector(_session(preferences={
        "axes": {"shape": 50, "energy": 50, "trend": 50},
        "palette": "ocean",
    }))
    assert vector["saturation"] == 55
    assert vector["temperature"] == 20


def test_vibe_values_mapping() -> None:
    vector = build_user_vector(_session(vibe={
        "occasion": "D", "wardrobe": "C", "expression": "E",
    }))
    assert vector["completion"] == 95
    assert vector["individuality"] == 90
    assert vector["regional_style"] == "法式"


def test_missing_inputs_fallback_to_neutral() -> None:
    vector = build_user_vector({"preferences": {}, "vibe": {}})
    assert vector["regional_style"] is None
    assert vector["completion"] == 50


def test_light_asian_derivation() -> None:
    vector = {
        "regional_style": "韩系",
        "silhouette": 80, "time_orientation": 75, "temperature": 30,
        "completion": 80, "individuality": 70,
    }
    assert derive_regional_style(vector) == "轻亚"
    # 仅命中 2 项：不升级。
    weak = {
        "regional_style": "欧美系",
        "silhouette": 80, "time_orientation": 75, "temperature": 60,
        "completion": 30, "individuality": 20,
    }
    assert derive_regional_style(weak) == "欧美系"
    # 法式不参与轻亚推导。
    french = dict(vector, regional_style="法式")
    assert derive_regional_style(french) == "法式"


def test_persona_region_mapping_matches_engineering_spec() -> None:
    expected = {
        "日系": ({"WABI"}, {"MUTE", "MELT", "FILM"}),
        "韩系": ({"ICED", "MELT"}, {"MUTE", "EASE", "EDGE"}),
        "欧美系": ({"HEIR", "NEON"}, {"EDGE", "BOLT", "NOIR", "OOPS"}),
        "中式": ({"JADE"}, {"WABI", "FLOU"}),
        "法式": ({"EASE", "FLOU", "BOLT", "FILM"}, {"HEIR"}),
        "轻亚": ({"EDGE"}, {"ICED", "NEON", "NOIR", "OOPS"}),
    }

    for region, (primary_codes, compatible_codes) in expected.items():
        assert {
            code for code, persona in PERSONAS.items() if persona.primary_region == region
        } == primary_codes
        assert {
            code for code, persona in PERSONAS.items() if region in persona.compatible_regions
        } == compatible_codes
    assert {
        code for code, persona in PERSONAS.items() if persona.primary_region == "无倾向"
    } == {"MUTE", "LOOP", "NOIR", "VOID", "OOPS"}


def test_classify_exact_center_hits_persona() -> None:
    # 构造与 MUTE 中心点一致的输入（shape 反向换算：silhouette 75 → shape 25）。
    session = _session(
        preferences={"axes": {"shape": 25, "energy": 10, "trend": 40}, "palette": "mono"},
        vibe={"occasion": "C", "wardrobe": "A", "expression": "A"},
    )
    result = classify_persona(build_user_vector(session))
    assert result["primary_persona"] == "MUTE"
    assert result["secondary_persona"] in PERSONAS
    assert 0.0 <= result["persona_confidence"] <= 1.0


def test_region_penalty_pushes_mismatched_persona_back() -> None:
    # 同一数值向量，选「中式」时 JADE（主风格中式）应比选「欧美系」时更靠前。
    base = {
        "silhouette": 70, "complexity": 40, "time_orientation": 15,
        "saturation": 30, "temperature": 50, "completion": 80, "individuality": 35,
    }
    chinese = classify_persona({**base, "regional_style": "中式"})
    western = classify_persona({**base, "regional_style": "欧美系"})
    rank_cn = _rank_distances({**base, "regional_style": "中式"})
    rank_us = _rank_distances({**base, "regional_style": "欧美系"})
    assert rank_cn["JADE"] < rank_us["JADE"]
    assert chinese["primary_persona"] == "JADE"
    assert western["primary_persona"] != "JADE" or western["persona_confidence"] < chinese["persona_confidence"]


def _rank_distances(vector: dict) -> dict[str, float]:
    from app.selfit_persona import _persona_distance

    return {code: _persona_distance(persona, vector)[1] for code, persona in PERSONAS.items()}


def test_persona_distance_uses_documented_weighted_absolute_distance() -> None:
    from app.selfit_persona import _persona_distance

    persona = PERSONAS["MUTE"]
    vector = dict(persona.center)
    # MUTE 的 silhouette 是核心维度（权重 1.5），complexity 也是核心维度。
    vector["silhouette"] += 10
    vector["complexity"] += 4
    vector["regional_style"] = "无倾向"

    numeric, total = _persona_distance(persona, vector)

    assert numeric == 10 * 1.5 + 4 * 1.5
    assert total == numeric


def test_neutral_regional_user_gets_no_region_penalty() -> None:
    vector = {
        "silhouette": 50, "complexity": 30, "time_orientation": 50,
        "saturation": 20, "temperature": 50, "completion": 10, "individuality": 95,
        "regional_style": None,
    }
    result = classify_persona(vector)
    assert result["primary_persona"] == "VOID"


def test_confidence_tiers() -> None:
    # 该向量在加权绝对距离下的前两名距离为 192.5 / 205，
    # confidence = (205 - 192.5) / 205 ≈ 0.061，应落入低置信度。
    vector = {
        "silhouette": 60,
        "complexity": 65,
        "time_orientation": 95,
        "saturation": 0,
        "temperature": 70,
        "completion": 40,
        "individuality": 35,
        "regional_style": None,
    }
    result = classify_persona(vector)
    assert result["persona_confidence"] == 0.061
    assert result["confidence_tier"] == "low"


def test_persona_makeup_styles() -> None:
    assert persona_makeup_styles("MELT") == ("甜美", ("自然",))
    assert persona_makeup_styles("LOOP") == (None, ())
    assert persona_makeup_styles("NOIR") == ("清冷", ("个性",))


def test_rectangle_body_branch() -> None:
    assert rectangle_body_branch({"silhouette": 30}) == "soft_curve"
    assert rectangle_body_branch({"silhouette": 75}) == "clean_line"


def test_all_persona_centers_are_complete() -> None:
    for persona in PERSONAS.values():
        assert set(persona.center) == set(DIMENSIONS)
        for value in persona.center.values():
            assert 0 <= value <= 100
        assert persona.makeup_primary == "不限制" or persona.makeup_primary in {"自然", "甜美", "清冷", "复古", "明艳", "个性"}
