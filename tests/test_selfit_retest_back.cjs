const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const src = fs.readFileSync(path.join(root, 'app/static/selfit/selfit.js'), 'utf8');
const navSource = src.slice(src.indexOf('  const ONBOARDING_NAV = {'), src.indexOf('  const SESSION_STORAGE_KEY'));
const returnSource = src.slice(src.indexOf('  const returnToProfile ='), src.indexOf('  let splashTimer'));

function navHarness(retest) {
  const back = {
    hidden: true, attrs: {},
    setAttribute(key, value) { this.attrs[key] = value; },
  };
  const stepper = { attrs: {}, setAttribute(key, value) { this.attrs[key] = value; } };
  const steps = ['like', 'suit', 'vibe'].map((step) => ({
    dataset: { step },
    classList: { toggle() {} },
    setAttribute() {},
    removeAttribute() {},
  }));
  const nav = { hidden: true };
  const context = vm.createContext({
    retestEntry: retest,
    onboardingNav: nav,
    onboardingBack: back,
    onboardingStepper: stepper,
    onboardingSteps: steps,
  });
  vm.runInContext(navSource, context);
  return { nav, back, stepper, update: (name) => vm.runInContext(`updateOnboardingNav('${name}')`, context) };
}

// 首次 onboarding：like 的返回键回到 intro 过场。
{
  const h = navHarness(false);
  h.update('like');
  assert.equal(h.nav.hidden, false);
  assert.equal(h.back.hidden, false);
  assert.equal(h.back.attrs['data-back'], 'intro');
  assert.equal(h.back.attrs['aria-label'], '返回');
}

// 重新测试：like 是第一步，返回键可见且直达「我的档案」。
{
  const h = navHarness(true);
  h.update('like');
  assert.equal(h.nav.hidden, false);
  assert.equal(h.back.hidden, false, 'retest like screen keeps the back button visible');
  assert.equal(h.back.attrs['data-back'], 'profile');
  assert.equal(h.back.attrs['aria-label'], '返回我的档案');
  h.update('vibe');
  assert.equal(h.back.attrs['data-back'], 'like', 'vibe still steps back inside the test');
  assert.equal(h.back.attrs['aria-label'], '返回');
}

// 返回「我的档案」跳转到主 App 的 profile 屏。
{
  const navigations = [];
  const context = vm.createContext({
    URL,
    window: { location: { origin: 'http://localhost:8000', assign: (url) => navigations.push(url) } },
  });
  vm.runInContext(returnSource, context);
  vm.runInContext('returnToProfile()', context);
  assert.deepEqual(navigations, ['/selfit/try-on?screen=profile']);
}

console.log('Retest back-to-profile nav passed.');
