const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm'), fs = require('node:fs');
const window = {location: {href:'https://selfit.test/selfit/try-on',origin:'https://selfit.test'}};
vm.runInNewContext(fs.readFileSync('app/static/selfit/selfit-image-url.js','utf8'),{window,URL});
const display = window.SelfitImageURL;

test('material and user images explicitly request WebP without changing identity/auth', () => {
  const asset = '/api/v1/material-assets/asset_'+'a'.repeat(64)+'/content';
  assert.equal(display(asset), 'https://selfit.test'+asset+'?format=webp');
  const url = new URL(display('/user-assets/tryon/job/result.png?access_token=test-only'));
  assert.equal(url.searchParams.get('access_token'),'test-only');
  assert.equal(url.searchParams.get('format'),'webp');
  assert.equal(url.pathname,'/user-assets/tryon/job/result.png');
  assert.equal(display(url.href),url.href);
});
test('generation/downloads can retrieve original while local uploads/external URLs stay intact', () => {
  assert.equal(new URL(display('/tryon-models/model.png',{original:true})).searchParams.get('format'),'original');
  for (const source of ['blob:personal-photo','data:image/png;base64,AAAA','https://cdn.test/picture.png?token=test-only']) {
    assert.equal(display(source),source);
  }
  assert.equal(display('/static/vector.svg'),'https://selfit.test/static/vector.svg');
  assert.equal(display(''),'');
});
test('static raster display and original fetch are isolated in mirror entry points', () => {
  assert.equal(new URL(display('/static/picture.webp?v=2')).searchParams.get('format'),'webp');
  const source=fs.readFileSync('app/static/selfit-tryon/studio.js','utf8');
  assert(source.includes('fetch(mediaURL(photo, true))'));
  assert(source.includes('fetch(mediaURL(state.result, true))'));
});
