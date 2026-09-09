const {test}=require('node:test');
const assert=require('node:assert/strict');
const {layout}=require('../app/static/selfit-tryon/outfit-layout.js');
const p=(id,category,name='')=>({id,category,name});
for(const [name,items] of [
 ['long skirt',[p('t','top'),p('s','skirt'),p('h','accessory','贝雷帽'),p('b','bag'),p('f','shoes')]],
 ['pants',[p('t','top'),p('p','bottom'),p('f','shoes')]],
 ['short skirt',[p('t','top'),p('s','skirt','短裙')]],
 ['dress and coat',[p('d','dress'),p('o','outer'),p('f','shoes')]],
 ['layering',[p('t','top'),p('o','outer'),p('p','bottom')]],
 ['incomplete',[p('t','top')]]
])test(name+' preserves every piece inside the frame',()=>{
 const boxes=layout(items);assert.equal(boxes.length,items.length);
 assert.equal(new Set(boxes.map(b=>b.id)).size,items.length);
 for(const b of boxes){assert.ok(b.x>=0&&b.y>=0&&b.x+b.w<=100&&b.y+b.h<=100);}
});
test('hat and bag do not overlap; long skirt gets more height than short skirt',()=>{
 const boxes=layout([p('t','top'),p('s','skirt'),p('h','accessory','贝雷帽'),p('b','bag')]);
 const h=boxes.find(b=>b.id==='h'),bag=boxes.find(b=>b.id==='b');assert.ok(h.y+h.h<=bag.y);
 const short=layout([p('t','top'),p('s','skirt','短裙')]).find(b=>b.id==='s');assert.ok(boxes.find(b=>b.id==='s').h>short.h);
});

test('two columns keep complete tall boots clear of the garments',()=>{
 const items=[p('t','top'),p('s','skirt'),p('b','bag'),{...p('f','shoes'),raw:{title:'黑色长靴'}}];
 const boxes=layout(items);
 assert.equal(new Set(boxes.map(b=>b.zone.x)).size,2);
 const boot=boxes.find(b=>b.id==='f'),skirt=boxes.find(b=>b.id==='s');
 const flat=layout([p('f','shoes','芭蕾鞋')])[0];
 assert.ok(boot.h/boot.w>flat.h/flat.w);
 assert.ok(skirt.x+skirt.w<boot.x || boot.x+boot.w<skirt.x || skirt.y+skirt.h<boot.y || boot.y+boot.h<skirt.y);
 const bag=boxes.find(b=>b.id==='b');assert.ok(bag.x+bag.w<=94);
});

test('selecting pants replaces a skirt without stacking, while keeping other pieces',()=>{
 const {replacePiece}=require('../app/static/selfit-tryon/outfit-layout.js');
 const original=[p('t','top'),p('s','skirt'),p('f','shoes')];
 const next=replacePiece(original,p('p','bottom'));
 assert.deepEqual(next.map(x=>x.id),['t','f','p']);
 assert.deepEqual(replacePiece(next,p('s2','skirt')).map(x=>x.id),['t','f','s2']);
 assert.deepEqual(replacePiece(next,p('d','dress')).map(x=>x.id),['f','d']);
 assert.deepEqual(replacePiece([p('d','dress')],p('t','top')).map(x=>x.id),['t']);
 assert.deepEqual(replacePiece([],p('p','bottom')).map(x=>x.id),['p']);
});
