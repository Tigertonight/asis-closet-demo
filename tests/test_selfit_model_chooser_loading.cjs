const assert=require('node:assert/strict');
const {test}=require('node:test');
const fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('app/static/selfit-tryon/studio.js','utf8');
const code=source.slice(source.indexOf('  async function models()'),source.indexOf('  async function selectModel('));
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {resolve,promise};};
const flush=()=>new Promise(resolve=>setImmediate(resolve));
function harness() {
  const photo=deferred(),catalog=deferred(),renders=[];
  const state={personalPhoto:'',modelLibrary:[{id:'fixed',name:'匀称型',image_url:'/fixed.webp'}],modelId:'fixed'};
  const sheet={open:true,classList:{contains:()=>true},scrollLeft:0};
  const button={dataset:{action:'upload-photo'},innerHTML:'上传我的全身照'};
  const ctx=vm.createContext({state,loadPhoto:()=>photo.promise,loadModels:()=>catalog.promise,
    modelSheet:html=>{renders.push(html);sheet.scrollLeft=0;},
    $:selector=>selector==='#sheet' ? sheet : button,esc:String,image:src=>`<img src="${src}">`});
  vm.runInContext(code,ctx);
  return {state,sheet,button,photo,catalog,renders,run:()=>vm.runInContext('models()',ctx)};
}
test('fixed-model choices become usable before optional historical photo; late preview only updates footer',async()=>{
  const h=harness(),ready=h.run();
  h.catalog.resolve();await ready;
  assert.match(h.renders.at(-1),/data-model-id="fixed"/);
  assert.match(h.renders.at(-1),/fixed.webp/);
  assert.equal(h.state.personalPhoto,'');
  h.sheet.scrollLeft=77;
  const count=h.renders.length;
  h.state.personalPhoto='blob:own-preview';h.photo.resolve();await flush();
  assert.equal(h.button.dataset.modelId,'self');
  assert.equal(h.button.dataset.action,undefined);
  assert.match(h.button.innerHTML,/使用我的照片/);
  assert.equal(h.renders.length,count);
  assert.equal(h.sheet.scrollLeft,77);
});
test('late optional photo never reopens a closed model chooser',async()=>{
  const h=harness(),ready=h.run();
  h.catalog.resolve();await ready;
  h.sheet.open=false;
  const count=h.renders.length;
  h.state.personalPhoto='blob:own-preview';h.photo.resolve();await flush();
  assert.equal(h.sheet.open,false);
  assert.equal(h.button.dataset.action,'upload-photo');
  assert.equal(h.renders.length,count);
});
