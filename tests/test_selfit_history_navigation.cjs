const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('app/static/selfit-tryon/studio.js','utf8');
const code=source.slice(source.indexOf('  function restoreTryonRecord('),source.indexOf('  async function tryonHistory('));
(async()=>{
 const state={page:'result-viewer',result:'old.png',viewerPhoto:false};const requests=[];
 const ctx={state,lookup:()=>null,render(){},api:()=>new Promise((resolve,reject)=>requests.push({resolve,reject}))};
 vm.createContext(ctx);vm.runInContext(code+';this.open=restoreHistoryRoute;',ctx);
 const a=ctx.open('a');assert.equal(state.viewerLoading,true);
 const b=ctx.open('b');requests[1].resolve({records:[{record_id:'b',image_path:'b.png'}]});await b;
 requests[0].resolve({records:[{record_id:'a',image_path:'a.png'}]});await a;
 assert.equal(state.result,'b.png');assert.equal(state.viewRecordId,'b');assert.equal(state.viewerLoading,false);
 const gone=ctx.open('deleted');requests[2].resolve({records:[]});await gone;
 assert.equal(state.result,'');assert(state.viewerError.includes('已不存在'));
 const retry=ctx.open('b');requests[3].resolve({records:[{record_id:'b',image_path:'b.png'}]});await retry;
 assert.equal(state.result,'b.png');assert.equal(state.viewerError,'');
 const late=ctx.open('a');state.page='mirror';requests[4].resolve({records:[{record_id:'a',image_path:'a.png'}]});await late;
 assert.equal(state.result,'b.png');
 console.log('History route identity, request ordering, missing record and retry: passed');
})().catch(e=>{console.error(e);process.exitCode=1});
