const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('app/static/selfit-tryon/studio.js','utf8');
const fn=source.slice(source.indexOf('  async function poll()'),source.indexOf('  async function importGarment('));
(async()=>{
 const requests=[];let failures=0;const notice={hidden:true};
 const state={page:'result-viewer',job:{job_id:'a'},result:'visible.png',viewerPhoto:false,viewRecordId:''};
 const ctx={state,pollTimer:null,clearTimeout(){},setTimeout(){},api:()=>new Promise((resolve,reject)=>requests.push({resolve,reject})),lookup:()=>null,normalizeOutfit:o=>({id:o.outfit_id}),$:s=>s==='#completionNotice'?notice:null,sessionStorage:{removeItem(){}},failure(){failures++},go(){throw Error('must not navigate')},notify(){}};
 vm.createContext(ctx);vm.runInContext(fn+';this.poll=poll;',ctx);
 const stale=ctx.poll();state.job={job_id:'b'};requests[0].resolve({job_id:'a',status:'completed',result:{result:{image_path:'a.png'}}});await stale;
 assert.equal(state.job.job_id,'b');assert.equal(state.result,'visible.png');
 const error=ctx.poll();state.job={job_id:'c'};requests[1].reject(Error('old network failure'));await error;assert.equal(failures,0);
 state.viewerPhoto=true;const current=ctx.poll();requests[2].resolve({job_id:'c',status:'completed',outfit_id:'outfit-c',result:{result:{image_path:'c.png'}}});await current;
 assert.equal(state.result,'visible.png');assert.equal(state.completedTryon.src,'c.png');assert.equal(notice.hidden,false);
 console.log('Stale job responses ignored and photo preview preserved on completion: passed');
})().catch(e=>{console.error(e);process.exitCode=1});
