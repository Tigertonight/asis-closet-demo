const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');
const source = fs.readFileSync(path.resolve(__dirname, '../app/static/selfit/selfit.js'), 'utf8');

function harness() {
  const events = {}, nodes = {}, saved = [];
  const node = key => nodes[key] ||= {dataset:{gender:key}, disabled:false, attrs:{},
    classList:{toggle(){}}, scrollTo(){}, setAttribute(k,v){this.attrs[k]=v;}, addEventListener(k,v){events[key+':'+k]=v;}};
  const choices = [node('female'),node('male')];
  const inputs = [node('face'),node('body'),node('sampleFace'),node('sampleBody')];
  const state = {screen:'suit',gender:null,genderBusy:false,genderEditing:false,revision:1,photoStatus:{face:'empty',body:'empty'}};
  const context = {state, document:{querySelector:node, querySelectorAll:selector=>selector==='[data-gender]'?choices:inputs},
    ensureSession:async ()=>'test',renderSuit:async()=>{},runButtonAction:(_,action)=>action(),
    updateOnboardingNav(){},onboardingBack:node('back'),suitRenderSeq:0,
    api:{saveGender:async (_,gender)=>{saved.push(gender);return {session:{revision:2}};}}};
  vm.createContext(context);
  vm.runInContext(source.slice(source.indexOf('  const choosingGender ='), source.indexOf('  const uploadPlaceholders ='))+
    '\nthis.sync=syncGenderControls;this.ready=genderReady;this.reselect=openGenderSelection;',context);
  return {context,state,node,choices,inputs,saved,choose:gender=>events[gender+':click']()};
}

