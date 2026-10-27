const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app/static/selfit/mirror-xhs-share.js', 'utf8');

function fixture({ expired = false, agent = 'Android 16', platform = 'Android', wechat = false, invalid = '', throws = false } = {}) {
  let now = 1800000000000, back = 0;
  const el = {}, calls = [], timers = [], storage = new Map(), events = {};
  const scheme = 'xhsdiscover://js_share_sdk?share_code=official-code&app_key=test&session_id=session';
  const universal = 'https://oia.xiaohongshu.com/oia?deeplink=' + encodeURIComponent(scheme);
  const payload = { expiresAt: now + (expired ? -1 : 180000), shareInfo: { type: 'normal', images: [
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
