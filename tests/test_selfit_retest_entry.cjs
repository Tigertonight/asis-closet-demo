const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const studio = fs.readFileSync(path.join(root, 'app/static/selfit-tryon/studio.js'), 'utf8');
const onboarding = fs.readFileSync(path.join(root, 'app/static/selfit/selfit.js'), 'utf8');
const profileSource = studio.slice(studio.indexOf('  function profile()'), studio.indexOf('  function profileFeatureEdit()'));
const profileContext = vm.createContext({
  state: {profile: {tested: true, manual: {}, report: {typeId: 'void', title: '我的风格报告'}}},
  reference: false, A: '', esc: String, image: () => '',
  profileHeader: () => '', profileArt: () => '', profilePhoto: () => '',
});
vm.runInContext(profileSource, profileContext);
const testedMarkup = vm.runInContext('profile()', profileContext);
assert.match(testedMarkup, /report=latest/, 'keep the saved report accessible');
const retestHref = testedMarkup.match(/class="profile-retest" href="([^"]+)"/)[1].replaceAll('&amp;', '&');
profileContext.state.profile = {tested: false, report: null};
const untestedMarkup = vm.runInContext('profile()', profileContext);
assert.match(untestedMarkup, /class="profile-test-invite" href="\/selfit\?from=mirror"/);
assert.doesNotMatch(untestedMarkup, /profile-retest/);

const entrySource = onboarding.match(/  const retestEntry = [^\n]+/)[0];
const routeSource = onboarding.slice(onboarding.indexOf('  const openAppForExistingReport ='), onboarding.indexOf('  const setAuthBusy ='));
const sessionSource = onboarding.slice(onboarding.indexOf('  let sessionPromise ='), onboarding.indexOf('  const reportNodes ='));

async function checkEntry(href, retest) {
  const calls = [], redirects = [];
  let stored = JSON.stringify({sessionId: 'previous-session', userId: 'user-1'});
  const context = vm.createContext({
    entryParams: new URL(href, 'http://localhost').searchParams,
    state: {authUser: {user_id: 'user-1', beta_qualified: true}, sessionId: null},
    authReady: Promise.resolve(), SESSION_STORAGE_KEY: 'session',
    document: {documentElement: {lang: 'zh-CN'}}, track() {},
    window: {location: {replace: url => redirects.push(url)}},
    localStorage: {getItem: () => stored, setItem: (_, value) => {stored = value;}, removeItem: () => {stored = null;}},
    api: {
      async getLatestReport() {calls.push('report'); return {report: {typeId: 'void', reportId: 'saved-report'}};},
      async getSession(sessionId) {calls.push('restore'); return {session: {sessionId, revision: 7}};},
      async createSession() {calls.push('create'); return {session: {sessionId: 'new-session', revision: 1}};},
    },
  });
  vm.runInContext(entrySource + routeSource + sessionSource, context);
  assert.equal(await vm.runInContext('openAppForExistingReport()', context), !retest);
  assert.equal(redirects.length, retest ? 0 : 1);
  assert.deepEqual(calls, retest ? [] : ['report']);
  calls.length = 0;
  const ids = await vm.runInContext('Promise.all([ensureSession(), ensureSession()])', context);
  assert.deepEqual(Array.from(ids), Array(2).fill(retest ? 'new-session' : 'previous-session'));
  assert.deepEqual(calls, [retest ? 'create' : 'restore']);
  await vm.runInContext('ensureSession()', context);
  assert.equal(calls.length, 1, 'reuse the current test session without creating duplicates');
  assert.equal(JSON.parse(stored).sessionId, retest ? 'new-session' : 'previous-session');
}

(async () => {
  await checkEntry(retestHref, true);
  await checkEntry('/selfit?from=mirror', false);
  console.log('Retest link, fresh session, and normal report routing passed.');
})().catch(error => {console.error(error); process.exitCode = 1;});
