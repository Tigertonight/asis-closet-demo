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
const binding = source.slice(source.indexOf('  const bindUpload ='), source.indexOf("  bindUpload('facePhoto'"));
const input = { files: [], value: 'selected', addEventListener(_, listener) { this.change = listener; } };
const requests = [];
const statuses = [];
const state = { photoAssets: { face: 'old-asset' }, photoStatus: { face: 'empty', body: 'empty' }, revision: 0 };
const context = vm.createContext({
  AbortController,
  document: { querySelector: (selector) => selector === '#facePhoto' ? input : {} },
  state,
  ensureSession: async () => 'isolated-test-session',
  renderPhotoPreview() {}, track() {}, showScreen() {},
  setPhotoState(kind, status, copy) { statuses.push({ kind, status, copy }); },
  api: { checkPhoto(session, kind, file, { signal }) {
    return new Promise((resolve, reject) => requests.push({ resolve, reject, signal, file }));
  } },
});
vm.runInContext(validation + binding + "\nbindUpload('facePhoto', 'face');", context);
const photo = (name) => ({name, size: 1024, type: 'image/jpeg'});
const select = (file) => { input.files = file ? [file] : []; input.value = 'selected'; return input.change(); };
const accepted = (assetId) => ({revision: 2, photo: {status: 'accepted', assetId}});
const flush = () => new Promise(resolve => setImmediate(resolve));
(async () => {
  const first = select(photo('first.jpg')); await flush();
  assert.equal(input.value, '', 'reset the input so the same file can be retried');
  const second = select(photo('second.jpg')); await flush();
  assert.equal(requests[0].signal.aborted, true);
  assert.equal(state.photoAssets.face, null, 'old accepted photo must not enable next during replacement');
  requests[0].reject(new Error('old request aborted')); await first;
  assert.equal(statuses.at(-1).status, 'checking', 'old rejection must not invalidate the new image');
  requests[1].resolve(accepted('second-asset')); await second;
  assert.equal(state.photoAssets.face, 'second-asset');
  assert.equal(statuses.at(-1).status, 'valid');
  const count = statuses.length; await select(null);
  assert.equal(statuses.length, count, 'cancelling the chooser retains the accepted image');

  const third = select(photo('late.jpg')); await flush();
  await select({name: 'document.pdf', type: 'application/pdf', size: 1024});
  assert.equal(requests[2].signal.aborted, true);
  requests[2].resolve(accepted('stale-asset')); await third;
  assert.equal(state.photoAssets.face, null);
  assert.equal(statuses.at(-1).status, 'invalid', 'late success cannot overwrite a newer invalid selection');
  assert.match(statuses.at(-1).copy, /请选择一张照片/);

  const retry = select(photo('second.jpg')); await flush();
  requests[3].resolve(accepted('retry-asset')); await retry;
  assert.equal(state.photoAssets.face, 'retry-asset');
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    subprocess.run(["node", "-e", harness, str(runtime)], check=True, capture_output=True, text=True)


def test_processing_requires_button_click_after_both_uploads_and_recovers_from_failures():
    runtime = Path(__file__).parents[1] / "app/static/selfit/selfit.js"
    harness = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync(process.argv[1], 'utf8');
const validation = source.slice(source.indexOf('  const validatePhoto ='), source.indexOf('  const renderPhotoPreview ='));
const photoStatus = source.slice(source.indexOf('  const syncSuitButton ='), source.indexOf('  let editingFeature ='));
const handlers = source.slice(source.indexOf('  const openUploadedSuit ='), source.indexOf("  document.querySelector('.manual-form').addEventListener"));
const timeout = setTimeout(() => { console.error('Upload/click flow did not settle'); process.exitCode = 1; }, 5000);
const flush = () => new Promise(resolve => setImmediate(resolve));
const accepted = (id) => ({photo: {status:'accepted', assetId:id}});
function setup() {
  const node = () => ({files:[], value:'', disabled:true, dataset:{}, classList:{toggle(){}}, addEventListener(event, fn) {this[event] = fn;}});
  const nodes = {'#facePhoto':node(), '#bodyPhoto':node(), '#suitNext':node()};
  const state = {screen:'suit', photoStatus:{face:'empty', body:'empty'}, photoAssets:{face:null,body:null}};
  const requests = [], analyses = [], screens = [], messages = [];
  const context = vm.createContext({
    AbortController, state,
    document:{querySelector(selector) {return nodes[selector] || (nodes[selector] = node()); }},
    ensureSession:async () => 'test-session',
    renderPhotoPreview() {}, track() {},
    showScreen(screen) {screens.push(screen); state.screen = screen;},
    toast(message) {messages.push(message);},
    runButtonAction(_, action) {return action();},
    renderSuit() {
      assert.equal(state.screen, 'suit-processing', 'show loading before requesting the result');
      assert.equal(state.photoStatus.face, 'valid');
      assert.equal(state.photoStatus.body, 'valid');
      return new Promise((resolve, reject) => analyses.push({
        resolve() {state.screen = 'suit-result'; resolve();}, reject,
      }));
    },
    api:{checkPhoto(session, kind, file, {signal}) {
      return new Promise((resolve, reject) => requests.push({kind, file, signal, resolve, reject}));
    }},
  });
  vm.runInContext(validation + photoStatus + handlers, context);
  const select = (kind, name = kind + '.jpg') => {
    const input = nodes['#' + kind + 'Photo'];
    input.files = [{name, type:'image/jpeg', size:1024}];
    return input.change();
  };
  return {state, requests, analyses, screens, messages, select, button:nodes['#suitNext'],
    recognize:() => nodes['#suitNext'].click({currentTarget:nodes['#suitNext']})};
}
(async () => {
  for (const firstKind of ['face','body']) {
    const t = setup(), secondKind = firstKind === 'face' ? 'body' : 'face';
    await t.recognize();
    assert.equal(t.analyses.length, 0, 'cannot request a result without both photos');
    const first = t.select(firstKind); await flush();
    assert.deepEqual(t.screens, [], 'first photo checks inline');
    t.requests[0].resolve(accepted(firstKind)); await first;
    assert.equal(t.state.screen, 'suit', 'first accepted photo stays on upload page');
    assert.equal(t.button.disabled, true);
    const second = t.select(secondKind); await flush();
    assert.equal(t.state.screen, 'suit', 'second photo must finish before full-screen loading');
    await t.recognize();
    assert.equal(t.analyses.length, 0, 'a pending upload prevents recognition');
    t.requests[1].resolve(accepted(secondKind)); await second;
    assert.equal(t.button.disabled, false);
    assert.equal(t.state.screen, 'suit', 'both accepted photos wait for the button');
    assert.deepEqual(t.screens, []);
    assert.equal(t.analyses.length, 0, 'upload completion must not request the result');
    const next = t.recognize();
    assert.deepEqual(t.screens, ['suit-processing']);
    await t.recognize();
    assert.equal(t.analyses.length, 1, 'duplicate clicks must not request the result twice');
    t.analyses[0].resolve(); await next;
    assert.equal(t.state.screen, 'suit-result');
    await t.recognize();
    assert.equal(t.analyses.length, 1);
  }
  for (const finishOrder of [[0,1],[1,0]]) {
    const t = setup();
    const pending = [t.select('face'), t.select('body')]; await flush();
    t.requests[finishOrder[0]].resolve(accepted('first')); await pending[finishOrder[0]];
    assert.equal(t.state.screen, 'suit', 'one pending upload must keep the upload page');
    t.requests[finishOrder[1]].resolve(accepted('last')); await Promise.all(pending);
    assert.equal(t.button.disabled, false);
    assert.equal(t.analyses.length, 0, 'neither completion order may auto-start recognition');
    const next = t.recognize();
    assert.deepEqual(t.screens, ['suit-processing']);
    t.analyses[0].resolve(); await next;
  }
  for (const failure of ['rejected','network']) {
    const t = setup();
    const face = t.select('face'); await flush();
    t.requests[0].resolve(accepted('face')); await face;
    const body = t.select('body'); await flush();
    if (failure === 'network') t.requests[1].reject(new Error('network failure'));
    else t.requests[1].resolve({photo:{status:'rejected', message:'请重拍'}});
    await body;
    assert.equal(t.state.screen, 'suit');
    assert.equal(t.state.photoStatus.body, 'invalid');
    assert.equal(t.state.photoAssets.face, 'face');
    assert.equal(t.button.disabled, true);
    await t.recognize();
    assert.equal(t.analyses.length, 0);
    const retry = t.select('body'); await flush();
    t.requests[2].resolve(accepted('body-retry')); await retry;
    assert.equal(t.state.screen, 'suit');
    assert.equal(t.button.disabled, false);
    assert.equal(t.analyses.length, 0);
    const firstAttempt = t.recognize();
    assert.equal(t.state.screen, 'suit-processing');
    t.analyses[0].reject(new Error('summary unavailable')); await firstAttempt;
    assert.equal(t.state.screen, 'suit');
    assert.equal(t.state.photoStatus.body, 'valid', 'summary failure retains successful uploads');
    assert.equal(t.messages.length, 1);
    const next = t.recognize(); await flush();
    assert.equal(t.state.screen, 'suit-processing');
    assert.equal(t.requests.length, 3, 'retry loads the result without uploading again');
    t.analyses[1].resolve(); await next;
  }
  const t = setup();
  const pending = [t.select('face'),t.select('body')]; await flush();
  t.state.screen = 'suit-manual';
  t.requests.forEach((request,index) => request.resolve(accepted(String(index))));
  await Promise.all(pending);
  assert.equal(t.state.screen, 'suit-manual', 'background uploads must not interrupt manual input');
  assert.equal(t.analyses.length, 0);
})().catch(error => {console.error(error); process.exitCode = 1;}).finally(() => clearTimeout(timeout));
"""
    subprocess.run(["node", "-e", harness, str(runtime)], check=True, capture_output=True, text=True)
