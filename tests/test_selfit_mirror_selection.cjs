const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');
const source = fs.readFileSync(path.resolve(__dirname, '../app/static/selfit-tryon/studio.js'), 'utf8');
const first = {id:'outfit-1',name:'第一套推荐',src:'/first.jpg',items:[{id:'shirt-1'}]};
const second = {id:'outfit-2',name:'第二套推荐',src:'/second.jpg',items:[{id:'shirt-2'}]};

function harness(overrides = {}, reference = false, query = '') {
  const state = {page:'mirror',source:'report',current:null,result:'',generating:null,
    photo:'/original.jpg',selected:new Set(),reportOutfits:[first,second],homeOutfits:[first,second],
    outfits:[],feed:[],topics:[],savedNotes:[], ...overrides};
  const context = {state,reference,params:new URLSearchParams(query),
    esc:String,image:() => '<img>', $:() => ({close(){}}),render(){},modal(){},
    go:page => {state.page=page;},
    lookup:id => [first,second].find(row=>row.id===id),normalizeOutfit:row=>row,
    api:async()=>{throw new Error('Unexpected network request');}};
  vm.createContext(context);
  const sections = [
    ['  function card(', '  function empty('],
    ['  async function restoreSelectedOutfit(', '  async function loadPhoto('],
    ['  function beginMirrorGeneration(', '  async function generateNote('],
    ['  function failure(', '  async function poll('],
    ['  function restoreTryonRecord(', '  async function restoreHistoryRoute('],
  ];
  for (const [start,end] of sections) vm.runInContext(source.slice(source.indexOf(start),source.indexOf(end)),context);
  return {state,context,card:(row,kind='outfit')=>context.card(row,kind)};
}

function inactive(html) {
  assert.doesNotMatch(html,/data-active="true"|aria-pressed="true"|class="outfit-state/);
}
function selected(html) {
  assert.match(html,/data-active="true"/);
  assert.match(html,/aria-label="已选中"/);
  assert.doesNotMatch(html,/class="outfit-state pending/);
}

for (const source of ['report','inspiration']) test(`${source}: first entry keeps all recommendations unselected`,async()=>{
  const h=harness({source});
  await h.context.restoreSelectedOutfit(null);
  assert.equal(h.state.current.id,first.id);
  inactive(h.card(first));inactive(h.card(second));
});

test('an outfit URL and restored item selections are not a completed try-on',async()=>{
  const h=harness({},false,'outfit=outfit-2');
  await h.context.restoreSelectedOutfit(second.id);
  assert.equal(h.state.current.id,second.id);
  assert.ok(h.state.selected.has('shirt-2'));
  inactive(h.card(first));inactive(h.card(second));
});

test('starting try-on marks only its target as pending; failure removes the selection',()=>{
  const h=harness({current:first});
  h.context.beginMirrorGeneration(second,h.state.photo);
  inactive(h.card(first));
  assert.match(h.card(second),/data-active="true"/);
  assert.match(h.card(second),/aria-label="正在试穿"/);
  assert.doesNotMatch(h.card(second),/aria-label="已选中"/);
  h.context.failure('test failure');
  assert.equal(h.state.current.id,second.id);
  inactive(h.card(first));inactive(h.card(second));
});

test('completed results and the item view retain the matching selection',()=>{
  const h=harness({current:second,result:'/result.jpg'});
  selected(h.card(second));inactive(h.card(first));
  h.state.styling=true;
  selected(h.card(second));
});

test('restoring a real history result selects the corresponding outfit',()=>{
  const h=harness();
  h.context.restoreTryonRecord({record_id:'record-1',outfit_id:first.id,image_path:'/history.jpg'});
  selected(h.card(first));inactive(h.card(second));
});

test('switching models or resetting a result does not keep a stale checkmark',()=>{
  const h=harness({current:first,result:'/result.jpg'});
  selected(h.card(first));
  h.state.result='';h.state.photo='/different-model.jpg';
  inactive(h.card(first));
});

test('generation target wins over a previously viewed outfit',()=>{
  const h=harness({current:first,result:'/old-result.jpg',generating:{target:second}});
  inactive(h.card(first));assert.match(h.card(second),/aria-label="正在试穿"/);
});

test('personal outfit aliases still highlight the same completed outfit',()=>{
  const h=harness({current:{id:'saved-outfit'},result:'/result.jpg'});
  selected(h.card({...first,personalId:'saved-outfit'}));
});

test('garment selections remain independent of the try-on status',()=>{
  const h=harness({selected:new Set(['shirt-1'])});
  assert.match(h.card({id:'shirt-1',name:'衬衫'},'item'),/aria-pressed="true"/);
  inactive(h.card(first));
});

test('reference preview is initially unselected, but its explicit generating preview remains marked',()=>{
  inactive(harness({current:first},true).card(first));
  assert.match(harness({current:first},true,'mirror_state=generating').card(first),/aria-label="正在试穿"/);
});
