from __future__ import annotations

import pytest

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
    # v1.2 OOPS 个性中心 100→80：wardrobe=C（90）距 OOPS 不变，
    # 但此向量 ind=35 距 OOPS 缩近 30 分，次名距离变化使 confidence 移至 0.0649
    assert result["persona_confidence"] == 0.0649
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


def test_frontend_mock_persona_matches_backend() -> None:
    """mock 模式前端移植（selfit-persona.js）必须与后端算法同口径。

    曾出现 buildMockReport 只按色板查表返回 6 个人格的问题；本测试对拍
    前后端向量化 + 分型结果，防止两侧算法再次漂移。
    """

    import json
    import shutil
    import subprocess
    from pathlib import Path

    node = shutil.which("node")
    if node is None:
        pytest.skip("node runtime unavailable")

    script = Path(__file__).resolve().parents[1] / "app" / "static" / "selfit" / "selfit-persona.js"
    palettes = ["mono", "earth", "ocean", "jewel", "bright", "pastel"]
    occasions = ["A", "B", "C", "D"]
    wardrobes = ["A", "B", "C"]
    expressions = ["A", "B", "C", "D", "E"]

    # 确定性样本：分层抽样 + 边界值。
    sessions: list[dict] = []
    index = 0
    for shape in (0, 25, 50, 75, 100):
        for energy in (0, 50, 100):
            for trend in (10, 40, 90):
                for palette in palettes:
                    index += 1
                    sessions.append({
                        "preferences": {
                            "axes": {"shape": shape, "energy": energy, "trend": trend},
                            "palette": palette,
                        },
                        "answers": {
                            "occasion": occasions[index % 4],
                            "wardrobe": wardrobes[index % 3],
                            "expression": expressions[index % 5],
                        },
                    })
    # 边界：缺失字段、空会话。
    sessions.append({"preferences": {"palette": "mono"}})
    sessions.append({"answers": {"occasion": "D"}})
    sessions.append({})

    runner = (
        "const fs=require('fs');global.window={};"
        f"eval(fs.readFileSync({json.dumps(str(script))},'utf-8'));"
        "const P=global.window.SelfitPersona;"
        "const input=JSON.parse(fs.readFileSync(0,'utf-8'));"
        "const out=input.map((s)=>{const v=P.buildUserVector(s);"
        "const c=P.classifyPersona(v);"
        "return {primary:c.primary_persona,secondary:c.secondary_persona,"
        "distance:Math.round(c.primary_distance*10000)/10000};});"
        "process.stdout.write(JSON.stringify(out));"
    )
    result = subprocess.run(
        [node, "-e", runner],
        input=json.dumps(sessions),
        capture_output=True,
        text=True,
        check=True,
    )
    frontend = json.loads(result.stdout)

    covered: set[str] = set()
    assert len(frontend) == len(sessions)
    for session, front in zip(sessions, frontend):
        vector = build_user_vector({
            "preferences": session.get("preferences") or {},
            "vibe": session.get("answers") or session.get("vibe") or {},
        })
        backend = classify_persona(vector)
        covered.add(backend["primary_persona"])
        assert front["primary"] == backend["primary_persona"], session
        assert front["secondary"] == backend["secondary_persona"], session
        assert abs(front["distance"] - backend["primary_distance"]) < 0.0001, session
    # 分型多样性必须显著超过色板数（防止退化为「颜色查表」）。
    assert len(covered) >= 10


# ---------------------------------------------------------------------------
# 跨侧冲突权重（内测缺陷修复：调大硬朗锐利不能变成奶油治愈）
# ---------------------------------------------------------------------------

def test_cross_side_conflict_upgrades_base_weight() -> None:
    """|Δ|>50 的跨侧冲突即使非核心维度也按 1.5 计分。"""

    from app.selfit_persona import CROSS_SIDE_DELTA_THRESHOLD, _persona_distance

    assert CROSS_SIDE_DELTA_THRESHOLD == 50.0
    # EASE 的 saturation 非核心（基础权重 1.0）：跨侧冲突时应按 1.5 计。
    persona = PERSONAS["EASE"]
    vector = dict(persona.center)
    vector["saturation"] = 100  # Δ=75 > 50，跨侧冲突
    vector["regional_style"] = None
    numeric, _ = _persona_distance(persona, vector)
    assert numeric == 75 * 1.5
    # 同样偏差若未跨侧（Δ≤50），保持基础权重 1.0。
    vector["saturation"] = 60  # Δ=35 ≤ 50
    numeric, _ = _persona_distance(persona, vector)
    assert numeric == 35 * 1.0


