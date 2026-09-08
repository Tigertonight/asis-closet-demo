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
const state = { photoAssets: { face: 'old-asset' }, revision: 0 };
const context = vm.createContext({
  AbortController,
  document: { querySelector: (selector) => selector === '#facePhoto' ? input : {} },
  state,
  ensureSession: async () => 'isolated-test-session',
  renderPhotoPreview() {}, track() {},
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
