const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const code=fs.readFileSync('app/static/selfit-tryon/studio.js','utf8');
const poll=code.slice(code.indexOf('  async function poll('),code.indexOf('  async function importGarment('));
(async()=>{
 const state={page:'result-viewer',job:{job_id:'note-job'},current:{id:'other-outfit'},photo:'different-person'};
 const note={id:'note:mute:1',title:'stored note',image_url:'note.jpg',width:1080,height:1440};
 let job={job_id:'note-job',kind:'inspiration',note,original_image_path:'original.png',status:'processing'};
 const ctx={state,pollTimer:null,clearTimeout(){},setTimeout(){},api:async()=>job,lookup:()=>null,render(){},
   $:s=>s==='#sheet'?{close(){}}:null,sessionStorage:{removeItem(){}},go:p=>state.page=p,notify(){},failure:e=>{throw Error(e);}};
 vm.createContext(ctx);vm.runInContext(poll+';this.poll=poll;',ctx);
 await ctx.poll();assert.equal(state.generating.target.kind,'note');assert.equal(state.generating.photo,'original.png');
 job={...job,status:'completed',result:{note,result:{image_path:'result.png'}}};
 await ctx.poll();assert.equal(state.page,'result-viewer');assert.equal(state.current.id,note.id);
 assert.equal(state.current.kind,'note');assert.equal(state.current.items.length,0);assert.equal(state.resultOriginal,'original.png');
 assert.equal(state.result,'result.png');assert.equal(state.generating,null);
 console.log('Notebook job resumes as a note, preserves original, and opens result without fabricated garments: passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
