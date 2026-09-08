(() => {
  const clone = value => JSON.parse(JSON.stringify(value));
  const names = {LOOP: '无限重启', WABI: '手作侘寂', VOID: '人间失格', FILM: '虚焦胶片'};
  const bodyProfile = data => data.bodyProfile === 'curvy' ||
    String(data.templateId || '').toLowerCase() === `${String(data.code || '').toLowerCase()}-curvy` ||
    String(data.name || '').endsWith('-微胖') ? 'curvy' : 'standard';
  const key = data => `${String(data.code || '').toUpperCase()}:${bodyProfile(data)}:${data.gender || 'unisex'}`;

  // Body profile is independent of the 16 persona codes and existing body-shape tags.
  function seeds(base) {
    const variants = Object.entries(names).flatMap(([code, name]) => {
      const original = base.find(item => key(item) === `${code}:standard:unisex`);
      if (!original || base.some(item => key(item) === `${code}:curvy:unisex`)) return [];
      const variant = clone(original);
      variant.name = `${name}-微胖`;
      variant.bodyProfile = 'curvy';
      variant.updatedAt = '';
      // Keep persona identity, colors, makeup and hair as an editable starting point.
      // Unreviewed original outfits must not masquerade as body-specific recommendations.
      variant.outfits = Array.from({length: 4}, () => ({name: '', byline: '', image: ''}));
      variant.outfitLibrary = [];
      variant.outfitSummary = '';
      variant.advice = ['', '', ''];
      variant.source = {...variant.source, copy: '微胖穿搭素材待配置'};
      variant.masterData = {
        typeId: original.masterData?.typeId || code.toLowerCase(),
        sourceCount: 0,
      };
      return [variant];
    });
    const maleDefinitions = {
      MUTE: ['静音时髦', ['克制', '秩序', '低表达']],
      HEIR: ['老钱新穿', ['经典', '质感', '体面']],
      WABI: ['手作侘寂', ['天然', '肌理', '手工感']],
      EDGE: ['甜酷轻亚', ['少年', '反差', '轻叛逆']],
      NEON: ['灵动吸睛', ['活力', '色彩', '社交感']],
      VOID: ['人间失格', ['风格未定', '偏好游移', '单套有美感']],
      NOIR: ['暗黑肃杀', ['全黑', '防御', '冷硬']],
    };
    const male = Object.entries(maleDefinitions).flatMap(([code, [name, keywords]]) => {
      const original = base.find(item => key(item) === `${code}:standard:unisex`);
      if (!original || base.some(item => key(item) === `${code}:standard:male`)) return [];
      const variant = clone(original);
      Object.assign(variant, {name: `${name}-男`, gender: 'male', bodyProfile: 'standard',
        keywords, updatedAt: '', hero: '/static/selfit/assets/personality/placeholder-hero.svg',
        outfitSummary: '', advice: ['', '', ''], outfitLibrary: [],
        masterData: {typeId: original.masterData?.typeId || code.toLowerCase(), sourceCount: 0}});
      for (const group of ['makeup', 'hair', 'outfits']) {
        variant[group] = Array.from({length: group === 'outfits' ? 4 : 2}, () => ({name: '', byline: '', image: ''}));
        delete variant[`${group}Library`];
      }
      variant.outfitLibrary = [];
      variant.source = {...variant.source, copy: '男性参考素材待配置'};
      return [variant];
    });
    return [...base, ...variants, ...male];
  }

  function appendMissing(records, seedData, recordFrom) {
    const existing = new Set(records.map(record => key(record.data)));
    seedData.forEach(seed => {
      if (existing.has(key(seed))) return;
      records.push(recordFrom(seed));
      existing.add(key(seed));
    });
  }

  window.SELFIT_BODY_VARIANTS = {key, bodyProfile, seeds, appendMissing};
})();
