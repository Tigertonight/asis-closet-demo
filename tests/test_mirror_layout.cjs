const {test}=require('node:test');
const assert=require('node:assert/strict');
const {layout,category,delicate,GAP}=require('../app/static/selfit-tryon/mirror-layout.js');
const piece=(id,category,aspect=1,name='')=>({id,category,aspect,name});
const outfit=[piece('coat','outer',.91),piece('top','top',.85),piece('skirt','skirt',.93,'浅蓝斜襟迷你裙'),piece('bag','bag',.89),piece('socks','socks',.26),piece('chain','accessory',.52,'金色方坠项链'),piece('earrings','accessory',.96,'金色小圈耳饰'),piece('glasses','accessory',2.4,'细金属框眼镜'),piece('ring','accessory',2.26,'金色细戒指'),piece('shoes','shoes',1.65)];
function separated(boxes) {
 for(const b of boxes) {
  assert.ok([b.x,b.y,b.w,b.h].every(Number.isFinite));
  assert.ok(b.x>=0 && b.y>=0 && b.w>0 && b.h>0 && b.x+b.w<=100 && b.y+b.h<=100);
  assert.ok(b.x>=b.zone.x+1-1e-8 && b.y>=b.zone.y+1-1e-8);
  assert.ok(b.x+b.w<=b.zone.x+b.zone.w-1+1e-8 && b.y+b.h<=b.zone.y+b.zone.h-1+1e-8);
 }
 for(let i=0;i<boxes.length;i++)for(let j=i+1;j<boxes.length;j++) {
  const a=boxes[i],b=boxes[j];
  assert.ok(a.x+a.w+GAP<=b.x || b.x+b.w+GAP<=a.x || a.y+a.h+GAP<=b.y || b.y+b.h+GAP<=a.y,`${a.id} overlaps ${b.id}`);
 }
}
test('filename classification prioritizes dresses, handles Chinese mini skirts and leaves unknowns pending',()=>{
 assert.equal(category({filename:'03_迷你裙.png'}),'skirt');
 assert.equal(category({src:'/uploads/%E8%BF%9E%E8%A1%A3%E8%A3%99.png'}),'dress');
 assert.equal(category({name:'黑色长裤'}),'pants');
 assert.equal(category({name:'item_31.png'}),null);
 assert.deepEqual(layout([piece('unknown','unclassified')]),[]);
});
test('ten-piece outfit preserves every silhouette with margins and balanced columns',()=>{
 const before=JSON.stringify(outfit),boxes=layout(outfit);
 assert.equal(boxes.length,outfit.length);separated(boxes);
 assert.equal(JSON.stringify(outfit),before);
 const left=boxes.filter(b=>b.zone.x===4);
 const tops=left.filter(b=>['outer','top'].includes(b.category));
 assert.ok(tops.length>=1 && tops.length<=2);
 assert.ok(left.some(b=>b.category==='skirt'));
 for(const b of boxes) {
  const p=outfit.find(p=>p.id===b.id);
  assert.ok(Math.abs(b.w*(207/437)/b.h-p.aspect)<1e-8);
 }
 assert.ok(boxes.find(b=>b.id==='coat').z<boxes.find(b=>b.id==='top').z);
});
test('builder preview keeps complete silhouettes in its wider 3:4 frame',()=>{
 const boxes=layout(outfit,{frameAspect:3/4,region:{x:4,y:4,w:92,h:92}});
 assert.equal(boxes.length,outfit.length);separated(boxes);
 for(const box of boxes) {
  const item=outfit.find(item=>item.id===box.id);
  assert.ok(Math.abs(box.w*(3/4)/box.h-item.aspect)<1e-8);
 }
});
test('ordinary visible areas follow the agreed 1 : 2/3 : 2/9 ratios',()=>{
 const boxes=layout([piece('coat','outer'),piece('top','top'),piece('pants','bottom'),piece('shoe','shoes')]);
 const area=id=>{const b=boxes.find(b=>b.id===id);return b.w*b.h;};
 assert.ok(Math.abs(area('coat')/area('top')-1.5)<1e-8);
 assert.ok(Math.abs(area('top')/area('shoe')-3)<1e-8);
});
test('same-item image replacement retains zones, IDs and manual scale',()=>{
 const first=layout(outfit).map(b=>b.id==='top'?{...b,manualScale:.7}:b);
 const next=layout(outfit.map(p=>p.id==='top'?{...p,src:'/different.png',aspect:2.6}:p),{previous:first});
 separated(next);
 assert.equal(next.find(b=>b.id==='top').manualScale,.7);
 for(const b of next) {
  const old=first.find(p=>p.id===b.id);
  assert.deepEqual(b.zone,old.zone);
  if(b.id!=='top') assert.deepEqual(b,old);
 }
 const replacement=layout(outfit.map(p=>p.id==='top'?{...p,id:'new-top',mirrorLayoutId:'top'}:p),{previous:first});
 assert.equal(replacement.find(b=>b.id==='new-top').layoutId,'top');
 assert.deepEqual(replacement.find(b=>b.id==='new-top').zone,first.find(b=>b.id==='top').zone);
});
test('thin accessories stay legible without applying wire treatment to lace clothing',()=>{
 assert.equal(delicate(piece('chain','accessory',.4,'细链项链')),true);
 assert.equal(delicate({...piece('wire','accessory'),inkRatio:.06}),true);
 assert.equal(delicate({...piece('lace','top'),inkRatio:.06}),false);
 const fine=layout([piece('coat','outer'),piece('a','accessory',1,'细链')]);
 assert.ok(fine.find(b=>b.id==='a').w>=14 && fine.find(b=>b.id==='a').w<=24);
 separated(fine);
});
test('compact accessory rows preserve breathing room without overlapping neighbors',()=>{
 const boxes=layout(outfit),fine=boxes.filter(b=>b.delicate);
 assert.ok(fine.some((a,i)=>fine.some((b,j)=>j>i && a.zone.y===b.zone.y)),'adjacent accessories share a row');
 const expanded=boxes.map(b=>({...b,x:b.x-(b.delicate?1.8:0),y:b.y-(b.delicate?1.8:0),w:b.w+(b.delicate?3.6:0),h:b.h+(b.delicate?3.6:0)}));
 for(const b of expanded) {
  assert.ok(b.x>=b.zone.x && b.y>=b.zone.y);
  assert.ok(b.x+b.w<=b.zone.x+b.zone.w && b.y+b.h<=b.zone.y+b.zone.h);
 }
 for(let i=0;i<expanded.length;i++)for(let j=i+1;j<expanded.length;j++) {
  const a=expanded[i],b=expanded[j];
  assert.ok(a.x+a.w+GAP<=b.x || b.x+b.w+GAP<=a.x || a.y+a.h+GAP<=b.y || b.y+b.h+GAP<=a.y);
 }
 const rows=[...new Map(boxes.filter(b=>b.zone.x===4).map(b=>[b.zone.y,b.zone])).values()].sort((a,b)=>a.y-b.y);
 for(let i=1;i<rows.length;i++) assert.ok(Math.abs(rows[i].y-rows[i-1].y-rows[i-1].h-GAP)<1e-8);
});
test('necklaces and glasses stay above the outfit while bags and wrist pieces sit below a top',()=>{
 const pieces=[...outfit,piece('bracelet','accessory',1.4,'细链手链'),piece('bangle','accessory',1,'金色手镯')];
 const boxes=layout(pieces),get=id=>boxes.find(b=>b.id===id);
 separated(boxes);
 const upperY=Math.min(get('top').zone.y,get('coat').zone.y);
 for(const id of ['chain','glasses','earrings']) assert.ok(get(id).zone.y+get(id).zone.h+GAP<=upperY+1e-8);
 for(const id of ['bag','bracelet','bangle']) assert.ok(get(id).y>=Math.min(get('top').y+get('top').h,get('coat').y+get('coat').h));
 const simple=layout([piece('top','top'),piece('skirt','skirt'),piece('bag','bag'),piece('bracelet','accessory',1,'细链手链')]);
 const top=simple.find(b=>b.id==='top');
 for(const id of ['bag','bracelet']) assert.ok(simple.find(b=>b.id===id).y>=top.y+top.h);
});
test('earrings remain small even when manually enlarged to the maximum',()=>{
 const first=layout(outfit),earrings=first.find(b=>b.id==='earrings');
 assert.ok(earrings.w<=8.1);
 const enlarged=layout(outfit,{previous:first.map(b=>b.id==='earrings'?{...b,manualScale:1.5}:b)});
 const next=enlarged.find(b=>b.id==='earrings');
 assert.ok(next.w<=10 && next.h<=6);
 for(const b of enlarged.filter(b=>b.id!=='earrings')) assert.deepEqual(b,first.find(old=>old.id===b.id));
 separated(enlarged);
});
test('crowded drafts and extreme aspect ratios never overlap or drop an item',()=>{
 for(const n of [1,2,8,16]) {
  const pieces=Array.from({length:n},(_,i)=>piece('item-'+i,['outer','top','pants','skirt','dress','bag','accessory','shoes'][i%8],[.15,.5,1,3,9][i%5]));
  const boxes=layout(pieces);assert.equal(boxes.length,n);separated(boxes);
 }
 separated(layout(Array.from({length:16},(_,i)=>piece('chain-'+i,'accessory',.15,'细链'))));
});
test('mirror selection inherits presentation slots while passing the new real ID to try-on',()=>{
 const fs=require('node:fs'),vm=require('node:vm');
 const source=fs.readFileSync('app/static/selfit-tryon/studio.js','utf8');
 const old=[piece('old-top','top',1),piece('pants','bottom',.5),piece('bag','bag',1)];
 const boxes=layout(old).map(b=>b.id==='old-top'?{...b,manualScale:.7}:b);
 const replacement={...piece('new-top','top',1.4),src:'/new-top.png'};
 const context={state:{page:'mirror',current:{id:'outfit',items:old,mirrorLayout:boxes}},reference:false,
  lookup:()=>replacement,$:()=>({scrollLeft:0,scrollTop:0}),rememberCanvas:()=>{},go:()=>{},notify:()=>{},
  window:{SelfitMirrorLayout:require('../app/static/selfit-tryon/mirror-layout.js'),SelfitOutfitLayout:require('../app/static/selfit-tryon/outfit-layout.js')}};
 vm.createContext(context);
 vm.runInContext(source.slice(source.indexOf('  function chooseItem('),source.indexOf('  async function photoFile(')),context);
 context.chooseItem('new-top');
 assert.deepEqual(Array.from(context.state.selected),['pants','bag','new-top']);
 const newTop=context.state.current.items.find(p=>p.id==='new-top');
 assert.equal(newTop.mirrorLayoutId,'old-top');
 const next=layout(context.state.current.items,{previous:context.state.current.mirrorLayout});
 assert.equal(next.find(b=>b.id==='new-top').manualScale,.7);
 assert.deepEqual(next.find(b=>b.id==='new-top').zone,boxes.find(b=>b.id==='old-top').zone);
});
