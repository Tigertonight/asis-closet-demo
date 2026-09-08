// Public API setup on an app-created guest; profile interactions use the real UI.
const {chromium}=require('playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const dir=path.resolve('docs/audits/20260908-main-app/evidence/live-guest-profile');fs.mkdirSync(dir,{recursive:true});
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 const page=await browser.newPage({viewport:{width:393,height:852}});page.setDefaultTimeout(30000);
 const errors=[];page.on('pageerror',e=>errors.push(e.name));
 async function api(url,method='GET',body){return page.evaluate(async({url,method,body})=>{
  const session=JSON.parse(sessionStorage.getItem('selfit.auth.session.v1'));
  const r=await fetch(url,{method,headers:{Authorization:`Bearer ${session.accessToken}`,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});
  if(!r.ok)throw Error(`Setup API ${r.status}: ${url}`);return r.json();
 },{url,method,body});}
 try{
  await page.goto('http://127.0.0.1:8000/selfit/try-on?screen=mirror');await page.locator('.mirror-favorite').waitFor();
  const {session}=await api('/api/v1/selfit/sessions','POST',{schemaVersion:'selfit-onboarding-v1',locale:'zh-CN'});
  const root='/api/v1/selfit/sessions/'+session.sessionId;
  await api(root+'/profile','PATCH',{manual:{skin:'暖白肤',faceShape:'椭圆脸',bodyShape:'梨型'}});
  await api(root+'/preferences','PATCH',{axes:{shape:42,energy:64,trend:42},palette:'mono'});
  await api(root+'/vibe','PATCH',{answers:{occasion:'A',wardrobe:'B',expression:'A'}});
  const {job}=await api(root+'/report-jobs','POST',{});
  let reportJob;
  for(let i=0;i<120;i++){
   reportJob=(await api('/api/v1/selfit/report-jobs/'+job.jobId)).job;
   if(['completed','failed'].includes(reportJob.status))break;
   await page.waitForTimeout(500);
  }
  assert.equal(reportJob.status,'completed');
  await page.locator('[data-page="profile"]').first().click();
  await page.locator('.profile-analysis').waitFor();
  await page.locator('.profile-header [data-action="edit-profile"]').click();
  await page.locator('[data-profile-field="faceShape"]').selectOption({label:'心形脸'});
  await page.locator('[data-profile-field="skin"]').selectOption({label:'小麦色'});
  await page.locator('[data-profile-field="bodyShape"]').selectOption({label:'苹果型'});
  await page.locator('[data-profile-photo="body"]').setInputFiles(path.resolve('tests/fixtures/tryon_models/female_medium_1.png'));
  await page.locator('.edit-photo img').waitFor();
  const saved=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/selfit/me/profile'&&r.request().method()==='PATCH',{timeout:90000});
  await page.locator('[data-action="save-profile"]').click();
  assert.equal((await saved).ok(),true);
  await page.locator('.profile-analysis').waitFor();
  await page.reload();await page.locator('.profile-analysis').waitFor();
  const profile=(await api('/api/v1/selfit/me/profile')).profile;
  assert.deepEqual(profile.manual,{faceShape:'心形脸',skin:'小麦色',bodyShape:'苹果型'});
  assert(profile.photos.body);
  assert.equal(await page.locator('.profile-analysis .profile-photo img[alt="全身照"]').evaluate(async i=>{await i.decode();return i.naturalWidth>0}),true);
  for(const width of [393,430,1280]){
   await page.setViewportSize({width,height:852});
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
   await page.screenshot({path:path.join(dir,'saved-'+width+'.png')});
  }
  await page.locator('.profile-header [data-action="edit-profile"]').click();
  await page.locator('[data-profile-field="faceShape"]').selectOption({label:'圆脸'});
  await page.locator('.profile-header [data-page="profile"]').click();
  assert((await page.locator('.profile-analysis').innerText()).includes('心形脸'));
  await page.locator('.profile-report').click();
  await page.locator('[data-screen="login"].is-active').waitFor();
  assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(dir,'result.json'),JSON.stringify({passed:true,reportId:reportJob.reportId,checks:['real-report-api-setup','manual-edit-and-body-upload','profile-patch','reload-keeps-fields-and-photo','cancel-preserves-saved-fields','visitor-report-requires-login'],registeredReportRoundTripVerified:false,runtimeErrors:errors},null,2));
  console.log('Real guest profile edit/upload/save/reload/cancel and report login boundary: passed');
 }catch(e){await page.screenshot({path:path.join(dir,'failure.png')});throw e}
 finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