def test_hardening_silhouette_never_lands_on_soft_persona() -> None:
    """内测缺陷回归：EASE 参数只调大「硬朗锐利」不能变成 MELT（奶油治愈）。

    修复前的机制：silhouette 是 EASE 核心维度（权重 1.5）但不是 MELT 的
    （1.0）。用户调硬朗时 EASE 被惩罚 1.5 倍速、MELT 只有 1.0 倍速，
    越调硬朗越快甩掉 EASE，反被廓形同样柔和（中心 20）的 MELT 接盘。
    """

    # 内测真实反馈的组合：该输入原为 EASE。
    base_preferences = {"axes": {"shape": 50, "energy": 60, "trend": 50}, "palette": "earth"}
    vibe = {"occasion": "B", "wardrobe": "A", "expression": "B"}

    before = classify_persona(build_user_vector(
        {"preferences": base_preferences, "vibe": vibe}
    ))
    assert before["primary_persona"] == "EASE"

    # 只把「硬朗锐利」拉满（shape → 0，silhouette → 100）。
    hardened_preferences = {"axes": {"shape": 0, "energy": 60, "trend": 50}, "palette": "earth"}
    after = classify_persona(build_user_vector(
        {"preferences": hardened_preferences, "vibe": vibe}
    ))
    assert after["primary_persona"] != "MELT"
    # 结果应推向硬朗侧人格（廓形中心明显偏硬朗），而不是更柔和的人格。
    before_center = PERSONAS[before["primary_persona"]].center["silhouette"]
    after_center = PERSONAS[after["primary_persona"]].center["silhouette"]
    assert after_center >= before_center


def test_hardening_scan_no_soft_landing() -> None:
    """全量扫描：任何「原本 EASE」的输入只调大硬朗，都不应落到 MELT。"""

    failures = []
    for shape in range(30, 100, 4):
        for energy in range(0, 100, 20):
            for trend in range(0, 100, 20):
                for palette in ("pastel", "earth", "mono", "bright"):
                    for occasion in "ABCD":
                        for wardrobe in "ABC":
                            for expression in "ABE":
                                vibe = {"occasion": occasion, "wardrobe": wardrobe, "expression": expression}
                                before = classify_persona(build_user_vector({"preferences": {
                                    "axes": {"shape": shape, "energy": energy, "trend": trend},
                                    "palette": palette,
                                }, "vibe": vibe}))
                                if before["primary_persona"] != "EASE":
                                    continue
                                after = classify_persona(build_user_vector({"preferences": {
                                    "axes": {"shape": 0, "energy": energy, "trend": trend},
                                    "palette": palette,
                                }, "vibe": vibe}))
                                if after["primary_persona"] == "MELT":
                                    failures.append((shape, energy, trend, palette, occasion, wardrobe, expression))
    assert not failures, f"调大硬朗后仍落到 MELT 的输入: {failures[:5]}"


def test_persona_breakdown_matches_classify_result() -> None:
    """分解输出与 classify_persona 同源：主/次人格一致、距离可复算。"""

    from app.selfit_persona import ALGORITHM_VERSION, persona_breakdown

    assert ALGORITHM_VERSION
    session = {
        "preferences": {"axes": {"shape": 20, "energy": 60, "trend": 50}, "palette": "earth"},
        "vibe": {"occasion": "B", "wardrobe": "A", "expression": "B"},
    }
    breakdown = persona_breakdown(session)
    vector = build_user_vector(session)
    result = classify_persona(vector)
    assert breakdown["classification"] == result
    assert breakdown["algorithmVersion"] == ALGORITHM_VERSION
    # 前两名的总距离与 classify 的距离一致（±0.1 舍入）
    assert abs(breakdown["ranking"][0]["totalDistance"] - result["primary_distance"]) < 0.1
    assert abs(breakdown["ranking"][1]["totalDistance"] - result["secondary_distance"]) < 0.1
    # 每个 persona 的维度贡献之和等于它的数值距离
    for row in breakdown["ranking"]:
        assert abs(sum(d["weighted"] for d in row["dimensions"]) - row["numericDistance"]) < 0.5


# ---------------------------------------------------------------------------
# v1.2-margin-hardening：2026-08-28 内测实录回归（服务器 sessions.json 实测输入）
# ---------------------------------------------------------------------------

def _classify_axes(shape: float, energy: float, trend: float, palette: str,
                   occasion: str, wardrobe: str, expression: str) -> str:
    return classify_persona(build_user_vector({"preferences": {
        "axes": {"shape": shape, "energy": energy, "trend": trend},
        "palette": palette,
    }, "vibe": {"occasion": occasion, "wardrobe": wardrobe, "expression": expression}}))["primary_persona"]


def test_noir_typical_answer_survives_slider_jitter() -> None:
    """NOIR 答卷在滑杆 ±10 偏差下必须命中 NOIR（内测实录：连测三次全 MUTE）。

    根因：temperature 原为 NOIR 核心维度，但无彩色色板温度恒为 50，
    中心冷调 20 不可达，1.5 倍权重形成永久罚分，对 MUTE 判别余量仅
    15 分。v1.2 将 temperature 移出核心后余量恢复。
    """

    for shape, energy, trend in [(25, 35, 65), (25, 25, 65), (25, 35, 55), (20, 30, 60), (25, 45, 70)]:
        assert _classify_axes(shape, energy, trend, "mono", "C", "A", "C") == "NOIR", (
            f"NOIR 答卷近似输入 ({shape},{energy},{trend}) 误判"
        )


