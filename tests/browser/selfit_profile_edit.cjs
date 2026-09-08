const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const dir=path.resolve('docs/audits/20260908-main-app/evidence/profile-edit-affordance');fs.mkdirSync(dir,{recursive:true});
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 const page=await browser.newPage({viewport:{width:393,height:852}});
 const errors=[];page.on('pageerror',e=>errors.push(e.name));
 try{
  await page.goto('http://127.0.0.1:8000/selfit/try-on?reference=1&screen=profile-edit&profile_state=no-photo');
  await page.locator('[data-profile-field="faceShape"]').waitFor();
  for(const [field,value] of [['faceShape','心形脸'],['skin','小麦色'],['bodyShape','苹果型']]){
   const select=page.locator(`[data-profile-field="${field}"]`);
   assert(await select.evaluate(el=>{const r=el.closest('label').getBoundingClientRect();return document.elementFromPoint(r.left+8,r.top+r.height/2)===el;}),'Entire row must open the selector');
   await select.selectOption({label:value});
   assert.equal(await select.inputValue(),value);
   assert.equal(await select.locator('..').locator('.profile-field-value').innerText(),value);
  }
  for(const width of [393,430,1280]){
   await page.setViewportSize({width,height:852});
   await page.locator('[data-profile-field="bodyShape"]').focus();
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
   await page.screenshot({path:path.join(dir,`edit-${width}.png`)});
  }
  await page.locator('[data-action="save-profile"]').click();
  await page.locator('.profile-analysis').waitFor();
  for(const value of ['心形脸','小麦色','苹果型'])assert((await page.locator('.profile-analysis').innerText()).includes(value));
  await page.locator('.profile-header [data-action="edit-profile"]').click();
  await page.locator('[data-profile-field="faceShape"]').selectOption({label:'圆脸'});
  await page.locator('.profile-header [data-page="profile"]').click();
  assert((await page.locator('.profile-analysis').innerText()).includes('心形脸'));
  assert.deepEqual(errors,[]);
  console.log('Profile full-row selectors, three draft changes, save and cancel: passed');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
