const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app/static/selfit/mirror-xhs-share.js', 'utf8');

function fixture({ expired = false, agent = 'Android 16', platform = 'Android', wechat = false, invalid = '', throws = false, autoOpen = false } = {}) {
  let now = 1800000000000, back = 0;
  const el = {}, calls = [], timers = [], storage = new Map(), events = {};
  const scheme = 'xhsdiscover://js_share_sdk?share_code=official-code&app_key=test&session_id=session';
  const universal = 'https://oia.xiaohongshu.com/oia?deeplink=' + encodeURIComponent(scheme);
  const payload = { autoOpen, expiresAt: now + (expired ? -1 : 180000), shareInfo: { type: 'normal', images: [
    `https://${invalid === 'image' ? 'attacker.invalid' : 'selfit.com.cn'}/api/v1/selfit/mirror/photos/mp_${'a'.repeat(32)}/files/print.png?signature=test`
  ] }, verifyConfig: { appKey: 'test' }, launch: { scheme, universal, platform, inWeChat: wechat } };
  if (invalid === 'scheme') payload.launch.scheme = 'javascript:alert(1)';
  if (invalid === 'universal') payload.launch.universal = 'https://attacker.invalid/oia?deeplink=' + encodeURIComponent(scheme);
  if (invalid === 'key') payload.verifyConfig.appKey = 'other';
  if (invalid === 'legacy') delete payload.launch;
  storage.set('selfit.xhsShare', JSON.stringify(payload));
  const document = { hidden: false, getElementById: id => el[id] ||= { disabled: true, hidden: true, removeAttribute(name) { delete this[name]; } } };
  const context = {
    document,
    location: { origin: 'https://selfit.com.cn', replace() {}, assign(url) { calls.push(url); if (throws) throw new Error('blocked'); } },
    history: { length: 2, back: () => back++ }, navigator: { userAgent: agent }, URL,
    Date: class extends Date { static now() { return now; } },
    sessionStorage: { getItem: k => storage.get(k), removeItem: k => storage.delete(k) },
    setTimeout: f => { timers.push(f); return timers.length; }, clearTimeout() {},
    addEventListener: (name, cb) => events[name] = cb,
    fetch() { throw new Error('No async request allowed before navigation'); },
  };
  vm.runInNewContext(source, context);
  return { el, calls, timers, storage, events, document, scheme, universal, back: () => back++, expire: () => now += 180000 };
}

for (const agent of ['Android 16', 'iPhone', 'Windows NT 10.0', 'OpenHarmony ArkWeb Mobile', '', 'Linux']) {
  test(`phone stays actionable even when JS UA is ${JSON.stringify(agent)}`, () => {
    const f = fixture({ agent });
    assert.equal(f.storage.size, 0);
    assert.equal(f.el.xhsOpen.disabled, false);
    assert.equal(f.calls.length, 0, 'no automatic app launch');
    f.el.xhsOpen.onclick();
    assert.deepEqual(f.calls, [f.scheme], 'request Android platform chooses immediate scheme navigation');
    assert.equal(f.el.xhsAlternate.href, f.universal);
    assert.doesNotMatch(f.el.xhsStatus.textContent, /发布成功|分享成功|请在手机上打开/);
  });
}

for (const opts of [{ platform: 'iOS' }, { platform: 'pc' }, { wechat: true }, { agent: 'Android MicroMessenger' }]) {
  test(`universal link is available for ${JSON.stringify(opts)}`, () => {
    const f = fixture(opts); f.el.xhsOpen.onclick();
    assert.deepEqual(f.calls, [f.universal]);
    assert.equal(f.el.xhsAlternate.href, f.scheme);
  });
}

for (const opts of [{ expired: true }, ...['image', 'scheme', 'universal', 'key', 'legacy'].map(invalid => ({ invalid }))]) {
  test(`invalid handoff never launches: ${JSON.stringify(opts)}`, () => {
    const f = fixture(opts);
    assert.equal(f.el.xhsOpen.disabled, true); assert.equal(f.calls.length, 0);
    assert.match(f.el.xhsStatus.textContent, /返回领图页/);
  });
}

test('expired primary and alternate both require a fresh handoff', () => {
  const f = fixture(); f.expire(); f.el.xhsOpen.onclick();
  let prevented = false; f.el.xhsAlternate.onclick({ preventDefault: () => prevented = true });
  assert.equal(prevented, true); assert.equal(f.calls.length, 0);
  assert.equal(f.el.xhsOpen.disabled, true); assert.equal(f.el.xhsAlternate.hidden, true);
});

