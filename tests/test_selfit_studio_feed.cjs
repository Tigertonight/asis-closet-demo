const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const code = fs.readFileSync('app/static/selfit-tryon/studio.js','utf8');
const loadFeed = code.slice(code.indexOf('  async function loadFeed('),code.indexOf('  async function load()'));
(async () => {
  const calls=[];
  let page=0, failSets=false;
  const notes=[0,1,2,3].map(i=>({id:`note:mute:${i}`,title:`note ${i}`,image_url:`note-${i}.webp`,width:1080,height:1439,favorite:i===0}));
  const state={feedBusy:false,feedMore:true,items:[],outfits:[],feed:[]};
  const context={state,Date,Promise,Set,console,
    uniqueItems: rows=>[...new Map(rows.map(x=>[x.id,x])).values()],
    normalizeOutfit:x=>({id:x.outfit_id,items:[],kind:'outfit'}),
    api:async(url,options)=>{
      calls.push({url,options});
      if(url.endsWith('inspiration-notes'))return {notes};
      if(failSets)throw Error('sets unavailable');
      return {outfits:Array.from({length:6},(_,i)=>({outfit_id:`set-${page*6+i}`})),session_id:'session',next_cursor:'cursor',has_more:true};
    }};
  vm.createContext(context);vm.runInContext(loadFeed+';this.loadFeed=loadFeed;',context);
  await context.loadFeed();
  assert.equal(state.feed.filter(x=>x.kind==='note').length,4);
  const indices=state.feed.map((x,i)=>x.kind==='note'?i:-1).filter(i=>i>=0);
  assert(indices.some(i=>i%2===0)&&indices.some(i=>i%2===1),'notes must reach both columns');
  assert.equal(state.feed[0].height,1439);
  assert.equal(state.feed[0].saved,true);
  page=1;await context.loadFeed(true);
  assert.equal(state.feed.filter(x=>x.kind==='note').length,4,'pagination must not repeat notes');
  assert.equal(state.feed.filter(x=>x.kind==='outfit').length,12);
  const lastBody=JSON.parse(calls.at(-2)?.options?.body || calls.at(-1).options.body);
  assert(lastBody.exclude_outfit_ids.every(id=>!id.startsWith('note:')));
  failSets=true;
  const cursor=state.feedCursor;
  await assert.rejects(()=>context.loadFeed(true));
  assert.equal(state.feedCursor,cursor,'failed pagination must preserve cursor');
  await context.loadFeed(false);
  assert.equal(state.feed.length,4,'available notes survive a set service failure');
  assert(state.feedError);
  console.log('Mixed feed, both columns, pagination, favorites and partial failure: passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
