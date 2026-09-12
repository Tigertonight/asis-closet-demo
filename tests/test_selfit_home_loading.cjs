const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {test} = require('node:test');
const code = fs.readFileSync('app/static/selfit-tryon/studio.js', 'utf8');
const slice = (a, b) => code.slice(code.indexOf(a), code.indexOf(b));
const loaders = slice('  async function loadModels()', '  function modelSheet(') +
  slice('  async function loadHomeNotes()', '  $("#sheet").addEventListener("click"');
const deferred = () => { let resolve; const promise = new Promise(r => resolve = r); return {promise, resolve}; };
const flush = () => new Promise(resolve => setImmediate(resolve));
function harness(query = '?screen=mirror', overrides = {}) {
  const calls = [], preloads = [], renders = [], photos = [];
  const state = {page:new URLSearchParams(query).get('screen') || 'mirror', source:query.includes('from=report') ? 'report' : 'inspiration',
    items:[], outfits:[], homeOutfits:[], reportOutfits:[], feed:[], topics:[], savedNotes:[], modelLibrary:[],
    selected:new Set(), photo:'', personalPhoto:'', file:null, personalFile:null, uploadURLs:[], loading:true,
    wardrobeLoaded:false, feedLoaded:false};
  const outfit = {outfit_id:'look-1',items:[{item_id:'top-1'}],report_note:{title:'第一套',image_url:'/note.jpg'}};
  const location = {search:query,href:'http://localhost'+query,origin:'http://localhost'};
  const normalizeOutfit = row => ({id:row.outfit_id,items:(row.items || []).map(x=>({id:x.item_id})),saved:!!row.favorite});
  const context = vm.createContext({state, location, params:new URLSearchParams(query), reference:false,
    URL, URLSearchParams, Set, Promise, Date, File, Blob, FormData, AbortController, setTimeout, clearTimeout,
    savedSession:{accessToken:'test-only'}, visitorReady:null,
    window:{SelfitAuth:{createClient:()=>({clear(){}})}},
    ensureVisitorSession:async()=>{}, pendingImport:()=>null, poll(){}, notify(){},
    history:{replaceState(_a,_b,url){location.href=url.href;location.search=url.search;}},
    sessionStorage:{getItem:()=>null,setItem(){}},
    normalizeOutfit, normalizeItem:x=>({id:x.item_id}),
    uniqueItems:rows=>[...new Map(rows.map(x=>[x.id,x])).values()],
    preloadMirrorImage:src=>preloads.push(src),
    render:()=>{vm.runInContext('loadPageData()', context);renders.push({page:state.page,loading:state.loading,wardrobe:state.wardrobeLoading,library:state.libraryLoading});},
    fetch:async(url,options)=>{photos.push(url);return overrides.photo ? overrides.photo(url, options) : {ok:true,status:204};},
    api:async(url,options)=>{
      calls.push(url);
      if(overrides.api) {const result=overrides.api(url,options);if(result!==undefined)return result;}
      if(url==='/closet/preferences')return {current_model_id:'fixed'};
      if(url==='/selfit/try-on/models')return {items:[{id:'fixed',gender:'female',image_url:'/fixed.png'}]};
      if(url.includes('/report-outfits'))return {outfits:[outfit],mode:'live'};
      if(url==='/selfit/try-on/wardrobe')return {items:[{item_id:'top-1'}],outfits:[{...outfit,outfit_id:'my-copy',favorite:true}]};
      if(url.endsWith('/inspiration-notes'))return {notes:[],saved_notes:[{id:'note:saved',title:'收藏笔记',favorite:true}]};
      if(url.endsWith('/inspiration-topics'))return {topics:[{id:'topic-1',outfits:[outfit]}]};
      if(url==='/closet/recommendations/outfits')return {outfits:[]};
      if(url.startsWith('/closet/outfits/'))return {...outfit,outfit_id:url.split('/').at(-1)};
      throw Error('Unexpected request: '+url);
    },
  });
  vm.runInContext(loaders, context);
  return {state,calls,preloads,renders,photos,run:expression=>vm.runInContext(expression,context)};
}

test('first mirror needs only preferences, models and its four notes; image starts before notes finish', async()=>{
  const notes=deferred();
  const h=harness('?screen=mirror',{api:url=>url.includes('/report-outfits/home') ? notes.promise : undefined});
  const ready=h.run('load()');await flush();
  assert.deepEqual(h.preloads,['/fixed.png']);
  assert.equal(h.state.loading,true);
  assert.equal(h.photos.length,0,'fixed model must not download the unused personal photo');
  notes.resolve({outfits:[{outfit_id:'picked',items:[],report_note:{title:'笔记',image_url:'/note.jpg'}}]});
  await ready;
  assert.equal(h.state.loading,false);
  assert.equal(h.state.current.id,'picked');
  assert.deepEqual(h.calls.sort(),['/closet/preferences','/selfit/try-on/models','/selfit/try-on/report-outfits/home?'].sort());
});

