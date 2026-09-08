const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const src=fs.readFileSync('app/static/selfit-tryon/studio.js','utf8');
const poll=src.slice(src.indexOf('  async function poll()'),src.indexOf('  async function importGarment('));
const go=src.slice(src.indexOf('  function go('),src.indexOf('  function categoryGroup('));
(async()=>{
 for(const page of ['inspiration','detail','profile-edit']){
 const viewed={id:'browsed-outfit'},notice={hidden:true};let closed=0,rendered=0;
 const state={page,current:viewed,photo:'browsing-photo',job:{job_id:'job-a'},generating:{},styling:false};
 const job={job_id:'job-a',status:'completed',original_image_path:'submitted-photo',outfit_id:'generated',result:{outfit:{outfit_id:'generated'},result:{image_path:'generated.png'}}};
 const ctx={state,pollTimer:null,clearTimeout(){},api:async()=>job,lookup:()=>null,normalizeOutfit:x=>({id:x.outfit_id}),
 sessionStorage:{removeItem(){}},$:s=>s==='#completionNotice'?notice:s==='#sheet'?{close(){closed++;}}:s==="#screen"?{scrollTop:0}:null,
 render(){rendered++;},URL,location:{href:'http://localhost/selfit/try-on?screen='+page},history:{pushState(){}},reference:false,
 notify(){},failure:e=>{throw Error(e);}};
 vm.createContext(ctx);vm.runInContext(poll+go+';this.poll=poll;this.go=go;',ctx);
 await ctx.poll();assert.equal(state.page,page);assert.equal(state.current,viewed);assert.equal(state.photo,'browsing-photo');
 assert.equal(closed,0);assert.equal(rendered,0);assert.equal(notice.hidden,false);
 ctx.go('mirror');assert.equal(state.current.id,'generated');assert.equal(state.result,'generated.png');
 assert.equal(state.resultOriginal,'submitted-photo');assert.equal(state.completedTryon,null);assert.equal(state.page,'mirror');
 }
 console.log('Background completion preserves browsing/editing and opens the correct submitted result on demand: passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
