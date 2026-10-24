const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync('app/static/selfit/stamp/app.js', 'utf8');
// Execute the actual import handler and decoder without booting the artwork/audio bundle.
const importCode = source.slice(source.indexOf('  function openAlbumPicker()'), source.indexOf('  async function setSourceFromCanvas('));

function setup() {
  let handler, nextUrl = 0;
  const urls = new Map(), timers = new Set(), images = [], messages = [], normalized = [];
  class Image {
    constructor() { images.push(this); }
    set src(value) {
      this.currentSrc = value;
      if (!value) return;
      const file = urls.get(value);
      this.naturalWidth = file.width; this.naturalHeight = file.height;
      if (file.hang) return;
      queueMicrotask(() => file.invalid ? this.onerror?.() : this.onload?.());
    }
  }
  const context = {
    Image, Math, Promise,
    URL: {createObjectURL(file) { const url = `blob:${++nextUrl}`; urls.set(url, file); return url; }, revokeObjectURL(url) { urls.delete(url); }},
    albumInput: {addEventListener(event, cb) { assert.equal(event, 'change'); handler = cb; }},
    state: {busy: false}, visitRevision: 0,
    setTimeout(cb) {timers.add(cb); return cb;}, clearTimeout(cb) {timers.delete(cb);},
    wait: async () => {}, stopCamera() {}, setView(view) {context.state.view = view;},
    workCanvas: {width: 1, height: 1, getContext: () => ({drawImage() {}})},
    setSourceFromCanvas: async (canvas, origin) => { normalized.push([canvas.width, canvas.height, origin]); }
  };
  vm.runInNewContext(importCode, context);
  context.showAlbumImportStatus = (message, failed) => messages.push({message, failed});
  context.closeAlbumImportStatus = () => {};
  return {context, timers, images, messages, normalized, urls,
    upload: (overrides = {}) => handler({target: {value: 'chosen.jpg', files: [{name:'chosen.jpg', type:'image/jpeg', size:1024, width:6000, height:8000, ...overrides}]}})
  };
}

test('48MP phone photo imports, keeps aspect ratio and releases the large decoded image', async () => {
  const q = setup(); await q.upload();
  assert.deepEqual(q.normalized, [[1050, 1400, 'album']]);
  assert.equal(q.context.state.view, 'printlab');
  assert.match(q.messages[0].message, /调整照片大小/);
  assert.equal(q.messages[0].failed, false);
  assert.equal(q.context.state.busy, false);
  assert.equal(q.images[0].currentSrc, '');
  assert.equal(q.urls.size, 0); assert.equal(q.timers.size, 0);
  assert.equal(q.context.workCanvas.width, 1);
});

test('64MP / 32MiB boundary is allowed; landscape and small images remain proportional', async () => {
  const q = setup();
  await q.upload({width:8000, height:8000, size:32 * 1024 * 1024});
  await q.upload({width:8000, height:6000});
  await q.upload({width:800, height:600});
  assert.deepEqual(q.normalized, [[1400,1400,'album'], [1400,1050,'album'], [800,600,'album']]);
});

test('above 64MP is rejected before drawing and a subsequent smaller photo can be selected', async () => {
  const q = setup(); await q.upload({width:8001, height:8000});
  assert.equal(q.normalized.length, 0);
  assert.match(q.messages.at(-1).message, /6400 万像素/);
  assert.equal(q.messages.at(-1).failed, true);
  assert.equal(q.images[0].currentSrc, ''); assert.equal(q.context.state.busy, false);
  await q.upload(); assert.equal(q.context.state.view, 'printlab');
});

test('oversized file is rejected before decode; invalid input leaves a clear retry state', async () => {
  const q = setup(); await q.upload({size:32 * 1024 * 1024 + 1});
  assert.equal(q.images.length, 0); assert.match(q.messages.at(-1).message, /32MB/);
  await q.upload({name:'file.txt', type:'text/plain'});
  assert.equal(q.images.length, 0); assert.match(q.messages.at(-1).message, /请选择/);
  await q.upload({invalid:true});
  assert.match(q.messages.at(-1).message, /暂时无法读取/);
  assert.equal(q.context.state.busy, false); assert.equal(q.urls.size, 0);
  assert.equal(q.images[0].currentSrc, '');
});

test('decode timeout clears busy state, cancels the image and permits retry', async () => {
  const q = setup(); const pending = q.upload({hang:true});
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(q.timers.size, 1);
  for (const timeout of q.timers) timeout();
  await pending;
  assert.match(q.messages.at(-1).message, /处理时间较长/);
  assert.equal(q.context.state.busy, false); assert.equal(q.urls.size, 0);
  assert.equal(q.images[0].onload, null); assert.equal(q.images[0].currentSrc, '');
  await q.upload(); assert.equal(q.context.state.view, 'printlab');
});

test('duplicate changes during import do not decode another full-size photo', async () => {
  const q = setup(); await Promise.all([q.upload(), q.upload()]);
  assert.equal(q.images.length, 1); assert.equal(q.normalized.length, 1);
});