test('report entry fetches its ordered outfits directly, no random or full library fallback',async()=>{
  const h=harness('?screen=mirror&from=report&report_notes=one,two&persona=void');
  await h.run('load()');
  assert.equal(h.state.current.id,'look-1');
  assert(!h.calls.some(url=>/random|wardrobe|inspiration-|recommendations/.test(url)));
  const broken=harness('?screen=mirror&from=report&report_notes=one',{api:url=>url.includes('/report-outfits?') ? Promise.reject(Error('报告素材已更新')) : undefined});
  await broken.run('load()');
  assert.equal(broken.state.error,'报告素材已更新');
  assert.equal(broken.state.current,null);
  assert.equal(broken.state.loading,false);
});

test('personal photo remains the selected generation input',async()=>{
  const h=harness('?screen=mirror',{api:url=>url==='/closet/preferences' ? {current_model_id:'self'} : undefined,
    photo:async()=>({ok:true,status:200,blob:async()=>new Blob(['personal-photo'],{type:'image/jpeg'})})});
  await h.run('load()');
  assert.equal(h.state.modelId,'self');
  assert.equal(h.state.photo,h.state.personalPhoto);
  assert.equal(await h.state.file.text(),'personal-photo');
  h.state.uploadURLs.forEach(URL.revokeObjectURL);
});

test('wardrobe is lazy, deduplicated, and cannot block or replace the mirror on return',async()=>{
  const gate=deferred();
  const h=harness('?screen=mirror',{api:url=>url.endsWith('/wardrobe') ? gate.promise : undefined});
  await h.run('load()');
  const original=h.state.current;
  h.state.page='closet';h.run('loadPageData()');h.run('loadPageData()');
  assert.equal(h.state.wardrobeLoading,true);
  assert.equal(h.calls.filter(url=>url.endsWith('/wardrobe')).length,1);
  assert(!h.calls.some(url=>url.includes('inspiration-topics') || url.includes('recommendations')));
  h.state.page='mirror';h.run('loadPageData()');
  assert.equal(h.state.loading,false);
  const waiting=h.run('loadWardrobe()');
  gate.resolve({items:[{item_id:'shirt'}],outfits:[]});await waiting;
  assert.equal(h.state.current,original);
  assert.equal(h.state.photo,'/fixed.png');
  assert.equal(h.state.savedNotes[0].id,'note:saved');
  assert.equal(h.state.items[0].id,'shirt');
});

test('library loads on entry with favorite state, shares requests and recovers from failure',async()=>{
  let failed=true;
  const h=harness('?screen=mirror',{api:url=>failed && url.endsWith('/inspiration-topics') ? Promise.reject(Error('offline')) : undefined});
  await h.run('load()');h.state.page='inspiration';
  h.run('loadPageData()');h.run('loadPageData()');
  await h.run('loadLibrary()');
  assert.equal(h.state.libraryLoading,false);
  assert(h.state.topicsError);
  assert.equal(h.calls.filter(url=>url.endsWith('/inspiration-notes')).length,1,'wardrobe and feed share the in-flight notes request');
  failed=false;
  await h.run('load()');await h.run('loadLibrary()');
  assert.equal(h.state.topicsError,'');
  assert.equal(h.state.topics[0].entries[0].saved,true);
  assert.equal(h.state.topics[0].entries[0].personalId,'my-copy');
  assert.equal(h.state.page,'inspiration');
});

test('direct closet and topic routes fetch their data; selected outfit survives reload',async()=>{
  const closet=harness('?screen=closet&outfit=own-look');
  await closet.run('load()');await closet.run('loadWardrobe()');
  assert.equal(closet.state.current.id,'own-look');
  assert.equal(closet.state.wardrobeLoading,false);
  const topic=harness('?screen=topic&topic=topic-1&outfit=look-1');
  await topic.run('load()');
  assert.equal(topic.state.topics.length,1);
  assert.equal(topic.state.current.id,'look-1');
  assert.equal(topic.state.libraryLoading,false);
});

test('leaving report mode lazily fills the normal strip without replacing the chosen outfit',async()=>{
  const h=harness('?screen=mirror&from=report&report_notes=one');
  await h.run('load()');
  const chosen={id:'chosen-from-library',items:[]};
  h.state.current=chosen;h.state.source='inspiration';
  h.run('loadPageData()');await h.run('ensureHomeNotes()');
  assert.equal(h.state.current,chosen);
  assert.equal(h.state.homeOutfits.length,1);
  assert.equal(h.calls.filter(url=>url.includes('/report-outfits/home')).length,1);
  h.run('loadPageData()');
  assert.equal(h.calls.filter(url=>url.includes('/report-outfits/home')).length,1);
});

