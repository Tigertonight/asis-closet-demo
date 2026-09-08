const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const onboarding = fs.readFileSync('app/static/selfit/selfit.js', 'utf8');
const studio = fs.readFileSync('app/static/selfit-tryon/studio.js', 'utf8');
const urlCode = onboarding.slice(onboarding.indexOf('  const reportTryOnUrl ='), onboarding.indexOf('  const renderReport ='));
const dataCode = studio.slice(studio.indexOf('  async function loadReportOutfits()'), studio.indexOf('  async function loadPhoto()'));
const lookupCode = studio.slice(studio.indexOf('  function lookup(id)'), studio.indexOf('  function openItem(id)'));
const tryCode = studio.slice(studio.indexOf('  async function startTry()'), studio.indexOf('  function beginMirrorGeneration('));
const generateCode = studio.slice(studio.indexOf('  async function generate()'), studio.indexOf('  function failure('));
const goCode = studio.slice(studio.indexOf('  function go(page,'), studio.indexOf('  function categoryGroup('));

(async () => {
  const state = {items: [], outfits: [], feed: [{id: 'unrelated', kind: 'outfit'}], savedNotes: [], source: 'report'};
  const calls = [], dialogs = [];
  const noteIds = ['outfits-03', 'outfits-01', 'outfits-04', 'outfits-02'];
  let fail = false, legacy = false;
  const assetIds = noteIds.map((_, i) => 'asset_' + String(i).repeat(64));
  const notices = [];
  const context = vm.createContext({
    URL, URLSearchParams, Set, FormData, location: {search: ''}, state,
    $: () => ({scrollTop: 0}), render() {}, notify: message => notices.push(message),
    normalizeOutfit: row => ({id: row.outfit_id, kind: 'outfit', items: row.items.map(i => ({id: i.item_id}))}),
    generationBusy: false, reference: false, photoFile: async () => new Blob(['fixture']),
    beginMirrorGeneration: (target, photo) => {state.generating = {target, photo};},
    sessionStorage: {setItem() {}}, poll() {}, failure(message) {throw Error(message);},
    crypto: {randomUUID: () => 'test-request'}, modal: (title, body) => dialogs.push({title, body}), esc: String,
    api: async (url, options) => {
      calls.push({url, options});
      if (fail) throw Error('报告搭配暂时无法加载，请稍后重试。');
      if (url === '/selfit/try-on/jobs') return {job_id: 'test-job', status: 'queued'};
      assert(url.startsWith('/selfit/try-on/report-outfits?'));
      const query = new URL(url, 'http://localhost').searchParams;
      assert.equal(query.get('persona'), 'void');
      assert.deepEqual(query.get('note_ids').split(','), noteIds);
      assert.equal(query.get('template_id'), 'void');
      assert.deepEqual(query.get('note_assets').split(','), legacy ? noteIds.map(() => 'legacy') : assetIds);
      return {mode: 'live', template_id:'void', resolved_legacy_assets:legacy, outfits: noteIds.map((id,i) => ({outfit_id: `set-${id}`, items: [{item_id: `set-${id}-top`}], report_note: {id: `note:void:${id}`, title: id, image_asset_id:assetIds[i]}}))};
    },
  });
  vm.runInContext(urlCode + dataCode + lookupCode + tryCode + generateCode + goCode, context);
  context.cards = noteIds.map((id, i) => ({id, imageAssetId: 'asset_' + String(i).repeat(64)}));
  const url = vm.runInContext("reportTryOnUrl('void', cards)", context);
  context.location.search = new URL(url, 'http://localhost').search;
  assert.equal(new URLSearchParams(context.location.search).get('screen'), 'mirror');
  await vm.runInContext('loadReportOutfits();', context);
  await vm.runInContext('restoreSelectedOutfit(null);', context);
  assert.deepEqual(Array.from(state.reportOutfits, row => row.id), noteIds.map(id => `set-${id}`));
  assert.equal(state.current.id, 'set-outfits-03');
  assert.equal(state.reportOutfitsMode, 'live');
  assert.doesNotMatch(state.current.name, /示例搭配/);
  const second = state.reportOutfits[1].id;
  context.location.search += `&outfit=${second}`;
  await vm.runInContext('loadReportOutfits();', context);
  await vm.runInContext('restoreSelectedOutfit(new URLSearchParams(location.search).get("outfit"));', context);
  assert.equal(state.current.id, second, 'refresh restores the selected report outfit');
  assert.equal(vm.runInContext(`lookup('${second}').reportNote.id`, context), 'note:void:outfits-01');
  state.photo = state.personalPhoto = 'fixture-photo';
  await vm.runInContext('startTry();', context);
  const submitted = calls.at(-1);
  assert.equal(submitted.url, '/selfit/try-on/jobs');
  assert.equal(submitted.options.body.get('outfit_id'), second, 'try-on uses the selected mapped outfit');
  assert.equal(submitted.options.body.get('wear_all_items'), 'true');
  assert.deepEqual(Array.from(state.selected), [`${second}-top`]);
  assert.equal(dialogs.length, 0, 'submit directly without piece confirmation');
  context.cards = noteIds.map((id,i) => ({id, assetId:assetIds[i], imageUrl:'https://cdn.example.com/look.jpg'}));
  const backendUrl = vm.runInContext("reportTryOnUrl('void', cards)", context);
  assert.equal(new URL(backendUrl,'http://localhost').searchParams.get('report_assets'), assetIds.join(','), 'backend assetId works without an ID in its URL');
  context.cards = noteIds.map((id,i) => ({id, imageUrl:`/api/v1/material-assets/${assetIds[i]}/content`}));
  assert.equal(vm.runInContext("reportTryOnUrl('void', cards)", context), backendUrl);
  context.cards = noteIds.map(id => ({id, imageUrl:'https://cdn.example.com/old.jpg'}));
  const legacyUrl = vm.runInContext("reportTryOnUrl('void', cards)", context);
  context.location.href = 'http://localhost' + legacyUrl + `&outfit=${second}`;
  context.location.search = new URL(context.location.href).search;
  context.history = {state:null, replaceState:(_, __, url) => {context.location.href=url.href;context.location.search=url.search;}};
  legacy = true;
  await vm.runInContext('loadReportOutfits();', context);
  await vm.runInContext('restoreSelectedOutfit(new URLSearchParams(location.search).get("outfit"));', context);
  assert.equal(state.current.id, second);
  assert.equal(new URL(context.location.href).searchParams.get('report_assets'), assetIds.join(','));
  assert.equal(notices.length, 0, 'legacy migration does not show a toast');
  assert.equal(new URLSearchParams(state.reportOutfitsKey).get('note_assets'), assetIds.join(','));
  legacy = false;
  await vm.runInContext('loadReportOutfits();', context);
  assert.equal(notices.length, 0, 'canonical refresh remains silent');
  fail = true;
  await assert.rejects(() => vm.runInContext('loadReportOutfits();', context), /报告搭配暂时无法加载/);
  assert.equal(state.current, null);
  assert.equal(state.reportOutfits.length, 0, 'no recommendation fallback on mapping failure');
  context.location.search = '?screen=mirror';
  state.source = 'inspiration';
  const count = calls.length;
  await vm.runInContext('loadReportOutfits(); restoreSelectedOutfit(null);', context);
  assert.equal(calls.length, count, 'normal mirror entry does not fetch report mappings');
  assert.equal(state.current.id, 'unrelated');
  state.source = 'report';
  context.location.href = 'http://localhost' + url;
  context.history = {pushState: (_, __, url) => {context.location.href = url.href;}};
  await vm.runInContext('go("detail");', context);
  assert.equal(state.source, 'inspiration');
  assert.equal(new URL(context.location.href).searchParams.has('report_notes'), false, 'opening an unrelated outfit must leave the report collection before refresh');
  assert.equal((onboarding.match(/continueToApp\.href\s*=/g) || []).length, 1, 'report generation must not overwrite the handoff');
  let errorStatus = 409;
  const errors = vm.createContext({AbortController, setTimeout, clearTimeout, savedSession:null,
    fetch:async () => ({ok:false,status:errorStatus,json:async () => ({detail:'报告穿搭素材已更新，请重新生成报告后再试。'})})});
  vm.runInContext(studio.slice(studio.indexOf('  async function api('), studio.indexOf('  function nav()')), errors);
  await assert.rejects(() => vm.runInContext("api('/selfit/try-on/report-outfits?persona=void')", errors), /报告穿搭素材已更新/);
  errorStatus = 500;
  await assert.rejects(() => vm.runInContext("api('/selfit/try-on/report-outfits?persona=void')", errors), /这次操作没有完成/);
  console.log('Report handoff, order, refresh, selected try-on payload, recovery and normal entry passed.');
})().catch(error => { console.error(error); process.exitCode = 1; });
