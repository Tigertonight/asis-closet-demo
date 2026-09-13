const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {test} = require('node:test');
const source = fs.readFileSync('app/static/selfit-tryon/studio.js', 'utf8');
const slice = (a, b) => source.slice(source.indexOf(a), source.indexOf(b));

test('invite denial has its own code; unrelated 403 and quota 429 stay separate', async () => {
  for (const [status, detail, header, expected] of [
    [403, '权限不足', 'invite-required', 'invite_required'],
    [403, '内测名额有限，输入邀请码解锁完整体验', '', 'invite_required'],
    [403, '这不是你的照片', '', undefined],
    [403, '', '', undefined],
    [429, '今日试穿额度已用完', '', undefined],
  ]) {
    const ctx = vm.createContext({AbortController, setTimeout, clearTimeout, savedSession: null,
      fetch: async () => ({ok: false, status, json: async () => ({detail}),
        headers: {get: name => name === 'X-Selfit-Access' ? header : null}})});
    vm.runInContext(slice('  async function api(', '  function nav()'), ctx);
    await assert.rejects(vm.runInContext("api('/selfit/try-on/jobs')", ctx), error => {
      assert.equal(error.status, status);
      assert.equal(error.code, expected);
      if (status === 403 && !detail) assert(!error.message.includes('邀请码'));
      return true;
    });
  }
});

test('browsing keeps the account without a beta redirect and refreshes qualification before try-on', async () => {
  for (const [user_id, qualified] of [
    ['guest_test', true], ['phone_test', true],
    ['guest_test', false], ['phone_test', false],
  ]) {
    const session = {accessToken: 'same-token', user: {user_id, beta_qualified: qualified}};
    const locations = [];
    let restored = 0, ensured = 0;
    const ctx = vm.createContext({reference: false, savedSession: {user: {user_id, beta_qualified: !qualified}},
      window: {location: {replace: url => locations.push(url)}},
      authClient: {
        restore: async options => {assert.equal(options.strict, true); restored++; return session;},
        ensureVisitor: async () => {ensured++; return session;},
      }});
    vm.runInContext(slice('  let visitorReady = null;', '  function mediaURL('), ctx);
    assert.equal(await vm.runInContext('ensureVisitorSession()', ctx), session);
    await vm.runInContext('ensureVisitorSession()', ctx);
    assert.equal(ensured, 1);
    assert.equal(restored, 0);
    assert.equal(await vm.runInContext('refreshSession()', ctx), session);
    assert.equal(restored, 1);
    assert.equal(locations.length, 0);
    assert.equal(ctx.savedSession.accessToken, 'same-token');
    assert.equal(ctx.savedSession.user.beta_qualified, qualified);
  }
});

test('try-on requires fresh beta access; local-qualified users can proceed', async () => {
  for (const beta_qualified of [false, true]) {
    let refreshed = 0;
    const ctx = vm.createContext({
      refreshSession: async () => {refreshed++; return {user: {beta_qualified}};},
    });
    vm.runInContext(slice('  async function requireTryonAccess()', '  function isTryonAccessError('), ctx);
    const pending = vm.runInContext('requireTryonAccess()', ctx);
    if (beta_qualified) await pending;
    else await assert.rejects(pending, error => error.status === 403 && error.code === 'auth.beta_required');
    assert.equal(refreshed, 1);
  }
});

test('backend invite denial opens unlock form rather than a generation failure dialog', () => {
  const state = {photo: '/original.jpg', current: {id: 'outfit'}, generating: {}, page: 'mirror'};
  let prompted = 0;
  const ctx = vm.createContext({state, render() {}, startTry() {},
    showTryonAccess: error => {assert.equal(error.code, 'invite_required'); prompted++;},
    modal: () => {throw Error('must not show retry/change photo');}});
  vm.runInContext(slice('  function isTryonAccessError(', '  function showTryonAccess(') +
    slice('  function failure(', '  async function poll('), ctx);
  vm.runInContext("failure({code:'invite_required'})", ctx);
  assert.equal(prompted, 1);
  assert.equal(state.generating, null);
  assert.equal(state.photo, '/original.jpg');
  assert.equal(state.current.id, 'outfit');
});
