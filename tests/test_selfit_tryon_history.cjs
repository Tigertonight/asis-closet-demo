const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const src = fs.readFileSync('app/static/selfit-tryon/studio.js', 'utf8');
const historyCode = src.slice(src.indexOf('  function tryonHistory()'), src.indexOf('  function importReview()'));
const goCode = src.slice(src.indexOf('  function go('), src.indexOf('  function categoryGroup('));
const state = {page:'tryon-history', historyRequest:0, historyRecords:[], source:'inspiration'};
let respond, rendered = '', authenticated = false, requests = 0;
const ctx = {
  state, reference:false, A:'/',
  esc:s=>String(s ?? '').replaceAll('<','&lt;').replaceAll('"','&quot;'),
  image:(src,alt)=>`<img src="${src}" alt="${ctx.esc(alt)}">`,
  ensureVisitorSession:async()=>{authenticated=true;},
  api:async path=>{assert.equal(path,'/closet/tryon-records');assert(authenticated);requests++;return new Promise(resolve=>{respond=resolve;});},
  render:()=>{rendered=ctx.tryonHistory();},
};
vm.createContext(ctx);
vm.runInContext(historyCode+';Object.assign(this,{tryonHistory,loadTryonHistory,resultViewer});',ctx);
(async()=>{
  const pending=ctx.loadTryonHistory();
  assert.match(rendered,/正在加载试穿历史/);
  await new Promise(setImmediate);
  const records=[{record_id:'recent',created_at:'2026-09-09T02:00:00Z',image_path:'/recent.png',outfit_title:'<script>'},
    {record_id:'earlier',created_at:'2026-09-01T02:00:00Z',image_path:'/earlier.png'},
    {record_id:'undated',created_at:null,image_path:'/undated.png'}];
  respond({records});await pending;
  assert.equal(requests,1);
  assert.match(rendered,/<h1 id="historyTitle">试穿历史<\/h1>/);
  assert.match(rendered,/aria-label="返回试衣镜"/);
  assert.match(rendered,/2026\/9\/9/);assert.match(rendered,/2026\/9\/1/);
  assert(!rendered.includes('1970')&&!rendered.includes('Invalid Date'));
  assert(!rendered.includes('<script>'));
  assert(rendered.indexOf('data-record="recent"')<rendered.indexOf('data-record="earlier"'));

  // Leaving while a fetch runs must not redraw the active page or replace newer records.
  const stale=ctx.loadTryonHistory();await new Promise(setImmediate);
  state.page='mirror';rendered='mirror';respond({records:[]});await stale;
  assert.equal(rendered,'mirror');assert.equal(state.historyRecords,records);
  state.page='tryon-history';
  ctx.api=async()=>{throw Error('private implementation error');};
  await ctx.loadTryonHistory();
  assert.match(rendered,/data-action="reload-tryon-history"/);
  assert(!rendered.includes('private implementation'));
  ctx.api=async()=>({records:[]});await ctx.loadTryonHistory();
  assert.match(rendered,/还没有试穿历史/);assert.match(rendered,/去试穿/);

  // Preserve the history return destination in record URLs, including reload.
  let pushed;
  Object.assign(ctx,{URL,location:{href:'http://localhost/selfit/try-on?screen=tryon-history'},
    history:{pushState:(_state,_title,url)=>{pushed=url;}},$:()=>({scrollTop:0}),loadChat(){},loadProfile(){}});
  vm.runInContext(goCode+';this.go=go;',ctx);
  state.viewRecordId='recent';state.viewerReturnPage='tryon-history';state.result='/recent.png';
  ctx.go('result-viewer');
  assert.equal(pushed.searchParams.get('record'),'recent');
  assert.equal(pushed.searchParams.get('viewer_from'),'history');
  assert.match(ctx.resultViewer(),/收起大图，返回试穿历史/);
  state.viewerReturnPage='mirror';ctx.go('result-viewer');
  assert.equal(pushed.searchParams.has('viewer_from'),false);
  assert.match(ctx.resultViewer(),/收起大图，返回试衣镜/);
  state.viewerReturnPage='tryon-history';state.viewerError='无法加载';
  assert.match(ctx.resultViewer(),/data-action="close-viewer">返回试穿历史/);
  console.log('History loading, failure, empty state, dates, stale responses and viewer return routes: passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
