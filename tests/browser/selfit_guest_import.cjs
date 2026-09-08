// Live extraction/confirmation against localhost, using a bundled fashion reference.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const base=process.env.SELFIT_TEST_URL || 'http://127.0.0.1:8000';
assert(['localhost','127.0.0.1'].includes(new URL(base).hostname));
const dir=path.resolve('docs/audits/20260908-main-app/evidence/live-guest-import');fs.mkdirSync(dir,{recursive:true});
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 const context=await browser.newContext({viewport:{width:393,height:852}});
 const page=await context.newPage();page.setDefaultTimeout(30000);
 const errors=[];page.on('pageerror',e=>errors.push(e.name));
 async function shot(name){
   await page.locator('#studio img').evaluateAll(async imgs=>Promise.all(imgs.map(i=>i.decode().catch(()=>{}))));
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
   await page.screenshot({path:path.join(dir,name+'.png')});
 }
 try{
   await page.goto(base+'/selfit/try-on?screen=closet');
   await page.locator('.wardrobe-header').waitFor();
   const submission=page.waitForResponse(r=>new URL(r.url()).pathname==='/closet/import/jobs' && r.request().method()==='POST');
   await page.locator('#garmentInput').setInputFiles(path.resolve('app/static/selfit/assets/personality/bolt/report-outfits-02.webp'));
   const job=await (await submission).json();assert(job.job_id);console.log('Submitted import',job.job_id);
   await page.locator('.import-choice').first().waitFor({timeout:180000});
   const ids=await page.locator('.import-choice').evaluateAll(nodes=>nodes.map(n=>n.dataset.importPiece));
   assert(ids.length>=2,'Need multiple extracted pieces to verify partial selection');
   await shot('01-recognized-pieces');
   const excluded=ids.at(-1);
   await page.locator(`[data-import-piece="${excluded}"]`).click();
   await page.reload();
   await page.locator('.import-choice').first().waitFor();
   assert.equal(await page.locator(`[data-import-piece="${excluded}"]`).getAttribute('aria-pressed'),'false');
   await page.locator('[data-action="leave-import"]').click();
   assert.equal(await page.locator('.closet-grid .item-card').count(),0);
   await page.locator('[data-action="resume-import"]').click();
   await page.locator('.import-choice').first().waitFor();
   assert.equal(await page.locator(`[data-import-piece="${excluded}"]`).getAttribute('aria-pressed'),'false');
   await shot('02-restored-selection');
   await page.locator('[data-action="confirm-import"]').click();
   await page.locator('.closet-grid .item-card').first().waitFor({timeout:90000});
   const actual=await page.locator('.closet-grid .item-card').evaluateAll(nodes=>nodes.map(n=>n.dataset.item).sort());
   assert.deepEqual(actual,ids.filter(id=>id!==excluded).sort());
   await page.reload();await page.locator('.closet-grid .item-card').first().waitFor();
   assert.equal(await page.locator('.closet-grid .item-card').count(),ids.length-1);
   assert.equal(await page.locator('[data-action="resume-import"]').count(),0);
   await shot('03-confirmed-wardrobe');
   const anchor=actual[0];
   await page.locator(`.closet-grid [data-item="${anchor}"]`).click();
   await shot('04-garment-sheet');
   const generatedResponse=page.waitForResponse(r=>new URL(r.url()).pathname===`/selfit/try-on/items/${anchor}/outfits`&&r.request().method()==='POST');
   await page.locator('#sheet [data-action="item-generate"]').click();
   const generatedHTTP=await generatedResponse;
   assert.equal(generatedHTTP.ok(),true,`Outfit generation HTTP ${generatedHTTP.status()}`);
   const generated=await generatedHTTP.json();
   assert.equal(generated.anchor_item_id,anchor);assert(generated.outfits.length>0);
   assert(generated.outfits.every(o=>o.items.some(i=>i.item_id===anchor)),'Every outfit retains selected garment');
   await page.locator(`[data-canvas-piece="${anchor}"]`).waitFor();
   const expected=generated.outfits[0].items.map(i=>i.item_id).sort();
   const canvasIds=()=>page.locator('[data-canvas-piece]').evaluateAll(nodes=>nodes.map(n=>n.dataset.canvasPiece).sort());
   assert.deepEqual(await canvasIds(),expected);
   await shot('05-generated-canvas');
   await page.reload();await page.locator(`[data-canvas-piece="${anchor}"]`).waitFor();
   assert.deepEqual(await canvasIds(),expected);
   await page.locator(`[data-canvas-piece="${anchor}"]`).click();
   await page.locator('[data-action="remove-piece"]').click();
   assert.deepEqual(await canvasIds(),expected.filter(id=>id!==anchor));
   await page.locator('[data-action="undo-canvas"]').click();
   assert.deepEqual(await canvasIds(),expected);
   await page.locator('[data-action="redo-canvas"]').click();
   assert.deepEqual(await canvasIds(),expected.filter(id=>id!==anchor));
   await page.locator('[data-action="undo-canvas"]').click();
   await shot('06-undo-restored-canvas');
   for(const width of [393,430,1280]){
     await page.setViewportSize({width,height:852});
     const bounds=await page.evaluate(()=>{
       const a=document.querySelector('.canvas-tools').getBoundingClientRect();
       const b=document.querySelector('.try-outfit-tools').getBoundingClientRect();
       return {overlap:a.left<b.right&&a.right>b.left&&a.top<b.bottom&&a.bottom>b.top,
         sizes:[...document.querySelectorAll('.canvas-tools button')].map(n=>{const r=n.getBoundingClientRect();return [r.width,r.height]})};
     });
     assert.equal(bounds.overlap,false);assert(bounds.sizes.every(([w,h])=>w>=44&&h>=44));
     await shot('07-canvas-tools-'+width);
   }
   await page.locator('#navigation [data-page="closet"]').click();
   await page.locator('.wardrobe-header [data-category="set"]').click();
   const wardrobeOutfits=await page.locator('.closet-grid .outfit-card').evaluateAll(nodes=>nodes.map(n=>n.dataset.outfit));
   assert(generated.outfits.every(o=>wardrobeOutfits.includes(o.outfit_id)),'All generated outfits are available in wardrobe');
   assert.deepEqual(errors,[]);
   fs.writeFileSync(path.join(dir,'result.json'),JSON.stringify({passed:true,jobId:job.job_id,candidates:ids.length,committed:actual.length,
     checks:['real-extraction','selection-survives-reload','no-items-before-confirmation','resume-preserves-selection','only-selected-items-committed','committed-items-survive-reload','generated-outfits-retain-anchor','canvas-survives-reload','remove-undo-redo','generated-outfits-in-wardrobe'],generatedOutfits:generated.outfits.length,runtimeErrors:errors},null,2));
   console.log('Live upload, extraction, selection restore and explicit confirmation: passed');
 }catch(e){await page.screenshot({path:path.join(dir,'failure.png')});throw e;}
 finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
