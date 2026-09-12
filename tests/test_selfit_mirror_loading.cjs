const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const {test}=require('node:test');
const source=fs.readFileSync('app/static/selfit-tryon/studio.js','utf8');
const cut=(a,b)=>source.slice(source.indexOf(a),source.indexOf(b));
function harness() {
  const requests=[],timers=[],renders=[];
  const state={photo:'/original.png',result:'',page:'mirror',loading:true,initialModelReady:false,
    modelCatalog:[{image_url:'/original.png',preview_url:'/small.webp'}]};
  const ctx=vm.createContext({state,Map,reference:false,esc:s=>s,mediaURL:s=>s,
    mirror:()=>'<main>MODEL</main>',render:()=>renders.push(state.photo),
    Image:class {constructor(){requests.push(this);} decode(){return Promise.resolve();}},
    setTimeout:fn=>{timers.push(fn);return timers.length-1;},clearTimeout:()=>{},
  });
  vm.runInContext(cut('  function modelDisplayURL(', '  const fixtures =')+
    cut('  const mirrorImages =','  let renderedBrowseKey ='),ctx);
  return {state,requests,timers,renders,run:s=>vm.runInContext(s,ctx)};
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
  h.run('readyMirror()');h.timers[0]();
  assert(h.run('readyMirror()').includes('模特图片未能加载'));
  await h.requests[0].onload();
  assert.equal(h.run('readyMirror()'),'<main>MODEL</main>');
});

test('an earlier request cannot override a retried request',async()=>{
  const h=harness();h.state.initialModelReady=true;
  h.run('readyMirror()');h.timers[0]();
  h.run('mirrorImages.delete(state.photo); preloadMirrorImage(state.photo)');
  await h.requests[0].onload();
  assert.equal(h.run('mirrorImages.get(state.photo)'), 'loading');
  h.requests[1].onerror();
  assert(h.run('readyMirror()').includes('模特图片未能加载'));
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
