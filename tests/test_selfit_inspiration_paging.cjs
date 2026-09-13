const {test}=require('node:test');
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const pagerCode=fs.readFileSync('app/static/selfit-tryon/inspiration-pager.js','utf8');
const source=fs.readFileSync('app/static/selfit-tryon/studio.js','utf8');
function harness(observers=true) {
  const images=[],watches=[];
  class Image {constructor(){images.push(this);} set src(value){this.url=value;}}
  class IntersectionObserver {
    constructor(callback,options){this.callback=callback;this.options=options;watches.push(this);}
    observe(target){this.target=target;}
    disconnect(){this.disconnected=true;}
    hit(){this.callback([{isIntersecting:true}]);}
  }
  const context=vm.createContext({Image,IntersectionObserver:observers?IntersectionObserver:undefined});
  vm.runInContext(pagerCode,context);
  return {pager:context.SelfitInspirationPager,images,watches};
}
test('one screen ahead triggers exactly once, detached or previous observers cannot append',()=>{
  const h=harness(),root={clientHeight:844},sentinel={isConnected:true},context={};let more=0;
  const watch=()=>h.pager.watch({root,sentinel,context,onMore:()=>more++});
  watch();assert.equal(h.watches[0].options.root,root);assert.equal(h.watches[0].options.rootMargin,'844px 0px');
  h.watches[0].hit();h.watches[0].hit();assert.equal(more,1);
  watch();sentinel.isConnected=false;h.watches[1].hit();assert.equal(more,1);
  sentinel.isConnected=true;watch();h.watches[1].hit();assert.equal(more,1);
  h.pager.reset();h.watches[2].hit();assert.equal(more,1,'leaving/resetting the library cancels observation');
});
test('prewarming shares URLs, caps concurrent images at four and advances after errors',()=>{
  const h=harness();const urls=Array.from({length:12},(_,i)=>`/preview-${i}.webp`);
  h.pager.preload([...urls,...urls]);assert.equal(h.images.length,4);
  assert(h.images.every(x=>x.fetchPriority==='low'&&x.decoding==='async'));
  h.images[0].onerror();assert.equal(h.images.length,5,'a broken preview cannot block the queue');
  for(let i=1;i<12;i++)h.images[i].onload();
  assert.deepEqual(h.images.map(x=>x.url),urls);
  h.pager.preload(urls);assert.equal(h.images.length,12,'already warmed URLs do not repeat');
});
test('gender/catalog change discards queued previews, while active requests remain bounded',()=>{
  const h=harness();const root={clientHeight:844},sentinel={isConnected:true};
  h.pager.watch({root,sentinel,context:'female',onMore(){}});
  h.pager.preload(Array.from({length:12},(_,i)=>`/female-${i}.webp`));
  h.pager.watch({root,sentinel,context:'male',onMore(){}});
  h.pager.preload(['/male.webp']);assert.equal(h.images.length,4);
  h.images[0].onload();assert.equal(h.images[4].url,'/male.webp');
  for(let i=1;i<5;i++)h.images[i].onload();assert.equal(h.images.length,5);
});
test('manual loading remains available without IntersectionObserver',()=>{
  const h=harness(false);h.pager.watch({root:{clientHeight:800},sentinel:{isConnected:true},context:{},onMore(){throw Error('automatic callback');}});
  assert.equal(h.watches.length,0);
});
test('cards append 12 at a time, prewarm only that batch, preserve existing nodes and stop at the end',()=>{
  const notes=Array.from({length:29},(_,i)=>({id:`note-${i}`,name:`穿搭 ${i}`,src:`/${i}.webp`,saved:i===16,raw:{gender:'female'},items:[{id:`shirt-${i}`}]}));
  const state={page:'inspiration',modelGender:'female',inspirationLimit:12,feed:notes,topics:[{id:'persona-1',kind:'persona',title:'型格',entries:notes}]};
  const existing={identity:'original image node'};const columns=[0,1].map(()=>({existing,html:'',insertAdjacentHTML(position,html){assert.equal(position,'beforeend');this.html+=html;}}));
  const warmed=[];let sentinel={isConnected:true,remove(){sentinel=null;}};
  const context=vm.createContext({state,document:{querySelectorAll:()=>columns},
    $:selector=>selector==='#screen'?{clientHeight:844,scrollTop:1120}:sentinel,
    window:{SelfitInspirationPager:{preload:urls=>warmed.push([...urls]),watch(){},reset(){}}},
    mirrorImageSource:x=>x,esc:String,image:(src,alt,cls,lazy)=>`<img src="${src}" loading="${lazy?'lazy':'eager'}">`,
    uniqueItems:rows=>[...new Map(rows.map(row=>[row.id,row])).values()],render(){throw Error('must append without a full rerender');}});
  vm.runInContext(source.slice(source.indexOf('  function libraryTopics()'),source.indexOf('  function detail()')),context);
  let html=vm.runInContext('inspiration()',context);
  assert.equal((html.match(/data-try=/g)||[]).length,12);
  assert(html.includes('data-inspiration-next'));
  vm.runInContext('showMoreInspiration()',context);
  assert.equal(state.inspirationLimit,24);assert.deepEqual(warmed[0],notes.slice(12,24).map(x=>x.src));
  assert.equal(columns[0].existing,existing);assert.equal(columns[1].existing,existing);
  assert(columns.map(x=>x.html).join('').includes('aria-pressed="true"'),'appended saved card preserves its state');
  vm.runInContext('showMoreInspiration()',context);
  assert.equal(state.inspirationLimit,29);assert.equal(sentinel,null);
  assert.deepEqual(warmed[1],notes.slice(24).map(x=>x.src));
  vm.runInContext('showMoreInspiration()',context);assert.equal(warmed.length,2);
  const appended=columns.map(x=>x.html).join('');
  assert.equal((appended.match(/data-try=/g)||[]).length,17);
  assert.equal(new Set([...appended.matchAll(/data-try="([^"]+)"/g)].map(x=>x[1])).size,17);
  assert(!vm.runInContext('inspiration()',context).includes('data-inspiration-next'));
  state.page='detail';state.inspirationLimit=12;vm.runInContext('showMoreInspiration()',context);
  assert.equal(state.inspirationLimit,12,'late observation cannot append on another page');
});
