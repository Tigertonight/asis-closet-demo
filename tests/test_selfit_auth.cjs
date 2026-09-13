const assert = require('node:assert/strict');
const {test} = require('node:test');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app/static/selfit/selfit-auth.js','utf8');
const key = 'selfit.auth.session.v2', inviteKey = 'selfit.auth.invite.v1';
const user = {user_id:'same-account',beta_qualified:true};
const stored = {accessToken:'expired-test-token',expiresAt:'2000-01-01T00:00:00Z',user};
const creds = {invite_code:'TEST-ONLY',device_id:'test-device'};
const response = (status,payload) => ({ok:status<400,status,json:async()=>payload});
function harness(session=stored, invite=creds, handler) {
  const data = new Map(), calls = [];
  if(session)data.set(key,JSON.stringify(session));
  if(invite)data.set(inviteKey,JSON.stringify(invite));
  const storage = {getItem:k=>data.get(k)||null,setItem:(k,v)=>data.set(k,v),removeItem:k=>data.delete(k)};
  const window = {crypto:require('node:crypto').webcrypto};
  vm.runInNewContext(source,{window,localStorage:storage,sessionStorage:{getItem:()=>null,removeItem(){}},
    AbortController,setTimeout,clearTimeout,fetch:async(url,options)=>{calls.push({url,options});return handler(url,options);}});
  const client=window.SelfitAuth.createClient({mode:'live'});
  return {client,data,calls};
}
test('expired token restores same account and keeps refreshed expiry, never creates guest',async()=>{
 const h=harness(stored,creds,(url,opts)=>{
  if(url==='/auth/invite/verify')return response(200,{access_token:'renewed',expires_in_seconds:2592000,user});
  assert.equal(url,'/auth/me');
  return opts.headers.Authorization.endsWith('renewed') ? response(200,{user}) : response(401,{detail:'expired'});
 });
 const session=await h.client.ensureVisitor();
 assert.equal(session.accessToken,'renewed');assert.equal(session.user.user_id,user.user_id);
 assert(Date.parse(session.expiresAt)>Date.now()+86400000);
 assert.equal(JSON.parse(h.data.get(key)).expiresAt,session.expiresAt);
 assert.deepEqual(h.calls.map(x=>x.url),['/auth/me','/auth/invite/verify','/auth/me']);
 assert(h.data.has(inviteKey));
});
test('server sliding expiry wins over expired browser metadata',async()=>{
 const h=harness(stored,null,()=>response(200,{user}));
 assert.equal((await h.client.ensureVisitor()).user.user_id,user.user_id);
 assert.deepEqual(h.calls.map(x=>x.url),['/auth/me']);
});
test('token missing still recovers saved invite credentials',async()=>{
 const h=harness(null,creds,url=>response(200,url.endsWith('/verify') ? {access_token:'restored',user} : {user}));
 assert.equal((await h.client.ensureVisitor()).accessToken,'restored');
 assert.deepEqual(h.calls.map(x=>x.url),['/auth/invite/verify','/auth/me']);
});
test('invalid authentication and network failures preserve identity and credentials',async()=>{
 for(const status of [401,410,503]) {
  const h=harness(stored,creds,()=>response(status,{detail:'not available'}));
  await assert.rejects(h.client.ensureVisitor());
  assert.equal(JSON.parse(h.data.get(key)).user.user_id,user.user_id);
  assert(h.data.has(inviteKey));assert(!h.calls.some(x=>x.url.endsWith('/guest')));
 }
 const h=harness(stored,creds,()=>{throw new TypeError('offline');});
 await assert.rejects(h.client.ensureVisitor(),/网络/);
 assert.equal((await h.client.restore()).user.user_id,user.user_id);
});
test('unrecoverable existing visitor also cannot silently become a new guest',async()=>{
 const guest={...stored,user:{user_id:'guest-existing',beta_qualified:false}};
 const h=harness(guest,null,()=>response(401,{detail:'expired'}));
 await assert.rejects(h.client.ensureVisitor(),error=>error.status===401);
 assert.equal(h.calls.length,1);assert(h.data.has(key));
});
test('fresh visitor only and explicit logout clear credentials',async()=>{
 const h=harness(null,null,()=>response(200,{access_token:'guest-test',user:{user_id:'guest-new'}}));
 await h.client.ensureVisitor();assert.equal(h.calls[0].url,'/auth/guest');
 h.data.set(inviteKey,JSON.stringify(creds));h.client.clear();
 assert(!h.data.has(key));assert(!h.data.has(inviteKey));
});
test('fresh /me authority overrides stale local beta flag',async()=>{
 const h=harness(stored,null,()=>response(200,{user:{...user,beta_qualified:false}}));
 assert.equal((await h.client.ensureVisitor()).user.beta_qualified,false);
});
test('silent recovery never switches accounts',async()=>{
 const h=harness(stored,creds,url=>url.endsWith('/me') ? response(401,{}) : response(200,{access_token:'different',user:{user_id:'different'}}));
 await assert.rejects(h.client.ensureVisitor(),error=>error.code==='auth.account_changed');
 assert.equal(JSON.parse(h.data.get(key)).user.user_id,user.user_id);
});
