const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const src=fs.readFileSync('app/static/selfit-tryon/studio.js','utf8');
const action=src.slice(src.indexOf('        case "favorite": {'),src.indexOf('        case "delete-outfit":'));
(async()=>{
 for(const kind of ['note','outfit']) for(const fromFeed of [false,true]){
 const target={id:'a',kind,saved:false,name:'a',items:[{id:'shirt-a'}]};
 const other={id:'b',saved:false};const state={current:fromFeed ? other : target,items:[],outfits:[],savedNotes:[],feed:[target,other]};let requests=[];
 const ctx={state,wardrobeRequest:null,b:{dataset:fromFeed ? {favoriteId:target.id} : {}},lookup:id=>id===target.id?target:null,reference:false,JSON,encodeURIComponent,render(){},notify(){},uniqueItems:x=>x,
 normalizeOutfit:x=>({id:x.outfit_id}),normalizeItem:x=>x,
 api:async(url,options)=>{requests.push({url,options});state.current=other;
 if(url.endsWith('/wardrobe'))return {items:[],outfits:[{outfit_id:'owned-a'}]};
 return {outfit_id:'owned-a'};}};
 vm.createContext(ctx);vm.runInContext('this.run=async()=>{switch("favorite"){'+action+'}};',ctx);
 await ctx.run();assert.equal(target.saved,true);assert.equal(other.saved,false);assert.equal(state.current,other);
 if(kind==='note')assert.equal(state.savedNotes[0].id,'a');
 else {assert.equal(target.personalId,'owned-a');assert.deepEqual(JSON.parse(requests[0].options.body).item_ids,['shirt-a']);}
 }
 // A catalog card can now be clicked before its favorite snapshot arrives.
 let release;
 const target={id:'library-look',kind:'outfit',saved:false,items:[{id:'shirt'}]};
 const state={current:target,items:[],outfits:[],feed:[target]};const requests=[];
 const ctx={state,b:{dataset:{}},reference:false,JSON,encodeURIComponent,render(){},notify(){},
   wardrobeRequest:new Promise(resolve=>{release=resolve;}),normalizeItem:x=>x,normalizeOutfit:x=>({id:x.outfit_id}),
   api:async(url,options)=>{requests.push({url,options});return {items:[],outfits:[]};}};
 vm.createContext(ctx);vm.runInContext('this.run=async()=>{switch("favorite"){'+action+'}};',ctx);
 const waiting=ctx.run();assert.equal(ctx.b.disabled,true);assert.equal(requests.length,0);
 target.saved=true;target.personalId='owned';state.outfits=[{id:'owned',saved:true}];release();await waiting;
 assert.equal(requests[0].url,'/closet/outfits/owned');assert.equal(requests[0].options.method,'PATCH');
 assert.deepEqual(JSON.parse(requests[0].options.body),{favorite:false});assert.equal(target.saved,false);
 console.log('Favorites remain bound to the clicked outfit/note across navigation: passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
