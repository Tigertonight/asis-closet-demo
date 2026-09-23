const assert = require('node:assert/strict');
const fs = require('node:fs'), vm = require('node:vm');
const src = fs.readFileSync('app/static/selfit-tryon/studio.js', 'utf8');
const code = src.slice(src.indexOf('  async function importGarment('), src.indexOf('  function importFailure('));
(async () => {
  for (const status of ['processing', 'awaiting_confirmation', 'completed', undefined, 'failed']) {
    const calls = [], sheet = {dataset:{}};
    const ctx = {importFile:null, importJob:{job_id:'job1',status}, importEpoch:0, importTimer:null,
      state:{page:'mirror'}, clearTimeout(){}, modal(){}, $:()=>sheet,
      api:async path=>{calls.push(path);return {job_id:'job1',status:'queued'};},
      pollImport:async()=>calls.push('poll'), rememberImport(){}, importFailure:message=>{throw Error(message);}};
    vm.createContext(ctx);vm.runInContext(code,ctx);await ctx.importGarment(true);
    assert.deepEqual(calls, status === 'failed' ? ['/closet/import/jobs/job1/retry','poll'] : ['poll']);
  }
  console.log('Import retry preserves existing tasks and restarts only confirmed failures');
})().catch(error=>{console.error(error);process.exitCode=1;});
