const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const src=fs.readFileSync('app/static/selfit-tryon/studio.js','utf8');
const fn=src.slice(src.indexOf('  async function poll()'),src.indexOf('  async function importGarment('));
(async()=>{
 const state={page:'result-viewer',job:{job_id:'job-a'},current:{id:'browsed-outfit'},photo:'newly-selected-model',jobPhoto:'old-local-photo'};
 const job={status:'completed',outfit_id:'generated-outfit',original_image_path:'/user-assets/tryon/job-inputs/original.png',result:{outfit:{outfit_id:'generated-outfit'},result:{image_path:'/user-assets/tryon/result.png'}}};
 let page;
 const ctx={state,clearTimeout(){},pollTimer:null,api:async()=>job,sessionStorage:{removeItem(){}},
   $:s=>s==='#sheet'?{close(){}}:null,lookup:()=>{throw Error('must use generated snapshot');},
   normalizeOutfit:x=>({id:x.outfit_id}),go:p=>{page=p;},notify(){},failure:msg=>{throw Error(msg)}};
 vm.createContext(ctx);vm.runInContext(fn+';this.poll=poll;',ctx);await ctx.poll();
 assert.equal(state.current.id,'generated-outfit');assert.equal(state.resultOriginal,job.original_image_path);
 assert.equal(state.photo,job.original_image_path);assert.equal(page,'result-viewer');
 console.log('Generation snapshot, original photo and viewer resume: passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
