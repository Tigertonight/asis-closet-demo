const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {test} = require('node:test');
const source = fs.readFileSync('app/static/selfit-tryon/studio.js', 'utf8');
const css = fs.readFileSync('app/static/selfit-tryon/studio.css', 'utf8');
const html = fs.readFileSync('app/static/selfit-tryon/index.html', 'utf8');

function render(overrides = {}) {
  const state = {closetCategory:'all', items:[{id:'tee'}], outfits:[{id:'outfit'}], savedNotes:[], ...overrides};
  const context = vm.createContext({state, uniqueItems:rows=>rows, esc:String,
    card:()=>'<article class="outfit"></article>',
    wardrobeItemSections:()=>'<div class="wardrobe-groups"></div>',
    wardrobeEmpty:()=>'<div class="wardrobe-empty"></div>', pendingImport:()=>null});
  vm.runInContext(source.slice(source.indexOf('  function closet()'), source.indexOf('  function libraryTopics()')), context);
  return context.closet();
}

test('both wardrobe tabs retain their content without the old header plus', () => {
  for (const closetCategory of ['all', 'set', 'saved']) {
    const result = render({closetCategory});
    assert.match(result, /我的单品/);
    assert.match(result, /我的搭配/);
    assert.doesNotMatch(result, /wardrobe-add|data-action="upload-garment"/);
    assert.match(result, closetCategory === 'all' ? /wardrobe-groups/ : /closet-grid/);
  }
  assert.match(render({items:[]}), /wardrobe-empty/);
  assert.match(render({wardrobeError:'请重新加载'}), /请重新加载/);
});

test('upload dock is a single labelled button outside the scrolling content', () => {
  assert.equal((html.match(/id="addGarmentFloating"/g) || []).length, 1);
  assert.match(html, /<div id="screen"[^>]*><\/div>[\s\S]*<button id="addGarmentFloating"/);
  assert.match(html, /id="addGarmentFloating"[^>]*data-action="upload-garment"[^>]*hidden/);
  assert.match(html, /<span>添加更多你的衣服<\/span>/);
  assert.match(source, /case "upload-garment":\s*\$\("#garmentInput"\)\.click\(\);\s*break;/);
});

test('dock only appears on a loaded wardrobe, including errors and empty states', () => {
  const rule = source.split('\n').find(line => line.includes('$("#addGarmentFloating").hidden ='));
  assert.ok(rule);
  for (const page of ['closet', 'mirror', 'inspiration', 'profile', 'import-review', 'builder', 'tryon-history']) {
    for (const loading of [false, true]) for (const wardrobeLoading of [false, true]) {
      const button = {hidden:true};
      const context = vm.createContext({state:{page, loading, wardrobeLoading}, $:()=>button});
      vm.runInContext(rule, context);
      assert.equal(Boolean(button.hidden), page !== 'closet' || loading || wardrobeLoading);
    }
  }
});

test('upload area reserves space above navigation and keeps text opaque', () => {
  assert.match(css, /--closet-upload-height: 72px/);
  assert.match(css, /--closet-navigation-height: calc\(109px \+ var\(--closet-safe-bottom\)\)/);
  assert.match(css, /env\(safe-area-inset-bottom, 0px\)/);
  assert.match(css, /#studio\[data-screen="closet"\] > #screen\s*\{[^}]*bottom: calc\(var\(--closet-upload-bottom\) \+ var\(--closet-upload-height\) \+ 12px\)/);
  const dock = css.match(/\.studio > \.add-garment\s*\{([^}]+)\}/)[1];
  assert.match(dock, /position: absolute/);
  assert.match(dock, /bottom: var\(--closet-upload-bottom\)/);
  assert.match(dock, /border: 1px dashed/);
  assert.match(dock, /background: rgb\(255 255 255 \/ 56%\)/);
  assert.doesNotMatch(dock, /(?:^|;)\s*opacity:/);
  assert.match(css, /\.studio > \.add-garment\[hidden\] \{ display: none; \}/);
  assert.match(css, /#studio\[data-screen="closet"\] > \.completion-notice\s*\{[^}]*bottom: calc\(var\(--closet-upload-bottom\) \+ var\(--closet-upload-height\) \+ 12px\)/);
  assert.match(source, /\$\('\[data-wardrobe-hold\]'\) \|\| \$\('#addGarmentFloating'\)/);
});
