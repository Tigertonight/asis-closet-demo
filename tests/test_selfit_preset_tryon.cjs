const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app/static/selfit-tryon/studio.js', 'utf8');
const start = source.slice(source.indexOf('  async function startTry()'), source.indexOf('  function beginMirrorGeneration('));
const generate = source.slice(source.indexOf('  async function generate()'), source.indexOf('  function failure('));
const polling = source.slice(source.indexOf('  async function poll('), source.indexOf('  async function importGarment('));
const tick = () => new Promise(resolve => setImmediate(resolve));

(async () => {
  const outfit = {id:'set-a', kind:'outfit', items:[{id:'top'}, {id:'shoes'}]};
  const state = {current:outfit, photo:'model.png', modelId:'female_medium_1', personalPhoto:'', page:'mirror'};
  const requests = [], timers = [], failures = [], completed = [];
  let now = 0, decode, rejectDecode;
  const job = {job_id:'job-a', outfit_id:'set-a', model_id:'female_medium_1', status:'completed',
    result:{generation_strategy:'preset', result:{image_path:'/preset.png'}}};
  class Image {
    decode() { return new Promise((resolve,reject)=>{decode=resolve;rejectDecode=reject;}); }
  }
  const context = vm.createContext({state, FormData, Set, Image, Promise, reference:false,
    generationBusy:false, Date:{now:()=>now}, crypto:{randomUUID:()=> 'request-a'},
    setTimeout:(fn,ms)=>{timers.push({fn,ms});}, mediaURL:x=>x,
    photoFile:async()=>new Blob(['model']), sessionStorage:{setItem(){},removeItem(){}},
    beginMirrorGeneration:(target,photo)=>{state.generating={target,photo};state.job=null;},
    notify(){}, modal(){throw Error('Fixed models should directly enter loading');}, models(){},
    failure:message=>{state.generating=null;failures.push(message);},
    poll:async value=>{state.generating=null;completed.push(value);},
    api:async(url,options)=>{requests.push({url,options});now=200;return job;},
  });
  vm.runInContext(start + generate, context);
  const pending = vm.runInContext('startTry()', context);
  assert.ok(state.generating, 'loading appears immediately');
  await tick();
  assert.equal(requests.length,1);
  assert.equal(requests[0].options.body.get('model_id'),'female_medium_1');
  assert.equal(timers[0].ms,2800, 'network preparation counts toward the 3-second loading');
  decode(); await tick();
  assert.equal(completed.length,0,'a ready image cannot bypass the loading duration');
  await vm.runInContext('startTry()',context);
  assert.equal(requests.length,1,'double click while the completed preset is waiting is blocked');
  timers.shift().fn(); await pending;
  assert.equal(completed[0],job,'reuse the completed job without starting a generation worker');

  state.job=null;now=0;
  const slow = vm.runInContext('startTry()',context);await tick();
  timers.shift().fn();await tick();
  assert.equal(completed.length,1,'keep loading until the preset image is decoded');
  decode();await slow;
  state.job=null;now=0;
  const broken = vm.runInContext('startTry()',context);await tick();
  rejectDecode(Error('image unavailable'));await broken;
  assert.equal(failures.length,1);
  assert.equal(state.generating,null,'failed preset can be retried');

  // An in-flight preset must not overwrite another outfit/model or navigate away.
  Object.assign(context,{pollTimer:null,clearTimeout(){},normalizeOutfit:x=>x,lookup:()=>outfit,
    $:()=>null,render(){},go(){throw Error('late result must not navigate');}});
  vm.runInContext(polling, context);
  for(const changed of [{current:{id:'different'},modelId:'female_medium_1',page:'mirror'},
    {current:outfit,modelId:'female_slim_1',page:'mirror'},
    {current:outfit,modelId:'female_medium_1',page:'closet'}]) {
    Object.assign(state,changed,{job,generating:{target:outfit},completedTryon:null,result:''});
    await vm.runInContext('poll(state.job)',context);
    assert.equal(state.result,'');
    assert.equal(state.current,changed.current);
    assert.equal(state.page,changed.page);
    assert.equal(state.generating,null);
  }
  console.log('Preset loading timing, decode, duplicate prevention, failure and navigation checks passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
