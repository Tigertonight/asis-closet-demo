const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const s=fs.readFileSync('app/static/selfit-tryon/studio.js','utf8');
const code=s.slice(s.indexOf('  async function photoFile('),s.indexOf('  async function startTry()'));
function harness({missing=false,failed=false}={}){
 const calls=[];const state={photo:'/old-model.png',modelId:'female_slim_1',file:null};
 const c=vm.createContext({state,File,URL,location:{origin:'https://selfit.test'},savedSession:{accessToken:'test'},
 api:async(url,options)=>{calls.push({url,options});return {items:missing?[]:[{id:'female_slim_1',image_url:'/current-master.png',preview_url:'/current-preview.webp'}]};},
 mediaURL:(url,original)=>{assert.equal(original,true);return url;},
 fetch:async(url,options)=>{calls.push({url,options});return {ok:!failed,blob:async()=>new Blob(['current-master'],{type:'image/png'})};}});
 vm.runInContext(code,c);return {calls,state,run:()=>vm.runInContext('photoFile()',c)};
}
test('stale fixed-model page uploads the newly resolved master, never cached URL or preview',async()=>{
 const h=harness(),file=await h.run();assert.equal(await file.text(),'current-master');assert.equal(file.name,'current-master.png');
 assert.deepEqual(h.calls.map(x=>x.url),['/selfit/try-on/models','/current-master.png']);assert.ok(h.calls.every(x=>x.options.cache==='no-store'));
});
test('missing or unavailable current model fails without falling back to old photo',async()=>{
 for(const config of [{missing:true},{failed:true}]){const h=harness(config);await assert.rejects(h.run());assert.ok(!h.calls.some(x=>x.url==='/old-model.png'));}
});
test('explicit user upload is kept byte-for-byte and does not resolve a fixed model',async()=>{
 const h=harness();h.state.modelId='self';h.state.file=new File(['personal-original'],'own.jpg',{type:'image/jpeg'});
 assert.equal(await h.run(),h.state.file);assert.equal(h.calls.length,0);
});
