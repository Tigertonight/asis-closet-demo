const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const code=fs.readFileSync('app/static/selfit-tryon/studio.js','utf8');
const begin=code.slice(code.indexOf('  function beginMirrorGeneration('),code.indexOf('  async function generateNote('));
const poll=code.slice(code.indexOf('  async function poll('),code.indexOf('  async function importGarment('));
(async()=>{
 const state={page:'detail',photo:'current-photo',result:'old-result',styling:true};
 const target={id:'submitted-outfit'};let rendered=0,closed=0,scheduled=0;
 let job={job_id:'job-a',status:'running',outfit_id:target.id,original_image_path:'stored-original'};
 const ctx={state,pollTimer:null,$:s=>s==='#sheet'?{close(){closed++;}}:null,
  go:page=>state.page=page,render:()=>rendered++,api:async()=>job,lookup:()=>target,
  clearTimeout(){},setTimeout(){scheduled++;},sessionStorage:{removeItem(){}},
  failure:()=>{state.generating=null;},normalizeOutfit:x=>({id:x.outfit_id}),notify(){}};
 vm.createContext(ctx);vm.runInContext(begin+poll+';this.begin=beginMirrorGeneration;this.poll=poll;',ctx);
 ctx.begin(target,'submitted-photo');
 assert.equal(state.page,'mirror');assert.equal(state.result,'');assert.equal(state.styling,false);assert.equal(closed,1);
 state.photo='another-photo';state.current={id:'another-outfit'};
 assert.equal(state.generating.photo,'submitted-photo');assert.equal(state.generating.target,target);
 state.job={job_id:'job-a'};state.generating=null;
 await ctx.poll();assert.equal(state.generating.photo,'stored-original');assert.equal(state.generating.target,target);
 assert.equal(rendered,1);assert.equal(scheduled,1);
 job={...job,status:'completed',result:{outfit:{outfit_id:target.id},result:{image_path:'generated-image'}}};
 await ctx.poll();assert.equal(state.generating,null);assert.equal(state.result,'generated-image');assert.equal(state.current.id,target.id);
 assert.equal(state.resultOriginal,'stored-original');
 console.log('Inline generation: captured submission, resume, in-place completion passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
