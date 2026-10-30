const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app/static/selfit/mirror-photo.js', 'utf8');
const settle = () => new Promise(resolve => setImmediate(resolve));

function fixture({ share = false, hasScene = true, xhs = false, xhsFail = false, scan = false, delayedShare = false, userAgent = 'Mozilla/5.0 Chrome/130', platform = '', maxTouchPoints = 0, encoding = '', shareFlow = '' } = {}) {
  let now = 1800000000000;
  const elements = new Map(), clicks = [], requests = [], requestHeaders = [], events = {}, shared = [], storage = new Map(), navigations = [];
  const ids = new Set([...fs.readFileSync('app/static/selfit/mirror-photo.html', 'utf8').matchAll(/id="([^"]+)"/g)].map(m => m[1]));
  const el = id => {
    assert.ok(ids.has(id), `element ${id} must exist in the page`);
    if (!elements.has(id)) elements.set(id, { hidden: false, disabled: false, textContent: '', decode: async () => {},
      open: false, showModal() { this.open = true; }, close() { this.open = false; this.onclose?.(); } });
    return elements.get(id);
  };
  const metadata = () => ({ expiresAt: now + 86400000, hasScene, edition: 'woken', xhsShareEnabled: xhs, imageLinks: {
    expiresAt: now + 600000,
    print: { view: `/files/print.png?inline=${now}`, download: `/files/print.png?download=${now}` },
    scene: { view: `/files/scene.png?inline=${now}`, download: `/files/scene.png?download=${now}` },
  } });
  let failing = false, releaseShare;
  const historyWrites = [];
  const context = {
    SelfitMirrorClient: { headers: () => ({ 'X-Selfit-Client-Id': 'mc_' + 'e'.repeat(32) }) },
    document: { hidden: false, getElementById: el, body: { append() {}, classList: { add() {} } },
      createElement: () => ({ click() { clicks.push({ href: this.href, filename: this.download }); }, remove() {} }) },
    location: { pathname: '/selfit/photo', search: '?' + new URLSearchParams({ ...(scan ? { intent: 'xhs' } : {}), ...(encoding ? { xhs_url_encoding: encoding } : {}) }), hash: '#mp_' + 'a'.repeat(32) + '.' + 'b'.repeat(64), assign: url => navigations.push(url) },
    history: { replaceState: (_, __, url) => historyWrites.push(url) }, URLSearchParams,
    sessionStorage: { setItem: (key, value) => storage.set(key, value) },
    navigator: { userAgent, platform, maxTouchPoints, ...(share ? { canShare: () => true, share: async value => { shared.push(value); } } : {}) }, File, Blob,
    Date: class extends Date { static now() { return now; } }, AbortSignal, TypeError,
    fetch: async (url, options) => {
      requests.push(url);
      requestHeaders.push(options.headers);
      if (failing) throw new TypeError('offline');
      if (delayedShare && url.endsWith('/xhs-share')) await new Promise(resolve => { releaseShare = resolve; });
      if (url.endsWith('/xhs-share')) return xhsFail ? { ok: false, json: async () => ({ detail: '分享暂时不可用' }) } : {
        ok: true, json: async () => ({ flow: shareFlow, expiresAt: now + 180000, shareInfo: { type: 'normal', images: ['https://selfit.com.cn/files/print.png?signature=test'] }, verifyConfig: { appKey: 'test', signature: 'test' } }),
      };
      if (share && url.endsWith('/download')) return { ok: true, blob: async () => new Blob(['stamp'], { type: 'image/png' }) };
      assert.ok(url.endsWith('/info'), 'must not request the removed scene');
      return { ok: true, json: async () => metadata() };
    },
    setTimeout: () => 1, clearTimeout() {}, addEventListener: (name, callback) => { events[name] = callback; },
  };
  vm.runInNewContext(source, context);
  return { el, clicks, requests, requestHeaders, events, shared, storage, navigations, historyWrites, release: () => releaseShare(), advance: () => { now += 601000; }, fail: () => { failing = true; } };
}

test('receipt, file preparation and XHS handoff carry the same browser ID without replacing authorization', async () => {
  const f = fixture({ share: true, xhs: true }); await settle();
  await f.el('phoneXhsShare').onclick();
  assert.ok(f.requests.some(url => url.endsWith('/info')));
  assert.ok(f.requests.some(url => url.endsWith('/download')));
  assert.ok(f.requests.some(url => url.endsWith('/xhs-share')));
  for (const headers of f.requestHeaders) {
    assert.equal(headers['X-Selfit-Client-Id'], 'mc_' + 'e'.repeat(32));
    assert.equal(headers.Authorization, 'Bearer ' + 'b'.repeat(64));
  }
});

test('QR share intent prepares immediately without fetching or decoding the photo', async () => {
  const f = fixture({ scan: true }); await settle();
  assert.equal(f.requests.length, 1);
  assert.ok(f.requests[0].endsWith('/xhs-share'));
  assert.deepEqual(f.navigations, ['/selfit/photo/share']);
  const payload = f.storage.get('selfit.xhsShare');
  assert.equal(JSON.parse(payload).autoOpen, true);
  assert.doesNotMatch(payload, new RegExp('b'.repeat(64)));
  assert.equal(f.historyWrites.length, 1);
  assert.match(f.historyWrites[0], /^\/selfit\/photo#mp_/);
  assert.doesNotMatch(f.historyWrites[0], /intent=/);
  f.events.pageshow({ persisted: true }); await settle();
  assert.equal(f.requests.filter(url => url.endsWith('/xhs-share')).length, 1, 'back must not launch again');
  assert.equal(f.el('phoneDownload').disabled, false);
});

test('QR preparation failure offers share retry and saving', async () => {
  const f = fixture({ scan: true, xhsFail: true }); await settle();
  assert.equal(f.navigations.length, 0);
  assert.equal(f.el('phoneViewPhoto').hidden, false);
  assert.equal(f.el('phoneXhsShare').disabled, false);
  assert.match(f.el('phoneStatus').textContent, /分享暂时不可用/);
  await f.el('phoneXhsShare').onclick();
  assert.equal(f.requests.filter(url => url.endsWith('/xhs-share')).length, 2);
  await f.el('phoneViewPhoto').onclick();
  assert.equal(f.el('phoneDownload').disabled, false);
  assert.equal(f.el('phoneViewPhoto').hidden, true);
});

test('choosing save while sharing is pending prevents a late launch', async () => {
  const f = fixture({ scan: true, delayedShare: true });
  await f.el('phoneXhsShare').onclick();
  assert.equal(f.requests.length, 1, 'disabled preparation cannot be submitted twice');
  await f.el('phoneViewPhoto').onclick(); f.release(); await settle();
  assert.equal(f.navigations.length, 0);
  assert.equal(f.storage.size, 0);
  assert.equal(f.el('phoneDownload').disabled, false);
});

test('XHS handoff is explicit, single-flight and contains no receipt secret', async () => {
  const f = fixture({ xhs: true }); await settle();
  assert.equal(f.el('phoneXhsShare').hidden, false);
  assert.ok(!f.requests.some(url => url.endsWith('/xhs-share')));
  const click = f.el('phoneXhsShare').onclick();
  await f.el('phoneXhsShare').onclick(); await click;
  assert.equal(f.requests.filter(url => url.endsWith('/xhs-share')).length, 1);
  assert.deepEqual(f.navigations, ['/selfit/photo/share']);
  assert.doesNotMatch(f.storage.get('selfit.xhsShare'), new RegExp('b'.repeat(64)));
});

test('XHS failure keeps saving and retry available; unconfigured action stays hidden', async () => {
  const absent = fixture(); await settle();
  assert.equal(absent.el('phoneXhsShare').hidden, true);
  const f = fixture({ xhs: true, xhsFail: true }); await settle();
  await f.el('phoneXhsShare').onclick();
  assert.equal(f.el('phoneXhsShare').disabled, false);
  assert.equal(f.el('phoneDownload').disabled, false);
  assert.equal(f.navigations.length, 0);
  assert.match(f.el('phoneStatus').textContent, /分享暂时不可用/);
});

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
  assert.match(f.el('phoneStatus').textContent, /已请求浏览器下载/);
  assert.doesNotMatch(f.el('phoneStatus').textContent, /已保存/);
});

