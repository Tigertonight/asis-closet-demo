const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const studio = fs.readFileSync('app/static/selfit-tryon/studio.js', 'utf8');
const slice = (start, end) => studio.slice(studio.indexOf(start), studio.indexOf(end));

(async () => {
  const state = {source:'inspiration', homeOutfits:[], items:[], outfits:[], feed:[{id:'flat-lay',kind:'outfit',items:[]}], savedNotes:[]};
  const calls = [];
  let failed = false;
  const rows = Array.from({length:4}, (_, i) => ({outfit_id:`real-note-${i}`, title:`笔记 ${i}`,
    cover_path:`/photo-${i}.jpg`, items:[{item_id:`top-${i}`},{item_id:`shoes-${i}`}],
    report_note:{id:`note:${i}`,title:`笔记 ${i}`,image_url:`/photo-${i}.jpg`}}));
  const context = vm.createContext({state, URLSearchParams, Set, FormData, reference:false,
    location:{search:'?screen=mirror&outfit=real-note-2'}, window:{},
    normalizeItem:row=>({id:row.item_id}), generationBusy:false,
    crypto:{randomUUID:()=> 'home-notes-test'},
    photoFile:async()=>new Blob(['photo']),
    beginMirrorGeneration:(target,photo)=>{state.generating={target,photo};},
    sessionStorage:{setItem(){}}, poll(){}, failure(message){throw Error(message);},
    api:async(url,options)=>{
      calls.push({url,options});
      if (failed) throw Error('穿搭笔记暂时无法加载，请稍后重试。');
      if (url==='/selfit/try-on/jobs') return {job_id:'test-only',status:'queued'};
      assert(url.startsWith('/selfit/try-on/report-outfits/home?'));
      assert.equal(new URL(url,'http://localhost').searchParams.get('selected_outfit_id'),'real-note-2');
      return {outfits:rows};
    },
  });
  vm.runInContext(slice('  function normalizeOutfit(', '  async function loadReportOutfits()') +
    slice('  async function restoreSelectedOutfit(', '  async function loadPhoto()') +
    slice('  function lookup(id)', '  function updateWardrobeBusy(') +
    slice('  async function startTry()', '  function beginMirrorGeneration(') +
    slice('  async function generate()', '  function failure('), context);
  await vm.runInContext('loadHomeNotes();',context);
  assert.equal(state.homeOutfits.length,4);
  assert(state.homeOutfits.every((row,i)=>row.src===rows[i].report_note.image_url && row.items.length===2));
  await vm.runInContext('loadHomeNotes(); restoreSelectedOutfit(null);',context);
  assert.equal(calls.length,1,'navigation and repeated load keep the current four notes');
  assert.equal(state.current.id,'real-note-0');
  await vm.runInContext("restoreSelectedOutfit('real-note-2');",context);
  assert.equal(state.current.homeNote.id,'note:2');
  assert.equal(vm.runInContext("lookup('shoes-2').id",context),'shoes-2');
  state.photo=state.personalPhoto='fixture-photo';
  await vm.runInContext('startTry();',context);
  const request=calls.at(-1).options.body;
  assert.equal(request.get('outfit_id'),'real-note-2');
  assert.equal(request.get('wear_all_items'),'true');
  assert.deepEqual(JSON.parse(request.get('selected_item_ids')),['top-2','shoes-2']);
  state.homeOutfits=[];state.current=null;failed=true;
  await vm.runInContext('loadHomeNotes(); restoreSelectedOutfit(null);',context);
  assert.match(state.homeNotesError,/穿搭笔记暂时无法加载/);
  assert.equal(state.current,null,'a failed notebook request must not select a flat lay');
  failed=false;
  await vm.runInContext('loadHomeNotes();',context);
  assert.equal(state.homeNotesError,'');
  assert.equal(state.homeOutfits.length,4);
  console.log('Home notebook photos, stable selection, full-outfit payload and retry passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