test('blocked browser has actionable fallback; leaving page does not imply publishing', () => {
  const f = fixture({ throws: true }); f.el.xhsOpen.onclick();
  assert.equal(f.el.xhsAlternate.hidden, false);
  assert.match(f.el.xhsStatus.textContent, /备用入口/);
  f.document.hidden = true; f.events.visibilitychange(); f.timers.at(-1)();
  assert.doesNotMatch(f.el.xhsStatus.textContent, /发布成功|分享成功/);
});

test('remaining in WeChat explains browser fallback', () => {
  const f = fixture({ wechat: true }); f.el.xhsOpen.onclick(); f.timers.at(-1)();
  assert.match(f.el.xhsStatus.textContent, /微信.*浏览器打开/);
  assert.equal(f.el.xhsOpen.disabled, false);
});

for (const wechat of [false, true]) test(`QR opens once on entry and retains tap fallback (WeChat: ${wechat})`, () => {
  const f = fixture({ autoOpen: true, wechat });
  assert.deepEqual(f.calls, [wechat ? f.universal : f.scheme]);
  assert.equal(f.el.xhsOpen.textContent, '继续打开小红书');
  assert.equal(f.storage.size, 0, 'handoff consumed before navigation');
  f.events.pagehide(); f.document.hidden = false; f.events.visibilitychange();
  assert.equal(f.calls.length, 1, 'returning must not automatically relaunch');
  f.el.xhsOpen.onclick();
  assert.equal(f.calls.length, 2, 'tap explicitly retries navigation');
});

test('invalid automatic handoff cannot launch; blocked automatic launch still allows a tap', () => {
  assert.equal(fixture({ autoOpen: true, expired: true }).calls.length, 0);
  const f = fixture({ autoOpen: true, throws: true });
  assert.equal(f.calls.length, 1);
  assert.equal(f.el.xhsOpen.disabled, false);
  assert.equal(f.el.xhsAlternate.hidden, false);
});

function officialFixture({ autoOpen = false, ready = true, sdk, telemetryThrows = false, encoding = undefined } = {}) {
  let now = 1800000000000;
  const el = {}, calls = [], reports = [], scripts = [], timers = [], events = {};
  const image = `https://selfit.com.cn/api/v1/selfit/mirror/photos/mp_${'a'.repeat(32)}/files/print.png?expires=1800000600&signature=${'b'.repeat(64)}`;
  const payload = { flow: 'official-sdk', imageUrlEncoding: encoding, autoOpen, expiresAt: now + 180000,
    shareInfo: { type: 'normal', images: [image] },
    verifyConfig: { appKey: 'test', nonce: 'nonce', timestamp: '1800000000', signature: 'signed' } };
  const share = args => { calls.push(args); return sdk ? sdk(args) : Promise.resolve(); };
  const document = { hidden: false,
    getElementById: id => el[id] ||= { disabled: true, hidden: true, removeAttribute(name) { delete this[name]; } },
    createElement: () => ({ remove() { this.removed = true; } }), head: { append: script => scripts.push(script) } };
  const context = { document, URL, navigator: { userAgent: 'iPhone MicroMessenger/8.0' },
    location: { origin: 'https://selfit.com.cn', assign() { assert.fail('official flow must use SDK'); } }, history: { length: 2, back() {} },
    sessionStorage: { getItem: () => JSON.stringify(payload), removeItem() {} },
    Date: class extends Date { static now() { return now; } },
    setTimeout: (fn, delay) => { const timer = { fn, delay }; timers.push(timer); return timer; },
    clearTimeout: timer => { if (timer) timer.cleared = true; },
    addEventListener: (name, cb) => events[name] = cb,
    fetch(url, options) {
      if (telemetryThrows) throw new Error('offline');
      reports.push({ url, body: JSON.parse(options.body) }); return Promise.resolve({ ok: true });
    }, ...(ready ? { xhs: { share } } : {}) };
  vm.runInNewContext(source, context);
  return { el, calls, reports, scripts, timers, events, document, payload,
    load() { context.xhs = { share }; scripts.at(-1).onload(); }, expire() { now += 180000; } };
}
const flush = async () => { for (let i = 0; i < 10; i++) await Promise.resolve(); };

test('iPhone calls official SDK with signed image only; auto-launch is once and manual retry is possible', async () => {
  const f = officialFixture({ autoOpen: true }); await flush();
  assert.equal(f.calls.length, 1);
  assert.deepEqual(JSON.parse(JSON.stringify(f.calls[0].shareInfo)), f.payload.shareInfo);
  assert.deepEqual(JSON.parse(JSON.stringify(f.calls[0].verifyConfig)), f.payload.verifyConfig);
  assert.equal(f.el.xhsAlternate.hidden, true);
  f.document.hidden = true; f.events.visibilitychange();
  f.document.hidden = false; f.events.visibilitychange(); await flush();
  assert.equal(f.calls.length, 1, 'return must not auto-relaunch');
  f.el.xhsOpen.onclick();
  assert.equal(f.calls.length, 2, 'tap invokes SDK synchronously'); await flush();
  assert.equal(f.el.xhsOpen.disabled, false);
  assert.doesNotMatch(f.el.xhsStatus.textContent, /发布成功|分享成功/);
  assert.ok(f.reports.some(r => r.body.event === 'sdk_returned'));
  assert.ok(f.reports.every(r => new URL(r.url).pathname.endsWith('/share-events')));
});