test('opening model chooser later reads latest own photo, not the legacy preference image',async()=>{
  const h=harness('?screen=mirror',{api:url=>url==='/closet/preferences' ? {current_model_id:'fixed',self_model_path:'/old-photo.jpg'} : undefined,
    photo:async()=>({ok:true,status:200,blob:async()=>new Blob(['latest-own-photo'],{type:'image/jpeg'})})});
  await h.run('load()');
  assert.equal(h.photos.length,0);
  assert.equal(h.state.photo,'/fixed.png');
  await h.run('loadPhoto()');
  assert.equal(await h.state.personalFile.text(),'latest-own-photo');
  assert.equal(h.state.photo,'/fixed.png','loading the optional own photo must not switch the current model');
  h.state.uploadURLs.forEach(URL.revokeObjectURL);
});

const genderCatalog = [
  {id:'fixed',gender:'female',image_url:'/female.png'},
  {id:'male_old',gender:'male',image_url:'/male-old.png'},
  {id:'male_standard_1',gender:'male',image_url:'/api/v1/material-assets/male/content',default_for_gender:true},
];
test('switching back to female replaces a previously saved male model',async()=>{
  const h=harness('?screen=mirror',{api:url=>url==='/closet/preferences' ? {gender:'female',current_model_id:'male_standard_1'} :
    url==='/selfit/try-on/models' ? {items:genderCatalog} : undefined});
  await h.run('load()');
  assert.equal(h.state.modelId,'fixed');
  assert(h.state.modelLibrary.every(row=>row.gender==='female'));
});
for (const query of ['?screen=mirror','?screen=mirror&from=onboarding']) {
  test('male account replaces legacy female default with the supplied male model: '+query,async()=>{
    const h=harness(query,{api:url=>url==='/closet/preferences' ? {current_model_id:'fixed',gender:'male',self_model_path:'/own-old.jpg'} :
      url==='/selfit/try-on/models' ? {items:genderCatalog} : undefined});
    await h.run('load()');
    assert.equal(h.state.modelId,'male_standard_1');
    assert.equal(h.state.photo,'/api/v1/material-assets/male/content');
    assert(h.state.modelLibrary.every(row=>row.gender==='male'));
    assert.equal(h.photos.length,0,'default male entry must not download or automatically switch to own photo');
    assert.equal(h.calls.length,3,'gender comes with preferences, keeping the small initial request budget');
  });
}

test('saved male choice persists; explicit own-photo choice is respected',async()=>{
  for (const selected of ['male_old','self']) {
    const h=harness('?screen=mirror',{api:url=>url==='/closet/preferences' ? {gender:'male',current_model_id:selected} :
      url==='/selfit/try-on/models' ? {items:genderCatalog} : undefined,
      photo:async()=>({ok:true,status:200,blob:async()=>new Blob(['own'],{type:'image/jpeg'})})});
    await h.run('load()');
    assert.equal(h.state.modelId,selected);
    assert(h.state.modelLibrary.every(row=>row.gender==='male'));
    h.state.uploadURLs.forEach(URL.revokeObjectURL);
  }
});

test('female and unknown gender keep the female model library',async()=>{
  for (const gender of ['female',undefined]) {
    const h=harness('?screen=mirror',{api:url=>url==='/closet/preferences' ? {gender,current_model_id:'fixed'} :
      url==='/selfit/try-on/models' ? {items:genderCatalog} : undefined});
    await h.run('load()');
    assert.equal(h.state.modelId,'fixed');
    assert(h.state.modelLibrary.every(row=>row.gender==='female'));
  }
});

test('try-on submits the selected male model bytes and model ID',async()=>{
  let submitted;
  const h=harness('?screen=mirror',{api:(url,options)=>{
    if(url==='/closet/preferences')return {gender:'male',current_model_id:'fixed'};
    if(url==='/selfit/try-on/models')return {items:genderCatalog};
    if(url==='/selfit/try-on/jobs'){submitted=options.body;return {job_id:'male-test-job',status:'queued'};}
  },photo:async()=>({ok:true,status:200,blob:async()=>new Blob(['selected-male-image'],{type:'image/png'})})});
  await h.run('load()');
  h.run(`let generationBusy=false;
    const crypto={randomUUID:()=>"male-test-request"};
    const mediaURL=path=>new URL(path,location.origin).href;
    function beginMirrorGeneration(target,photo){state.generating={target,photo};}
    function failure(message){throw Error(message);}
  `+slice('  async function photoFile(', '  async function startTry()')+
    slice('  async function generate()', '  async function waitForPresetResult('));
  await h.run('generate()');
  assert.equal(submitted.get('model_id'),'male_standard_1');
  assert.equal(await submitted.get('person_image').text(),'selected-male-image');
  assert.equal(submitted.get('wear_all_items'),'true');
  assert.deepEqual(JSON.parse(submitted.get('selected_item_ids')),['top-1']);
  assert.equal(h.photos.at(-1),'http://localhost/api/v1/material-assets/male/content');
});
