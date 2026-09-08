const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const context = vm.createContext({window: {}});
for (const file of ['seed-templates.js', 'body-variants.js']) {
  vm.runInContext(fs.readFileSync(`app/static/report-builder/${file}`, 'utf8'), context);
}
const api = context.window.SELFIT_BODY_VARIANTS;
const delivered = context.window.SELFIT_REPORT_MASTER_DATA.templates;
const base = delivered.filter(item => item.bodyProfile !== 'curvy');
const copy = value => JSON.parse(JSON.stringify(value));

test('four body variants keep persona identity and isolate unreviewed outfits', () => {
  const before = JSON.stringify(base);
  const seeds = api.seeds(base);
  assert.equal(seeds.length, 27);
  assert.equal(new Set(seeds.map(api.key)).size, 27);
  for (const code of ['LOOP', 'WABI', 'VOID', 'FILM']) {
    const original = seeds.find(item => api.key(item) === `${code}:standard:unisex`);
    const variant = seeds.find(item => api.key(item) === `${code}:curvy:unisex`);
    assert.equal(variant.code, original.code);
    assert.equal(variant.masterData.typeId, original.masterData.typeId);
    assert.ok(variant.name.endsWith('-微胖'));
    assert.equal(variant.outfitLibrary.length, 0);
    assert.ok(variant.outfits.every(item => !item.image && !item.sourceUrl));
    variant.colors[0].name = 'changed';
    assert.notEqual(original.colors[0].name, 'changed');
  }
  assert.equal(JSON.stringify(base), before);
  assert.equal(api.seeds(seeds).length, 27);
});

test('migration preserves custom edits and active record identities without duplicating variants', () => {
  const records = base.map((data, id) => ({id, data: copy(data)}));
  records[0].data.summary = '已编辑';
  const saved = JSON.stringify(records);
  const add = data => ({id: records.length, data: copy(data)});
  api.appendMissing(records, api.seeds(base), add);
  assert.equal(records.length, 27);
  assert.equal(JSON.stringify(records.slice(0, 16)), saved);
  records[16].data.name = '自定义微胖标题';
  api.appendMissing(records, api.seeds(base), add);
  assert.equal(records.length, 27);
  assert.equal(records[16].data.name, '自定义微胖标题');
  assert.equal(api.key(copy(records[16].data)), 'LOOP:curvy:unisex');
});

test('builder migrates saved v7 library and preserves body profile through JSON normalization', () => {
  const source = fs.readFileSync('app/static/report-builder/builder.js', 'utf8');
  const setup = source.slice(0, source.indexOf('  const $ ='));
  const helpers = source.slice(source.indexOf('  function clone('), source.indexOf('  function persist('));
  vm.runInContext(`${setup}\n${helpers}\nwindow.testBuilder={normalize,migrateLibrary};})();`, context);
  const builder = context.window.testBuilder;
  const records = base.map((data, id) => ({id: String(id), data: copy(data)}));
  records[0].data.summary = '保留编辑';
  const migrated = builder.migrateLibrary({seedVersion: 7, activeId: '3', templates: records});
  assert.equal(migrated.templates.length, 27);
  assert.equal(migrated.activeId, '3');
  assert.equal(migrated.templates[0].data.summary, '保留编辑');
  const normalized = builder.normalize(copy(migrated.templates.find(item => api.key(item.data) === 'LOOP:curvy:unisex')));
  assert.equal(normalized.bodyProfile, 'curvy');
  assert.equal(normalized.code, 'LOOP');
  assert.ok(normalized.outfits.every(item => item.image));
  assert.equal(builder.normalize(base[0]).bodyProfile, 'standard');
  assert.equal(builder.migrateLibrary(migrated).templates.length, 27);
});

test('seven male templates retain exact names and keywords through import normalization', () => {
  const expected = {
    MUTE: ['静音时髦-男', ['克制', '秩序', '低表达']],
    HEIR: ['老钱新穿-男', ['经典', '质感', '体面']],
    WABI: ['手作侘寂-男', ['天然', '肌理', '手工感']],
    EDGE: ['甜酷轻亚-男', ['少年', '反差', '轻叛逆']],
    NEON: ['灵动吸睛-男', ['活力', '色彩', '社交感']],
    VOID: ['人间失格-男', ['风格未定', '偏好游移', '单套有美感']],
    NOIR: ['暗黑肃杀-男', ['全黑', '防御', '冷硬']],
  };
  const male = api.seeds(base).filter(item => item.gender === 'male');
  assert.equal(male.length, 7);
  for (const item of male) {
    const normalized = context.window.testBuilder.normalize(copy(item));
    assert.equal(normalized.name, expected[item.code][0]);
    assert.deepEqual(copy(normalized.keywords), expected[item.code][1]);
    assert.equal(normalized.gender, 'male');
    assert.equal(normalized.bodyProfile, 'standard');
    assert.equal(api.key(normalized), `${item.code}:standard:male`);
    for (const group of ['makeup', 'hair', 'outfits']) {
      assert.ok(normalized[group].every(card => !card.image && !card.sourceUrl));
    }
  }
});

