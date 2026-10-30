const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { webcrypto } = require('node:crypto');
const source = fs.readFileSync('app/static/selfit/mirror-client.js', 'utf8');

function client(store = new Map(), { blocked = false, random = true } = {}) {
  const context = { Uint8Array, crypto: random ? webcrypto : undefined,
    localStorage: {
      getItem(key) { if (blocked) throw new Error('blocked'); return store.get(key); },
      setItem(key, value) { if (blocked) throw new Error('blocked'); store.set(key, value); },
    } };
  vm.runInNewContext(source, context);
  return context.SelfitMirrorClient;
}

test('one browser reuses its random identifier across page loads; another browser gets a new one', () => {
  const store = new Map(), first = client(store), reload = client(store), another = client();
  assert.match(first.id, /^mc_[a-f0-9]{32}$/);
  assert.equal(first.id, reload.id);
  assert.notEqual(first.id, another.id);
  assert.equal(first.headers()['X-Selfit-Client-Id'], first.id);
  store.clear(); assert.notEqual(client(store).id, first.id);
});

test('malformed storage cannot be propagated into request headers', () => {
  for (const saved of ['SECRET_TOKEN', 'mc_' + 'a'.repeat(32) + '\n', 'mc_' + 'a'.repeat(33), '']) {
    const store = new Map([['selfit.mirrorClient.v1', saved]]);
    const current = client(store);
    assert.match(current.id, /^mc_[a-f0-9]{32}$/);
    assert.equal(current.id.length, 35);
    assert.notEqual(current.id, saved);
  }
});

test('blocked storage keeps a page-scoped ID; unavailable randomness disables diagnostics safely', () => {
  const current = client(new Map(), { blocked: true });
  assert.match(current.id, /^mc_[a-f0-9]{32}$/);
  assert.equal(current.headers()['X-Selfit-Client-Id'], current.id);
  const missing = client(new Map(), { blocked: true, random: false });
  assert.equal(missing.id, null);
  assert.deepEqual(Object.keys(missing.headers()), []);
});
