const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app/static/selfit-tryon/studio.js', 'utf8');
const loader = source.slice(source.indexOf('  async function loadFeed('), source.indexOf('  async function load()'));
const topics = ['commute', 'date', 'vacation', 'trend'].map(id => ({
  id, title: id, cover: `${id}.jpg`, previews: [],
  outfits: Array.from({length: 4}, (_, i) => ({
    outfit_id: `${id}-${i}`, title: `${id} ${i}`, cover_path: `${id}-${i}.jpg`,
    items: [{item_id: `${id}-${i}-top`}, {item_id: `${id}-${i}-shoes`}],
  })),
}));
function normalized(row) {
  return {id: row.outfit_id, name: row.title, src: row.cover_path, kind: 'outfit',
    saved: false, items: row.items.map(item => ({id: item.item_id})), raw: row};
}

(async () => {
  const state = {feed: [], items: [], outfits: [], topics: [], savedNotes: []};
  const calls = [];
  let notesFail = true, topicsFail = false;
  const context = vm.createContext({state, Date, Promise, Boolean, Math, normalizeOutfit: normalized,
    uniqueItems: rows => [...new Map(rows.map(row => [row.id, row])).values()],
    api: async (url, options) => {
      calls.push(url);
      if (url.endsWith('inspiration-notes')) {
        if (notesFail) throw Error('notes unavailable');
        return {notes: [], saved_notes: []};
      }
      if (url.endsWith('inspiration-topics')) {
        if (topicsFail) throw Error('topics unavailable');
        return {topics, total: 16};
      }
      const request = JSON.parse(options.body);
      return {outfits: request.offset ? [topics[0].outfits[0]] : [], has_more: true, next_offset: 12};
    },
  });
  vm.runInContext(loader, context);
  await vm.runInContext('loadFeed()', context);
  assert.equal(state.topics.length, 4);
  assert.equal(state.feed.length, 16, 'topics remain visible if persona notes fail');
  assert.equal(state.topics.flatMap(x => x.entries).length, 16);
  assert(state.feed.every(x => x.kind === 'outfit' && x.items.length === 2), 'use structured try-on, not photo-only note jobs');
  assert(state.feedError);
  await vm.runInContext('loadFeed(true)', context);
  assert.equal(state.feed.length, 16, 'pagination must not duplicate topic outfits');
  assert.equal(calls.filter(x => x.endsWith('inspiration-topics')).length, 1);
  state.outfits = [{id: 'personal-copy', saved: true, items: [{id: 'commute-0-top'}, {id: 'commute-0-shoes'}]}];
  notesFail = false;
  await vm.runInContext('loadFeed()', context);
  for (const row of [state.feed[0], state.topics[0].entries[0]]) {
    assert.equal(row.saved, true);
    assert.equal(row.personalId, 'personal-copy');
  }
  topicsFail = true;
  await vm.runInContext('loadFeed()', context);
  assert.equal(state.topics.length, 4, 'a recoverable refresh failure retains visible themes');
  assert(state.feedError);
  assert.equal(state.feedBusy, false);
  console.log('Four inspiration themes: structured outfits, partial recovery, pagination and favorites passed.');
})().catch(error => {console.error(error); process.exitCode = 1;});
