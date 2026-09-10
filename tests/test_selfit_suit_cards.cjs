const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

class Element {
  constructor(tag) {
    this.tagName = tag;
    this.children = [];
    this.dataset = {};
    this.attributes = {};
    this.style = {};
    this.classList = { add() {} };
  }
  append(...children) { this.children.push(...children); }
  prepend(...children) { this.children.unshift(...children); }
  replaceChildren(...children) { this.children = children; }
  setAttribute(key, value) { this.attributes[key] = value; }
}
const context = { window: {}, document: { createElement: tag => new Element(tag) } };
const componentPath = process.env.SUIT_CARDS_JS || path.resolve(__dirname, '../app/static/selfit/selfit-suit-cards.js');
vm.runInNewContext(fs.readFileSync(componentPath, 'utf8'), context);
const render = options => {
  const container = new Element('section');
  context.window.SelfitSuitCards.render(container, options);
  return container.children;
};

for (const [key, title, value] of [['skin', '肤色', '冷白肤'], ['faceShape', '脸型', '鹅蛋脸'], ['bodyShape', '身材比例', '沙漏型']]) {
  test(`${title}: manual calibration is a small title-side label, not a button`, () => {
    let edited;
    const [card] = render({ features: [{ key, title, value, source: 'manual', description: '说明' }], onEdit: k => { edited = k; } });
    const [header, description] = card.children;
    const [valueRow, edit] = header.children;
    const [heading, badge] = valueRow.children;
    assert.equal(heading.textContent, value);
    assert.equal(badge.tagName, 'small');
    assert.equal(badge.className, 'suit-feature-calibration');
    assert.equal(badge.textContent, '手动校准');
    assert.equal(description.className, 'suit-feature-description');
    assert.equal(card.children.filter(n => n.tagName === 'small').length, 0);
    edit.onclick();
    assert.equal(edited, key);
  });
}
test('photo-derived results have no manual label', () => {
  const [card] = render({ features: [{ key: 'skin', value: '冷白肤', source: 'photo' }], analyses: { face: { attributes: { skin: { label: '冷白肤', subLabel: '明亮' } } } } });
  const row = card.children[0].children[0];
  assert.equal(row.children.length, 1);
  assert.equal(row.children[0].textContent, '冷白肤 · 明亮');
  assert.equal(card.children.length, 1);
});
test('missing photo and inconclusive analysis keep their explanatory text', () => {
  for (const [key, photos, expected] of [['skin', {}, '还没有上传面部照'], ['bodyShape', {}, '还没有上传全身照'], ['skin', { face: {} }, '暂时无法判断']]) {
    const [card] = render({ features: [{ key, source: 'unknown' }], photos });
    assert.equal(card.children[1].textContent, expected);
    assert.equal(card.children[0].children[0].children.length, 1);
  }
});
test('read-only profile cards also show manual calibration beside the value', () => {
  const [card] = render({ features: [{ key: 'bodyShape', value: '梨型', source: 'manual' }] });
  const header = card.children[0];
  assert.equal(header.children.length, 1);
  assert.equal(header.children[0].children[1].textContent, '手动校准');
});