test('no default gender; uploads, examples and next remain disabled',()=>{
  const h=harness();h.context.sync();
  assert.equal(h.context.ready(),false);
  assert.ok(h.inputs.every(n=>n.disabled));
  assert.ok(h.choices.every(n=>n.attrs['aria-pressed']==='false'));
  assert.equal(h.node('#suitNext').disabled,true);
  assert.equal(h.node('.gender-card').hidden,false);
  assert.equal(h.node('[data-suit-photos]').hidden,true);
  assert.equal(h.node('#suitTitle').textContent,'选择你的性别');
});
for(const gender of ['female','male']) test(`${gender}: only successful save enables uploads`,async()=>{
  const h=harness(); await h.choose(gender);
  assert.equal(h.state.gender,gender);assert.deepEqual(h.saved,[gender]);
  assert.ok(h.inputs.every(n=>!n.disabled));
  assert.equal(h.node('.gender-card').hidden,true);
  assert.equal(h.node('[data-suit-photos]').hidden,false);
  assert.equal(h.node('#suitNext').disabled,true);
  h.state.photoStatus={face:'valid',body:'valid'};h.context.sync();
  assert.equal(h.node('#suitNext').disabled,false);
});
test('failed save does not unlock photos or preselect gender',async()=>{
  const h=harness();h.context.api.saveGender=async()=>{throw new Error('offline');};
  await assert.rejects(h.choose('male'),/offline/);
  assert.equal(h.state.gender,null);assert.equal(h.state.genderBusy,false);
  assert.ok(h.inputs.every(n=>n.disabled));
  assert.equal(h.node('.gender-card').hidden,false);
  assert.equal(h.node('[data-suit-photos]').hidden,true);
});
test('pending save locks uploads and blocks a second selection',async()=>{
  const h=harness();let finish;
  h.context.api.saveGender=()=>new Promise(resolve=>{finish=resolve;});
  const pending=h.choose('female');await Promise.resolve();
  assert.equal(h.state.genderBusy,true);assert.ok(h.inputs.every(n=>n.disabled));
  await h.choose('male');finish({session:{revision:2}});await pending;
  assert.equal(h.state.gender,'female');
});
test('restored choice is visible; uploading does not infer or replace gender',()=>{
  const h=harness();h.state.gender='male';h.state.photoStatus.face='checking';h.context.sync();
  assert.equal(h.node('male').attrs['aria-pressed'],'true');
  assert.ok(h.choices.every(n=>n.disabled));
  h.state.photoStatus={face:'valid',body:'valid'};h.context.sync();
  assert.equal(h.state.gender,'male');assert.ok(h.choices.every(n=>!n.disabled));
});
test('back reopens gender selection without deleting photos; same or new choice returns to photos',async()=>{
  for(const selection of ['male','female']) {
    const h=harness();h.state.gender='male';h.state.photoStatus={face:'valid',body:'valid'};
    h.context.reselect();
    assert.equal(h.node('.gender-card').hidden,false);
    assert.equal(h.node('[data-suit-photos]').hidden,true);
    assert.equal(h.node('male').attrs['aria-pressed'],'true');
    assert.equal(h.node('#suitNext').disabled,true);
    assert.equal(h.context.suitRenderSeq,1);
    await h.choose(selection);
    assert.equal(h.state.gender,selection);
    assert.equal(h.node('.gender-card').hidden,true);
    assert.equal(h.node('[data-suit-photos]').hidden,false);
    assert.deepEqual(h.state.photoStatus,{face:'valid',body:'valid'});
  }
});
test('failed reselection preserves the previous saved value but stays on the selection page',async()=>{
  const h=harness();h.state.gender='male';h.context.reselect();
  h.context.api.saveGender=async()=>{throw new Error('offline');};
  await assert.rejects(h.choose('female'),/offline/);
  assert.equal(h.state.gender,'male');
  assert.equal(h.node('.gender-card').hidden,false);
  assert.equal(h.node('[data-suit-photos]').hidden,true);
});
test('back is blocked during save and the upload page back target is gender selection',()=>{
  const h=harness();h.state.genderBusy=true;h.context.sync();h.context.reselect();
  assert.equal(h.node('back').disabled,true);
  assert.equal(h.state.genderEditing,false);
  assert.match(source,/back: choosingGender\(\) \? 'like' : 'suit-gender'/);
  assert.match(source,/back.dataset.back === 'suit-gender'\) \{ openGenderSelection\(\); return; \}/);
});
test('removed guidance is absent and photos start hidden in HTML before scripts load',()=>{
  const html=fs.readFileSync(path.resolve(__dirname,'../app/static/selfit/index.html'),'utf8');
  for(const copy of ['先认识一下你','让后面的穿搭参考，更贴近你','先选择性别，再上传照片或使用示例。','性别已记下，风格由你定义。']) {
    assert.equal(html.includes(copy),false);assert.equal(source.includes(copy),false);
  }
  assert.match(html,/<div data-suit-photos hidden>/);
});
test('new sessions request fresh-photo mode and restore the persisted gender',()=>{
  assert.match(source,/onboardingMode: retestEntry \? 'retest' : 'new'/);
  assert.match(source,/state.gender = restored.session.gender \|\| null/);
  assert.match(source,/state.gender = null;[\s\S]*?resetOnboardingPhotos\(\)/);
});
test('gender HTML, interaction script and API load the same cache-busting release',()=>{
  const html=fs.readFileSync(path.resolve(__dirname,'../app/static/selfit/index.html'),'utf8');
  const release=file=>html.match(new RegExp(file.replaceAll('.', '\\.')+'\\?v=([^" ]+)'))?.[1];
  assert.equal(release('selfit.js'),release('selfit.css'));
  assert.equal(release('selfit-api.js'),release('selfit.css'));
  assert.notEqual(release('selfit.js'),'20260910-gender1');
});
test('a render error during click does not leave both choices permanently locked',async()=>{
  const h=harness();const original=h.context.document.querySelector;let fail=true;
  h.context.document.querySelector=selector=>{
    if(selector==='#suitTitle' && fail){fail=false;return null;}
    return original(selector);
  };
  await assert.rejects(h.choose('female'),/null/);
  assert.equal(h.state.genderBusy,false);
  assert.ok(h.choices.every(n=>!n.disabled));
  await h.choose('female');assert.equal(h.node('[data-suit-photos]').hidden,false);
});
test('mock API persists gender and forwards it to the report builder',async()=>{
  const apiSource=fs.readFileSync(path.resolve(__dirname,'../app/static/selfit/selfit-api.js'),'utf8');
  const context={window:{},setTimeout:fn=>{fn();return 1;},clearTimeout(){}};
  vm.createContext(context);vm.runInContext(apiSource,context);
  let input;
  const api=context.window.SelfitApi.createClient({mode:'mock',buildMockReport:session=>{input=session;return {};}});
  const {session}=await api.createSession({onboardingMode:'new'});
  await assert.rejects(api.checkPhoto(session.sessionId,'face',{name:'example.jpg'}),/选择性别/);
  await assert.rejects(api.createReportJob(session.sessionId),/选择性别/);
  await api.saveGender(session.sessionId,'male');
  await api.checkPhoto(session.sessionId,'face',{name:'example.jpg'});
  assert.equal((await api.getSession(session.sessionId)).session.gender,'male');
  await api.createReportJob(session.sessionId);assert.equal(input.gender,'male');
});
