const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const src=fs.readFileSync('app/static/selfit-tryon/studio.js','utf8');
const code=src.slice(src.indexOf('  async function pollImport()'),src.indexOf('  function normalizeItem('));
function setup(open=false){
 const requests=[],events=[];
 const sheet={open,dataset:{importFlow:'true'},close(){this.open=false;events.push('close');}};
 const ctx={state:{page:'mirror',importSelection:new Set()},importEpoch:1,importJob:{job_id:'old'},importTimer:null,
 clearTimeout(){},setTimeout(){},$:s=>s==='#sheet'?sheet:null,
 api:()=>new Promise(resolve=>requests.push(resolve)),rememberImport(){},normalizeItem:x=>({id:x.item_id}),
 render(){events.push('render');},go:p=>events.push(p),notify:m=>events.push(m),importFailure:m=>events.push(m)};
 vm.createContext(ctx);vm.runInContext(code,ctx);return {ctx,requests,events};
}
const ready={job_id:'old',status:'awaiting_confirmation',result:{items:[{item_id:'top'}]}};
(async()=>{
 const background=setup();const bg=background.ctx.pollImport();background.requests[0](ready);await bg;
 assert.equal(background.ctx.state.importItems[0].id,'top');
 assert(!background.events.includes('import-review'),'background completion must not navigate');
 assert(!background.events.includes('close'),'must not close unrelated UI');
 const foreground=setup(true);const fg=foreground.ctx.pollImport();foreground.requests[0](ready);await fg;
 assert(foreground.events.includes('import-review'));
 const stale=setup(true);const old=stale.ctx.pollImport();stale.ctx.importEpoch++;stale.ctx.importJob={job_id:'new'};
 stale.requests[0](ready);await old;
 assert.equal(stale.ctx.importJob.job_id,'new');assert.equal(stale.events.length,0);
 console.log('Import polling: background, foreground and superseded uploads passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
