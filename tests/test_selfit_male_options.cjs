const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');
const root = path.resolve(__dirname, '..');
const context = {window:{}};
vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(root,'app/static/selfit/selfit-manual-options.js'),'utf8'),context);
const catalog = context.window.SelfitManualOptions;
const plain = value => JSON.parse(JSON.stringify(value));
const fields = ['skin','faceShape','bodyShape'];

test('male skin colors and option labels match the supplied palette exactly',()=>{
  const supplied=JSON.parse(fs.readFileSync(path.join(root,'app/static/selfit/assets/manual-selection/male/colors.json'),'utf8'));
  assert.deepEqual(plain(catalog.getOptions('male','skin').map(o=>[o.label,o.color])),supplied.colors.map(c=>[c.name,c.hex]));
});
test('male face and body order and labels match the supplied image set',()=>{
  assert.deepEqual(plain(catalog.getOptions('male','faceShape').map(o=>o.label)),['方形脸','菱形脸','倒三角脸','椭圆脸','圆形脸']);
  assert.deepEqual(plain(catalog.getOptions('male','bodyShape').map(o=>o.value)),['梯形','三角形','倒三角形','矩形','椭圆形']);
  for(const field of ['faceShape','bodyShape']) for(const option of catalog.getOptions('male',field)) {
    assert.match(option.src,/manual-selection\/male\//);
    assert.ok(fs.existsSync(path.join(root,'app',option.src)));
  }
});
test('male body images use text-free assets and retain separate option labels',()=>{
  const nodes={}, form={dataset:{},querySelector:s=>nodes[s] ||= {innerHTML:''}};
  catalog.renderOnboarding(form,'male');
  const html=nodes['.manual-visual-options--body'].innerHTML;
  for(const option of catalog.getOptions('male','bodyShape')) {
    assert.match(option.src,/-no-label\.webp$/);
    assert.ok(html.includes(`class="manual-option-label">${option.label}</span>`));
    assert.ok(html.includes(`alt="${option.label}示意"`));
  }
  assert.ok(catalog.getOptions('male','faceShape').every(o=>!o.src.includes('-no-label')));
});
test('female and unspecified profiles keep the original catalog without male assets',()=>{
  for(const field of fields) {
    assert.deepEqual(plain(catalog.getOptions(null,field)),plain(catalog.getOptions('female',field)));
    assert.ok(catalog.getOptions('female',field).every(o=>!o.src?.includes('/male/')));
  }
  assert.deepEqual(plain(catalog.getOptions('female','bodyShape').map(o=>o.value)),['梨型','倒三角型','沙漏型','矩型','苹果型']);
});
test('onboarding switches all groups and restores female options on reselection',()=>{
  const nodes={}, form={dataset:{},querySelector:s=>nodes[s] ||= {innerHTML:''}};
  catalog.renderOnboarding(form,'male');
  assert.equal(form.dataset.gender,'male');
  assert.match(nodes['.skin-options'].innerHTML,/#F2D0C7/);
  assert.match(nodes['.manual-visual-options--face'].innerHTML,/倒三角脸/);
  assert.match(nodes['.manual-visual-options--body'].innerHTML,/梯形/);
  catalog.renderOnboarding(form,'female');
  assert.equal(form.dataset.gender,'female');
  assert.match(nodes['.skin-options'].innerHTML,/#FFDED7/);
  assert.doesNotMatch(nodes['.manual-visual-options--body'].innerHTML,/male\/|梯形/);
});
test('legacy photo labels can highlight a matching male body option without changing its saved value',()=>{
  const option=catalog.findOption('male','bodyShape','矩型');
  assert.equal(option.value,'矩形');
  assert.equal(catalog.matches(option,'矩型'),true);
  assert.equal(catalog.findOption('male','bodyShape','沙漏型'),undefined);
});
const studio=fs.readFileSync(path.join(root,'app/static/selfit-tryon/studio.js'),'utf8');
for(const gender of ['male','female']) for(const field of fields) test(`profile editor uses ${gender} ${field} catalog and requires an explicit click`,()=>{
  const ctx={window:context.window,state:{profile:{gender},profileEditingField:field,profileFeatureValue:'矩型',profileFeatureTouched:false},
    profileLabels:{skin:'肤色',faceShape:'脸型',bodyShape:'身型'},esc:s=>String(s),image:(src,alt)=>`<img src="${src}" alt="${alt}">`};
  vm.createContext(ctx);
  vm.runInContext(studio.slice(studio.indexOf('  function profileFeatureEdit()'),studio.indexOf('  function profileEdit()')),ctx);
  const html=ctx.profileFeatureEdit();
  assert.match(html,new RegExp('data-gender="'+gender+'"'));
  for(const o of catalog.getOptions(gender,field)) {
    assert.ok(html.includes('data-profile-choice="'+o.value+'"'));
    assert.ok(html.includes(o.src || o.color));
  }
  assert.match(html,/data-action="confirm-profile-feature" disabled/);
});
test('both entry points load the shared catalog before their interaction script',()=>{
  for(const [htmlFile,script] of [['selfit/index.html','/static/selfit/selfit.js?'],['selfit-tryon/index.html','/static/selfit-tryon/studio.js?']]) {
    const html=fs.readFileSync(path.join(root,'app/static',htmlFile),'utf8');
    assert.ok(html.indexOf('selfit-manual-options.js?')>=0);
    assert.ok(html.indexOf('selfit-manual-options.js?')<html.indexOf(script));
  }
  const source=fs.readFileSync(path.join(root,'app/static/selfit/selfit.js'),'utf8');
  assert.match(source,/renderOnboarding\(document.querySelector\('\.manual-form'\), state.gender\)/);
});
