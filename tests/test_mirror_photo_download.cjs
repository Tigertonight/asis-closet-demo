const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app/static/selfit/mirror-photo.js', 'utf8');
const settle = () => new Promise(resolve => setImmediate(resolve));

function fixture({ share = false, hasScene = true } = {}) {
  let now = 1800000000000;
  const elements = new Map(), clicks = [], requests = [], events = {}, shared = [];
  const ids = new Set([...fs.readFileSync('app/static/selfit/mirror-photo.html', 'utf8').matchAll(/id="([^"]+)"/g)].map(m => m[1]));
  const el = id => {
    assert.ok(ids.has(id), `element ${id} must exist in the page`);
    if (!elements.has(id)) elements.set(id, { hidden: false, disabled: false, textContent: '', decode: async () => {} });
    return elements.get(id);
  };
  const metadata = () => ({ expiresAt: now + 86400000, hasScene, edition: 'woken', imageLinks: {
    expiresAt: now + 600000,
    print: { view: `/files/print.png?inline=${now}`, download: `/files/print.png?download=${now}` },
    scene: { view: `/files/scene.png?inline=${now}`, download: `/files/scene.png?download=${now}` },
  } });
  let failing = false;
  const context = {
    document: { hidden: false, getElementById: el, body: { append() {}, classList: { add() {} } },
      createElement: () => ({ click() { clicks.push({ href: this.href, filename: this.download }); }, remove() {} }) },
    location: { hash: '#mp_' + 'a'.repeat(32) + '.' + 'b'.repeat(64) }, navigator: share ? { canShare: () => true, share: async value => { shared.push(value); } } : {}, File, Blob,
    Date: class extends Date { static now() { return now; } }, AbortSignal, TypeError,
    fetch: async url => {
      requests.push(url);
      if (failing) throw new TypeError('offline');
      if (share && url.endsWith('/download')) return { ok: true, blob: async () => new Blob(['stamp'], { type: 'image/png' }) };
      assert.ok(url.endsWith('/info'), 'must not request the removed scene');
      return { ok: true, json: async () => metadata() };
    },
    setTimeout: () => 1, clearTimeout() {}, addEventListener: (name, callback) => { events[name] = callback; },
  };
  vm.runInNewContext(source, context);
  return { el, clicks, requests, events, shared, advance: () => { now += 601000; }, fail: () => { failing = true; } };
}

test('PNG download is synchronous with the tap and uses a real file URL', async () => {
  const f = fixture(); await settle();
  assert.match(f.el('phonePhoto').src, /^\/files\/print.png\?inline=/);
  assert.equal(f.el('phoneDownload').disabled, false);
  const requests = f.requests.length;
  f.el('phoneDownload').onclick();
  assert.equal(f.clicks.length, 1, 'no await before native download');
  assert.match(f.clicks[0].href, /^\/files\/print.png\?download=/);
  assert.equal(f.clicks[0].filename, 'WOKEN-DAY-STAMP.png');
  assert.equal(f.requests.length, requests);
  assert.equal(f.el('phoneOriginal').hidden, false);
  assert.match(f.el('phoneStatus').textContent, /已发起下载/);
  assert.doesNotMatch(f.el('phoneStatus').textContent, /已保存/);
});

test('expired links renew before a new user tap starts the download', async () => {
  const f = fixture(); await settle(); f.advance();
  f.el('phoneDownload').onclick();
  assert.equal(f.clicks.length, 0);
  await settle();
  assert.match(f.el('phoneStatus').textContent, /再次点击保存/);
  f.el('phoneDownload').onclick();
  assert.equal(f.clicks.length, 1);
});

test('fallback opens a real inline PNG and also handles expiry', async () => {
  const f = fixture(); await settle();
  let prevented = false;
  f.el('phoneOriginal').onclick({ preventDefault() { prevented = true; } });
  assert.equal(prevented, false);
  assert.match(f.el('phoneOriginal').href, /print.png\?inline=/);
  f.advance();
  f.el('phoneOriginal').onclick({ preventDefault() { prevented = true; } });
  assert.equal(prevented, true);
  await settle();
  assert.match(f.el('phoneStatus').textContent, /链接已更新/);
});

test('renewal network failure keeps the page and does not claim a download', async () => {
  const f = fixture(); await settle(); f.advance(); f.fail();
  f.el('phoneDownload').onclick(); await settle();
  assert.equal(f.clicks.length, 0);
  assert.match(f.el('phoneStatus').textContent, /网络暂时无法连接/);
  assert.equal(f.el('phoneDownload').disabled, false);
});

for (const hasScene of [true, false]) test(`shares only the stamp (historical scene: ${hasScene})`, async () => {
  const f = fixture({ share: true, hasScene }); await settle();
  assert.equal(f.el('phoneShare').textContent, '分享邮票');
  assert.equal(f.el('phoneShare').hidden, false);
  await f.el('phoneShare').onclick();
  assert.equal(f.shared[0].files.length, 1);
  assert.equal(f.shared[0].files[0].name, 'WOKEN-DAY-STAMP.png');
  assert.ok(f.requests.every(url => !url.includes('scene')));
  assert.doesNotMatch(f.el('phoneIntro').textContent, /展示图/);
});
