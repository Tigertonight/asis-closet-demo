const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {test} = require('node:test');
const source = fs.readFileSync('app/static/selfit-tryon/studio.js', 'utf8');
const rows = label => Array.from({length:4}, (_, i) => ({outfit_id:`${label}-${i}`,
  items:[], report_note:{title:`${label} ${i}`, image_url:`/${label}-${i}.webp`}}));

function harness() {
  const current = {id:'selected', items:[]};
  const pending = {target:current, photo:'/my-photo'};
  const state = {page:'mirror',source:'report',current,photo:'/my-photo',result:'/my-result',
    generating:pending,job:{job_id:'pending-job'},items:[],homeOutfits:[{id:'old'}],selected:new Set(['old-piece'])};
  const calls = [], notices = [];
  const context = vm.createContext({state,reference:false,homeNotesRevision:0,
    api:(...args) => new Promise((resolve,reject) => calls.push({args,resolve,reject})),
    normalizeOutfit:row=>({id:row.outfit_id,items:row.items}),
    render(){},notify:message=>notices.push(message), $:()=>null,
  });
  vm.runInContext(source.slice(source.indexOf('  function applyHomeNotes('), source.indexOf('  async function loadReportOutfits(')), context);
  return {state,calls,notices,context,refresh:()=>vm.runInContext('refreshHomeNotes()', context)};
}

test('explicit refresh changes only the batch, not a pending try-on or report selection', async () => {
  const {state,calls,refresh} = harness();
  const original = {...state};
  const first = refresh();
  await refresh();
  assert.equal(calls.length,1,'double taps must share one request');
  assert.equal(calls[0].args[0],'/selfit/try-on/report-outfits/home/refresh');
  assert.equal(calls[0].args[1].method,'POST');
  calls[0].resolve({outfits:rows('new')});
  await first;
  assert.equal(state.homeOutfits[0].id,'new-0');
  for (const key of ['current','photo','result','generating','job','selected','source','page']) assert.equal(state[key],original[key],key);
  assert.equal(state.homeNotesRefreshing,false);
});

test('a failed or malformed refresh keeps the previous list and can retry', async () => {
  const {state,calls,notices,refresh} = harness();
  const previous=state.homeOutfits;
  let task=refresh();calls[0].reject(Error('请重试'));await task;
  assert.equal(state.homeOutfits,previous);
  assert.equal(state.homeNotesRefreshing,false);
  assert.equal(notices[0],'请重试');
  task=refresh();calls[1].resolve({outfits:[]});await task;
  assert.equal(state.homeOutfits,previous);
  task=refresh();calls[2].resolve({outfits:rows('retry')});await task;
  assert.equal(state.homeOutfits[0].id,'retry-0');
});

test('late refresh cannot restore a previous gender or navigate back from another page', async () => {
  const {state,calls,context,refresh} = harness();
  const previous=state.homeOutfits;
  let task=refresh();vm.runInContext('homeNotesRevision++',context);
  state.homeNotesRefreshing=false;calls[0].resolve({outfits:rows('stale')});await task;
  assert.equal(state.homeOutfits,previous);
  task=refresh();state.page='tryon-history';calls[1].resolve({outfits:rows('fresh')});await task;
  assert.equal(state.page,'tryon-history');assert.equal(state.homeOutfits[0].id,'fresh-0');
});

test('report handoff and reload load the persisted account batch independently of selection', () => {
  const load=source.slice(source.indexOf('  async function load()'),source.indexOf('  $("#sheet").addEventListener'));
  assert.match(load,/if \(state.source === "report"\) await loadReportOutfits\(\);\s*await ensureHomeNotes\(\);/);
  const mirror=source.slice(source.indexOf('  function mirror()'),source.indexOf('  const trimmedPieces'));
  assert.doesNotMatch(mirror, /\? state.reportOutfits/);
  assert.match(mirror, /: state.homeOutfits/);
});
