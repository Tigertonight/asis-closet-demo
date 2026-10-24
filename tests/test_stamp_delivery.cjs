const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync('app/static/selfit/stamp/delivery.js', 'utf8');
function setup(fetch) {
  const context = {window:{}, crypto:require('node:crypto').webcrypto, URL, fetch, FormData, Blob, Uint8Array, AbortController, setTimeout, clearTimeout, clearInterval, TypeError};
  vm.runInNewContext(source, context);
  return new context.window.StampDelivery();
}
function bundle() {return {original:new Blob(['raw']),final:new Blob(['stamp']),settings:{stampYear:'2025-2026'}};}
function ok(value) {return {ok:true,json:async()=>value,blob:async()=>new Blob(['qr'])};}

test('lost upload response retries with the same secret and photo; duplicate taps create no extra upload', async()=>{
  const keys=[];let attempts=0;
  const delivery=setup(async(url,options)=>{
    if(options.method==='POST') {assert.equal(options.body.has('scene'),false);assert.ok(options.body.get('final') instanceof Blob);keys.push(options.headers['Idempotency-Key']);if(++attempts===1)throw new TypeError('network lost');return ok({photoId:'mp_test',expiresAt:Date.now()+86400000});}
    return ok({});
  });
  const photo=bundle();delivery.setPhoto(photo);await delivery.pending;
  assert.match(delivery.error,/网络/);
  await Promise.all([delivery.save(),delivery.save()]);
  assert.equal(keys.length,2);assert.equal(keys[0],keys[1]);assert.ok(delivery.qrUrl);
  delivery.setPhoto({...photo});await delivery.save();assert.equal(keys.length,2);
  delivery.reset();
});

test('QR failure retries retrieval without creating a second saved photo',async()=>{
  let posts=0, qrs=0;
  const delivery=setup(async(url,options)=>{
    if(options.method==='POST'){posts++;return ok({photoId:'mp_test',expiresAt:Date.now()+86400000});}
    if(++qrs===1)return {ok:false,json:async()=>({detail:'请重试'})};return ok({});
  });
  delivery.setPhoto(bundle());await delivery.pending;
  assert.equal(delivery.error,'请重试');await delivery.save();
  assert.equal(posts,1);assert.equal(qrs,2);assert.ok(delivery.qrUrl);delivery.reset();
});

test('a late response from the previous visitor cannot replace the next photo',async()=>{
  let release, attempts=0;
  const delivery=setup(async(url,options)=>{
    if(options.method==='POST') {
      if(++attempts===1) return new Promise(resolve=>{release=()=>resolve(ok({photoId:'mp_old'}));});
      return ok({photoId:'mp_new',expiresAt:Date.now()+86400000});
    }
    return ok({});
  });
  delivery.setPhoto(bundle());const previous=delivery.pending;
  delivery.setPhoto(bundle());await delivery.pending;release();await previous;
  assert.equal(delivery.record.photoId,'mp_new');assert.ok(delivery.qrUrl);delivery.reset();
});
