const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const studio = fs.readFileSync('app/static/selfit-tryon/studio.js','utf8');
const code = studio.slice(studio.indexOf('  function wardrobeItemGroups('),studio.indexOf('  function feedCard('));
const items = [
  ...Array.from({length:5},(_,i)=>({id:`top-${i}`,category:i===4?'outer':'top',name:`上装 ${i}`,src:'/top.png'})),
  {id:'skirt',category:'skirt',name:'半裙',src:'/skirt.png'},
  {id:'dress',category:'dress',name:'连衣裙',src:'/dress.png'},
  {id:'suit',category:'jumpsuit',name:'连体裤',src:'/suit.png'},
  {id:'bag',category:'bag',name:'托特包',src:'/bag.png'},
  {id:'scarf',category:'scarf',name:'围巾',src:'/scarf.png'},
  {id:'unknown',category:'new-category',name:'新单品',src:'/other.png'},
  {id:'deleted',category:'shoes',name:'已删除',src:'/shoe.png',raw:{deleted:true}},
];
const state={items,closetCategory:'all',outfits:[{id:'my-set',name:'我的套装'}],savedNotes:[]};
const context=vm.createContext({state,items,esc:String,image:(src)=>`<img src="${src}">`,
  uniqueItems:rows=>rows,card:(row)=>`<button data-outfit="${row.id}">${row.name}</button>`,
  pendingImport:()=>null,wardrobeEmpty:()=>'<div class="wardrobe-empty">添加单品</div>'});
vm.runInContext(code,context);
const groups=vm.runInContext('wardrobeItemGroups(items)',context);
assert.deepEqual(Array.from(groups,g=>g.id),['top','bottom','dress','bag','accessory','other']);
assert.equal(groups[0].items.length,5);
assert.equal(groups.find(g=>g.id==='dress').items.length,2);
assert.equal(new Set(groups.flatMap(g=>Array.from(g.items,i=>i.id))).size,11);
const html=vm.runInContext('closet()',context);
assert.equal((html.match(/class="wardrobe-items-row"/g)||[]).length,6);
assert.doesNotMatch(html,/wardrobe-filters|wardrobe-group-shoes|wardrobe-group-hat/);
assert.match(html,/data-wardrobe-hold="top-4"/);
assert.doesNotMatch(html,/wardrobe-item-name|data-item=|title=/);
assert.equal((html.match(/>帮我搭配<\/button>/g)||[]).length,11);
assert.equal((html.match(/data-action="delete-item"[^>]* hidden/g)||[]).length,11);
assert.equal((html.match(/<article class="card item-card"/g)||[]).length,11);
state.closetCategory='set';
const outfits=vm.runInContext('closet()',context);
assert.match(outfits,/closet-grid/);
assert.doesNotMatch(outfits,/wardrobe-items-row/);
state.closetCategory='all';state.items=[];
assert.match(vm.runInContext('closet()',context),/wardrobe-empty/);
assert.deepEqual(Array.from(vm.runInContext('wardrobeItemGroups([])',context)),[]);
console.log('Category grouping, hidden empty categories, retained items and outfit tab passed.');
