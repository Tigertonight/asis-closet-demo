const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');
const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'app/static/selfit/selfit.js'), 'utf8');
const sampleSource = source.slice(source.indexOf('  const SAMPLE_PHOTOS ='), source.indexOf("  document.querySelector('.manual-form').addEventListener"));

function harness(gender) {
  const clicks = {}, uploads = [];
  const state = {gender, photoStatus:{face:'empty',body:'empty'}};
  const buttons = ['face', 'body'].map(kind => ({dataset:{samplePhoto:kind}, addEventListener:(_, fn) => {clicks[kind] = fn;}}));
  const context = {state, document:{querySelectorAll:() => buttons},
    genderReady:() => ['female', 'male'].includes(state.gender), track(){},
    fetch:()=>assert.fail('sample originals must not be downloaded'),
    File:class {constructor(){assert.fail('sample must not become an upload file');}},
    uploadPhoto:async (kind, file, {sampleId}) => uploads.push({kind,file,sampleId}),
  };
  vm.createContext(context);vm.runInContext(sampleSource,context);
  return {clicks,state,context,uploads};
}
for(const gender of ['female','male']) test(`${gender} sample buttons submit IDs without downloading or uploading originals`,async()=>{
  const h=harness(gender);await h.clicks.face();await h.clicks.body();
  assert.deepEqual(h.uploads,[{kind:'face',file:null,sampleId:`${gender}-face`},{kind:'body',file:null,sampleId:`${gender}-body`}]);
});
test('samples follow reselection and cannot start before gender or while busy',async()=>{
  const h=harness(null);await h.clicks.face();assert.equal(h.uploads.length,0);
  h.state.gender='female';await h.clicks.face();
  h.state.gender='male';await h.clicks.body();
  h.state.photoStatus.face='checking';await h.clicks.face();assert.equal(h.uploads.length,2);
  h.state.photoStatus.face='invalid';await h.clicks.face();assert.equal(h.uploads[2].sampleId,'male-face');
});
function flowHarness(){
  const state={photoControllers:{},photoAssets:{},samplePhotos:{},photoStatus:{},screen:'suit',revision:1};
  const previews=[], requests=[];
  const pending=(type,args)=>new Promise((resolve,reject)=>requests.push({type,args,resolve,reject}));
  const context={state,AbortController,genderReady:()=>true,validatePhoto:()=>'',
    document:{querySelector:()=>({})},renderPhotoPreview:(_,photo)=>previews.push(photo),
    setPhotoState:(kind,status)=>{state.photoStatus[kind]=status;},ensureSession:async()=> 'session',
    api:{useSamplePhoto:(...args)=>pending('sample',args),checkPhoto:(...args)=>pending('upload',args)},
    track(){},renderSuit:async()=>{},applyAnalysisOverlay(){},toast(){}};
  vm.createContext(context);
  vm.runInContext(source.slice(source.indexOf('  const uploadPhoto ='),source.indexOf('  const bindUpload ='))+';globalThis.upload=uploadPhoto;',context);
  return {state,previews,requests,upload:context.upload};
}
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const result=id=>({photo:{status:'accepted',assetId:id},revision:2});
test('sample preview appears before analysis and an old sample cannot overwrite a personal upload',async()=>{
  const h=flowHarness();const first=h.upload('face',null,{sampleId:'female-face'});await tick();
  assert.equal(h.previews[0],'/api/v1/selfit/sample-photos/female-face/preview');
  assert.equal(h.state.photoStatus.face,'checking');
  const file={name:'self.jpg',type:'image/jpeg'};const second=h.upload('face',file);await tick();
  assert(h.requests[0].args[3].signal.aborted);
  h.requests[0].resolve(result('old'));await first;assert.notEqual(h.state.photoAssets.face,'old');
  h.requests[1].resolve(result('new'));await second;
  assert.equal(h.state.photoAssets.face,'new');assert.equal(h.state.facePhoto,file);assert.equal(h.state.samplePhotos.face,null);
});
test('failed analysis permits retry and keeps the selected sample preview',async()=>{
  const h=flowHarness();const first=h.upload('body',null,{sampleId:'male-body'});await tick();
  h.requests[0].reject(new Error('请求超时'));await first;
  assert.equal(h.state.photoStatus.body,'invalid');assert.equal(h.state.samplePhotos.body,'male-body');
  const second=h.upload('body',null,{sampleId:'male-body'});await tick();
  h.requests[1].resolve(result('retried'));await second;
  assert.equal(h.state.photoStatus.body,'valid');assert.equal(h.state.photoAssets.body,'retried');
});
test('sample API sends small JSON with cancellation and idempotency',async()=>{
  const calls=[];const context={window:{},AbortController,setTimeout,clearTimeout,
    fetch:async(url,options)=>{calls.push({url,options});return {ok:true,json:async()=>result('sample')};}};
  vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(root,'app/static/selfit/selfit-api.js'),'utf8'),context);
  const api=context.window.SelfitApi.createClient({mode:'live'});
  await api.useSamplePhoto('session','face','male-face',{idempotencyKey:'one-selection'});
  assert.equal(calls[0].url,'/api/v1/selfit/sessions/session/photos/face/sample');
  assert.equal(calls[0].options.body,JSON.stringify({sampleId:'male-face'}));
  assert.equal(calls[0].options.headers['X-Idempotency-Key'],'one-selection');
  const controller=new AbortController();controller.abort();
  await api.useSamplePhoto('session','face','male-face',{signal:controller.signal});
  assert(calls[1].options.signal.aborted);
});

