// Live local-server test. Uses only a new app-created guest and its own saved outfit.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const base=process.env.SELFIT_TEST_URL || 'http://127.0.0.1:8000';
assert(['localhost','127.0.0.1'].includes(new URL(base).hostname),'Local server only');
const evidence=path.resolve('docs/audits/20260908-main-app/evidence/live-guest-closet');
fs.mkdirSync(evidence,{recursive:true});
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 const context=await browser.newContext({viewport:{width:393,height:852}});
 const page=await context.newPage();page.setDefaultTimeout(25000);
 const errors=[];page.on('pageerror',e=>errors.push(e.name));
 const checks=[];
 async function screen(name){
   await page.locator('#studio img').evaluateAll(async imgs=>{
     await Promise.all(imgs.map(img=>img.decode().catch(()=>{})));
   });
   const result=await page.evaluate(()=>({width:innerWidth,overflow:document.documentElement.scrollWidth>innerWidth,
     broken:[...document.querySelectorAll('#studio img')].filter(i=>!i.complete||!i.naturalWidth).length}));
   assert.equal(result.overflow,false);assert.equal(result.broken,0);
   await page.screenshot({path:path.join(evidence,name+'.png')});checks.push({name,...result});
 }
 try {
   await page.goto(base+'/selfit/try-on?screen=mirror');
   await page.locator('.mirror-favorite').waitFor();
   await page.locator('.mirror-favorite').click();
   await page.locator('.mirror-favorite[aria-pressed="true"]').waitFor();
   await page.locator('#navigation [data-page="closet"]').click();
   assert.equal(await page.locator('.closet-grid .item-card').count(),0);
   await page.locator('.wardrobe-header [data-category="set"]').click();
   await page.locator('.closet-grid .outfit-card').waitFor();
   assert.equal(await page.locator('.closet-grid .outfit-card').count(),1);
   await screen('01-saved-outfit');
   await page.reload();
   await page.locator('.wardrobe-header').waitFor();
   await page.locator('.wardrobe-header [data-category="set"]').click();
   await page.locator('.closet-grid .outfit-card').waitFor();
   assert.equal(await page.locator('.closet-grid .outfit-card').count(),1);
   checks.push({name:'favorite-survives-reload',passed:true});
   await page.locator('#navigation [data-page="mirror"]').click();
   await page.locator('.mirror-favorite[aria-pressed="true"]').click();
   await page.locator('.mirror-favorite[aria-pressed="false"]').waitFor();
   await page.locator('#navigation [data-page="closet"]').click();
   await page.locator('.wardrobe-header [data-category="set"]').click();
   assert.equal(await page.locator('.closet-grid .outfit-card').count(),0);
   checks.push({name:'unfavorite-library-outfit-removes-it-from-wardrobe',passed:true});
   await page.locator('#navigation [data-page="mirror"]').click();
   await page.locator('.mirror-favorite[aria-pressed="false"]').click();
   await page.locator('.mirror-favorite[aria-pressed="true"]').waitFor();
   await page.locator('#navigation [data-page="closet"]').click();
   await page.locator('.wardrobe-header [data-category="set"]').click();
   await page.locator('.closet-grid .outfit-card').waitFor();
   assert.equal(await page.locator('.closet-grid .outfit-card').count(),1);
   checks.push({name:'refavorite-restores-exactly-one-outfit',passed:true});
   await page.locator('.closet-grid .outfit-card').click();
   await page.locator('#sheet [data-action="delete-outfit"]').click();
   await page.locator('[data-action="cancel-delete-outfit"]').click();
   await page.locator('#sheet [data-action="delete-outfit"]').waitFor();
   await screen('02-delete-cancel-restores-detail');
   await page.locator('#sheet [data-action="delete-outfit"]').click();
   await page.locator('[data-action="confirm-delete"]').click();
   await page.locator('#sheet').waitFor({state:'hidden'});
   await page.waitForFunction(()=>!new URL(location.href).searchParams.has('outfit'));
   assert.equal(await page.locator('.closet-grid .outfit-card').count(),0);
   await page.reload();
   await page.locator('.wardrobe-header').waitFor();
   await page.locator('.wardrobe-header [data-category="set"]').click();
   assert.equal(await page.locator('.closet-grid .outfit-card').count(),0);
   checks.push({name:'delete-survives-reload-without-stale-outfit-url',passed:true});
   for(const width of [393,430,1280]){
     await page.setViewportSize({width,height:852});
     await screen('03-empty-wardrobe-'+width);
   }
   assert.deepEqual(errors,[]);
   fs.writeFileSync(path.join(evidence,'result.json'),JSON.stringify({passed:true,checks,runtimeErrors:errors},null,2));
   console.log('Live guest favorite/reload/delete/cancel and responsive screenshots: passed');
 } catch(e){
   await page.screenshot({path:path.join(evidence,'failure.png')});
   throw e;
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
