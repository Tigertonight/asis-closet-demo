const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app/static/selfit/mirror-xhs-share.js', 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));

function fixture({ expired = false, mobile = true, sdk = 'ok', invalid = false } = {}) {
  const now = 1800000000000, el = {}, calls = [], scripts = [], timers = [], storage = new Map();
  const payload = { expiresAt: now + (expired ? -1 : 180000), shareInfo: { type: 'normal', images: [
    `https://${invalid ? 'attacker.invalid' : 'selfit.com.cn'}/api/v1/selfit/mirror/photos/mp_${'a'.repeat(32)}/files/print.png?signature=test`
  ] }, verifyConfig: { appKey: 'test', nonce: 'test', timestamp: String(now), signature: 'test' } };
  storage.set('selfit.xhsShare', JSON.stringify(payload));
  let back = 0;
  const context = {
    document: { getElementById: id => el[id] ||= { disabled: true }, createElement: () => ({}), head: { append: s => scripts.push(s) } },
    location: { origin: 'https://selfit.com.cn', replace() {} }, history: { length: 2, back: () => back++ },
    navigator: { userAgent: mobile ? 'iPhone' : 'Windows' }, URL,
    Date: class extends Date { static now() { return now; } },
    sessionStorage: { getItem: k => storage.get(k), removeItem: k => storage.delete(k) },
    setTimeout: f => { timers.push(f); return timers.length; }, clearTimeout() {},
    window: { xhs: { share: args => {
      calls.push(args);
      if (sdk === 'fail') args.fail({ errCode: 20003 });
      if (sdk === 'throw') throw new Error('SDK error');
      return sdk === 'pending' ? new Promise(() => {}) : Promise.resolve();
    } } },
  };
  vm.runInNewContext(source, context);
  scripts[0]?.onload();
  return { el, scripts, storage, calls, timers, back: () => back };
}

test('SDK loads on clean handoff page, waits for tap and sends only the composed image', async () => {
  const f = fixture();
  assert.equal(f.storage.size, 0);
  assert.equal(f.scripts[0].src, 'https://fe-static.xhscdn.com/biz-static/goten/xhs-1.0.1.js');
  assert.equal(f.calls.length, 0);
  f.el.xhsOpen.onclick();
  assert.equal(f.calls.length, 1, 'invoke in user activation, without an await');
  assert.deepEqual(Object.keys(f.calls[0].shareInfo), ['type', 'images']);
  f.el.xhsOpen.onclick();
  assert.equal(f.calls.length, 1);
  await tick();
  assert.equal(f.el.xhsOpen.disabled, false);
  assert.doesNotMatch(f.el.xhsStatus.textContent, /已发布|发布成功|分享成功/);
  f.el.xhsBack.onclick(); assert.equal(f.back(), 1);
});

for (const opts of [{ expired: true }, { invalid: true }, { mobile: false }]) test(`unusable context never calls SDK: ${JSON.stringify(opts)}`, () => {
  const f = fixture(opts);
  assert.equal(f.scripts.length, 0); assert.equal(f.calls.length, 0);
  assert.equal(f.el.xhsOpen.disabled, true);
  f.el.xhsBack.onclick(); assert.equal(f.back(), 1);
});

for (const sdk of ['fail', 'throw', 'pending']) test(`SDK ${sdk} has recovery without claiming success`, async () => {
  const f = fixture({ sdk }); f.el.xhsOpen.onclick(); await tick();
  if (sdk === 'pending') f.timers.at(-1)();
  assert.equal(f.el.xhsOpen.disabled, false);
  assert.match(f.el.xhsStatus.textContent, /重试|保存照片/);
  assert.doesNotMatch(f.el.xhsStatus.textContent, /发布成功/);
});
