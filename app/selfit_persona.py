"""selfit 十六型人格分型算法（V0 定版口径）。

依据文档：
- 《Selfit 用户输入 × 16 型人格 × 内容标签映射方案》（题目数值映射、
  权重规则、置信度公式、人格匹配分）；
- 《Selfit 16型人格 × 8项风格映射表》（16 型中心点、主/兼容风格、
  核心辨识——中心点配置只维护该一份）；
- 《Selfit 地域风格 × 16 型人格映射方案》（地域加减分、轻亚推导、
  无倾向规则）；
- 《Selfit 十六型：输入题目 → 分型与推荐 全链路工程规格》（总架构）。

坐标系（重要）
--------------
7 个数值维度统一 0-100，方向见 DIMENSION_LABELS。注意「廓形」：
0=柔和曲线、100=硬朗直线。前端 LIKE 滑杆 shape 的 0=硬朗、100=柔和
（index.html 标签顺序「硬朗锐利 … 柔和温柔」），因此后端换算
``silhouette = 100 - shape``；energy/trend 与维度方向一致，直通。

分型只依赖 LIKE 4 题 + VIBE 3 题；SUITE（肤色/脸型/体型）不介入分型。
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# 维度定义
# ---------------------------------------------------------------------------

DIMENSIONS = (
    "silhouette",       # 廓形：0 柔和曲线 → 100 硬朗直线
    "complexity",       # 繁简：0 简约留白 → 100 繁复装饰
    "time_orientation", # 时间：0 经典复古 → 100 先锋新潮
    "saturation",       # 饱和度：0 无彩低饱和 → 100 高饱和撞色
    "temperature",      # 冷暖：0 冷调 → 100 暖调
    "completion",       # 完成度：0 随意松弛 → 100 精修全套呼应
    "individuality",    # 个性（游移/混搭度）：0 稳定统一 → 100 游移混搭
)

DIMENSION_LABELS = {
    "silhouette": "廓形",
    "complexity": "繁简",
    "time_orientation": "时间",
    "saturation": "饱和度",
    "temperature": "冷暖",
    "completion": "完成度",
    "individuality": "个性",
}

REGIONAL_STYLES = ("日系", "韩系", "欧美系", "中式", "法式", "轻亚", "无倾向")

# 算法版本指纹：每次修改分型口径（中心点/权重/阈值/换算）必须递增并说明变更，
# 并同步三处：前端移植版 selfit-persona.js、管理后台人格匹配展示、
# tests/test_selfit_persona.py 对拍测试。详见 docs/PERSONA_ALGORITHM.md。
ALGORITHM_VERSION = "v1.3-vibe1-remap"

# VIBE 题 key（onboarding 契约）→ 维度。
# v1.3：《16 型人格典型答卷》定版映射——VIBE1 只有 A/B/C 三档（20/55/90），
# D 档（95）随 UI 三选项方案一并删除；新 B=55 较旧 B=40 上移后，
# FILM 完成度中心同步 40→50（见 FILM 定义处注释）。
VIBE_COMPLETION_VALUES = {"A": 20, "B": 55, "C": 90}
VIBE_INDIVIDUALITY_VALUES = {"A": 20, "B": 55, "C": 90}
VIBE_REGIONAL_VALUES = {"A": "日系", "B": "韩系", "C": "欧美系", "D": "中式", "E": "法式"}

# 前端色板枚举（onboarding 契约 palette）→（饱和度, 冷暖）。
# 对应 L4 六色板：无彩色/自然中性色/冷调中饱和/暖调中饱和/高饱和彩色/低饱和彩色。
PALETTE_SIGNALS = {
    "mono": {"saturation": 5, "temperature": 50},
    "earth": {"saturation": 20, "temperature": 65},
    "ocean": {"saturation": 55, "temperature": 20},
    "jewel": {"saturation": 55, "temperature": 80},
    "bright": {"saturation": 90, "temperature": 50},
    "pastel": {"saturation": 30, "temperature": 50},
}

# 轻亚推导阈值（地域风格×16型人格映射方案第五节；算法坐标系下）。
LIGHT_ASIAN_RULES = (
    ("silhouette", ">=", 65),
    ("time_orientation", ">=", 70),
    ("temperature", "<=", 40),
    ("completion", ">=", 70),
    ("individuality", ">=", 60),
)
LIGHT_ASIAN_MIN_HITS = 3
LIGHT_ASIAN_SOURCE_REGIONS = {"韩系", "欧美系"}

# 地域加减分（命中主 0 / 兼容 +5 / 不匹配 +15 / 人格主风格无倾向不计）。
REGION_PRIMARY_PENALTY = 0.0
REGION_COMPATIBLE_PENALTY = 5.0
REGION_MISMATCH_PENALTY = 15.0

# 权重：人格核心维度 1.5，普通维度 1.0（用户输入×16型人格×内容标签映射方案）。
CORE_DIMENSION_WEIGHT = 1.5
BASE_DIMENSION_WEIGHT = 1.0
# 跨侧冲突阈值：用户与人格中心在某维度上分处量表两端（|Δ| > 50）时，
# 视为明确的风格冲突，即使该维度不是此人格的核心辨识也按核心强度计分。
# 修复缺陷：否则「调大硬朗」反而会甩掉把廓形列为核心的人格（如 EASE 权重 1.5），
# 落到廓形同样柔和、却不把廓形列为核心的人格上（如 MELT 权重 1.0）——
# 内测反馈：EASE 参数只调大硬朗锐利，结果变成奶油治愈 MELT。
CROSS_SIDE_DELTA_THRESHOLD = 50.0

# 置信度分层阈值。
CONFIDENCE_HIGH = 0.20
CONFIDENCE_MID = 0.10


# ---------------------------------------------------------------------------
# 16 型人格配置（单一来源：16型人格×8项风格映射表第三节）
# ---------------------------------------------------------------------------

class Persona:
    __slots__ = (
        "code", "name", "primary_region", "compatible_regions",
        "center", "core_dimensions", "signature", "traits",
        "makeup_primary", "makeup_compatible",
    )

    def __init__(
        self,
        code: str,
        name: str,
        primary_region: str,
        compatible_regions: tuple[str, ...],
        center: dict[str, int],
        core_dimensions: tuple[str, ...],
        signature: str,
        traits: tuple[str, ...],
        makeup_primary: str,
        makeup_compatible: tuple[str, ...],
    ) -> None:
        self.code = code
        self.name = name
        self.primary_region = primary_region
        self.compatible_regions = compatible_regions
        self.center = center
        self.core_dimensions = core_dimensions
        self.signature = signature
        self.traits = traits
        self.makeup_primary = makeup_primary
        self.makeup_compatible = makeup_compatible


def _persona(
    code: str,
    name: str,
    primary_region: str,
    compatible_regions: tuple[str, ...],
    values: tuple[int, ...],
    core_dimensions: tuple[str, ...],
    signature: str,
    traits: tuple[str, ...],
    makeup_primary: str,
    makeup_compatible: tuple[str, ...],
) -> Persona:
    center = dict(zip(DIMENSIONS, values))
    return Persona(
        code, name, primary_region, compatible_regions, center,
        core_dimensions, signature, traits, makeup_primary, makeup_compatible,
    )


# 中心点 7 元组顺序 = DIMENSIONS：
# (廓形, 繁简, 时间, 饱和度, 冷暖, 完成度, 个性)
# 核心维度按「核心辨识」拍定（权重 1.5），其余 1.0。
PERSONAS: dict[str, Persona] = {
    p.code: p
    for p in (
        _persona("MUTE", "静音时髦", "无倾向", ("日系", "韩系"),
                 (75, 10, 40, 10, 35, 70, 20),
                 ("silhouette", "complexity", "saturation"),
                 "硬朗、极简、低饱和、稳定", ("硬朗利落", "极简克制", "低饱和"),
                 "清冷", ("自然",)),
        _persona("ICED", "冷感冰面", "韩系", ("轻亚",),
                 (25, 20, 65, 25, 15, 75, 25),
                 ("silhouette", "temperature", "completion"),
                 "柔和、简约、冷调、精修", ("清冷简约", "冷调通透", "精致完成度"),
                 "清冷", ("自然",)),
        _persona("HEIR", "老钱新穿", "欧美系", ("法式",),
                 (70, 30, 15, 25, 60, 90, 15),
                 ("silhouette", "time_orientation", "completion"),
                 "结构、经典、低饱和、高完成度", ("经典结构", "低调质感", "高完成度"),
                 "复古", ("自然",)),
        _persona("EASE", "松弛讲究", "法式", ("韩系",),
                 (25, 25, 25, 25, 65, 60, 25),
                 ("silhouette", "time_orientation", "temperature"),
                 "柔和、经典、暖调、松弛讲究", ("松弛慵懒", "暖调柔和", "经典耐看"),
                 "自然", ("复古",)),
        _persona("MELT", "奶油治愈", "韩系", ("日系",),
                 (20, 70, 60, 35, 65, 75, 35),
                 ("complexity", "saturation", "completion"),
                 "柔和、甜色、装饰感、精修", ("甜感装饰", "柔和治愈", "精致甜色"),
                 "甜美", ("自然",)),
        _persona("WABI", "手作侘寂", "日系", ("中式",),
                 (25, 20, 10, 15, 55, 35, 20),
                 ("complexity", "time_orientation", "saturation"),
                 "柔和、极简、经典、自然低饱和", ("自然侘寂", "极简手作", "低饱和"),
                 "自然", ("清冷",)),
        _persona("FLOU", "造梦浪漫", "法式", ("中式",),
                 (15, 90, 30, 35, 60, 90, 45),
                 # v1.2：completion 移出核心。FLOU 完成度中心 90 只有
                 # occasion=D（95）能接近，问卷 UI 上限为 C（70）；
                 # 用户代答 B（40）时核心权重罚 75 分，FLOU 对 FILM
                 # 判别余量仅 25 分，滑杆小幅偏差即误判虚焦胶片（内测
                 # 实录：FLOU 答卷连测四次全部 FILM）。繁简（90 vs 40）
                 # 仍是 FLOU/FILM 的首要区分维度，completion 降为普通
                 # 权重后距离信号保留。
                 ("complexity", "silhouette"),
                 "柔和、高装饰、经典浪漫、高完成度", ("浪漫装饰", "梦幻柔美", "高完成度"),
                 "甜美", ("复古",)),
        _persona("NEON", "灵动吸睛", "欧美系", ("轻亚",),
                 (65, 75, 90, 95, 50, 75, 75),
                 ("saturation", "time_orientation", "individuality"),
                 "高饱和、先锋、强表达、高个性", ("高饱和撞色", "先锋大胆", "吸睛表达"),
                 "个性", ("明艳",)),
        _persona("EDGE", "甜酷轻亚", "轻亚", ("韩系", "欧美系"),
                 (85, 65, 85, 45, 20, 90, 70),
                 ("silhouette", "temperature", "time_orientation"),
                 "硬朗、先锋、冷调、强轮廓", ("甜酷先锋", "冷调强轮廓", "高完成度"),
                 "个性", ("清冷", "明艳")),
        _persona("BOLT", "在逃千金", "法式", ("欧美系",),
                 (55, 75, 20, 35, 45, 95, 55),
                 ("complexity", "completion", "time_orientation"),
                 "戏剧装饰、复古、角色感、极高完成度", ("戏剧千金", "复古华丽", "角色感强"),
                 "复古", ("明艳",)),
        _persona("FILM", "虚焦胶片", "法式", ("日系",),
                 # v1.3：completion 中心 40→50。VIBE1 定版三档（A=20/B=55/C=90）
                 # 后 FILM 典型答卷答 B（55）：中心 40 时对 EASE（中心 60）
                 # 判别余量仅 15 分，滑杆 ±5 偏差即误判松弛讲究。50 仍保持
                 # 「生活感低完成度」梯队（低于 EASE 60/MELT 75），且 B 答案
                 # 距 FILM(50) 与 EASE(60) 对称，判别回归繁简维度（40 vs 25）
                 # ——FILM 的首要辨识。
                 (30, 40, 20, 35, 70, 50, 45),
                 ("time_orientation", "temperature", "completion"),
                 "柔和、复古、暖调、生活感", ("复古胶片", "暖调生活感", "柔和氛围"),
                 "复古", ("自然",)),
        _persona("JADE", "东方玉骨", "中式", (),
                 (70, 40, 15, 30, 50, 80, 35),
                 ("silhouette", "time_orientation", "saturation"),
                 "硬朗、经典、东方秩序、中低饱和", ("东方秩序", "经典骨相", "克制雅致"),
                 "复古", ("清冷",)),
        _persona("LOOP", "无限重启", "无倾向", (),
                 (50, 50, 50, 50, 50, 95, 60),
                 ("completion", "individuality"),
                 "高完成度、反复调整、视觉方向不限", ("高完成度", "反复打磨", "方向探索"),
                 "不限制", ()),
        _persona("NOIR", "暗黑肃杀", "无倾向", ("轻亚", "欧美系"),
                 (75, 35, 65, 5, 20, 80, 35),
                 # v1.2：temperature 移出核心。无彩色色板（NOIR 典型答案的
                 # 色板）温度恒为 50（中性），中心冷调 20 经问卷不可达，
                 # 1.5 倍权重形成永久 45 分罚分，NOIR 答卷对 MUTE 判别
                 # 余量仅 15 分，滑杆 ±10 偏差即误判静音时髦（内测实录：
                 # NOIR 答卷连测三次全部 MUTE）。冷调信号仍由 saturation
                 # 核心维度隐含覆盖（六色板中仅无彩色与冷调中饱和偏低饱和）。
                 ("silhouette", "saturation"),
                 "极低饱和、冷调、硬朗、深色执念", ("暗黑极简", "冷调深色", "硬朗肃杀"),
                 "清冷", ("个性",)),
        _persona("VOID", "人间失格", "无倾向", (),
                 (50, 30, 50, 20, 50, 10, 95),
                 ("completion", "individuality"),
                 "低完成度、高游移、方向不稳定", ("松弛游移", "低完成度", "混搭冲突"),
                 "不限制", ()),
        _persona("OOPS", "搭配事故", "无倾向", ("欧美系", "轻亚"),
                 # v1.2：individuality 中心 100 → 80。中心钉在量表极值时
                 # 只有 wardrobe=C（90）算「接近」，答 B（55）即触发
                 # 45×1.5=67.5 罚分并被 NEON（个性中心 75）接盘——内测
                 # 实录：LIKE 四值全部命中 OOPS 答卷仅因 wardrobe 答 B
                 # 即判 NEON。降到 80 后 OOPS 仍是全表次高个性中心
                 # （主动混搭辨识保留），B 答案罚分减 30 分；NEON 答卷
                 # （wardrobe=C=90）距 |90-80| 与 |90-100| 同为 15 分，
                 # NEON 判别完全不受影响。
                 (70, 90, 90, 85, 50, 70, 80),
                 ("complexity", "time_orientation", "individuality", "saturation"),
                 "高繁复、高先锋、高冲突、主动混搭", ("主动混搭", "高冲突感", "先锋实验"),
                 "个性", ("明艳",)),
    )
}

# 妆容风格枚举（用户特征×穿搭妆发标签映射方案第五节，固定枚举禁止表外同义词）。
MAKEUP_STYLES = ("自然", "甜美", "清冷", "复古", "明艳", "个性")


# ---------------------------------------------------------------------------
# 用户向量构建
# ---------------------------------------------------------------------------

def _axis(axes: dict[str, Any], key: str, default: int = 50) -> float:
    value = axes.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return float(min(100, max(0, value)))


def build_user_vector(session: dict[str, Any]) -> dict[str, Any]:
    """从 onboarding 会话记录构建用户风格向量（7 数值 + regional_style）。

    输入是内部 snake_case 会话记录（preferences/vibe）。缺失项用中性值
    50 填充、地域回退无倾向，分型照常执行（置信度自然降低）。
    """

    preferences = session.get("preferences") or {}
    axes = preferences.get("axes") or {}
    vibe = session.get("vibe") or {}

    # 前端 shape 滑杆 0=硬朗、100=柔和；算法廓形 0=柔和、100=硬朗 → 反向。
    silhouette = 100.0 - _axis(axes, "shape")
    complexity = _axis(axes, "energy")
    time_orientation = _axis(axes, "trend")

    palette = preferences.get("palette")
    signals = PALETTE_SIGNALS.get(str(palette)) if palette else None
    saturation = float(signals["saturation"]) if signals else 50.0
    temperature = float(signals["temperature"]) if signals else 50.0

    completion_value = vibe.get("occasion")
    completion = float(VIBE_COMPLETION_VALUES.get(str(completion_value), 50)) \
        if completion_value else 50.0

    individuality_value = vibe.get("wardrobe")
    individuality = float(VIBE_INDIVIDUALITY_VALUES.get(str(individuality_value), 50)) \
        if individuality_value else 50.0

    regional_value = vibe.get("expression")
    regional_style = VIBE_REGIONAL_VALUES.get(str(regional_value)) \
        if regional_value else None

    vector = {
        "silhouette": silhouette,
        "complexity": complexity,
        "time_orientation": time_orientation,
        "saturation": saturation,
        "temperature": temperature,
        "completion": completion,
        "individuality": individuality,
        "regional_style": regional_style,
    }
    vector["regional_style"] = derive_regional_style(vector)
    return vector


def derive_regional_style(vector: dict[str, Any]) -> str | None:
    """轻亚推导：不覆盖用户答案的类别，只在韩/欧美 + 特征命中时升级。

    返回值即最终 regional_style：用户答案、轻亚或 None（无倾向/未答）。
    """

    regional = vector.get("regional_style")
    if regional is None:
        return None
    if regional in LIGHT_ASIAN_SOURCE_REGIONS:
        hits = 0
        for dimension, operator, threshold in LIGHT_ASIAN_RULES:
            value = float(vector.get(dimension) or 0)
            if (operator == ">=" and value >= threshold) or (
                operator == "<=" and value <= threshold
            ):
                hits += 1
        if hits >= LIGHT_ASIAN_MIN_HITS:
            return "轻亚"
    return regional


# ---------------------------------------------------------------------------
# 分型计算
# ---------------------------------------------------------------------------

def _region_penalty(persona: Persona, regional: str | None) -> float | None:
    """地域加减分；人格主风格为无倾向时不计（返回 None 表示不参与）。"""

    if persona.primary_region == "无倾向":
        return None
    if regional is None or regional == "无倾向":
        # 用户未给出地域信号：不惩罚任何人格。
        return None
    if regional == persona.primary_region:
        return REGION_PRIMARY_PENALTY
    if regional in persona.compatible_regions:
        return REGION_COMPATIBLE_PENALTY
    return REGION_MISMATCH_PENALTY


def _persona_distance(persona: Persona, vector: dict[str, Any]) -> tuple[float, float]:
    """加权绝对距离 + 地域加减分；返回 (数值距离, 总距离)。

    工程规格定义的数值距离为 ``Σ wᵢ · |userᵢ - centerᵢ|``。
    不对差值平方，避免单个问卷维度的较大偏差被额外放大。

    权重规则：
    - 人格核心维度按 1.5 计（核心辨识，用于区分相近人格）；
    - 跨侧冲突（|user - center| > 50，用户与人格分处量表两端）时，
      不论是否核心维度一律按 1.5 计——核心维度权重只表达「区分相近
      人格」的分辨率，不能反过来让明显跨侧冲突被轻判。
    """

    weighted_distance = 0.0
    for dimension in DIMENSIONS:
        weight = CORE_DIMENSION_WEIGHT if dimension in persona.core_dimensions else BASE_DIMENSION_WEIGHT
        delta = abs(float(vector.get(dimension) or 0) - float(persona.center[dimension]))
        if delta > CROSS_SIDE_DELTA_THRESHOLD and weight < CORE_DIMENSION_WEIGHT:
            weight = CORE_DIMENSION_WEIGHT
        weighted_distance += weight * delta
    numeric_distance = weighted_distance
    penalty = _region_penalty(persona, vector.get("regional_style"))
    total = numeric_distance if penalty is None else numeric_distance + penalty
    return numeric_distance, total


def classify_persona(vector: dict[str, Any]) -> dict[str, Any]:
    """计算主/次人格与置信度（用户输入×16型人格×内容标签映射方案第五节）。"""

    ranked = sorted(
        (
            {"persona": persona, "numeric": numeric, "total": total}
            for persona in PERSONAS.values()
            for numeric, total in (_persona_distance(persona, vector),)
        ),
        key=lambda item: item["total"],
    )
    primary = ranked[0]
    secondary = ranked[1]
    primary_distance = primary["total"]
    secondary_distance = secondary["total"]
    confidence = (secondary_distance - primary_distance) / max(secondary_distance, 1.0)
    if confidence >= CONFIDENCE_HIGH:
        tier = "high"
    elif confidence >= CONFIDENCE_MID:
        tier = "mid"
    else:
        tier = "low"
    return {
        "primary_persona": primary["persona"].code,
        "secondary_persona": secondary["persona"].code,
        "primary_distance": round(primary_distance, 4),
        "secondary_distance": round(secondary_distance, 4),
        "numeric_distance": round(primary["numeric"], 4),
        "persona_confidence": round(max(0.0, min(1.0, confidence)), 4),
        "confidence_tier": tier,
    }


# ---------------------------------------------------------------------------
# 匹配过程分解（管理后台展示用；算法口径变化时需同步维护，见 docs/PERSONA_ALGORITHM.md）
# ---------------------------------------------------------------------------

# 每个维度值来自哪道题（展示层文案，与 build_user_vector 的换算一一对应）。
VECTOR_VALUE_SOURCES = {
    "silhouette": "LIKE「硬朗锐利 ↔ 柔和温柔」滑杆（反向换算：硬朗=高分）",
    "complexity": "LIKE「简约利落 ↔ 繁复华丽」滑杆",
    "time_orientation": "LIKE「经典耐看 ↔ 先锋新潮」滑杆",
    "saturation": "偏好色板（六选一映射）",
    "temperature": "偏好色板（六选一映射）",
    "completion": "VIBE「出门场合」题",
    "individuality": "VIBE「衣橱状态」题",
}


def persona_breakdown(session: dict[str, Any]) -> dict[str, Any]:
    """完整人格匹配分解：用户向量来源 + 16 型逐维度距离贡献 + 排名。

    供管理后台「人格匹配」展示与客服对齐用。输出结构与 classify_persona
    同源同口径——展示直接复用分型代码路径，算法改动自动反映到这里。
    """

    vector = build_user_vector(session)
    classification = classify_persona(vector)

    rows = []
    for persona in PERSONAS.values():
        penalty = _region_penalty(persona, vector.get("regional_style"))
        dimensions = []
        numeric = 0.0
        for dimension in DIMENSIONS:
            user_value = float(vector.get(dimension) or 0)
            center_value = float(persona.center[dimension])
            delta = abs(user_value - center_value)
            is_core = dimension in persona.core_dimensions
            weight = CORE_DIMENSION_WEIGHT if is_core else BASE_DIMENSION_WEIGHT
            cross_side = delta > CROSS_SIDE_DELTA_THRESHOLD
            effective_weight = CORE_DIMENSION_WEIGHT if cross_side else weight
            weighted = effective_weight * delta
            numeric += weighted
            dimensions.append(
                {
                    "dimension": dimension,
                    "label": DIMENSION_LABELS[dimension],
                    "userValue": round(user_value, 1),
                    "center": round(center_value, 1),
                    "delta": round(delta, 1),
                    "weight": weight,
                    "effectiveWeight": effective_weight,
                    "isCore": is_core,
                    "crossSide": cross_side,
                    "weighted": round(weighted, 1),
                }
            )
        total = numeric if penalty is None else numeric + penalty
        rows.append(
            {
                "code": persona.code,
                "name": persona.name,
                "signature": persona.signature,
                "primaryRegion": persona.primary_region,
                "coreDimensions": [DIMENSION_LABELS[d] for d in persona.core_dimensions],
                "numericDistance": round(numeric, 1),
                "regionPenalty": penalty,
                "totalDistance": round(total, 1),
                "dimensions": dimensions,
            }
        )
    rows.sort(key=lambda row: row["totalDistance"])

    user_vector_view = [
        {
            "dimension": dimension,
            "label": DIMENSION_LABELS[dimension],
            "value": round(float(vector.get(dimension) or 0), 1),
            "source": VECTOR_VALUE_SOURCES[dimension],
        }
        for dimension in DIMENSIONS
    ]

    return {
        "algorithmVersion": ALGORITHM_VERSION,
        "thresholds": {
            "coreWeight": CORE_DIMENSION_WEIGHT,
            "baseWeight": BASE_DIMENSION_WEIGHT,
            "crossSideDelta": CROSS_SIDE_DELTA_THRESHOLD,
            "regionPenalties": {
                "primary": REGION_PRIMARY_PENALTY,
                "compatible": REGION_COMPATIBLE_PENALTY,
                "mismatch": REGION_MISMATCH_PENALTY,
            },
        },
        "vector": user_vector_view,
        "regionalStyle": vector.get("regional_style"),
        "classification": classification,
        "ranking": rows,
    }


# ---------------------------------------------------------------------------
# 推荐侧的派生规则
# ---------------------------------------------------------------------------

def persona_makeup_styles(persona_code: str) -> tuple[str | None, tuple[str, ...]]:
    """人格 →（优先妆容风格, 兼容妆容风格）；「不限制」人格返回 (None, ())。"""

    persona = PERSONAS.get(persona_code)
    if persona is None:
        return None, ()
    if persona.makeup_primary == "不限制":
        return None, ()
    return persona.makeup_primary, persona.makeup_compatible


def rectangle_body_branch(vector: dict[str, Any]) -> str:
    """矩型体型的人格分叉判据。

    矩型不加题：偏柔和曲线（廓形 < 50）优先高腰/自然腰＋合体不贴造曲线；
    偏简约利落（廓形 ≥ 50）优先无腰线/自然腰＋宽松＋纵向弱化腰线。
    """

    return "soft_curve" if float(vector.get("silhouette") or 0) < 50 else "clean_line"
