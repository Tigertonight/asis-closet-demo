const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');
const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'app/static/selfit/selfit.js'), 'utf8');
const sampleSource = source.slice(source.indexOf('  const SAMPLE_PHOTOS ='), source.indexOf("  document.querySelector('.manual-form').addEventListener"));

function harness(gender) {
  const clicks = {}, fetched = [], uploads = [];
  const state = {gender};
  const buttons = ['face', 'body'].map(kind => ({dataset:{samplePhoto:kind}, addEventListener:(_, fn) => {clicks[kind] = fn;}}));
  const context = {
    state, document:{querySelectorAll:() => buttons},
    genderReady:() => ['female', 'male'].includes(state.gender),
    runButtonAction:(_, action) => action(), track(){},
    fetch:async url => {
      fetched.push(url);
      const bytes = fs.readFileSync(path.join(root, 'app', url));
      return {ok:true, blob:async () => ({bytes, type:url.endsWith('.png') ? 'image/png' : 'image/jpeg'})};
    },
    File:class {constructor(parts, name, {type}) {Object.assign(this, {parts, name, type});}},
    uploadPhoto:async (kind, file) => {uploads.push({kind, file});},
  };
  vm.createContext(context);
  vm.runInContext(sampleSource, context);
  return {clicks, state, context, fetched, uploads};
}

test('female buttons use the supplied face PNG and replacement body JPEG without recompressing them', async () => {
  const h = harness('female');
  await h.clicks.face(); await h.clicks.body();
  assert.deepEqual(h.fetched, ['/static/selfit/assets/samples/female-face-sample.png', '/static/selfit/assets/samples/female-body-sample-v2.jpg']);
  for (const {kind, file} of h.uploads) {
    assert.equal(file.type, kind === 'face' ? 'image/png' : 'image/jpeg');
    assert.equal(file.name, kind === 'face' ? 'female-face-sample.png' : 'female-body-sample-v2.jpg');
    const bytes = file.parts[0].bytes;
    if (kind === 'face') {
      assert.equal(bytes.subarray(0, 8).toString('hex'), '89504e470d0a1a0a');
      assert.deepEqual([bytes.readUInt32BE(16), bytes.readUInt32BE(20)], [1086, 1448]);
    } else {
      assert.equal(bytes.subarray(0, 3).toString('hex'), 'ffd8ff');
    }
  }
});

test('male buttons use the supplied face and body PNGs without recompressing them', async () => {
  const h = harness('male');
  await h.clicks.face(); await h.clicks.body();
  assert.deepEqual(h.fetched, ['/static/selfit/assets/samples/male-face-sample.png', '/static/selfit/assets/samples/male-body-sample.png']);
  for (const {kind, file} of h.uploads) {
    assert.equal(file.type, 'image/png');
    assert.equal(file.name, `male-${kind}-sample.png`);
    const bytes = file.parts[0].bytes;
    assert.equal(bytes.subarray(0, 8).toString('hex'), '89504e470d0a1a0a');
    assert.deepEqual([bytes.readUInt32BE(16), bytes.readUInt32BE(20)], [1084, 1451]);
  }
});

test('sample choice follows the current gender after reselection', async () => {
  const h = harness('male');
  h.state.gender = 'female'; await h.clicks.face();
  h.state.gender = 'male'; await h.clicks.body();
  assert.deepEqual(h.fetched, ['/static/selfit/assets/samples/female-face-sample.png', '/static/selfit/assets/samples/male-body-sample.png']);
});

test('no sample is fetched before the user chooses gender', async () => {
  const h = harness(null);
  await h.clicks.face(); await h.clicks.body();
  assert.equal(h.fetched.length, 0);
  assert.equal(h.uploads.length, 0);
});

test('failed sample loading never uploads an invalid file', async () => {
  const h = harness('female');
  h.context.fetch = async () => ({ok:false});
  await assert.rejects(h.clicks.face(), /示例图暂时无法加载/);
  assert.equal(h.uploads.length, 0);
});

function profileHarness(reference, query = '') {
  const studio = fs.readFileSync(path.join(root, 'app/static/selfit-tryon/studio.js'), 'utf8');
  const state = {profile:null,profileLoading:false,page:'profile',uploadURLs:[]};
  const fetched = [];
  const context = {state,reference,params:new URLSearchParams(query),
    A:'/static/selfit-tryon/assets/',REFERENCE_PROFILE_SUIT:{},render(){},
    savedSession:{accessToken:'test-only'},
    api:async()=>({profile:{gender:'female',photos:{face:'/my-face',body:'/my-body'},suit:{}}}),
    fetch:async url=>{fetched.push(url);return {ok:true,status:200,blob:async()=>url};},
    URL:{createObjectURL:url=>`blob:${url}`}};
  vm.createContext(context);
  vm.runInContext(studio.slice(studio.indexOf('  async function loadProfile('),studio.indexOf('  async function uploadProfilePhoto(')),context);
  return {state,fetched,load:()=>context.loadProfile()};
}

test('female profile preview shares the latest onboarding body sample; male preview stays unchanged',async()=>{
  const onboarding=harness('female');await onboarding.clicks.body();
  const female=profileHarness(true);await female.load();
  assert.equal(female.state.profile.photos.body,onboarding.fetched[0]);
  const male=profileHarness(true,'profile_gender=male');await male.load();
  assert.equal(male.state.profile.photos.body,'/static/selfit-tryon/assets/main-app/archive-body-reference.svg');
});

test('real profiles keep the user’s saved photos, never replacing them with a sample',async()=>{
  const h=profileHarness(false);await h.load();
  assert.deepEqual(h.fetched,['/my-face','/my-body']);
  assert.equal(h.state.profile.photos.body,'blob:/my-body');
});
