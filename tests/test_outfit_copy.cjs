const {test}=require('node:test');
const assert=require('node:assert/strict');
const {create}=require('../app/static/selfit-app/outfit-copy.js');
const item=(category,title,colors,color_hex=[])=>({category,title,attributes:{colors,color_hex}});
test('copy describes garments rather than inventory titles or carousel order',()=>{
 const card={title:'MUTE 日常 07',items:[item('top','Polo 针织',['黑','蓝'],['#171927']),item('bottom','烟管裤',['灰','白'],['#c4c1bb'])]};
 const c=create(card);assert.equal(c.title,'藏蓝针织与浅灰裤装');assert.match(c.reason,/深浅对比/);
 assert.deepEqual(create({...card,title:'我的搭配'}),c);
 assert.ok(!/雨|好走|显高|气温/.test(c.reason));
});
test('missing data and single garments do not invent pieces',()=>{
 assert.match(create({items:[]}).reason,/查看/);
 const c=create({items:[item('dress','连衣裙',['red'])]});
 assert.match(c.reason,/红色连衣裙/);assert.ok(!c.reason.includes('裤'));
});
test('floral description needs floral garment evidence',()=>{
 const c=create({items:[item('top','衬衫',['white']),item('skirt','碎花半身裙',['pink'])]});
 assert.equal(c.tag,'印花点缀');assert.match(c.reason,/印花半身裙/);
});
