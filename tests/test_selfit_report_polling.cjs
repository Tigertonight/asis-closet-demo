const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('app/static/selfit/selfit.js','utf8');
function harness(hidden=false){
 let now=0,id=0;const timers=new Map(),listeners=new Set();
 const document={hidden,addEventListener:(_,f)=>listeners.add(f),removeEventListener:(_,f)=>listeners.delete(f)};
 const ctx=vm.createContext({document,Promise,Math,Number,Date:{now:()=>now},setTimeout:(f,ms)=>{timers.set(++id,{f,at:now+ms});return id;},clearTimeout:i=>timers.delete(i)});
 vm.runInContext(source.slice(source.indexOf('  function reportPollDelay('),source.indexOf('  const generateReport')),ctx);
 return {run:s=>vm.runInContext(s,ctx),listeners,timers,advance(ms){now+=ms;for(const [id,t] of [...timers])if(t.at<=now){timers.delete(id);t.f();}},visibility(hidden){document.hidden=hidden;for(const f of listeners)f();}};
}
test('polling backs off from two to five seconds and bounds server hints',()=>{
 const h=harness();assert.equal(h.run('reportPollDelay(0,800)'),2000);assert.equal(h.run('reportPollDelay(3,800)'),3000);assert.equal(h.run('reportPollDelay(6,800)'),5000);assert.equal(h.run('reportPollDelay(0,90000)'),5000);
});
test('background time pauses a pending timer and is excluded from timeout',async()=>{
 const h=harness();let done=false;const p=h.run('waitForReportPoll(2000)').then(ms=>{done=true;return ms;});
 h.advance(500);h.visibility(true);h.advance(150000);await Promise.resolve();assert.equal(done,false);assert.equal(h.timers.size,0);
 h.visibility(false);h.advance(1499);await Promise.resolve();assert.equal(done,false);h.advance(1);assert.equal(await p,150000);assert.equal(h.listeners.size,0);
});
test('initially hidden page makes no polling timer until visible',async()=>{
 const h=harness(true);const p=h.run('waitForReportPoll(0)');assert.equal(h.timers.size,0);h.advance(3000);h.visibility(false);h.advance(0);assert.equal(await p,3000);
});
