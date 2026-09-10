const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const studio=fs.readFileSync('app/static/selfit-tryon/studio.js','utf8');
function harness() {
  const requests=[],notices=[];
  const state={page:'closet',items:[{id:'owned',name:'白 T',src:'/owned.png'}],outfits:[],builderRequest:0,builderMatching:false,builderMatchMinMs:0,selected:new Set()};
  const context=vm.createContext({state,reference:false,Set,URL,location:{href:'http://localhost/selfit/try-on?screen=closet'},history:{pushState(){}},setTimeout,
    $:()=>({close(){},scrollTop:0}),render(){},notify:x=>notices.push(x),normalizeItem:x=>({id:x.item_id,name:x.title,raw:x}),normalizeOutfit:x=>({id:x.outfit_id,items:x.items}),
    uniqueItems:xs=>[...new Map(xs.map(x=>[x.id,x])).values()],
    api:(path,options,timeout)=>new Promise((resolve,reject)=>requests.push({path,options,timeout,resolve,reject}))});
  vm.runInContext(studio.slice(studio.indexOf('  function go('),studio.indexOf('  function categoryGroup(')),context);
  vm.runInContext(studio.slice(studio.indexOf('  async function generateForItem('),studio.indexOf('  function outfitBuilder(')),context);
  vm.runInContext(studio.slice(studio.indexOf('  async function saveBuilder('),studio.indexOf('  function openOutfitSheet(')),context);
  return {state,requests,notices,run:code=>vm.runInContext(code,context)};
}
const response={anchor_item_id:'owned',outfits:[{items:[{item_id:'note-outer'},{item_id:'owned'},{item_id:'note-skirt'}]}],matches:[{title:'笔记',reason:'搭配理由'}]};

test('matching uses backend result and keeps notebook pieces outside personal wardrobe',async()=>{
  const h=harness(),job=h.run('generateForItem("owned")');
  assert.equal(h.state.page,'builder');assert.equal(h.state.builderMatching,true);
  await h.run('generateForItem("owned")');assert.equal(h.requests.length,1);
  assert.equal(h.requests[0].path,'/selfit/try-on/items/owned/outfits');
  h.requests[0].resolve(response);await job;
  assert.deepEqual([...h.state.builderIds],['note-outer','owned','note-skirt']);
  assert.equal(h.state.items.length,1);assert.equal(h.state.builderMatch.reason,'搭配理由');
  assert.equal(h.state.builderMatches.length,1);assert.equal(h.state.builderMatchIndex,0);
  assert.equal(h.state.builderMatching,false);
});

test('selecting another note swaps the presented outfit',async()=>{
  const h=harness(),job=h.run('generateForItem("owned")');
  const second={outfit:{items:[{item_id:'note-coat'},{item_id:'owned'}]},match:{title:'第二套笔记',reason:'另一个理由'}};
  h.requests[0].resolve({anchor_item_id:'owned',outfits:[response.outfits[0],second.outfit],matches:[response.matches[0],second.match]});await job;
  assert.equal(h.state.builderMatch.title,'笔记');
  h.run('selectBuilderMatch(1)');
  assert.equal(h.state.builderMatchIndex,1);assert.equal(h.state.builderMatch.title,'第二套笔记');
  assert.deepEqual([...h.state.builderIds],['note-coat','owned']);
  h.run('selectBuilderMatch(9)');
  assert.equal(h.state.builderMatchIndex,1);
});

test('leaving cancels the pending presentation; late result cannot override another request',async()=>{
  const h=harness(),old=h.run('generateForItem("owned")');
  h.run('go("closet")');assert.equal(h.state.builderMatching,false);
  const next=h.run('generateForItem("owned")');
  h.requests[0].resolve(response);await old;
  assert.equal(h.state.builderMatching,true);assert.equal(h.state.builderMatch,null);
  h.requests[1].resolve(response);await next;assert.equal(h.state.builderMatch.title,'笔记');
});

test('failure offers retry and never fabricates a successful outfit',async()=>{
  const h=harness(),job=h.run('generateForItem("owned")');
  h.requests[0].reject(Error('搭配助手暂未连接，请稍后再试。'));await job;
  assert.match(h.state.builderMatchError,/暂未连接/);assert.equal(h.state.builderMatch,null);
  await h.run('saveBuilder()');assert.equal(h.requests.length,1);
  const retry=h.run('generateForItem("owned")');h.requests[1].resolve(response);await retry;
  assert.equal(h.state.builderMatchError,'');
});

test('incomplete matches without the anchor are dropped',async()=>{
  const h=harness(),job=h.run('generateForItem("owned")');
  h.requests[0].resolve({outfits:[{items:[{item_id:'note-outer'},{item_id:'note-skirt'}]}],matches:[{title:'笔记',reason:'理由'}]});await job;
  assert.match(h.state.builderMatchError,/不完整/);assert.equal(h.state.builderMatch,null);
});

test('save submits every selected library ID to the library-aware endpoint',async()=>{
  const h=harness(),job=h.run('generateForItem("owned")');
  const items=[{item_id:'owned'},...Array.from({length:9},(_,i)=>({item_id:'note-'+i}))];
  h.requests[0].resolve({outfits:[{items}],matches:response.matches});await job;
  const save=h.run('saveBuilder()');
  assert.equal(h.requests[1].path,'/selfit/try-on/outfits');
  const body=JSON.parse(h.requests[1].options.body);
  assert.equal(body.item_ids.length,10);assert.equal(body.favorite,true);assert.equal(body.canvas_layout,undefined);
  h.requests[1].resolve({outfit_id:'saved',items});await save;
  assert.equal(h.state.page,'closet');assert.equal(h.state.closetCategory,'set');assert.equal(h.state.outfits.length,1);
});
