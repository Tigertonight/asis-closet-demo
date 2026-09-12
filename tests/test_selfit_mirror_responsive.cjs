const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');
const root = path.resolve(__dirname, '../app/static');
const source = fs.readFileSync(path.join(root, 'selfit-tryon/studio.js'), 'utf8');
const css = fs.readFileSync(path.join(root, 'selfit-tryon/mirror-responsive.css'), 'utf8');
const html = fs.readFileSync(path.join(root, 'selfit-tryon/index.html'), 'utf8');
const notes = Array.from({length:4}, (_, i) => ({id:String(i), items:[]}));

function render(overrides = {}) {
  const context = {
    state:{source:'report', photo:'/model.jpg', current:{reportNote:{title:'自在都市'}},
      reportOutfits:notes, homeOutfits:notes, outfits:notes, items:[], ...overrides},
    reference:false, params:new URLSearchParams(), A:'/assets/',
    image:() => '<img>', esc:String, uniqueItems:rows=>rows,
    card:row => '<article class="card">' + row.id + '</article>',
    empty:message => '<p class="empty">' + message + '</p>',
    livePieces:() => '<div class="outfit-composition"></div>', canvasTools:() => '',
  };
  vm.createContext(context);
  vm.runInContext(source.slice(source.indexOf('  function mirror()'), source.indexOf('  const trimmedPieces')), context);
  return context.mirror();
}

for (const source of ['report', 'inspiration', 'closet']) {
  for (const styling of [false, true]) test(source + ' / ' + (styling ? 'styling' : 'model') + ': notes and pagination stay in one reserved row', () => {
    const output = render({source, styling});
    const recommendation = output.slice(output.indexOf('<div class="mirror-recommendations">'));
    assert.match(output, /<\/div><div class="mirror-recommendations">/);
    assert.equal((recommendation.match(/class="card"/g) || []).length, 4);
    assert.match(recommendation, /class="mirror-pagination"/);
    assert.match(recommendation, /<\/div><\/div><\/section>$/);
    if (source === 'report') assert.match(recommendation, /来自你的型格推荐/);
  });
}

test('loading, failure and empty notes keep the same layout boundary', () => {
  for (const state of [{loading:true}, {error:'请稍后重试'}, {reportOutfits:[]}]) {
    const output = render(state);
    assert.match(output, /<div class="mirror-recommendations">[\s\S]*class="empty"/);
    assert.match(output, /<\/div><\/section>$/);
  }
  assert.doesNotMatch(render({reportOutfits:[notes[0]]}), /class="mirror-pagination"/);
});

test('mirror alone reserves navigation plus safe area and can scroll on short screens', () => {
  assert.match(css, /#studio\[data-screen="mirror"\] > #screen\s*\{[^}]*bottom: var\(--mirror-navigation-height\)/);
  assert.match(css, /--mirror-navigation-height: calc\(109px \+ var\(--mirror-safe-bottom\)\)/);
  assert.match(css, /env\(safe-area-inset-bottom, 0px\)/);
  assert.match(css, /flex: 1 0 260px/);
  assert.match(css, /max-height: none/);
  assert.match(css, /\.mirror-recommendations\s*\{[^}]*flex: none/);
  assert.match(css, /\.mirror-recommendations\s*\{[^}]*padding: 12px 0/);
  assert.match(css, /\.mirror-pagination\s*\{[^}]*margin-top: 12px/);
  assert.match(css, /height: calc\(100% - var\(--mirror-top-gap\)\)/);
});

test('live viewport adapter and responsive stylesheet load with the app', () => {
  assert.match(html, /selfit\/selfit-compat\.js\?v=/);
  assert.match(html, /selfit-tryon\/mirror-responsive\.css\?v=/);
  assert.ok(html.indexOf('mirror-responsive.css') > html.indexOf('studio.css'));
  assert.match(css, /height: var\(--visual-viewport-height, 100dvh\)/);
  assert.match(css, /height: min\(852px, calc\(var\(--visual-viewport-height, 100dvh\) - 48px\)\)/);
});
