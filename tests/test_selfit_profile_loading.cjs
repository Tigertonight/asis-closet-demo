const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {test} = require('node:test');
const code = fs.readFileSync('app/static/selfit-tryon/studio.js', 'utf8');
const slice = (a, b) => code.slice(code.indexOf(a), code.indexOf(b));
const deferred = () => { let resolve, reject; const promise = new Promise((r,j) => {resolve=r;reject=j;}); return {promise,resolve,reject}; };
const flush = () => new Promise(resolve => setImmediate(resolve));
const profileData = () => ({tested:true,revision:1,manual:{skin:'中性自然肤'},manualOverrides:{},
  photos:{face:'/photos/face',body:'/photos/body'},
  report:{reportId:'report-1',typeId:'flou',title:'造梦浪漫',heroImage:{src:'/hero.png'}},
  suit:{features:[{key:'skin',value:'中性自然肤'}]}});
const photoResponse = value => ({ok:true,status:200,blob:async()=>new Blob([value],{type:'image/webp'})});
function harness(overrides={}) {
  const calls=[], photos=[], renders=[], updates=[], blobs=[];
  const state={page:'profile',profile:null,profilePhotos:{},profileLoading:false,profileError:'',
    profilePhotoDraft:{},profileManualChanges:{},uploadURLs:[]};
  let context;
  const slots=Object.fromEntries(['face','body'].map(kind=>[kind,{
    dataset:{editable:'false'},set outerHTML(html){updates.push({kind,html});}
  }]));
  context=vm.createContext({state,reference:false,params:new URLSearchParams(),
    A:'/assets/',savedSession:{accessToken:'test-only',user:{user_id:'guest_test'}},
    URL:{createObjectURL:blob=>{blobs.push(blob);return `blob:test-${blobs.length}`;}},
    image:(src,alt='')=>`<img src="${src}" alt="${alt}">`,esc:String,
    document:{querySelectorAll:selector=>[slots[selector.match(/="(face|body)"/)[1]]]},
    render:()=>renders.push(vm.runInContext('profile()',context)),
    notify(){},go:page=>state.page=page,
    api:async(url,options)=>{calls.push({url,options});return overrides.api ? overrides.api(url,options) : {profile:profileData()};},
    fetch:async(url,options)=>{photos.push({url,options});return overrides.photo ? overrides.photo(url,options) : photoResponse(url);},
    uploadProfilePhoto:async()=>{},
  });
  vm.runInContext(slice('  function profileHeader(', '  async function uploadProfilePhoto(')+
    slice('  async function saveProfile()', '  function restoreTryonRecord('),context);
  return {state,calls,photos,renders,updates,blobs,run:expression=>vm.runInContext(expression,context)};
}

