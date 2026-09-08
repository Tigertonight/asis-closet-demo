// Real local-server conversation using an isolated app-created guest.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const base=process.env.SELFIT_TEST_URL||'http://127.0.0.1:8000';
assert(['localhost','127.0.0.1'].includes(new URL(base).hostname));
const evidence=path.resolve('docs/audits/20260908-main-app/evidence/live-guest-chat');
fs.mkdirSync(evidence,{recursive:true});
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 const page=await browser.newPage({viewport:{width:393,height:852}});
 page.setDefaultTimeout(25000);
 const errors=[];page.on('pageerror',e=>errors.push(e.name));
 try{
  await page.goto(base+'/selfit/try-on?screen=mirror');
  await page.locator('.mirror-favorite').waitFor();
  await page.locator('[data-action="open-chat"]').click();
  await page.locator('#chatInput').fill('我想用白衬衫和深蓝直筒牛仔裤去日常通勤，请用两句话建议鞋子和包包。');
  const response=Promise.race([
   page.waitForResponse(r=>r.url().endsWith('/stylist/chat')&&r.request().method()==='POST',{timeout:270000}),
   page.waitForEvent('requestfailed',{predicate:r=>r.url().endsWith('/stylist/chat'),timeout:270000}).then(()=>{throw Error('Chat request failed before a response was received')})
  ]);
  await page.locator('#chatComposer button[type=submit]').click();
  await page.locator('.chat-thinking').waitFor();
  const result=await response;
  const payload=await result.json();
  if(process.env.SELFIT_EXPECT_CHAT_UNAVAILABLE==='1'){
   assert.equal(result.status(),503);
   await page.locator('.chat-error').waitFor();
   assert.match(await page.locator('.chat-error').innerText(),/问题已保留/);
   assert.match(await page.locator('#chatInput').inputValue(),/白衬衫/);
   assert.equal(await page.locator('#chatComposer button').isEnabled(),true);
   await page.screenshot({path:path.join(evidence,'unavailable.png')});
   await page.reload();
   await page.locator('.from-assistant').waitFor();
   assert.equal(await page.locator('.from-assistant p').innerText(),'这次没有收到搭配建议，请稍后重新发送。');
   assert.doesNotMatch(await page.locator('.chat-messages').innerText(),/OpenClaw|runtime|STYLIST/);
   await page.locator('.chat-header [aria-label="返回上一页"]').click();
   await page.locator('.mirror-favorite').waitFor();
   assert.deepEqual(errors,[]);
   fs.writeFileSync(path.join(evidence,'unavailable-result.json'),JSON.stringify({failureRecoveryPassed:true,normalReplyVerified:false,status:result.status(),errorCode:payload.error?.code,runtimeErrors:errors},null,2));
   console.log('Live unavailable-service recovery and sanitized persisted error: passed; normal reply NOT verified');
   return;
  }
  assert.equal(result.ok(),true,`Chat HTTP ${result.status()}: ${payload.error?.code||''}`);
  assert.notEqual(payload.status,'failed');
  await page.locator('.from-assistant').waitFor();
  const reply=await page.locator('.from-assistant p').innerText();
  assert(reply.length>10);
  assert.equal(await page.locator('.from-user').count(),1);
  const layouts=[];
  for(const [width,height] of [[393,852],[430,740],[1280,852]]){
   await page.setViewportSize({width,height});
   const geometry=await page.evaluate(()=>({overflow:document.documentElement.scrollWidth>innerWidth,
    send:(()=>{const r=document.querySelector('#chatComposer button').getBoundingClientRect();return {bottom:r.bottom,height:r.height}})()}));
   assert.equal(geometry.overflow,false);assert(geometry.send.bottom<=height);assert(geometry.send.height>=44);
   await page.screenshot({path:path.join(evidence,`reply-${width}.png`)});layouts.push({width,height,...geometry});
  }
  await page.reload();
  await page.locator('.from-assistant').waitFor();
  assert.equal(await page.locator('.from-assistant p').innerText(),reply);
  assert.equal(await page.locator('.from-user').count(),1);
  await page.locator('.chat-header [aria-label="返回上一页"]').click();
  await page.waitForURL(url=>url.pathname==='/selfit/try-on'&&url.searchParams.get('screen')==='mirror');
  await page.locator('[data-action="open-chat"]').click();
  assert.equal(await page.locator('.from-assistant p').innerText(),reply);
  assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(evidence,'result.json'),JSON.stringify({passed:true,status:payload.status,mode:payload.mode,replyLength:reply.length,layouts,runtimeErrors:errors},null,2));
  console.log('Live guest chat send/reply/reload/return and responsive layout: passed');
 }catch(e){await page.screenshot({path:path.join(evidence,'failure.png')});throw e}
 finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