test('in-flight SDK call cannot duplicate; numeric failure is logged without private messages', async () => {
  let finish;
  const f = officialFixture({ sdk: () => new Promise(resolve => finish = resolve) }); await flush();
  f.el.xhsOpen.onclick(); f.el.xhsOpen.onclick();
  assert.equal(f.calls.length, 1); assert.equal(f.el.xhsOpen.disabled, true);
  f.calls[0].fail({ errCode: 20003, message: 'SECRET_SIGNATURE_URL' }); finish(); await flush();
  assert.equal(f.el.xhsOpen.disabled, false);
  assert.match(f.el.xhsStatus.textContent, /失败.*重新尝试/);
  assert.equal(f.reports.find(r => r.body.event === 'sdk_failed').body.error_code, 20003);
  assert.equal(f.reports.some(r => r.body.event === 'sdk_returned'), false);
  assert.doesNotMatch(JSON.stringify(f.reports), /SECRET_SIGNATURE_URL/);
});

for (const timeout of [false, true]) test(`SDK load failure is recoverable (timeout: ${timeout})`, async () => {
  const f = officialFixture({ ready: false, autoOpen: true });
  assert.equal(f.el.xhsOpen.disabled, true); assert.equal(f.scripts.length, 1);
  if (timeout) f.timers.find(t => t.delay === 8000).fn(); else f.scripts[0].onerror();
  await flush();
  assert.equal(f.scripts[0].removed, true); assert.equal(f.el.xhsOpen.disabled, false);
  assert.equal(f.el.xhsOpen.textContent, '重新加载分享'); assert.equal(f.calls.length, 0);
  f.el.xhsOpen.onclick(); assert.equal(f.scripts.length, 2); f.load(); await flush();
  assert.equal(f.calls.length, 1); assert.equal(f.el.xhsOpen.disabled, false);
});

test('expired or hidden page never automatically launches after delayed SDK loading', async () => {
  const expired = officialFixture({ ready: false, autoOpen: true }); expired.expire(); expired.load(); await flush();
  assert.equal(expired.calls.length, 0); assert.equal(expired.el.xhsOpen.disabled, true);
  assert.match(expired.el.xhsStatus.textContent, /过期/);
  const hidden = officialFixture({ ready: false, autoOpen: true });
  hidden.document.hidden = true; hidden.events.visibilitychange(); hidden.load(); await flush();
  assert.equal(hidden.calls.length, 0);
  hidden.document.hidden = false; hidden.events.visibilitychange(); await flush();
  assert.equal(hidden.calls.length, 0); hidden.el.xhsOpen.onclick(); assert.equal(hidden.calls.length, 1); await flush();
});

test('diagnostic network failure does not prevent SDK sharing; synchronous SDK failure stays recoverable', async () => {
  const f = officialFixture({ autoOpen: true, telemetryThrows: true }); await flush();
  assert.equal(f.calls.length, 1); assert.equal(f.el.xhsOpen.disabled, false);
  const broken = officialFixture({ autoOpen: true, sdk: () => { throw new Error('PRIVATE_ERROR'); } }); await flush();
  assert.equal(broken.el.xhsOpen.disabled, false); assert.match(broken.el.xhsStatus.textContent, /重新尝试/);
  assert.doesNotMatch(broken.el.xhsStatus.textContent, /PRIVATE_ERROR/);
});


test('opt-in encoded iOS image keeps raw preview and signature; repeated taps never double-encode', async () => {
  const f = officialFixture({ encoding: 'component' }); await flush();
  const raw = f.payload.shareInfo.images[0];
  f.el.xhsOpen.onclick(); await flush();
  f.el.xhsOpen.onclick(); await flush();
  for (const call of f.calls) {
    assert.equal(call.shareInfo.images[0], encodeURIComponent(raw));
    assert.equal(decodeURIComponent(call.shareInfo.images[0]), raw);
  }
  assert.equal(f.el.xhsPhoto.src, raw);
  assert.equal(f.payload.shareInfo.images[0], raw);
  assert.ok(f.reports.every(r => r.body.image_url_encoding === 'component'));
  assert.ok(f.reports.every(r => new URL(r.url).searchParams.get('signature') === 'b'.repeat(64)));
});