test('profile and report render before either photo; photos start together and update independently', async()=>{
  const face=deferred(),body=deferred();
  const h=harness({photo:url=>url.endsWith('face') ? face.promise : body.promise});
  await h.run('loadProfile()');
  assert.equal(h.state.profileLoading,false);
  assert.deepEqual(h.photos.map(x=>x.url),['/photos/face','/photos/body']);
  assert(h.photos.every(x=>x.options.headers.Authorization==='Bearer test-only'));
  assert.equal(h.state.profileSuit.features[0].value,'中性自然肤');
  const html=h.renders.at(-1);
  assert.match(html,/查看我的风格报告/);
  assert.match(html,/身体特征分析/);
  assert.match(html,/照片加载中/);
  assert.doesNotMatch(html,/正在整理你的档案|src="\/photos\//);
  const renderCount=h.renders.length;
  face.resolve(photoResponse('face'));await flush();
  assert.equal(h.state.profile.photos.face,'blob:test-1');
  assert.equal(h.state.profilePhotos.body.loading,true);
  assert.equal(h.renders.length,renderCount,'photo completion does not rerender the screen');
  assert.equal(h.updates.at(-1).kind,'face');
  body.resolve(photoResponse('body'));await flush();
  assert.equal(h.state.profile.photos.body,'blob:test-2');
  assert.equal(h.renders.length,renderCount);
});

test('one failed photo leaves the profile usable and retries only that photo, once', async()=>{
  const retry=deferred();let faceRequests=0;
  const h=harness({photo:url=>url.endsWith('face') ? (++faceRequests===1 ? Promise.reject(Error('offline')) : retry.promise) : photoResponse('body')});
  await h.run('loadProfile()');await flush();
  assert.equal(h.state.profileError,'');
  assert.equal(h.state.profilePhotos.face.error,true);
  assert.equal(h.state.profilePhotos.body.error,false);
  assert.match(h.run("profilePhoto('face')"),/重新加载正面照/);
  assert.match(h.run('profile()'),/查看我的风格报告/);
  const pending=h.run("loadProfilePhoto('face')");
  await h.run("loadProfilePhoto('face')");
  assert.equal(faceRequests,2);
  assert.equal(h.calls.length,1);
  assert.equal(h.photos.filter(x=>x.url.endsWith('body')).length,1);
  retry.resolve(photoResponse('recovered'));await pending;
  assert.equal(h.state.profilePhotos.face.error,false);
  assert.match(h.run("profilePhoto('face')"),/更换正面照/);
});

test('absent photos are upload slots, not errors or unauthorized image requests',async()=>{
  const h=harness({photo:async url=>({ok:url.endsWith('face'),status:url.endsWith('face') ? 204 : 404})});
  await h.run('loadProfile()');await flush();
  for(const kind of ['face','body']) {
    assert.equal(h.state.profile.photos[kind],null);
    assert.equal(h.state.profilePhotos[kind].error,false);
    assert.match(h.run(`profilePhoto('${kind}')`),/还未上传/);
  }
  const empty=harness({api:async()=>({profile:{...profileData(),photos:{}}})});
  await empty.run('loadProfile()');
  assert.equal(empty.photos.length,0);
});

test('failed profile data remains retryable; concurrent entries share the request',async()=>{
  const gate=deferred();let tries=0;
  const h=harness({api:async()=>++tries===1 ? gate.promise : {profile:profileData()}});
  const first=h.run('loadProfile()');await h.run('loadProfile()');
  assert.equal(h.calls.length,1);
  gate.reject(Error('档案暂时无法加载'));await first;
  assert.equal(h.state.profileLoading,false);
  assert.match(h.renders.at(-1),/重新加载/);
  assert.equal(h.photos.length,0);
  await h.run('loadProfile(true)');await flush();
  assert.equal(h.state.profileError,'');
  assert.match(h.renders.at(-1),/查看我的风格报告/);
});

test('late old photos cannot overwrite a refreshed profile or allocate unused blob URLs',async()=>{
  const oldFace=deferred(),oldBody=deferred();let requests=0;
  const h=harness({photo:url=>++requests<=2 ? (url.endsWith('face') ? oldFace.promise : oldBody.promise) : photoResponse('new')});
  await h.run('loadProfile()');
  await h.run('loadProfile(true)');await flush();
  const current={...h.state.profile.photos};
  oldFace.resolve(photoResponse('old face'));oldBody.resolve(photoResponse('old body'));await flush();
  assert.deepEqual({...h.state.profile.photos},current);
  assert.equal(h.blobs.length,2);
});

test('late photo completion preserves manual edits and does not navigate or rerender after leaving',async()=>{
  const face=deferred(),body=deferred();
  const h=harness({photo:url=>url.endsWith('face') ? face.promise : body.promise});
  await h.run('loadProfile()');
  h.state.profile={...h.state.profile,manual:{skin:'暖白肤'}};
  h.state.page='profile-edit';h.state.profileFeatureValue='圆脸';h.state.profileFeatureTouched=true;
  const count=h.renders.length;
  face.resolve(photoResponse('face'));await flush();
  assert.equal(h.state.profileFeatureValue,'圆脸');
  assert.equal(h.state.profileFeatureTouched,true);
  assert.equal(h.state.profile.manual.skin,'暖白肤');
  assert.equal(h.state.profile.photos.face,'blob:test-1');
  assert.equal(h.renders.length,count);
  h.state.page='mirror';const updates=h.updates.length;
  body.resolve(photoResponse('body'));await flush();
  assert.equal(h.state.page,'mirror');assert.equal(h.updates.length,updates);
  await h.run('loadProfile()');
  assert.equal(h.calls.length,1);assert.equal(h.photos.length,2);
});

test('saving a new photo invalidates its older pending preview request',async()=>{
  const oldFace=deferred();
  const h=harness({photo:url=>url.endsWith('face') ? oldFace.promise : photoResponse('body')});
  await h.run('loadProfile()');await flush();
  h.state.profilePhotoDraft={face:{file:new Blob(['new upload']),url:'blob:replacement'}};
  await h.run('saveProfile()');
  oldFace.resolve(photoResponse('old face'));await flush();
  assert.equal(h.state.profile.photos.face,'blob:replacement');
  assert.equal(h.state.profilePhotos.face,null);
});
