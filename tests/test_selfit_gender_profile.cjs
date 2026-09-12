const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('app/static/selfit-tryon/studio.js','utf8');
const block=source.slice(source.indexOf('  function profileGenderEdit()'),source.indexOf('  const REFERENCE_PROFILE_SUIT'));
function harness(failure=false){
  const calls=[];
  const state={profile:{gender:'female',genderRevision:3,photos:{body:'/own.jpg'}},profileFeatureValue:'male',
    profileFeatureTouched:true,profileSaving:false,profileEditingField:'gender',builderRequest:1,
    homeOutfits:[{id:'old'}],reportOutfits:[{id:'old-report'}],builderMatches:[{}],current:{id:'old'},result:'/old-result'};
  const context=vm.createContext({state,reference:false,URL,homeNotesRequest:null,savedSession:{user:{gender:'female'}},
    location:{href:'http://localhost/selfit/try-on?screen=profile-edit&from=report&outfit=old&report_notes=one'},
    esc:String,render(){},notify(){},history:{replaceState:(_,__,url)=>calls.push({url:String(url)})},
    go:page=>{state.page=page;},filterModelsByGender(){},
    prepareInitialModel:async prefs=>{state.modelGender=prefs.gender;},loadPreferences:async()=>({gender:'male'}),
    api:async(path,options)=>{calls.push({path,options});if(failure)throw Error('保存失败，请重试');
      return {profile:{gender:'male',genderRevision:4,photos:{body:'/protected'},suit:{}}};}});
  vm.runInContext(block,context);
  return {state,calls,context,save:()=>vm.runInContext('saveProfileGender()',context)};
}
test('gender save updates the view, discards stale recommendations and keeps own photo',async()=>{
  const h=harness();await h.save();
  assert.equal(h.calls[0].path,'/api/v1/selfit/me/gender');
  assert.equal(h.calls[0].options.headers['If-Match'],'3');
  assert.deepEqual(JSON.parse(h.calls[0].options.body),{gender:'male'});
  assert.equal(h.state.profile.gender,'male');assert.equal(h.state.profile.photos.body,'/own.jpg');
  assert.equal(h.state.modelGender,'male');assert.equal(h.state.page,'profile');
  assert.equal(h.state.homeOutfits.length,0);assert.equal(h.state.reportOutfits.length,0);
  assert.equal(h.state.builderMatches.length,0);assert.equal(h.state.current,null);
  assert.equal(h.state.profileSaving,false);
  assert(!h.calls.at(-1).url.includes('from=report'));
});
test('failed save keeps the choice and current model/content for retry',async()=>{
  const h=harness(true);await h.save();
  assert.equal(h.state.profile.gender,'female');assert.equal(h.state.profileFeatureValue,'male');
  assert.equal(h.state.profileEditingField,'gender');assert.equal(h.state.homeOutfits.length,1);
  assert.equal(h.state.profileSaving,false);assert.match(h.state.profileError,/保存失败/);
});
test('pending save prevents a duplicate request',async()=>{
  const h=harness();let done;h.context.api=()=>new Promise(resolve=>{done=resolve;});
  const pending=h.save();await h.save();assert.equal(h.state.profileSaving,true);
  done({profile:{gender:'male',genderRevision:4}});await pending;assert.equal(h.state.profileSaving,false);
});
test('the untested profile can open the gender editor and the report keeps try-on available',()=>{
  assert(source.indexOf("if(state.profileEditingField === 'gender') return profileGenderEdit();") < source.indexOf('if(!state.profile.tested) return profile();'));
  const report=fs.readFileSync('app/static/selfit/selfit.js','utf8');
  assert.match(report,/continueToApp.hidden = false/);
  assert.match(report,/pendingGenderContent\s*\? '\/selfit\/try-on\?screen=mirror'/);
});
