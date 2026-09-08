const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const code=fs.readFileSync('app/static/selfit-tryon/studio.js','utf8');
const fn=code.slice(code.indexOf('  async function confirmImport()'),code.indexOf('  function render()'));
(async()=>{
  let calls=0, fail=true, requested, page;
  const state={importSaving:false,importSelection:new Set(['top']),importItems:[{id:'top'},{id:'bottom'}],items:[],outfits:[]};
  const ctx={state,reference:false,importJob:{job_id:'draft'},render(){},notify(){},go:p=>page=p,
    sessionStorage:{removeItem(){}},normalizeItem:x=>({id:x.item_id}),normalizeOutfit:x=>x,
    uniqueItems:xs=>[...new Map(xs.map(x=>[x.id,x])).values()],
    api:async(url,options)=>{calls++;requested=JSON.parse(options.body);if(fail)throw Error('offline');return {result:{items:[{item_id:'top'}],outfits:[]}};}};
  vm.createContext(ctx);vm.runInContext(fn+';this.confirmImport=confirmImport;',ctx);
  await ctx.confirmImport();
  assert.equal(ctx.importJob.job_id,'draft','failed request retains job for idempotent retry');
  assert.equal(state.importSaving,false);
  assert.equal(state.items.length,0,'failed confirm must not invent wardrobe items');
  assert.deepEqual(requested.selected_item_ids,['top']);
  fail=false;await ctx.confirmImport();
  assert.deepEqual(state.items.map(x=>x.id),['top']);
  assert.equal(page,'closet');assert.equal(ctx.importJob,null);
  state.importSelection.clear();await ctx.confirmImport();assert.equal(calls,2,'empty selection does not submit');
  console.log('Selected-only request, failure recovery, committed-only wardrobe update: passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
