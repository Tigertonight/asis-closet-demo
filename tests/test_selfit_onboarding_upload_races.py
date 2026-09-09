"""Exercise the actual upload event handler with controllable async responses."""
from pathlib import Path
import subprocess


def test_replacing_and_retrying_photos_keeps_the_latest_selection_authoritative():
    runtime = Path(__file__).parents[1] / "app/static/selfit/selfit.js"
    harness = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync(process.argv[1], 'utf8');
const validation = source.slice(source.indexOf('  const validatePhoto ='), source.indexOf('  const renderPhotoPreview ='));
const upload = source.slice(source.indexOf('  const uploadPhoto ='), source.indexOf("  bindUpload('facePhoto'"));
const input = { files: [], value: 'selected', addEventListener(_, listener) { this.change = listener; } };
const requests = [];
const statuses = [];
const renders = [];
const overlays = [];
const state = { screen: 'suit', photoAssets: { face: 'old-asset' }, photoStatus: { face: 'empty', body: 'empty' }, photoControllers: { face: null, body: null }, revision: 0 };
const context = vm.createContext({
  AbortController,
  document: { querySelector: (selector) => selector === '#facePhoto' ? input : {} },
  state,
  ensureSession: async () => 'isolated-test-session',
  renderPhotoPreview() {}, track() {}, showScreen() {},
  renderSuit() { renders.push(Date.now()); return Promise.resolve(); },
  applyAnalysisOverlay(kind) { overlays.push(kind); return Promise.resolve(); },
  setPhotoState(kind, status, copy) { statuses.push({ kind, status, copy }); state.photoStatus[kind] = status; },
  api: { checkPhoto(session, kind, file, { signal }) {
    return new Promise((resolve, reject) => requests.push({ resolve, reject, signal, file }));
  } },
});
vm.runInContext(validation + upload + "\nbindUpload('facePhoto', 'face');", context);
const photo = (name) => ({name, size: 1024, type: 'image/jpeg'});
const select = (file) => { input.files = file ? [file] : []; input.value = 'selected'; return input.change(); };
const accepted = (assetId) => ({revision: 2, photo: {status: 'accepted', assetId}});
const flush = () => new Promise(resolve => setImmediate(resolve));
const settle = async () => { await flush(); await flush(); };
(async () => {
  select(photo('first.jpg')); await flush();
  assert.equal(input.value, '', 'reset the input so the same file can be retried');
  select(photo('second.jpg')); await flush();
  assert.equal(requests[0].signal.aborted, true);
  assert.equal(state.photoAssets.face, null, 'old accepted photo must not enable next during replacement');
  requests[0].reject(new Error('old request aborted')); await settle();
  assert.equal(statuses.at(-1).status, 'checking', 'old rejection must not invalidate the new image');
  requests[1].resolve(accepted('second-asset')); await settle();
  assert.equal(state.photoAssets.face, 'second-asset');
  assert.equal(statuses.at(-1).status, 'valid');
  assert.equal(renders.length, 1, 'an accepted photo renders the inline result immediately');
  assert.equal(overlays.length, 1, 'an accepted photo draws analysis lines on its upload card');
  const count = statuses.length; select(null);
  assert.equal(statuses.length, count, 'cancelling the chooser retains the accepted image');

  select(photo('late.jpg')); await flush();
  await select({name: 'document.pdf', type: 'application/pdf', size: 1024});
  assert.equal(requests[2].signal.aborted, true);
  requests[2].resolve(accepted('stale-asset')); await settle();
  assert.equal(state.photoAssets.face, null);
  assert.equal(statuses.at(-1).status, 'invalid', 'late success cannot overwrite a newer invalid selection');
  assert.match(statuses.at(-1).copy, /请选择一张照片/);

  select(photo('second.jpg')); await flush();
  requests[3].resolve(accepted('retry-asset')); await settle();
  assert.equal(state.photoAssets.face, 'retry-asset');
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    subprocess.run(["node", "-e", harness, str(runtime)], check=True, capture_output=True, text=True)


def test_each_accepted_photo_renders_inline_and_survives_summary_failures():
    runtime = Path(__file__).parents[1] / "app/static/selfit/selfit.js"
    harness = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync(process.argv[1], 'utf8');
const validation = source.slice(source.indexOf('  const validatePhoto ='), source.indexOf('  const renderPhotoPreview ='));
const photoStatus = source.slice(source.indexOf('  const syncSuitButton ='), source.indexOf('  let editingFeature ='));
const upload = source.slice(source.indexOf('  const uploadPhoto ='), source.indexOf('  // Built-in sample photos'));
const timeout = setTimeout(() => { console.error('Upload flow did not settle'); process.exitCode = 1; }, 5000);
const flush = () => new Promise(resolve => setImmediate(resolve));
const accepted = (id) => ({revision: 2, photo: {status: 'accepted', assetId: id}});
function setup() {
  const node = () => ({files: [], value: '', disabled: true, dataset: {}, hidden: false, classList: {toggle() {}, remove() {}, add() {}}, replaceChildren() {}, addEventListener(event, fn) {this[event] = fn;}, onclick: null});
  const nodes = {'#facePhoto': node(), '#bodyPhoto': node(), '#suitNext': node()};
  const state = {screen: 'suit', photoStatus: {face: 'empty', body: 'empty'}, photoAssets: {face: null, body: null}, photoControllers: {face: null, body: null}, revision: 0};
  const requests = [], renders = [], overlays = [], messages = [];
  const context = vm.createContext({
    AbortController, state,
    document: {querySelector(selector) {return nodes[selector] || (nodes[selector] = node()); }},
    ensureSession: async () => 'test-session',
    renderPhotoPreview() {}, track() {},
    toast(message) {messages.push(message);},
    renderSuit() {return new Promise((resolve, reject) => renders.push({resolve, reject}));},
    applyAnalysisOverlay(kind) {overlays.push(kind); return Promise.resolve();},
    api: {checkPhoto(session, kind, file, {signal}) {
      return new Promise((resolve, reject) => requests.push({kind, file, signal, resolve, reject}));
    }},
  });
  vm.runInContext(validation + photoStatus + upload, context);
  const select = (kind, name = kind + '.jpg') => {
    const input = nodes['#' + kind + 'Photo'];
    input.files = [{name, type: 'image/jpeg', size: 1024}];
    return input.change();
  };
  return {state, requests, renders, overlays, messages, select, button: nodes['#suitNext']};
}
(async () => {
  for (const firstKind of ['face', 'body']) {
    const t = setup(), secondKind = firstKind === 'face' ? 'body' : 'face';
    t.select(firstKind); await flush();
    assert.equal(t.renders.length, 0, 'a pending upload must not render results');
    t.requests[0].resolve(accepted(firstKind)); await flush(); await flush();
    assert.equal(t.state.screen, 'suit', 'results render inline without leaving the upload page');
    assert.equal(t.renders.length, 1, 'each accepted photo re-runs the suit summary render');
    assert.equal(t.button.disabled, true, 'one accepted photo alone keeps the primary action locked');
    t.select(secondKind); await flush();
    t.requests[1].resolve(accepted(secondKind)); await flush(); await flush();
    assert.equal(t.renders.length, 2);
    assert.equal(t.button.disabled, false, 'both accepted photos unlock the primary action');
    t.renders.forEach((render) => render.resolve());
  }
  for (const failure of ['rejected', 'network']) {
    const t = setup();
    t.select('face'); await flush();
    t.requests[0].resolve(accepted('face')); await flush(); await flush();
    assert.equal(t.renders.length, 1);
    t.select('body'); await flush();
    if (failure === 'network') t.requests[1].reject(new Error('network failure'));
    else t.requests[1].resolve({revision: 3, photo: {status: 'rejected', message: '请重拍'}});
    await flush(); await flush();
    assert.equal(t.state.screen, 'suit');
    assert.equal(t.state.photoStatus.body, 'invalid');
    assert.equal(t.state.photoAssets.face, 'face', 'the other accepted photo is retained');
    assert.equal(t.renders.length, 1, 'a failed photo must not render results');
    assert.equal(t.button.disabled, true);
    t.select('body'); await flush();
    t.requests[2].resolve(accepted('body-retry')); await flush(); await flush();
    assert.equal(t.state.screen, 'suit');
    assert.equal(t.button.disabled, false);
    assert.equal(t.renders.length, 2);
  }
  const summary = setup();
  summary.select('face'); await flush();
  summary.requests[0].resolve(accepted('face')); await flush(); await flush();
  assert.equal(summary.messages.length, 0);
  summary.renders[0].reject(new Error('summary unavailable')); await flush();
  assert.equal(summary.messages.length, 1, 'summary failure toasts a retry hint');
  assert.equal(summary.state.photoStatus.face, 'valid', 'summary failure retains successful uploads');
  summary.renders.length = 0;
  summary.select('face'); await flush();
  summary.requests[1].resolve(accepted('face-retry')); await flush(); await flush();
  assert.equal(summary.renders.length, 1, 're-uploading retries the inline render');

  const manual = setup();
  manual.select('face'); manual.select('body'); await flush();
  manual.state.screen = 'suit-manual';
  manual.requests.forEach((request, index) => request.resolve(accepted(String(index))));
  await flush(); await flush();
  assert.equal(manual.state.screen, 'suit-manual', 'background uploads must not interrupt manual input');
  assert.equal(manual.renders.length, 0, 'uploads finishing elsewhere must not render the suit page');
})().catch(error => {console.error(error); process.exitCode = 1;}).finally(() => clearTimeout(timeout));
"""
    subprocess.run(["node", "-e", harness, str(runtime)], check=True, capture_output=True, text=True)
