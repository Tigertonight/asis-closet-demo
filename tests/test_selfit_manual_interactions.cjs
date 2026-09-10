const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');
const source = fs.readFileSync(path.resolve(__dirname, '../app/static/selfit/selfit.js'), 'utf8');
const section = (start, end) => source.slice(source.indexOf(start), source.indexOf(end, source.indexOf(start)));

function harness() {
  const events = {}, nodes = new Map(), saves = [], screens = [], storage = new Map();
  const node = selector => {
    if (!nodes.has(selector)) nodes.set(selector, { dataset: {}, classList: { toggle() {} }, setAttribute() {},
      addEventListener: (type, fn) => { events[selector + ':' + type] = fn; } });
    return nodes.get(selector);
  };
  const state = { manual: { skin: '暖黄肤', faceShape: '椭圆脸', bodyShape: '矩型' }, authUser: { user_id: 'test-user' }, sessionId: 'old' };
  let created = 0, restored = 0;
  const context = {
    state, document: { querySelector: node, querySelectorAll: () => [], documentElement: { lang: 'zh-CN' } },
    showScreen: name => screens.push(name), setPhotoState() {}, resetOnboardingPhotos() {}, track() {},
    runButtonAction: (_, action) => action(), authReady: Promise.resolve(), retestEntry: false,
    SESSION_STORAGE_KEY: 'session', localStorage: { getItem: k => storage.get(k), setItem: (k,v) => storage.set(k,v), removeItem: k => storage.delete(k) },
    api: {
      saveManualProfile: async (_, profile) => { saves.push(profile); return { session: { revision: 2 } }; },
      getSession: async () => { restored++; return { session: { sessionId: 'old', revision: 2 } }; },
      createSession: async () => { created++; return { session: { sessionId: 'new', revision: 1 } }; },
    },
  };
  vm.createContext(context);
  vm.runInContext(section('  let editingFeature = null;', '  let suitRenderSeq = 0;') +
    section('  let sessionPromise = null;', '  const reportNodes = {') +
    section("  document.querySelector('.manual-form').addEventListener", "  document.querySelector('#paletteGrid').addEventListener") +
    '\nthis.open = openManual; this.begin = startNewAssessment; this.ensure = ensureSession;', context);
  return { context, node, state, saves, screens, storage, counts: () => ({created, restored}),
    choose: (key, value) => events['.manual-form:click']({ target: { closest: () => ({ dataset: { manual: key, value } }) } }),
    save: () => events['#manualNext:click']({ currentTarget: node('#manualNext') }) };
}

test('opening the editor with an inferred value does not enable or submit a manual save', async () => {
  const h = harness(); h.context.open('skin');
  assert.equal(h.node('#manualNext').disabled, true);
  await h.save();
  assert.equal(h.saves.length, 0);
});
for (const [field, value] of [['skin','冷白肤'],['faceShape','方脸'],['bodyShape','梨型']]) {
  test(`${field}: only the explicitly clicked field is saved`, async () => {
    const h = harness(); h.context.open(field); h.choose(field,value);
    assert.equal(h.node('#manualNext').disabled, false);
    await h.save();
    assert.deepEqual(JSON.parse(JSON.stringify(h.saves)), [{[field]:value}]);
  });
}
test('reopening clears an unsaved choice; inferred fields are not submitted in setup', async () => {
  const h = harness(); h.context.open('skin'); h.choose('skin','冷白肤'); h.context.open('skin');
  await h.save(); assert.equal(h.saves.length,0);
  h.context.open(); h.choose('bodyShape','梨型'); await h.save();
  assert.deepEqual(JSON.parse(JSON.stringify(h.saves)), [{bodyShape:'梨型'}]);
});
test('starting again creates a new session without erasing the old session or report', async () => {
  const h = harness();
  h.storage.set('session', JSON.stringify({sessionId:'old',userId:'test-user'}));
  h.context.begin();
  assert.equal(h.storage.get('session').includes('old'), true);
  assert.equal(await h.context.ensure(),'new');
  assert.deepEqual(h.counts(),{created:1,restored:0});
  assert.equal(h.state.manual.skin,null);
});
test('ordinary draft resumption still restores the saved session', async () => {
  const h = harness(); h.state.sessionId=null;
  h.storage.set('session', JSON.stringify({sessionId:'old',userId:'test-user'}));
  assert.equal(await h.context.ensure(),'old');
  assert.deepEqual(h.counts(),{created:0,restored:1});
});

test('profile editor submits only explicit changes, not the prefilled photo values', async () => {
  const studio = fs.readFileSync(path.resolve(__dirname, '../app/static/selfit-tryon/studio.js'), 'utf8');
  const block = studio.slice(studio.indexOf('  async function saveProfile()'), studio.indexOf('  function restoreTryonRecord'));
  const writes = [];
  const profile = {tested:true,revision:1,manual:{skin:'暖黄肤',faceShape:'椭圆脸',bodyShape:'矩型'},report:{reportId:'report-test'}};
  const context = {state:{profile,profileManualChanges:{skin:'冷白肤'},profilePhotoDraft:{}},reference:false,
    render(){},go(){},notify(){},api:async (_,options)=>{
      if(options?.method==='PATCH') writes.push(JSON.parse(options.body));
      return {profile};
    }};
  vm.createContext(context); vm.runInContext(block,context);
  await context.saveProfile();
  assert.deepEqual(writes,[{reportId:'report-test',manual:{skin:'冷白肤'}}]);
});
