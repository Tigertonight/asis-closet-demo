const assert = require('node:assert/strict');
const {test} = require('node:test');
const fs = require('node:fs');
const vm = require('node:vm');

function gestures() {
  const timers = new Map(); let next = 0;
  function node() {
    const events = new Map();
    return {addEventListener(type, fn) {if (!events.has(type)) events.set(type, []); events.get(type).push(fn);},
      removeEventListener(type, fn) {events.set(type, events.get(type).filter(f => f !== fn));},
      fire(type, props = {}) {
        const event = {button:0, pointerId:1, isPrimary:true, clientX:0, clientY:0, detail:1,
          preventDefault() {this.prevented = true;}, stopImmediatePropagation() {this.stopped = true;}, ...props};
        for (const fn of events.get(type) || []) {fn(event); if (event.stopped) break;}
        return event;
      }};
  }
  const view = node(), doc = node(), root = node();
  view.setTimeout = (fn, delay) => {timers.set(++next, {fn, delay}); return next;};
  view.clearTimeout = id => timers.delete(id);
  doc.defaultView = view; root.ownerDocument = doc; root.contains = x => Boolean(x?.card);
  function card() {
    const classes = new Set();
    const card = {isConnected:true, classList:{add:x=>classes.add(x), remove:x=>classes.delete(x)},
      closest:selector => selector === '[data-wardrobe-card]' ? card : null};
    const photo = {card, disabled:false, expanded:'false', setAttribute(key, value) {this.expanded=value;},
      focus() {this.focused=true;}, closest:selector => selector === '[data-wardrobe-hold]' ? photo : card};
    const remove = {card, hidden:true, focus() {this.focused=true;}, closest:selector => selector === '[data-wardrobe-card]' ? card : null};
    card.querySelector = selector => selector === '[data-wardrobe-hold]' ? photo : remove;
    return {card, photo, remove};
  }
  const context = vm.createContext({window:{}});
  vm.runInContext(fs.readFileSync('app/static/selfit-tryon/wardrobe-gestures.js','utf8'), context);
  const binding = context.window.SelfitWardrobeGestures.bind(root);
  return {view, doc, root, card, binding, timers, tick() {for (const [id, {fn}] of [...timers]) {timers.delete(id); fn();}}};
}

test('tap does nothing; 500ms hold only reveals and release click cannot delete', () => {
  const g = gestures(), c = g.card();
  g.doc.fire('pointerdown', {target:c.photo}); g.view.fire('pointerup'); g.tick();
  assert.equal(c.remove.hidden, true);
  g.doc.fire('pointerdown', {target:c.photo});
  assert.equal([...g.timers.values()][0].delay, 500); g.tick();
  assert.equal(c.remove.hidden, false);
  g.view.fire('pointerup');
  assert.equal(g.root.fire('click', {target:c.remove}).stopped, true);
  g.doc.fire('pointerdown', {target:c.remove});
  assert.equal(g.root.fire('click', {target:c.remove}).stopped, undefined);
});

test('scroll, movement, cancellation and blur cancel a hold without revealing', () => {
  for (const cancel of [g=>g.root.fire('scroll'), g=>g.view.fire('pointermove',{clientX:11}), g=>g.view.fire('pointercancel'), g=>g.view.fire('blur')]) {
    const g=gestures(), c=g.card(); g.doc.fire('pointerdown',{target:c.photo}); cancel(g); g.tick();
    assert.equal(c.remove.hidden,true);
  }
});

test('CTA never starts a hold; only one delete is visible and outside press dismisses', () => {
  const g=gestures(), a=g.card(), b=g.card();
  g.doc.fire('pointerdown',{target:a.remove}); g.tick(); assert.equal(a.remove.hidden,true);
  g.root.fire('contextmenu',{target:a.photo}); assert.equal(a.remove.hidden,false);
  g.root.fire('contextmenu',{target:b.photo}); assert.equal(a.remove.hidden,true); assert.equal(b.remove.hidden,false);
  g.doc.fire('pointerdown',{target:null}); assert.equal(b.remove.hidden,true);
});