def test_flou_typical_answer_survives_occasion_substitution() -> None:
    """FLOU 答卷在 occasion 用 B/C 代答 D 时必须命中 FLOU（内测实录：连测四次全 FILM）。

    根因：FLOU 完成度中心 90 依赖 occasion=D（95），问卷 UI 上限 C（70）；
    completion 原为核心维度，代答 B（40）罚 75 分后对 FILM 判别余量仅
    25 分。v1.2 将 completion 移出核心后 B/C 代答均可容错。
    """

    for occasion in ("B", "C"):
        assert _classify_axes(85, 90, 30, "pastel", occasion, "B", "E") == "FLOU", (
            f"FLOU 答卷 occasion={occasion} 代答误判"
        )
    # 滑杆 ±10 偏差 + occasion=B 代答仍需命中
    assert _classify_axes(80, 82, 35, "pastel", "B", "B", "E") == "FLOU"


def test_oops_typical_answer_survives_wardrobe_stale_answer() -> None:
    """OOPS 答卷在 wardrobe 误答 B（残留上题答案）时必须命中 OOPS（内测实录）。

    根因：OOPS 个性中心原为 100（量表极值），仅 wardrobe=C（90）算接近，
    误答 B（55）触发 67.5 罚分被 NEON 接盘；LIKE 四值全部命中也无济于事。
    v1.2 将中心降至 80：OOPS 仍为全表次高个性中心，NEON 判别不受影响
    （wardrobe=C 时 |90-80| 与 |90-100| 距离相同）。
    """

    # 内测实录输入：LIKE 四值命中，wardrobe 误答 B
    assert _classify_axes(20, 89, 88, "bright", "C", "B", "C") == "OOPS"
    # wardrobe 误答 A（更远）也需命中
    assert _classify_axes(30, 90, 90, "bright", "C", "A", "C") == "OOPS"
    # 正确答卷（wardrobe=C）命中
    assert _classify_axes(30, 90, 90, "bright", "C", "C", "C") == "OOPS"


def test_neon_typical_answer_unaffected_by_oops_center_change() -> None:
    """NEON 答卷不受 OOPS 个性中心下调影响（wardrobe=C 时 |90-80| = |90-100|）。"""

    from app.selfit_persona import PERSONAS, _persona_distance

    assert _classify_axes(35, 75, 90, "bright", "C", "C", "C") == "NEON"
    # 不变性本身：wardrobe=C（ind=90）向量到 OOPS 的距离在中心 80/100 下相同
    vector = build_user_vector({"preferences": {
        "axes": {"shape": 35, "energy": 75, "trend": 90}, "palette": "bright",
    }, "vibe": {"occasion": "C", "wardrobe": "C", "expression": "C"}})
    numeric, _ = _persona_distance(PERSONAS["OOPS"], vector)
    # ind 贡献 |90-80|×1.5 = 15（与 |90-100|×1.5 相同），其余维度贡献不变
    assert abs(numeric - 50.0) < 0.01


def test_typical_answer_sheets_all_hit_after_v12() -> None:
    """《16 型人格典型答卷》全表精确命中（v1.2 变更后回归）。"""

    sheets = {
        "MUTE": (75, 10, 40, "mono", "C", "A", "A"),
        "ICED": (25, 20, 65, "ocean", "C", "A", "B"),
        "HEIR": (70, 30, 15, "earth", "D", "A", "C"),
        "EASE": (25, 25, 25, "earth", "C", "A", "E"),
        "MELT": (20, 70, 60, "pastel", "C", "A", "B"),
        "WABI": (25, 20, 10, "earth", "B", "A", "A"),
        "FLOU": (15, 90, 30, "pastel", "D", "B", "E"),
        "NEON": (65, 75, 90, "bright", "C", "C", "C"),
        "EDGE": (85, 65, 85, "ocean", "D", "B", "B"),
        "BOLT": (55, 75, 20, "pastel", "D", "B", "E"),
        "FILM": (30, 40, 20, "earth", "B", "B", "E"),
        "JADE": (70, 40, 15, "pastel", "C", "A", "D"),
        "LOOP": (50, 50, 50, "pastel", "D", "B", "A"),
        "NOIR": (75, 35, 65, "mono", "C", "A", "C"),
        "VOID": (50, 30, 50, "pastel", "A", "C", "A"),
        "OOPS": (70, 90, 90, "bright", "C", "C", "C"),
    }
    for code, (like1, like2, like3, palette, v1, v2, v3) in sheets.items():
        assert _classify_axes(100 - like1, like2, like3, palette, v1, v2, v3) == code, (
            f"{code} 典型答卷误判"
        )
