const assert = require('node:assert/strict');
const {test} = require('node:test');
const fs = require('node:fs');
const vm = require('node:vm');
const source=fs.readFileSync('app/static/selfit-tryon/studio.js','utf8');
const slice=(a,b)=>source.slice(source.indexOf(a),source.indexOf(b));
const code=slice('  async function requireTryonAccess()', '  async function loadModels()')+
 slice('  async function generateNote()', '  async function waitForPresetResult(')+
 slice('  function failure(', '  async function poll(');
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};};
function harness({beta=false,kind='outfit',check,upgrade,api}={}) {
 const counts={photos:0,posts:0,polls:0},dialogs=[];
 const photoFile=new File(['original photo'],'my-photo.jpg',{type:'image/jpeg'});
 const target={id:'look-a',kind,items:[{id:'top'}]};
 const state={current:target,photo:'blob:my-photo',file:photoFile,modelId:'self',page:'mirror',selected:new Set(),job:null};
 const sheet={open:false,close(){this.open=false;}};
 let form,message;
 const user={user_id:'guest-same-account',beta_qualified:beta};
 const session={accessToken:'test-token',user};
 const context=vm.createContext({state,generationBusy:false,FormData,crypto:require('node:crypto').webcrypto,Date,Set,
  sessionStorage:{setItem(){}},render(){},notify(){},go(){},esc:x=>String(x),
  savedSession:session,refreshSession:async()=>{if(check)await check();return session;},
  authClient:{session,async upgradeInvite(value){if(upgrade)await upgrade(value);user.beta_qualified=true;}},
  acceptSession:value=>{context.savedSession=value;return value;},
  $:selector=>selector==='#sheet'?sheet:selector==='#tryonAccessForm'?form:message,
  modal:(title,html)=>{
   sheet.open=true;dialogs.push({title,html});message={textContent:''};form=null;
   if(html.includes('tryonAccessForm')) {
    const button={disabled:false,setAttribute(){},removeAttribute(){}},input={value:'TEST-ONLY'};
    form={querySelector:selector=>selector==='input'?input:button,addEventListener(_name,fn){this.submit=()=>fn({preventDefault(){}});}};
   }
  },
  photoFile:async()=>{counts.photos++;return photoFile;},
  beginMirrorGeneration:()=>{state.generating={target};state.job=null;sheet.close();},
  poll:async()=>{counts.polls++;},
  api:async(path,options)=>{counts.posts++;if(api)return api(path,options);return {job_id:'job-one',status:'pending'};},
  startTry:()=>vm.runInContext(kind==='note'?'generateNote()':'generate()',context),
 });
 vm.runInContext(code,context);
 return {state,user,counts,dialogs,sheet,get form(){return form;},get message(){return message;},run:expression=>vm.runInContext(expression,context)};
}
for(const kind of ['outfit','note']) test(`${kind}: guest unlocks in place and submits original selection exactly once`,async()=>{
 const h=harness({kind}),original=h.state.file,target=h.state.current;
 await h.run(kind==='note'?'generateNote()':'generate()');
 assert.equal(h.dialogs.at(-1).title,'解锁试穿');assert.equal(h.counts.photos,0);assert.equal(h.counts.posts,0);
 assert.equal(h.state.file,original);assert.equal(h.state.current,target);
 const form=h.form;
 await Promise.all([form.submit(),form.submit()]);
 assert.equal(h.counts.posts,1);assert.equal(h.counts.photos,1);assert.equal(h.counts.polls,1);
 assert.equal(h.user.user_id,'guest-same-account');assert.equal(h.state.file,original);assert.equal(h.state.current,target);
});
test('invalid invite keeps form and photo and does not submit generation',async()=>{
 const h=harness({upgrade:async()=>{throw Object.assign(Error('邀请码不正确'),{status:400});}});
 await h.run('generate()');const form=h.form;await form.submit();
 assert.equal(h.form,form);assert.equal(h.message.textContent,'邀请码不正确');assert.equal(h.counts.posts,0);
});
test('closing unlock while verifying cancels automatic generation',async()=>{
 const gate=deferred(),h=harness({upgrade:()=>gate.promise});
 await h.run('generate()');const pending=h.form.submit();await new Promise(r=>setImmediate(r));
 h.sheet.close();gate.resolve();await pending;
 assert.equal(h.counts.posts,0);assert.equal(h.state.file.name,'my-photo.jpg');
});
test('changing page while access is being checked cancels submission',async()=>{
 const gate=deferred(),h=harness({beta:true,check:()=>gate.promise});
 const pending=h.run('generate()');h.state.page='closet';gate.resolve();await pending;
 assert.equal(h.counts.photos,0);assert.equal(h.counts.posts,0);
});
test('expired authentication gives login recovery without replacing photo',async()=>{
 const h=harness({check:async()=>{throw Object.assign(Error('expired'),{status:401});}});
 await h.run('generate()');assert.equal(h.dialogs.at(-1).title,'登录已过期');
 assert(h.dialogs.at(-1).html.includes('target="_blank"'));assert(!h.dialogs.at(-1).html.includes('更换照片'));
 assert.equal(h.counts.posts,0);assert.equal(h.state.file.name,'my-photo.jpg');
});
test('server-side beta refusal still routes to unlock, and quota denial routes to waiting',async()=>{
 for(const status of [403,429]) {
  const h=harness({beta:true,api:async path=>{throw Object.assign(Error(status===429?'今日额度已用完':'内测名额有限'),{status,path});}});
  await h.run('generate()');assert.equal(h.dialogs.at(-1).title,status===403?'解锁试穿':'稍后再试');
  assert(!h.dialogs.at(-1).html.includes('更换照片'));assert.equal(h.counts.posts,1);
 }
});
test('job retry keeps the job and waits for unlock; success retries once',async()=>{
 const h=harness();h.state.job={job_id:'old-job',status:'failed'};
 await h.run('retryTryonJob()');assert.equal(h.counts.posts,0);assert.equal(h.state.job.job_id,'old-job');
 await h.form.submit();assert.equal(h.counts.posts,1);assert.equal(h.counts.photos,0);
});
test('API restores on 401 once, preserves request body, and never retries 403/429',async()=>{
 const end=source.indexOf('\n  function ',source.indexOf('  async function api('));
 const exact=source.slice(source.indexOf('  async function api('),end);
 for(const status of [401,403,429]) {
  const requests=[];let restored=0;
  const ctx=vm.createContext({AbortController,setTimeout,clearTimeout,Error,TypeError,
   savedSession:{accessToken:'old'},refreshSession:async()=>{restored++;ctx.savedSession={accessToken:'new'};},
   fetch:async(path,options)=>{requests.push(options);return {ok:requests.length>1,status:requests.length>1?200:status,json:async()=>({detail:'denied'}),headers:{get:()=>null}};},
  });
  vm.runInContext(exact,ctx);
  const promise=vm.runInContext("api('/selfit/try-on/jobs',{method:'POST',body:'original-body'})",ctx);
  if(status===401)await promise;else await assert.rejects(promise,e=>e.status===status);
  assert.equal(restored,status===401?1:0);assert.equal(requests.length,status===401?2:1);
  if(status===401){assert.equal(requests[1].body,'original-body');assert.equal(requests[1].headers.Authorization,'Bearer new');}
 }
});
