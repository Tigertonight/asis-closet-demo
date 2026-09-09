const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app/static/selfit-tryon/studio.js','utf8');
const helper = source.slice(source.indexOf('  async function tryFromCard('),source.indexOf('  async function photoFile('));
const cards = [{id:'note-a',items:[{id:'top'},{id:'shoes'}]}, {id:'note-b',items:[{id:'dress'}]}];

(async()=>{
  const state={page:'mirror',current:cards[1],result:'old.png',completedTryon:{src:'older.png'}};
  const strip={scrollLeft:200}, started=[], notices=[];
  let finish, remembered=0;
  const context=vm.createContext({state,Set,generationBusy:false,
    lookup:id=>cards.find(x=>x.id===id),$:()=>strip,
    rememberCanvas:()=>remembered++,notify:message=>notices.push(message),
    startTry:()=>{started.push(state.current);strip.scrollLeft=0;state.job={status:'processing'};return new Promise(resolve=>finish=resolve);},
  });
  vm.runInContext(helper,context);
  const first=vm.runInContext("tryFromCard('note-a')",context);
  assert.equal(started[0],cards[0]);
  assert.deepEqual([...state.selected],['top','shoes']);
  assert.equal(state.result,'');
  assert.equal(state.completedTryon,null);
  assert.equal(strip.scrollLeft,200,'preserve the row during loading');
  await vm.runInContext("tryFromCard('note-b')",context);
  assert.equal(state.current,cards[0],'a second card cannot replace the in-flight outfit');
  assert.equal(started.length,1);
  assert.equal(remembered,1);
  finish();await first;
  assert.equal(strip.scrollLeft,200);
  state.job={status:'completed'};
  const next=vm.runInContext("tryFromCard('note-b')",context);finish();await next;
  assert.equal(started[1],cards[1]);
  assert.deepEqual([...state.selected],['dress']);
  console.log('Single-click notebook try-on, complete item selection, duplicate guard and row scrolling passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
