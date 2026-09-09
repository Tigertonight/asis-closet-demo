const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app/static/selfit-tryon/studio.js', 'utf8');
const startCode = source.slice(source.indexOf('  async function startTry()'), source.indexOf('  function beginMirrorGeneration('));
const generateCode = source.slice(source.indexOf('  async function generate()'), source.indexOf('  function failure('));
const generateNoteCode = source.slice(source.indexOf('  async function generateNote()'), source.indexOf('  async function generate()'));
const outfit = () => ({id: 'set-a', kind: 'outfit', items: ['top', 'bottom', 'shoes', 'bag'].map(id => ({id}))});

(async () => {
  const state = {current: outfit(), photo: 'photo-a', personalPhoto: 'photo-a', selected: new Set(['top'])};
  const calls = [], notices = [], dialogs = [], failures = [];
  let resolvePhoto, failRequest = false, uuid = 0;
  const context = vm.createContext({
    state, FormData, Set, reference: false, generationBusy: false,
    crypto: {randomUUID: () => `request-${++uuid}`},
    photoFile: (photo) => {calls.push({photo}); return new Promise(resolve => {resolvePhoto = resolve;});},
    beginMirrorGeneration: (target, photo) => {state.generating = {target, photo}; state.job = null;},
    sessionStorage: {setItem() {}}, poll() {},
    failure: message => {state.generating = null; failures.push(message);},
    notify: message => notices.push(message), modal: (title) => dialogs.push(title), models: () => dialogs.push('models'),
    api: async (url, options) => {
      calls.push({url, options});
      if (failRequest) throw Error('network unavailable');
      if (url === '/selfit/try-on/outfits') return {outfit_id: 'saved-set'};
      assert(['/selfit/try-on/jobs', '/selfit/try-on/inspiration-jobs'].includes(url), 'no preview request');
      return {job_id: 'job-a', status: 'queued'};
    },
  });
  vm.runInContext(startCode + generateCode + generateNoteCode, context);
  const pending = vm.runInContext('startTry()', context);
  assert.equal(state.generating.target.id, 'set-a', 'show loading before preparing the photo');
  await vm.runInContext('startTry()', context);
  assert.equal(calls.length, 1, 'double click does not start another request');
  state.current = {id: 'set-b', items: [{id: 'different-top'}]};
  state.selected = new Set(['different-top']);
  state.photo = 'photo-b';
  resolvePhoto(new Blob(['photo-a']));
  await pending;
  const request = calls.at(-1).options.body;
  assert.equal(request.get('outfit_id'), 'set-a', 'keep the outfit selected at click time');
  assert.deepEqual(JSON.parse(request.get('selected_item_ids')), ['top', 'bottom', 'shoes', 'bag']);
  assert.equal(request.get('wear_all_items'), 'true');
  assert.equal(dialogs.length, 0);

  state.current = outfit(); state.current.id = ''; state.job = null;
  const unsaved = vm.runInContext('startTry()', context);
  resolvePhoto(new Blob(['photo-b'])); await unsaved;
  const create = calls.find(call => call.url === '/selfit/try-on/outfits');
  assert.deepEqual(JSON.parse(create.options.body).item_ids, ['top', 'bottom', 'shoes', 'bag']);
  assert.equal(calls.at(-1).options.body.get('outfit_id'), 'saved-set');

  state.current = outfit(); state.job = null; failRequest = true;
  const failed = vm.runInContext('startTry()', context);
  resolvePhoto(new Blob(['photo-b'])); await failed;
  assert.equal(state.generating, null);
  assert.equal(failures.length, 1);
  const retryId = calls.at(-1).options.body.get('client_request_id');
  failRequest = false;
  const retry = vm.runInContext('startTry()', context);
  resolvePhoto(new Blob(['photo-b'])); await retry;
  assert.equal(calls.at(-1).options.body.get('client_request_id'), retryId, 'network retry is idempotent');
  state.job = null; state.photo = '';
  await vm.runInContext('startTry()', context);
  assert.equal(dialogs.at(-1), 'models');
  state.current = {id:'note:mute:outfits-01', kind:'note', items:[]};
  state.photo = 'photo-a'; state.job = null;
  const before = calls.length, dialogCount = dialogs.length;
  const note = vm.runInContext('startTry()', context);
  assert.equal(state.generating.target.id, 'note:mute:outfits-01', 'notes show loading immediately');
  assert.equal(dialogs.length, dialogCount, 'notes do not require a confirmation click');
  await vm.runInContext('startTry()', context);
  assert.equal(calls.length, before + 1, 'repeated note clicks must not duplicate the request');
  resolvePhoto(new Blob(['photo-a'])); await note;
  assert.equal(calls.at(-1).url, '/selfit/try-on/inspiration-jobs');
  assert.equal(calls.at(-1).options.body.get('note_id'), 'note:mute:outfits-01');
  assert(calls.at(-1).options.body.get('person_image'));
  assert(calls.at(-1).options.body.get('client_request_id'));
  // Browsing a notebook image must not replace a finished result or submit a try-on.
  const previewCode = source.slice(source.indexOf('  function openNotePreview('), source.indexOf('  function showDetail('));
  state.current = outfit(); state.result = '/completed-result.png'; state.page = 'mirror';
  const original = JSON.stringify(state), beforePreview = calls.length;
  const previewNote = {id:'another-note', name:'另一张笔记', src:'/notebook-original.png'};
  let preview;
  Object.assign(context, {lookup:id=>id===previewNote.id ? previewNote : null, esc:s=>s,
    image:(src,alt)=>({src,alt}), modal:(title,body)=>{preview={title,body};},
    $:()=>({classList:{add(){}}})});
  vm.runInContext(previewCode, context);
  vm.runInContext("openNotePreview('another-note')", context);
  assert.equal(preview.body.src,previewNote.src,'show the exact notebook image');
  assert.equal(JSON.stringify(state),original,'keep result, selection and active page');
  assert.equal(calls.length,beforePreview,'image preview never starts generation');
  console.log('Direct outfit and note submission, immediate loading, duplicate prevention, snapshot, save, retry and photo recovery passed.');
})().catch(error => {console.error(error); process.exitCode = 1;});