for (const browser of [
  { name: 'Android WeChat', userAgent: 'Mozilla/5.0 (Android) MicroMessenger/8.0', label: '查看高清原图' },
  { name: 'iPhone WeChat', userAgent: 'Mozilla/5.0 (iPhone) MicroMessenger/8.0', label: '查看高清原图' },
  { name: 'iPhone Safari', userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) AppleWebKit/605.1.15 Version/18.6 Mobile/15E148 Safari/604.1', label: '保存到相册' },
  { name: 'iPhone Chrome', userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) AppleWebKit/605.1.15 CriOS/140.0 Mobile/15E148 Safari/604.1', label: '保存到相册' },
  { name: 'iPad desktop Safari', userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15) Version/18.6 Safari/605.1.15', platform: 'MacIntel', maxTouchPoints: 5, label: '保存到相册' },
]) test(`${browser.name} opens a real full-resolution image without downloading into Files`, async () => {
  const f = fixture(browser); await settle();
  assert.equal(f.el('phoneDownload').textContent, browser.label);
  f.el('phoneDownload').onclick(); await settle();
  assert.equal(f.el('phoneViewer').open, true);
  assert.equal(f.el('phoneOriginalPhoto').hidden, false);
  assert.equal(f.el('phoneOriginalPhoto').src, f.el('phonePhoto').src);
  assert.match(f.el('phoneOriginalPhoto').src, /print.png\?inline=/);
  assert.match(f.el('phoneViewerHint').textContent, /长按图片/);
  assert.match(f.el('phoneViewerHint').textContent, /存储到照片|保存图片/);
  assert.equal(f.clicks.length, 0);
  assert.equal(f.requests.length, 1);
  f.el('phoneViewerClose').onclick();
  assert.equal(f.el('phoneViewer').open, false);
  let prevented = false;
  f.el('phoneOriginal').onclick({ preventDefault() { prevented = true; } }); await settle();
  assert.equal(prevented, true);
  assert.equal(f.el('phoneViewer').open, true);
  assert.equal(f.clicks.length, 0);
});

