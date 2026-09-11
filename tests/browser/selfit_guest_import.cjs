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
    await page.locator('.builder-composition-canvas[aria-busy="false"] img').first().waitFor();
    const noteCards=page.locator('[data-builder-match]');
    assert.equal(await noteCards.count(),generated.matches.length,'One note card per matched outfit');
    assert.equal(await noteCards.first().getAttribute('aria-selected'),'true');
    const firstTitle=await page.locator('.builder-match-note strong').textContent();
    await shot('05-matched-notes');
    if(generated.matches.length>1){
      await noteCards.nth(1).click();
      assert.equal(await noteCards.nth(1).getAttribute('aria-selected'),'true');
      const secondTitle=await page.locator('.builder-match-note strong').textContent();
      assert.notEqual(secondTitle,firstTitle,'Selecting another note swaps the presented match');
      await noteCards.first().click();
    }
    await shot('06-note-selected');
    await page.locator('[data-action="save-builder"]').click();
    await page.locator('.closet-grid .outfit-card').first().waitFor();
    const wardrobeOutfits=await page.locator('.closet-grid .outfit-card').evaluateAll(nodes=>nodes.map(n=>n.dataset.outfit));
    assert(wardrobeOutfits.length>0,'Saved matched outfit is available in wardrobe');
    assert.deepEqual(errors,[]);
    fs.writeFileSync(path.join(dir,'result.json'),JSON.stringify({passed:true,jobId:job.job_id,candidates:ids.length,committed:actual.length,
      checks:['real-extraction','selection-survives-reload','no-items-before-confirmation','resume-preserves-selection','only-selected-items-committed','committed-items-survive-reload','generated-outfits-retain-anchor','note-cards-match-count','note-selection-swaps-match','saved-outfit-in-wardrobe'],generatedOutfits:generated.outfits.length,runtimeErrors:errors},null,2));
    console.log('Live upload, extraction, selection restore and explicit confirmation: passed');
 }catch(e){await page.screenshot({path:path.join(dir,'failure.png')});throw e;}
 finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
