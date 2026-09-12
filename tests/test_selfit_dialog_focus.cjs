const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');
const root = path.resolve(__dirname, '../app/static/selfit-tryon');
const source = fs.readFileSync(path.join(root, 'studio.js'), 'utf8');
const css = fs.readFileSync(path.join(root, 'studio.css'), 'utf8');

test('shared dialogs focus their title and retain the accessible close action', () => {
  let shown = 0;
  const sheet = {
    dataset:{}, classList:{remove(){}}, open:false,
    showModal() {
      assert.match(this.innerHTML, /<h2 id="sheetTitle" tabindex="-1" autofocus>/);
      this.open = true;
      shown++;
    },
  };
  const context = vm.createContext({$:()=>sheet, esc:String});
  vm.runInContext(source.slice(source.indexOf('  function modal('), source.indexOf('  async function loadModels(')), context);
  for (const title of ['波点温柔', '绑定你的智能穿衣镜', '选择模特']) {
    sheet.open = false;
    context.modal(title, '<p>弹窗内容</p>');
    assert.match(sheet.innerHTML, /class="close" data-action="close" aria-label="关闭">×<\/button>/);
    assert.equal((sheet.innerHTML.match(/autofocus/g)||[]).length, 1);
  }
  assert.equal(shown, 3);
  context.modal('刷新弹窗', '<p>更新内容</p>');
  assert.equal(shown, 3, 'do not call showModal twice on an open dialog');
});

test('close controls lose the square outline, not their hit area or keyboard indicator', () => {
  const closeRule = css.match(/dialog \.close\s*\{([^}]+)\}/)[1];
  assert.match(closeRule, /width: 44px/);
  assert.match(closeRule, /height: 44px/);
  assert.match(closeRule, /border-radius: 50%/);
  assert.match(css, /dialog \.close:focus\s*\{\s*outline: none/);
  assert.match(css, /dialog \.close:focus-visible\s*\{[^}]*background: #f3e8ea;[^}]*color: var\(--brand\)/);
});
