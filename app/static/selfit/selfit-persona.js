(() => {
  // selfit 十六型人格分型算法（mock 模式前端移植版）。
  // 逻辑必须与后端 app/selfit_persona.py 保持一致（单一算法口径），
  // 修改任何中心点 / 权重 / 阈值时两侧同步更新，并由
  // tests/test_selfit_persona.py::test_frontend_mock_persona_matches_backend 对拍校验。
  const DIMENSIONS = [
    'silhouette', 'complexity', 'time_orientation',
    'saturation', 'temperature', 'completion', 'individuality',
  ];

  const VIBE_COMPLETION_VALUES = { A: 10, B: 40, C: 70, D: 95 };
  const VIBE_INDIVIDUALITY_VALUES = { A: 20, B: 55, C: 90 };
  const VIBE_REGIONAL_VALUES = { A: '日系', B: '韩系', C: '欧美系', D: '中式', E: '法式' };

  const PALETTE_SIGNALS = {
    mono: { saturation: 5, temperature: 50 },
    earth: { saturation: 20, temperature: 65 },
    ocean: { saturation: 55, temperature: 20 },
    jewel: { saturation: 55, temperature: 80 },
    bright: { saturation: 90, temperature: 50 },
    pastel: { saturation: 30, temperature: 50 },
  };

  const LIGHT_ASIAN_RULES = [
    ['silhouette', '>=', 65],
    ['time_orientation', '>=', 70],
    ['temperature', '<=', 40],
    ['completion', '>=', 70],
    ['individuality', '>=', 60],
  ];
  const LIGHT_ASIAN_MIN_HITS = 3;
  const LIGHT_ASIAN_SOURCE_REGIONS = new Set(['韩系', '欧美系']);

  const REGION_COMPATIBLE_PENALTY = 5.0;
  const REGION_MISMATCH_PENALTY = 15.0;

  const CORE_DIMENSION_WEIGHT = 1.5;
  const BASE_DIMENSION_WEIGHT = 1.0;

  // 中心点 7 元组顺序 = DIMENSIONS：(廓形, 繁简, 时间, 饱和度, 冷暖, 完成度, 个性)
  // [code, center, coreDimensions, primaryRegion, compatibleRegions]
  const PERSONA_ROWS = [
    ['MUTE', [75, 10, 40, 10, 35, 70, 20], ['silhouette', 'complexity', 'saturation'], '无倾向', ['日系', '韩系']],
    ['ICED', [25, 20, 65, 25, 15, 75, 25], ['silhouette', 'temperature', 'completion'], '韩系', ['轻亚']],
    ['HEIR', [70, 30, 15, 25, 60, 90, 15], ['silhouette', 'time_orientation', 'completion'], '欧美系', ['法式']],
    ['EASE', [25, 25, 25, 25, 65, 60, 25], ['silhouette', 'time_orientation', 'temperature'], '法式', ['韩系']],
    ['MELT', [20, 70, 60, 35, 65, 75, 35], ['complexity', 'saturation', 'completion'], '韩系', ['日系']],
    ['WABI', [25, 20, 10, 15, 55, 35, 20], ['complexity', 'time_orientation', 'saturation'], '日系', ['中式']],
    ['FLOU', [15, 90, 30, 35, 60, 90, 45], ['complexity', 'completion', 'silhouette'], '法式', ['中式']],
    ['NEON', [65, 75, 90, 95, 50, 75, 75], ['saturation', 'time_orientation', 'individuality'], '欧美系', ['轻亚']],
    ['EDGE', [85, 65, 85, 45, 20, 90, 70], ['silhouette', 'temperature', 'time_orientation'], '轻亚', ['韩系', '欧美系']],
    ['BOLT', [55, 75, 20, 35, 45, 95, 55], ['complexity', 'completion', 'time_orientation'], '法式', ['欧美系']],
    ['FILM', [30, 40, 20, 35, 70, 40, 45], ['time_orientation', 'temperature', 'completion'], '法式', ['日系']],
    ['JADE', [70, 40, 15, 30, 50, 80, 35], ['silhouette', 'time_orientation', 'saturation'], '中式', []],
    ['LOOP', [50, 50, 50, 50, 50, 95, 60], ['completion', 'individuality'], '无倾向', []],
    ['NOIR', [75, 35, 65, 5, 20, 80, 35], ['saturation', 'temperature', 'silhouette'], '无倾向', ['轻亚', '欧美系']],
    ['VOID', [50, 30, 50, 20, 50, 10, 95], ['completion', 'individuality'], '无倾向', []],
    ['OOPS', [70, 90, 90, 85, 50, 70, 100], ['complexity', 'time_orientation', 'individuality', 'saturation'], '无倾向', ['欧美系', '轻亚']],
  ];

  const PERSONAS = PERSONA_ROWS.map(([code, center, coreDimensions, primaryRegion, compatibleRegions]) => ({
    code,
    center: Object.fromEntries(DIMENSIONS.map((dimension, index) => [dimension, center[index]])),
    coreDimensions: new Set(coreDimensions),
    primaryRegion,
    compatibleRegions: new Set(compatibleRegions),
  }));

  const axisValue = (axes, key) => {
    const value = axes?.[key];
    if (typeof value !== 'number' || Number.isNaN(value)) return 50;
    return Math.min(100, Math.max(0, value));
  };

  const buildUserVector = (session = {}) => {
    const preferences = session.preferences || {};
    const axes = preferences.axes || {};
    // mock 会话把 VIBE 答案存为顶层 answers（live 后端为 vibe），两者都兼容。
    const vibe = session.vibe || session.answers || {};

    const silhouette = 100 - axisValue(axes, 'shape');
    const complexity = axisValue(axes, 'energy');
    const timeOrientation = axisValue(axes, 'trend');

    const signals = preferences.palette ? PALETTE_SIGNALS[String(preferences.palette)] : null;
    const saturation = signals ? signals.saturation : 50;
    const temperature = signals ? signals.temperature : 50;

    const completionValue = vibe.occasion;
    const completion = completionValue && Object.hasOwn(VIBE_COMPLETION_VALUES, String(completionValue))
      ? VIBE_COMPLETION_VALUES[String(completionValue)] : 50;

    const individualityValue = vibe.wardrobe;
    const individuality = individualityValue && Object.hasOwn(VIBE_INDIVIDUALITY_VALUES, String(individualityValue))
      ? VIBE_INDIVIDUALITY_VALUES[String(individualityValue)] : 50;

    let regionalStyle = vibe.expression ? (VIBE_REGIONAL_VALUES[String(vibe.expression)] || null) : null;

    const vector = {
      silhouette, complexity, time_orientation: timeOrientation,
      saturation, temperature, completion, individuality,
      regional_style: regionalStyle,
    };
    vector.regional_style = deriveRegionalStyle(vector);
    return vector;
  };

  const deriveRegionalStyle = (vector) => {
    const regional = vector.regional_style;
    if (regional === null || regional === undefined) return null;
    if (LIGHT_ASIAN_SOURCE_REGIONS.has(regional)) {
      let hits = 0;
      for (const [dimension, operator, threshold] of LIGHT_ASIAN_RULES) {
        const value = Number(vector[dimension]) || 0;
        if ((operator === '>=' && value >= threshold) || (operator === '<=' && value <= threshold)) hits += 1;
      }
      if (hits >= LIGHT_ASIAN_MIN_HITS) return '轻亚';
    }
    return regional;
  };

  const regionPenalty = (persona, regional) => {
    if (persona.primaryRegion === '无倾向') return null;
    if (regional === null || regional === undefined || regional === '无倾向') return null;
    if (regional === persona.primaryRegion) return 0;
    if (persona.compatibleRegions.has(regional)) return REGION_COMPATIBLE_PENALTY;
    return REGION_MISMATCH_PENALTY;
  };

  const personaDistance = (persona, vector) => {
    let weightedDistance = 0;
    for (const dimension of DIMENSIONS) {
      const weight = persona.coreDimensions.has(dimension) ? CORE_DIMENSION_WEIGHT : BASE_DIMENSION_WEIGHT;
      const delta = (Number(vector[dimension]) || 0) - persona.center[dimension];
      weightedDistance += weight * Math.abs(delta);
    }
    const penalty = regionPenalty(persona, vector.regional_style);
    return { numeric: weightedDistance, total: penalty === null ? weightedDistance : weightedDistance + penalty };
  };

  const classifyPersona = (vector) => {
    const ranked = PERSONAS
      .map((persona) => ({ persona, ...personaDistance(persona, vector) }))
      .sort((a, b) => a.total - b.total);
    const primary = ranked[0];
    const secondary = ranked[1];
    const confidence = (secondary.total - primary.total) / Math.max(secondary.total, 1.0);
    return {
      primary_persona: primary.persona.code,
      secondary_persona: secondary.persona.code,
      primary_distance: primary.total,
      secondary_distance: secondary.total,
      numeric_distance: primary.numeric,
      persona_confidence: Math.max(0, Math.min(1, confidence)),
    };
  };

  window.SelfitPersona = Object.freeze({
    DIMENSIONS,
    PALETTE_SIGNALS,
    buildUserVector,
    deriveRegionalStyle,
    classifyPersona,
  });
})();