test('keyboard exposes delete and Escape restores focus; render resets pending hold', () => {
  const g=gestures(), c=g.card();
  g.root.fire('keydown',{target:c.photo,key:'F10',shiftKey:true});
  assert.equal(c.remove.hidden,false); assert.equal(c.remove.focused,true);
  g.root.fire('keydown',{target:c.remove,key:'Escape'});
  assert.equal(c.remove.hidden,true); assert.equal(c.photo.focused,true);
  g.doc.fire('pointerdown',{target:c.photo}); g.binding.reset(); g.tick(); assert.equal(c.remove.hidden,true);
});

function deletion(api) {
  const studio=fs.readFileSync('app/static/selfit-tryon/studio.js','utf8');
  const code=studio.slice(studio.indexOf('  async function deleteWardrobeItem('),studio.indexOf('  async function generateForItem('));
  const item={id:'one'}, other={id:'two'}, notices=[], calls=[];
  const state={items:[item,other],outfits:[{id:'set',items:[item,other]}],current:{items:[item,other]},
    selected:new Set(['one','two']), builderIds:new Set(['one']), builderBoxes:{one:{}}, builderActive:'one',
    result:'old-result',canvasHistory:[{}],canvasFuture:[],wardrobeDeleting:''};
  const context=vm.createContext({state,reference:false,encodeURIComponent,api:async(...args)=>{calls.push(args);return api(...args);},
    normalizeItem:x=>x,normalizeOutfit:x=>x,document:{activeElement:null},render(){},updateWardrobeBusy(){},notify:x=>notices.push(x)});
  vm.runInContext(code,context);
  return {state,calls,notices,remove:()=>vm.runInContext('deleteWardrobeItem("one")',context)};
}

test('delete persists through endpoint, refreshes outfits and clears selections', async () => {
  const d=deletion(async url=>url.includes('/items/')?{}:{items:[{id:'two'}],outfits:[]});
  await d.remove();
  assert.deepEqual(d.calls.map(([url,options])=>[url,options?.method]),[['/closet/items/one','DELETE'],['/selfit/try-on/wardrobe',undefined]]);
  assert.deepEqual(Array.from(d.state.items,x=>x.id),['two']);
  assert.equal(d.state.outfits.length,0); assert.equal(d.state.selected.has('one'),false);
  assert.equal(d.state.builderIds.has('one'),false); assert.equal(d.state.builderBoxes.one,undefined);
  assert.equal(d.state.current.items.length,1); assert.equal(d.state.result,'');
  assert.equal(d.state.wardrobeDeleting,''); assert.equal(d.notices.at(-1),'已删除单品');
});

test('failed delete retains item and allows retry; concurrent clicks send one request', async () => {
  let reject;
  const d=deletion(()=>new Promise((_,no)=>{reject=no;}));
  const first=d.remove(); await d.remove(); assert.equal(d.calls.length,1);
  reject(Error('offline')); await first;
  assert.equal(d.state.items.length,2); assert.equal(d.state.selected.has('one'),true);
  assert.equal(d.state.wardrobeDeleting,''); assert.equal(d.notices.at(-1),'删除失败，请重试');
  const retry=d.remove(); assert.equal(d.calls.length,2); reject(Error('offline')); await retry;
});

test('failed wardrobe refresh cannot restore an already deleted item or hide the wardrobe', async () => {
  const d=deletion(async url=>{if(url.includes('/items/')) return {}; throw Error('offline');});
  await d.remove();
  assert.deepEqual(Array.from(d.state.items,x=>x.id),['two']);
  assert.equal(d.state.wardrobeError,undefined);
  assert.match(d.notices.at(-1),/单品已删除/);
});
