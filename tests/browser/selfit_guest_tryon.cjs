// Runs one real try-on using the app's example model, in a new isolated guest.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const base=process.env.SELFIT_TEST_URL || 'http://127.0.0.1:8000';
assert(['localhost','127.0.0.1'].includes(new URL(base).hostname));
const dir=path.resolve('docs/audits/20260908-main-app/evidence/live-guest-tryon');
fs.mkdirSync(dir,{recursive:true});
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 const context=await browser.newContext({viewport:{width:393,height:852}});
 const page=await context.newPage();page.setDefaultTimeout(30000);
 const errors=[];page.on('pageerror',e=>errors.push(e.name));
 let completed;
 page.on('response',async response=>{
   if(!new URL(response.url()).pathname.startsWith('/selfit/try-on/jobs/') || !response.ok())return;
   const job=await response.json().catch(()=>null);
   if(job?.status==='completed')completed=job;
 });
 async function shot(name){
   await page.locator('#studio img').evaluateAll(async imgs=>Promise.all(imgs.map(i=>i.decode().catch(()=>{}))));
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
   await page.screenshot({path:path.join(dir,name+'.png')});
 }
 try{
   await page.goto(base+'/selfit/try-on?screen=mirror');
   await page.locator('.mirror-favorite').click();
   await page.locator('.mirror-favorite[aria-pressed="true"]').waitFor();
   await page.locator('#navigation [data-page="closet"]').click();
   await page.locator('.wardrobe-header [data-category="set"]').click();
   await page.locator('.closet-grid .outfit-card').click();
   await page.locator('#sheet [data-action="try"]').click();
   await page.locator('[data-action="use-example"]').click();
   await page.locator('[data-action="generate"]').waitFor();
   const submission=page.waitForResponse(r=>new URL(r.url()).pathname==='/selfit/try-on/jobs' && r.request().method()==='POST');
   const start=Date.now();
   await page.locator('[data-action="generate"]').click();
   const created=await (await submission).json();
   assert(created.job_id);console.log('Submitted test job',created.job_id);
   await page.locator('.mirror-stage.is-generating').waitFor();
   await shot('01-generating');
   await page.locator('#navigation [data-page="inspiration"]').click();
   await page.locator('#completionNotice').waitFor({state:'visible',timeout:180000});
   assert.equal(new URL(page.url()).searchParams.get('screen'),'inspiration');
   await shot('02-background-success');
   await page.locator('#completionNotice').click();
   await page.locator('.mirror-stage.has-result').waitFor();
   assert(completed && completed.job_id===created.job_id);
   const expectedPath=new URL(completed.result.result.image_path,base).pathname;
   assert.equal(new URL(await page.locator('.model-photo').getAttribute('src'),base).pathname,expectedPath);
   await shot('03-result');
   await page.locator('[data-action="result-actions"]').click();
   await page.locator('[data-action="tryon-history"]').click();
   await page.locator('#sheet [data-record]').waitFor();
   assert.equal(await page.locator('#sheet [data-record]').count(),1);
   await page.locator('#sheet [data-record]').click();
   const record=new URL(page.url()).searchParams.get('record');assert(record);
   await page.reload();
   await page.locator('.result-viewer-photo').waitFor();
   assert.equal(new URL(await page.locator('.result-viewer-photo').getAttribute('src'),base).pathname,expectedPath);
   await shot('04-history-reloaded');
   await page.locator('[data-action="close-viewer"]').click();
   await page.goBack();
   await page.locator('.result-viewer-photo').waitFor();
   assert.equal(new URL(page.url()).searchParams.get('record'),record);
   assert.equal(new URL(await page.locator('.result-viewer-photo').getAttribute('src'),base).pathname,expectedPath);
   await page.goForward();
   await page.locator('.mirror-stage.has-result').waitFor();
   assert.equal(new URL(page.url()).searchParams.get('screen'),'mirror');
   assert.deepEqual(errors,[]);
   fs.writeFileSync(path.join(dir,'result.json'),JSON.stringify({passed:true,jobId:created.job_id,recordId:record,
     elapsedSeconds:(Date.now()-start)/1000,resultStatus:completed.result.status,
     checks:['background-completion-preserves-page','submitted-result-identity','history-created','real-reload-restores-record','back-forward-restores-record'],runtimeErrors:errors},null,2));
   console.log('Live try-on, completion notice, history reload and browser navigation: passed');
 }catch(e){await page.screenshot({path:path.join(dir,'failure.png')});throw e;}
 finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