function profileHarness(reference, query = '') {
  const studio = fs.readFileSync(path.join(root, 'app/static/selfit-tryon/studio.js'), 'utf8');
  const state = {profile:null,profileLoading:false,page:'profile',uploadURLs:[]};
  const fetched = [];
  const context = {state,reference,params:new URLSearchParams(query),
    A:'/static/selfit-tryon/assets/',REFERENCE_PROFILE_SUIT:{},render(){},refreshProfilePhoto(){},
    savedSession:{accessToken:'test-only'},
    api:async()=>({profile:{gender:'female',photos:{face:'/my-face',body:'/my-body'},suit:{}}}),
    fetch:async url=>{fetched.push(url);return {ok:true,status:200,blob:async()=>url};},
    URL:{createObjectURL:url=>`blob:${url}`}};
  vm.createContext(context);
  vm.runInContext(studio.slice(studio.indexOf('  async function loadProfilePhoto('),studio.indexOf('  async function uploadProfilePhoto(')),context);
  return {state,fetched,load:async()=>{
    await context.loadProfile();
    // Photo requests now finish independently after the profile is displayed.
    await new Promise(resolve=>setImmediate(resolve));
  }};
}

test('female profile preview shares the latest onboarding body sample; male preview stays unchanged',async()=>{
  const female=profileHarness(true);await female.load();
  assert.equal(female.state.profile.photos.body,'/static/selfit/assets/samples/female-body-sample-v2.jpg');
  const male=profileHarness(true,'profile_gender=male');await male.load();
  assert.equal(male.state.profile.photos.body,'/static/selfit-tryon/assets/main-app/archive-body-reference.svg');
});

test('real profiles keep the user’s saved photos, never replacing them with a sample',async()=>{
  const h=profileHarness(false);await h.load();
  assert.equal(h.state.profileError,'');
  assert.deepEqual(h.fetched,['/my-face','/my-body']);
  assert.equal(h.state.profile.photos.body,'blob:/my-body');
});

test('preview download timeout remains active until the entire body finishes',async()=>{
  const context={window:{},AbortController,setTimeout,clearTimeout,
    fetch:async(url,{signal})=>({ok:true,blob:()=>new Promise((resolve,reject)=>signal.addEventListener('abort',()=>reject(new Error('aborted')),{once:true}))})};
  vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(root,'app/static/selfit/selfit-api.js'),'utf8'),context);
  const api=context.window.SelfitApi.createClient({mode:'live'});
  await assert.rejects(api.request('/preview',{blob:true,timeoutMs:10}),error=>error.code==='network.timeout');
});

test('mock samples use the same gender lifecycle and preserve personal uploads',async()=>{
  const context={window:{},setTimeout:fn=>{fn();return 1;},clearTimeout(){}};
  vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(root,'app/static/selfit/selfit-api.js'),'utf8'),context);
  const api=context.window.SelfitApi.createClient({mode:'mock'});
  const {session}=await api.createSession({onboardingMode:'new'});
  await api.saveGender(session.sessionId,'female');
  await api.useSamplePhoto(session.sessionId,'face','female-face');
  assert.equal((await api.getSuit(session.sessionId)).samplePhotos.face,'female-face');
  await api.saveGender(session.sessionId,'male');
  assert.equal((await api.getSuit(session.sessionId)).photos.face,false);
  await api.checkPhoto(session.sessionId,'face',{name:'personal.jpg'});
  await api.saveGender(session.sessionId,'female');
  assert.equal((await api.getSuit(session.sessionId)).photos.face,true);
});
