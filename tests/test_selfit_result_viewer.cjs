const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const src=fs.readFileSync('app/static/selfit-tryon/studio.js','utf8');
const fn=src.slice(src.indexOf('  async function poll('),src.indexOf('  async function importGarment('));
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
 // A direct preset-result URL identifies the image even when today's random
 // notebook or saved model differs from the original submission.
 state.current={id:'another-random-note'};state.modelId='another-model';
 state.viewerJobId='job-a';state.job={job_id:'job-a'};state.result='';
 job.job_id='job-a';job.model_id='preset-model';job.result.generation_strategy='preset';
 await ctx.poll();
 assert.equal(state.result,job.result.result.image_path);
 assert.equal(state.current.id,'generated-outfit');assert.equal(state.modelId,'preset-model');
 // The same response cannot replace a model the user explicitly switched to
 // after leaving that viewer route.
 state.page='mirror';state.viewerJobId='';state.current={id:'new-choice'};state.modelId='new-model';state.result='';
 ctx.render=()=>{};
 await ctx.poll();assert.equal(state.current.id,'new-choice');assert.equal(state.result,'');
 console.log('Generation snapshot, original photo and viewer resume: passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