test('desktop Safari still downloads the PNG instead of opening the album-saving viewer', async () => {
  const f = fixture({ userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15) Version/18.6 Safari/605.1.15', platform: 'MacIntel', maxTouchPoints: 0 });
  await settle(); f.el('phoneDownload').onclick();
  assert.equal(f.clicks.length, 1);
  assert.equal(f.el('phoneViewer').open, false);
  assert.match(f.clicks[0].href, /download=/);
});

test('iPhone Safari renews an expired photo link before offering album saving', async () => {
  const f = fixture({ userAgent: 'Mozilla/5.0 (iPhone) Version/18.6 Safari/604.1' });
  await settle(); const before = f.el('phonePhoto').src;
  f.advance(); f.el('phoneDownload').onclick(); await settle();
  assert.equal(f.el('phoneViewer').open, true);
  assert.notEqual(f.el('phoneOriginalPhoto').src, before);
  assert.equal(f.el('phoneOriginalPhoto').hidden, false);
  assert.equal(f.clicks.length, 0);
  assert.doesNotMatch(f.el('phoneStatus').textContent, /已保存|已请求浏览器下载/);
});

test('WeChat renews expired links and opens the original in the same tap', async () => {
  const f = fixture({ userAgent: 'MicroMessenger/8.0' }); await settle();
  const old = f.el('phonePhoto').src;
  f.advance(); f.el('phoneDownload').onclick(); await settle();
  assert.equal(f.el('phoneViewer').open, true);
  assert.equal(f.el('phoneOriginalPhoto').hidden, false);
  assert.notEqual(f.el('phoneOriginalPhoto').src, old);
  assert.equal(f.clicks.length, 0);
  assert.equal(f.requests.length, 2);
});

test('WeChat renewal failure retains a closeable viewer and offers retry', async () => {
  const f = fixture({ userAgent: 'MicroMessenger/8.0' }); await settle();
  f.advance(); f.fail(); f.el('phoneDownload').onclick(); await settle();
  assert.equal(f.el('phoneViewer').open, true);
  assert.equal(f.el('phoneOriginalPhoto').hidden, true);
  assert.match(f.el('phoneViewerHint').textContent, /网络暂时无法连接/);
  assert.equal(f.el('phoneViewerRetry').hidden, false);
  assert.equal(f.clicks.length, 0);
  f.el('phoneViewerClose').onclick();
  assert.equal(f.el('phoneViewer').open, false);
});

test('WeChat image decode failure can be retried without downloading', async () => {
  const f = fixture({ userAgent: 'MicroMessenger/8.0' }); await settle();
  f.el('phoneOriginalPhoto').decode = async () => { const e = new Error('decode'); e.name = 'EncodingError'; throw e; };
  f.el('phoneDownload').onclick(); await settle();
  assert.equal(f.el('phoneViewerRetry').hidden, false);
  assert.match(f.el('phoneViewerHint').textContent, /原图暂时未加载成功/);
  f.el('phoneOriginalPhoto').decode = async () => {};
  await f.el('phoneViewerRetry').onclick();
  assert.equal(f.el('phoneOriginalPhoto').hidden, false);
  assert.equal(f.el('phoneViewerRetry').hidden, true);
  assert.equal(f.clicks.length, 0);
});

test('closing WeChat viewer ignores a late image failure', async () => {
  const f = fixture({ userAgent: 'MicroMessenger/8.0' }); await settle();
  let reject;
  f.el('phoneOriginalPhoto').decode = () => new Promise((_, fail) => { reject = fail; });
  f.el('phoneDownload').onclick();
  f.el('phoneViewerClose').onclick(); reject(new Error('late failure')); await settle();
  assert.equal(f.el('phoneViewer').open, false);
  assert.equal(f.el('phoneViewerRetry').hidden, true);
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


for (const shareFlow of ['official-sdk', 'prepared-link']) for (const encoding of ['', 'component', 'raw']) for (const scan of [false, true]) test(`image URL encoding handoff: ${shareFlow}, ${encoding || 'default'}, scan=${scan}`, async () => {
  const f = fixture({ xhs: true, encoding, shareFlow, scan }); await settle();
  if (!scan) await f.el('phoneXhsShare').onclick();
  const handoff = JSON.parse(f.storage.get('selfit.xhsShare'));
  assert.equal(handoff.imageUrlEncoding, shareFlow === 'official-sdk' && encoding !== 'raw' ? 'component' : 'raw');
  assert.equal(handoff.autoOpen, scan);
  assert.ok(handoff.shareInfo.images[0].startsWith('https://'));
});
