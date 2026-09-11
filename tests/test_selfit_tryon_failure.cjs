const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync('app/static/selfit-tryon/studio.js', 'utf8');
const poll = source.slice(source.indexOf('  async function poll('), source.indexOf('  async function importGarment('));
const failure = source.slice(source.indexOf('  function failure('), source.indexOf('  async function poll('));

(async () => {
  for (const [error, result, expected] of [
    [{message: '面部与原照片差异较大。请重新尝试。'}, {}, '面部与原照片差异较大。请重新尝试。'],
    [null, {decision: {user_message: '图片服务暂时不可用，请稍后重试。'}}, '图片服务暂时不可用，请稍后重试。'],
    [null, {}, '这次试穿没有完成，请重新尝试。你选择的照片和搭配都已保留。'],
    [{message: '<img src=x onerror=alert(1)>'}, {}, '&lt;img src=x onerror=alert(1)&gt;'],
  ]) {
    const job = {job_id: 'failed-job', status: 'failed', error, result};
    const state = {page: 'mirror', job: {job_id: job.job_id}, photo: 'original.png', generating: {}};
    let dialog, removed;
    const ctx = {
      state, pollTimer: null, clearTimeout() {}, api: async () => job, $: () => null,
      sessionStorage: {removeItem: key => {removed = key;}}, render() {},
      esc: text => String(text).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;'),
      modal: (title, body) => {dialog = {title, body};},
    };
    vm.createContext(ctx);
    vm.runInContext(failure + poll + ';this.poll = poll;', ctx);
    await ctx.poll();
    assert.equal(dialog.title, '试穿暂未完成');
    assert.ok(dialog.body.includes(`<p>${expected}</p>`));
    assert.ok(dialog.body.includes('data-action="retry-job"'));
    assert.equal(state.generating, null);
    assert.equal(state.photo, 'original.png');
    assert.equal(removed, 'selfit.studio.job');
  }
  console.log('Try-on failure preserves the real reason, retry action and original photo; escapes message markup: passed');
})().catch(error => {console.error(error); process.exitCode = 1;});