test('v8 migration preserves custom copy while filling previously empty curvy cards', () => {
  const records = api.seeds(base).filter(item => item.gender !== 'male').map((data, id) => ({id: String(id), data: copy(data)}));
  records[16].data.summary = '微胖版本已编辑';
  const before = JSON.stringify(records.slice(0, 16));
  const migrated = context.window.testBuilder.migrateLibrary({seedVersion: 8, activeId: '16', templates: records});
  assert.equal(migrated.templates.length, 27);
  assert.equal(migrated.activeId, '16');
  assert.ok(JSON.stringify(migrated.templates.slice(0, 16)) === before);
  assert.equal(migrated.templates[16].data.summary, '微胖版本已编辑');
  assert.ok(migrated.templates[16].data.outfits.every(item => item.image));
  assert.equal(migrated.seedVersion, 14);
});

test('Cowork editor preserves audience fields and exact male keywords with remote persistence', () => {
  const source = fs.readFileSync('cowork/report-template-editor/web/assets/builder.js', 'utf8');
  const setup = source.slice(0, source.indexOf('  const $ ='));
  const helpers = source.slice(source.indexOf('  function clone('), source.indexOf('  function recordFrom('));
  vm.runInContext(`${setup}\n${helpers}\nwindow.remoteNormalize=normalize;})();`, context);
  const remote = JSON.parse(fs.readFileSync('cowork/report-template-editor/web/assets/16-personality-templates.json', 'utf8'));
  assert.equal(remote.templates.length, 27);
  assert.equal(new Set(remote.templates.map(api.key)).size, 27);
  const male = remote.templates.find(item => item.code === 'VOID' && item.gender === 'male');
  const result = context.window.remoteNormalize(male);
  assert.equal(result.gender, 'male');
  assert.equal(result.keywords[2], '单套有美感');
  assert.equal(api.key(result), 'VOID:standard:male');
});

test('delivered curvy sets retain their four configured cards without replacing defaults', () => {
  const seeds = api.seeds(delivered);
  assert.equal(seeds.length, 27);
  assert.equal(new Set(seeds.map(api.key)).size, 27);
  for (const code of ['FILM', 'WABI', 'LOOP', 'VOID']) {
    const variant = seeds.find(item => api.key(item) === `${code}:curvy:unisex`);
    const standard = seeds.find(item => api.key(item) === `${code}:standard:unisex`);
    assert.equal(variant.outfits.length, 4);
    assert.ok(variant.outfits.every((item, i) => item.image && item.position === i + 1));
    assert.notDeepEqual(copy(variant.outfits), copy(standard.outfits));
  }
});

test('legacy wrong bodyProfile is repaired by stable template ID before import matching', () => {
  const legacy = {code: 'FILM', templateId: 'film-curvy', name: '自定义标题', bodyProfile: 'standard'};
  const normalized = context.window.testBuilder.normalize(legacy);
  assert.equal(normalized.bodyProfile, 'curvy');
  assert.equal(api.key(legacy), 'FILM:curvy:unisex');
  const byName = context.window.testBuilder.normalize({code: 'WABI', name: '手作侘寂-微胖', bodyProfile: 'standard'});
  assert.equal(byName.bodyProfile, 'curvy');
});

test('v14 migration updates older notes but preserves newer saved work', () => {
  const data = copy(base.find(item => item.code === 'BOLT'));
  data.outfits[0].name = '旧笔记';
  const older = {id: 'old', updatedAt: '2026-09-01T00:00:00Z', data};
  const newer = {id: 'new', updatedAt: '2026-09-10T00:00:00Z', data: copy(data)};
  const migrated = context.window.testBuilder.migrateLibrary({seedVersion: 9, templates: [older, newer]});
  assert.equal(migrated.templates.find(x => x.id === 'old').data.outfits[0].name, '高智衬衫');
  assert.equal(migrated.templates.find(x => x.id === 'new').data.outfits[0].name, '旧笔记');
});
