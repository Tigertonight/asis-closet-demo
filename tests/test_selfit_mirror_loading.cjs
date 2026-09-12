const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const {test}=require('node:test');
const source=fs.readFileSync('app/static/selfit-tryon/studio.js','utf8');
const cut=(a,b)=>source.slice(source.indexOf(a),source.indexOf(b));
function harness() {
  const requests=[],timers=[],renders=[]; let reloads=0;
  const state={photo:'/original.png',result:'',page:'mirror',loading:true,initialModelReady:false,
    modelCatalog:[{image_url:'/original.png',preview_url:'/small.webp'}]};
  const ctx=vm.createContext({state,Map,reference:false,esc:s=>s,mediaURL:s=>s,
    mirror:()=>'<main>MODEL</main>',render:()=>renders.push(state.photo),load:()=>reloads++,
    Image:class {constructor(){requests.push(this);} decode(){return Promise.resolve();}},
    setTimeout:(fn,ms)=>{const timer={fn,ms,active:true};timers.push(timer);return timer;},clearTimeout:t=>{if(t)t.active=false;},
  });
  vm.runInContext(cut('  function modelDisplayURL(', '  const fixtures =')+
    cut('  const mirrorImages =','  let renderedBrowseKey =')+
    cut('  async function waitForPresetResult(', '  function failure('),ctx);
  return {state,requests,timers,renders,get reloads(){return reloads;},fire:ms=>{const timer=timers.find(t=>t.active&&t.ms===ms);assert(timer,`No active ${ms}ms timer`);timer.active=false;timer.fn();},run:s=>vm.runInContext(s,ctx)};
}

test('model displays before notes finish and downloads only its preview',async()=>{
  const h=harness();
  assert(h.run('readyMirror()').includes('正在准备你的试衣镜'));
  h.state.initialModelReady=true;
  assert(h.run('readyMirror()').includes('正在加载模特'));
  assert.equal(h.requests[0].src,'/small.webp');
  await h.requests[0].onload();
  assert.equal(h.run('readyMirror()'),'<main>MODEL</main>');
  assert.equal(h.state.photo,'/original.png','generation input remains untouched');
  assert.equal(h.state.loading,true,'outfit restoration is still in progress');
  assert.equal(h.renders.length,1);
});

test('a download that finishes after 20 seconds recovers without reloading',async()=>{
  const h=harness();h.state.initialModelReady=true;
  h.run('readyMirror()');h.fire(20000);
  assert(h.run('readyMirror()').includes('图片加载较慢'));
  await h.requests[0].onload();
  assert.equal(h.run('readyMirror()'),'<main>MODEL</main>');
});

test('an earlier request cannot override a retried request',async()=>{
  const h=harness();h.state.initialModelReady=true;
  h.run('readyMirror()');h.fire(20000);
  h.run('mirrorImages.delete(state.photo); preloadMirrorImage(state.photo)');
  await h.requests[0].onload();
  assert.equal(h.run('mirrorImages.get(state.photo)'), 'loading');
  await h.requests[1].onload();
  assert.equal(h.run('readyMirror()'),'<main>MODEL</main>');
});

test('late completion does not move another screen or replace a different model',async()=>{
  const h=harness();h.state.initialModelReady=true;
  h.run('readyMirror()');h.state.photo='/another.png';h.state.page='closet';
  await h.requests[0].onload();
  assert.equal(h.renders.length,0);
  assert.equal(h.state.photo,'/another.png');
  assert.equal(h.run('modelDisplayURL("blob:personal")'),'blob:personal');
  assert.equal(h.run('modelDisplayURL("/tryon-result.png")'),'/tryon-result.png');
});


test('network failures retry twice and rendering reuses the successful retry URL',async()=>{
  const h=harness();h.state.initialModelReady=true;
  h.run('readyMirror()');h.requests[0].onerror();
  assert(!h.run('readyMirror()').includes('未能加载'));
  h.fire(1000);assert.match(h.requests[1].src,/small.webp\?selfit_image_retry=/);
  h.requests[1].onerror();h.fire(2000);
  await h.requests[2].onload();
  assert.equal(h.run('readyMirror()'),'<main>MODEL</main>');
  assert.equal(h.run('mirrorImageSource(state.photo)'),h.requests[2].src);
  assert.equal(h.requests.length,3);
});

test('a failed result is labelled as a result and manual retry keeps its job and outfit',()=>{
  const h=harness();h.state.initialModelReady=true;h.state.result='/result.png';
  const job={job_id:'completed',status:'completed'},outfit={id:'chosen'};
  h.state.job=job;h.state.current=outfit;
  h.run('readyMirror()');h.requests[0].onerror();h.fire(1000);
  h.requests[1].onerror();h.fire(2000);h.requests[2].onerror();
  assert(h.run('readyMirror()').includes('试穿图暂时未能加载，结果已保留'));
  h.run('retryMirrorImage()');
  assert.equal(h.reloads,0);assert.equal(h.state.job,job);assert.equal(h.state.current,outfit);
  assert.equal(h.state.result,'/result.png');assert.match(h.requests[3].src,/selfit_image_retry=/);
});

test('a late success after the recovery button appears still recovers',async()=>{
  const h=harness();h.state.initialModelReady=true;
  h.run('readyMirror()');h.fire(20000);h.fire(60000);
  assert(h.run('readyMirror()').includes('照片暂时未能加载'));
  await h.requests[0].onload();assert.equal(h.run('readyMirror()'),'<main>MODEL</main>');
});

test('queued retries stop after leaving the mirror or manually replacing the request',()=>{
  const h=harness();h.state.initialModelReady=true;
  h.run('readyMirror()');h.requests[0].onerror();h.state.page='closet';h.fire(1000);
  assert.equal(h.requests.length,1);
  h.state.page='mirror';h.run('readyMirror()');h.requests[1].onerror();
  h.run('retryMirrorImage()');h.fire(1000);
  assert.equal(h.requests.length,3);assert.equal(h.reloads,0);
});

test('a decoded preset enters the mirror without starting another image request',async()=>{
  const h=harness();h.state.initialModelReady=true;
  const ready=h.run('waitForPresetResult({result:{result:{image_path:"/preset.png"}}},0)');
  h.fire(0);await ready;h.state.result='/preset.png';
  assert.equal(h.run('readyMirror()'),'<main>MODEL</main>');
  assert.equal(h.requests.length,1);assert.equal(h.run('mirrorImageSource(state.result)'),'/preset.png');
});
